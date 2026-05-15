"""
proxy_server.py — Motor de proxies locais HTTP/HTTPS e SOCKS5
Responsável por: handlers, autenticação, relay bidirecional, graceful shutdown
"""

import asyncio
import base64
import select
import socket
import struct
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils import setup_logger

logger = setup_logger("proxy_server")

# ---------------------------------------------------------------------------
# Repositório central de instâncias ativas
# Chave: str(port) → dict de estado da instância
# ---------------------------------------------------------------------------
local_proxies: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Helpers de estado
# ---------------------------------------------------------------------------

def proxy_log(port: int | str, msg: str) -> None:
    """
    Registra uma mensagem no buffer de logs de uma instância e incrementa
    o contador de requisições. Thread-safe para leitura/escrita simples.
    """
    port_key = str(port)
    state = local_proxies.get(port_key)
    if not state:
        return
    state["req_count"] += 1
    state["logs"].append(msg)
    # Mantém o buffer em no máximo 200 linhas (rolling window)
    if len(state["logs"]) > 200:
        state["logs"] = state["logs"][-150:]
    logger.debug("[port=%s] %s", port_key, msg)


def _new_state(port: int, ptype: str, auth_b64: str | None,
               auth_socks: bool, user: str, passwd: str) -> dict:
    """Cria o dicionário de estado inicial para uma nova instância de proxy."""
    return {
        "running": True,
        "type": ptype,
        "port": port,
        "auth": auth_b64,
        "auth_socks": auth_socks,
        "user": user,
        "pass": passwd,
        "server": None,
        "loop": None,
        "thread": None,
        "logs": [],
        "req_count": 0,
    }


# ---------------------------------------------------------------------------
# HTTP / HTTPS Proxy Handler
# ---------------------------------------------------------------------------

class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    Handler para proxy HTTP com suporte a CONNECT tunnel (HTTPS) e
    autenticação Basic via cabeçalho Proxy-Authorization.
    """

    # Silencia os logs padrão do BaseHTTPServer — usamos proxy_log()
    def log_message(self, format, *args):  # noqa: A002
        pass

    def log_request(self, code="-", size="-"):
        if isinstance(code, HTTPStatus):
            code = code.value
        port = self.server.server_address[1]
        proxy_log(port, f"{self.command} {self.path} → {code}")

    @property
    def _state(self) -> dict:
        port_key = str(self.server.server_address[1])
        return local_proxies.get(port_key, {})

    # ── Autenticação ──────────────────────────────────────────────────────
    def check_auth(self) -> bool:
        required = self._state.get("auth")
        if not required:
            return True
        provided = self.headers.get("Proxy-Authorization", "")
        if provided == required:
            return True
        logger.warning("[HTTP] Autenticação falhou para %s", self.address_string())
        try:
            self.send_response(407)
            self.send_header("Proxy-Authenticate", 'Basic realm="ProxyHunter"')
            self.end_headers()
        except OSError:
            pass
        return False

    # ── Relay TCP bidirecional ────────────────────────────────────────────
    def relay(self, client_sock: socket.socket, target_sock: socket.socket) -> None:
        """
        Faz relay bidirecional entre dois sockets usando select().
        Encerra graciosamente quando qualquer lado fecha a conexão.
        """
        conns = [client_sock, target_sock]
        try:
            while True:
                readable, _, exceptional = select.select(conns, [], conns, 30)
                if exceptional or not readable:
                    break
                for sock in readable:
                    other = target_sock if sock is client_sock else client_sock
                    try:
                        data = sock.recv(8192)
                    except OSError as exc:
                        logger.debug("relay recv error: %s", exc)
                        return
                    if not data:
                        return
                    try:
                        other.sendall(data)
                    except OSError as exc:
                        logger.debug("relay send error: %s", exc)
                        return
        except OSError as exc:
            logger.debug("relay select error: %s", exc)
        finally:
            for s in (client_sock, target_sock):
                try:
                    s.close()
                except OSError:
                    pass

    # ── CONNECT (HTTPS tunnel) ────────────────────────────────────────────
    def do_CONNECT(self):
        if not self.check_auth():
            return
        parts = self.path.rsplit(":", 1)
        if len(parts) != 2:
            self.send_error(400, "Bad CONNECT target")
            return
        host, raw_port = parts
        try:
            port = int(raw_port)
        except ValueError:
            port = 443
        try:
            remote = socket.create_connection((host, port), timeout=10)
        except (OSError, socket.timeout) as exc:
            logger.warning("[HTTP/CONNECT] %s:%s falhou: %s", host, port, exc)
            self.send_error(502)
            return
        self.send_response(200, "Connection Established")
        self.end_headers()
        self.log_request(200)
        self.relay(self.connection, remote)

    # ── Métodos HTTP comuns ───────────────────────────────────────────────
    do_GET = do_POST = do_HEAD = do_OPTIONS = do_PUT = do_DELETE = \
        lambda self: self._proxy_request()

    def _proxy_request(self):
        if not self.check_auth():
            return
        url = self.path
        if url.startswith("/"):
            host_header = self.headers.get("Host")
            if host_header:
                url = f"http://{host_header}{url}"
            else:
                self.send_error(400, "Missing Host header")
                return
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname
            port = parsed.port or 80
            remote = socket.create_connection((host, port), timeout=10)
        except (OSError, socket.timeout) as exc:
            logger.warning("[HTTP] Conexão com destino falhou: %s", exc)
            try:
                self.send_error(502)
            except OSError:
                pass
            return

        try:
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            remote.sendall(f"{self.command} {path} HTTP/1.1\r\n".encode("iso-8859-1"))
            for header, value in self.headers.items():
                if header.lower() == "proxy-connection":
                    continue
                remote.sendall(f"{header}: {value}\r\n".encode("iso-8859-1"))
            remote.sendall(b"\r\n")
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length)
                remote.sendall(body)
        except OSError as exc:
            logger.warning("[HTTP] Erro ao encaminhar requisição: %s", exc)
            try:
                self.send_error(502)
            except OSError:
                pass
            remote.close()
            return

        self.log_request(200)
        self.relay(self.connection, remote)


# ---------------------------------------------------------------------------
# SOCKS5 Proxy (asyncio)
# ---------------------------------------------------------------------------

def _make_socks5_handler(port_key: str):
    """
    Factory que cria uma coroutine assíncrona de handler SOCKS5,
    fechada sobre o port_key para acessar o estado correto.
    """

    async def _safe_close(writer: asyncio.StreamWriter) -> None:
        """Fecha um StreamWriter com proteção a erros de rede."""
        try:
            writer.close()
            await writer.wait_closed()
        except (OSError, asyncio.CancelledError):
            pass

    async def _relay_half(
        src: asyncio.StreamReader, dst: asyncio.StreamWriter, label: str
    ) -> None:
        """Faz relay de um único sentido de um par de streams."""
        try:
            while True:
                data = await src.read(8192)
                if not data:
                    break
                dst.write(data)
                await dst.drain()
        except (OSError, asyncio.CancelledError) as exc:
            logger.debug("[SOCKS5/relay/%s] encerrado: %s", label, exc)

    async def handle_socks5(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        state = local_proxies.get(port_key)
        if not state:
            await _safe_close(writer)
            return

        local_addr = writer.get_extra_info("peername", ("?", "?"))
        logger.debug("[SOCKS5] nova conexão de %s:%s", *local_addr)

        try:
            # ── 1. Handshake de método ────────────────────────────────────
            header = await asyncio.wait_for(reader.readexactly(2), timeout=5)
            version, nmethods = header
            if version != 5:
                logger.warning("[SOCKS5] versão inválida: %d", version)
                await _safe_close(writer)
                return

            methods = set(await asyncio.wait_for(reader.readexactly(nmethods), timeout=5))

            req_auth = state.get("auth_socks")
            if req_auth:
                if 2 not in methods:
                    writer.write(b"\x05\xFF")
                    await writer.drain()
                    await _safe_close(writer)
                    return
                writer.write(b"\x05\x02")
                await writer.drain()

                # Sub-negociação username/password (RFC 1929)
                await asyncio.wait_for(reader.readexactly(1), timeout=5)  # versão sub
                ulen = (await asyncio.wait_for(reader.readexactly(1), timeout=5))[0]
                uname = (await asyncio.wait_for(reader.readexactly(ulen), timeout=5)).decode(errors="replace")
                plen = (await asyncio.wait_for(reader.readexactly(1), timeout=5))[0]
                passwd = (await asyncio.wait_for(reader.readexactly(plen), timeout=5)).decode(errors="replace")

                if uname == state.get("user") and passwd == state.get("pass"):
                    writer.write(b"\x01\x00")
                    await writer.drain()
                else:
                    logger.warning("[SOCKS5] autenticação falhou para %s:%s", *local_addr)
                    writer.write(b"\x01\x01")
                    await writer.drain()
                    await _safe_close(writer)
                    return
            else:
                if 0 not in methods:
                    writer.write(b"\x05\xFF")
                    await writer.drain()
                    await _safe_close(writer)
                    return
                writer.write(b"\x05\x00")
                await writer.drain()

            # ── 2. Requisição de conexão ──────────────────────────────────
            req_header = await asyncio.wait_for(reader.readexactly(4), timeout=5)
            _ver, cmd, _rsv, atyp = req_header

            if cmd != 1:  # Somente CONNECT suportado
                logger.warning("[SOCKS5] Comando não suportado: %d", cmd)
                await _safe_close(writer)
                return

            if atyp == 0x01:  # IPv4
                raw = await asyncio.wait_for(reader.readexactly(4), timeout=5)
                address = socket.inet_ntoa(raw)
            elif atyp == 0x03:  # Domain
                dlen = (await asyncio.wait_for(reader.readexactly(1), timeout=5))[0]
                address = (await asyncio.wait_for(reader.readexactly(dlen), timeout=5)).decode(errors="replace")
            elif atyp == 0x04:  # IPv6
                raw = await asyncio.wait_for(reader.readexactly(16), timeout=5)
                address = socket.inet_ntop(socket.AF_INET6, raw)
            else:
                logger.warning("[SOCKS5] Tipo de endereço inválido: %d", atyp)
                await _safe_close(writer)
                return

            port_bytes = await asyncio.wait_for(reader.readexactly(2), timeout=5)
            dest_port = struct.unpack("!H", port_bytes)[0]

            proxy_log(port_key, f"SOCKS5 CONNECT {address}:{dest_port}")

            # ── 3. Conexão com destino ────────────────────────────────────
            try:
                rem_reader, rem_writer = await asyncio.wait_for(
                    asyncio.open_connection(address, dest_port), timeout=10
                )
            except (OSError, asyncio.TimeoutError) as exc:
                logger.warning("[SOCKS5] Falha ao conectar %s:%s — %s", address, dest_port, exc)
                writer.write(b"\x05\x05\x00\x01" + b"\x00" * 6)
                await writer.drain()
                await _safe_close(writer)
                return

            bind_addr = rem_writer.get_extra_info("sockname", ("0.0.0.0", 0))
            bind_ip = socket.inet_aton(bind_addr[0])
            bind_port = struct.pack("!H", bind_addr[1])
            writer.write(b"\x05\x00\x00\x01" + bind_ip + bind_port)
            await writer.drain()

            # ── 4. Relay bidirecional ─────────────────────────────────────
            t1 = asyncio.create_task(_relay_half(reader, rem_writer, "client→remote"))
            t2 = asyncio.create_task(_relay_half(rem_reader, writer, "remote→client"))

            _done, pending = await asyncio.wait(
                [t1, t2], return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            await _safe_close(rem_writer)

        except asyncio.TimeoutError:
            logger.warning("[SOCKS5] Timeout durante handshake de %s:%s", *local_addr)
        except (OSError, asyncio.IncompleteReadError) as exc:
            logger.debug("[SOCKS5] Conexão encerrada inesperadamente: %s", exc)
        except Exception as exc:  # salvaguarda final para não derrubar o servidor
            logger.error("[SOCKS5] Erro inesperado: %s", exc)
        finally:
            await _safe_close(writer)

    return handle_socks5


def _run_socks5_server(host: str, port: int, port_key: str) -> None:
    """Target de thread para executar o event loop do servidor SOCKS5."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    local_proxies[port_key]["loop"] = loop
    proxy_log(port_key, f"SOCKS5 Proxy escutando em {host}:{port}")
    try:
        server_coro = asyncio.start_server(_make_socks5_handler(port_key), host, port)
        server = loop.run_until_complete(server_coro)
        loop.run_forever()
        server.close()
        loop.run_until_complete(server.wait_closed())
    except OSError as exc:
        logger.error("[SOCKS5/port=%s] Não foi possível iniciar: %s", port_key, exc)
        proxy_log(port_key, f"ERRO ao iniciar: {exc}")
    except Exception as exc:
        logger.error("[SOCKS5/port=%s] Encerrado com erro: %s", port_key, exc)
    finally:
        try:
            loop.close()
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# API de gerenciamento de instâncias
# ---------------------------------------------------------------------------

def start_proxy(port: int, ptype: str, user: str = "", passwd: str = "",
                use_auth: bool = False) -> str:
    """
    Inicia uma nova instância de proxy na porta especificada.
    Retorna o IP local onde foi iniciada ou lança ValueError/OSError.
    """
    from utils import get_local_ip, is_valid_port

    port_key = str(port)

    if not is_valid_port(port):
        raise ValueError(f"Porta inválida: {port}")

    if port_key in local_proxies and local_proxies[port_key].get("running"):
        raise ValueError(f"Já existe uma proxy ativa na porta {port}.")

    auth_b64: str | None = None
    auth_socks = False

    if use_auth and user and passwd:
        if ptype == "http":
            raw = f"{user}:{passwd}"
            auth_b64 = "Basic " + base64.b64encode(raw.encode()).decode()
        else:
            auth_socks = True

    state = _new_state(port, ptype, auth_b64, auth_socks, user, passwd)
    local_proxies[port_key] = state
    sys_ip = get_local_ip()

    try:
        if ptype == "http":
            server = ThreadingHTTPServer(("0.0.0.0", port), ProxyHTTPRequestHandler)
            state["server"] = server
            thread = threading.Thread(target=server.serve_forever, daemon=True, name=f"http-proxy-{port}")
            state["thread"] = thread
            thread.start()
            proxy_log(port_key, f"HTTP/HTTPS Proxy escutando em {sys_ip}:{port}")
            logger.info("[HTTP] Proxy iniciada na porta %d", port)

        elif ptype in ("socks5", "socks"):
            thread = threading.Thread(
                target=_run_socks5_server,
                args=("0.0.0.0", port, port_key),
                daemon=True,
                name=f"socks5-proxy-{port}",
            )
            state["thread"] = thread
            thread.start()
            logger.info("[SOCKS5] Proxy iniciada na porta %d", port)
        else:
            raise ValueError(f"Tipo de proxy desconhecido: {ptype!r}")

    except (OSError, ValueError) as exc:
        state["running"] = False
        logger.error("[proxy/start] Falha na porta %d: %s", port, exc)
        raise

    return sys_ip


def stop_proxy(port: int) -> None:
    """Para e limpa uma instância de proxy existente."""
    port_key = str(port)
    state = local_proxies.get(port_key)
    if not state or not state.get("running"):
        return

    ptype = state.get("type")
    try:
        if ptype == "http" and state.get("server"):
            # shutdown() bloqueia; executamos em thread separada para não travar Flask
            shutdown_thread = threading.Thread(target=state["server"].shutdown, daemon=True)
            shutdown_thread.start()
            shutdown_thread.join(timeout=3)
            try:
                state["server"].server_close()
            except OSError:
                pass
        elif ptype in ("socks5", "socks"):
            loop: asyncio.AbstractEventLoop | None = state.get("loop")
            if loop and loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
    except Exception as exc:
        logger.error("[proxy/stop] Erro ao parar porta %d: %s", port, exc)
    finally:
        state["running"] = False
        state["server"] = None
        state["loop"] = None
        logger.info("[proxy/stop] Instância na porta %d encerrada.", port)


def list_active_proxies(sys_ip: str) -> list[dict]:
    """Retorna lista de instâncias ativas formatadas para a API."""
    active = []
    for port_key, state in list(local_proxies.items()):
        if state.get("running"):
            active.append({
                "port": state["port"],
                "type": state["type"],
                "req_count": state["req_count"],
                "ip": sys_ip,
                "auth_enabled": bool(state["auth"] or state["auth_socks"]),
                "user": state["user"],
                "pass": state["pass"],
            })
    return active
