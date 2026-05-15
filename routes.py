"""
routes.py — Rotas Flask do ProxyHunter (Blueprint)
Responsável por: todos os endpoints REST e SSE, centraliza respostas JSON
"""

import json
import time

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from proxy_server import list_active_proxies, local_proxies, proxy_log, start_proxy, stop_proxy
from scrapers import collect_all_proxies
from utils import get_local_ip, random_headers, setup_logger

logger = setup_logger("routes")

bp = Blueprint("main", __name__)

# ---------------------------------------------------------------------------
# Configurações de Teste de Proxy
# ---------------------------------------------------------------------------
TEST_URL     = "http://httpbin.org/ip"
TEST_TIMEOUT = 8   # segundos
MAX_WORKERS  = 40  # threads de teste simultâneas


# ---------------------------------------------------------------------------
# Teste individual de proxy
# ---------------------------------------------------------------------------
def test_proxy(proxy: dict) -> dict:
    """
    Testa uma proxy enviando uma requisição GET para o TEST_URL.
    Retorna dicionário com status, latência e IP externo reportado.
    """
    host = proxy["host"]
    ptype = proxy["type"]
    
    scheme = ptype.lower() if ptype in ("SOCKS4", "SOCKS5") else "http"
    proxy_dict = {"http": f"{scheme}://{host}", "https": f"{scheme}://{host}"}
    
    start = time.monotonic()
    try:
        resp = requests.get(
            TEST_URL,
            proxies=proxy_dict,
            timeout=TEST_TIMEOUT,
            headers=random_headers(),
        )
        elapsed_ms = round((time.monotonic() - start) * 1000)
        if resp.status_code == 200:
            ip_info = resp.json().get("origin", "?")
            return {
                "host": host,
                "type": ptype,
                "status": "alive",
                "latency": elapsed_ms,
                "ip": ip_info,
                "tested": time.strftime("%H:%M:%S", time.gmtime()),
            }
    except requests.exceptions.Timeout:
        logger.debug("[test] Timeout: %s", host)
    except requests.exceptions.ProxyError:
        logger.debug("[test] ProxyError: %s", host)
    except requests.exceptions.ConnectionError:
        logger.debug("[test] ConnectionError: %s", host)
    except Exception as exc:
        logger.debug("[test] Erro inesperado para %s: %s", host, exc)

    return {
        "host": host,
        "type": ptype,
        "status": "dead",
        "latency": None,
        "ip": None,
        "tested": time.strftime("%H:%M:%S", time.gmtime()),
    }


# ---------------------------------------------------------------------------
# Página Principal
# ---------------------------------------------------------------------------
@bp.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Scanner de Proxies (SSE Stream)
# ---------------------------------------------------------------------------
@bp.route("/api/test-stream")
def api_test_stream():
    """SSE endpoint: faz scraping + teste de proxies e envia eventos em tempo real."""

    def generate():
        proxies = collect_all_proxies()
        total = len(proxies)
        yield f"data: {json.dumps({'event': 'start', 'total': total})}\n\n"
        logger.info("[scan] Iniciando teste de %d proxies com %d workers", total, MAX_WORKERS)

        alive_count = dead_count = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {executor.submit(test_proxy, p): p for p in proxies}
            for future in as_completed(future_map):
                try:
                    result = future.result()
                except Exception as exc:
                    logger.error("[scan] Erro ao processar resultado: %s", exc)
                    continue

                if result["status"] == "alive":
                    alive_count += 1
                else:
                    dead_count += 1

                payload = {
                    "event": "result",
                    "result": result,
                    "alive": alive_count,
                    "dead": dead_count,
                    "processed": alive_count + dead_count,
                    "total": total,
                }
                yield f"data: {json.dumps(payload)}\n\n"

        logger.info("[scan] Concluído. Vivas: %d | Mortas: %d", alive_count, dead_count)
        yield f"data: {json.dumps({'event': 'done', 'alive': alive_count, 'dead': dead_count, 'total': total})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# API de Proxies Locais
# ---------------------------------------------------------------------------

@bp.route("/api/proxy/start", methods=["POST"])
def proxy_start():
    """Inicia uma nova instância de proxy local."""
    data: dict = request.get_json(silent=True) or {}

    try:
        port = int(data.get("port", 8080))
    except (TypeError, ValueError):
        return jsonify({"error": "Porta inválida."}), 400

    ptype   = str(data.get("type", "http")).lower()
    use_auth = bool(data.get("auth", False))
    user    = str(data.get("user", ""))
    passwd  = str(data.get("pass", ""))

    try:
        sys_ip = start_proxy(port, ptype, user=user, passwd=passwd, use_auth=use_auth)
        return jsonify({"status": "success", "ip": sys_ip})
    except ValueError as exc:
        logger.warning("[API/start] %s", exc)
        return jsonify({"error": str(exc)}), 400
    except OSError as exc:
        logger.error("[API/start] OSError ao iniciar porta %d: %s", port, exc)
        return jsonify({"error": f"Não foi possível abrir a porta {port}: {exc}"}), 500


@bp.route("/api/proxy/stop", methods=["POST"])
def proxy_stop():
    """Para uma instância de proxy local pelo número de porta."""
    data: dict = request.get_json(silent=True) or {}
    try:
        port = int(data.get("port", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Porta inválida."}), 400

    stop_proxy(port)
    return jsonify({"status": "success"})


@bp.route("/api/proxy/status", methods=["GET"])
def proxy_status():
    """Retorna lista de todos os proxies locais ativos."""
    sys_ip = get_local_ip()
    return jsonify(list_active_proxies(sys_ip))


@bp.route("/api/proxy/logs", methods=["GET"])
def proxy_logs_sse():
    """SSE endpoint: envia logs em tempo real de uma instância de proxy pelo port."""
    try:
        port_key = str(int(request.args.get("port", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "Porta inválida"}), 400

    def generate():
        last_idx = 0
        logger.debug("[logs-sse] Início do stream para porta %s", port_key)
        while True:
            state = local_proxies.get(port_key)
            if not state or not state.get("running"):
                yield f"data: {json.dumps({'event': 'stopped'})}\n\n"
                break
            logs = state["logs"]
            if len(logs) > last_idx:
                for msg in logs[last_idx:]:
                    yield f"data: {json.dumps({'log': msg})}\n\n"
                last_idx = len(logs)
            time.sleep(0.3)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
