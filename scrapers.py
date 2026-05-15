"""
scrapers.py — Coleta de proxies de fontes públicas
Responsável por: scraping multi-thread, deduplicação, log de falhas por fonte
"""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils import random_headers, setup_logger

logger = setup_logger("scrapers")

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
FETCH_TIMEOUT = 12  # segundos por requisição de scraping

# ---------------------------------------------------------------------------
# Funções Individuais de Scraping
# ---------------------------------------------------------------------------

def _parse_lines(text: str, proto: str) -> list[dict]:
    """Parseia linhas brutas no formato 'host:porta' e retorna lista de dicts."""
    results = []
    for line in text.strip().splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            results.append({"host": line, "type": proto.upper()})
    return results


def fetch_proxyscrape_http() -> list[dict]:
    proxies = []
    for proto in ("http", "https"):
        url = (
            f"https://api.proxyscrape.com/v4/free-proxy-list/get"
            f"?request=display_proxies&protocol={proto}&timeout=5000"
            f"&country=all&ssl=all&anonymity=all&simplified=true"
        )
        try:
            r = requests.get(url, timeout=FETCH_TIMEOUT, headers=random_headers())
            r.raise_for_status()
            proxies.extend(_parse_lines(r.text, proto))
        except requests.RequestException as exc:
            logger.warning("[proxyscrape/%s] Falha ao coletar: %s", proto, exc)
    return proxies


def fetch_proxyscrape_socks() -> list[dict]:
    proxies = []
    for proto in ("socks4", "socks5"):
        url = (
            f"https://api.proxyscrape.com/v4/free-proxy-list/get"
            f"?request=display_proxies&protocol={proto}&timeout=5000"
            f"&country=all&simplified=true"
        )
        try:
            r = requests.get(url, timeout=FETCH_TIMEOUT, headers=random_headers())
            r.raise_for_status()
            proxies.extend(_parse_lines(r.text, proto))
        except requests.RequestException as exc:
            logger.warning("[proxyscrape/%s] Falha ao coletar: %s", proto, exc)
    return proxies


def fetch_proxylist_download() -> list[dict]:
    proxies = []
    for proto in ("https", "http"):
        url = f"https://www.proxy-list.download/api/v1/get?type={proto}"
        try:
            r = requests.get(url, timeout=FETCH_TIMEOUT, headers=random_headers())
            r.raise_for_status()
            proxies.extend(_parse_lines(r.text, proto))
        except requests.RequestException as exc:
            logger.warning("[proxy-list.download/%s] Falha ao coletar: %s", proto, exc)
    return proxies


def fetch_github_clarketm() -> list[dict]:
    url = "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt"
    try:
        r = requests.get(url, timeout=FETCH_TIMEOUT, headers=random_headers())
        r.raise_for_status()
        return _parse_lines(r.text, "http")
    except requests.RequestException as exc:
        logger.warning("[github/clarketm] Falha ao coletar: %s", exc)
        return []


def fetch_github_monosans() -> list[dict]:
    proxies = []
    for proto, path in [("HTTP", "http"), ("SOCKS4", "socks4"), ("SOCKS5", "socks5")]:
        url = f"https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/{path}.txt"
        try:
            r = requests.get(url, timeout=FETCH_TIMEOUT, headers=random_headers())
            r.raise_for_status()
            proxies.extend(_parse_lines(r.text, proto))
        except requests.RequestException as exc:
            logger.warning("[github/monosans/%s] Falha ao coletar: %s", path, exc)
    return proxies


def fetch_github_thesproxy() -> list[dict]:
    proxies = []
    for proto, path in [("HTTP", "http"), ("SOCKS4", "socks4"), ("SOCKS5", "socks5")]:
        url = f"https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/proxy/{path}.txt"
        try:
            r = requests.get(url, timeout=FETCH_TIMEOUT, headers=random_headers())
            r.raise_for_status()
            proxies.extend(_parse_lines(r.text, proto))
        except requests.RequestException as exc:
            logger.warning("[github/TheSpeedX/%s] Falha ao coletar: %s", path, exc)
    return proxies


# ---------------------------------------------------------------------------
# Orquestrador Principal
# ---------------------------------------------------------------------------
ALL_FETCHERS = [
    fetch_proxyscrape_http,
    fetch_proxyscrape_socks,
    fetch_proxylist_download,
    fetch_github_clarketm,
    fetch_github_monosans,
    fetch_github_thesproxy,
]


def collect_all_proxies() -> list[dict]:
    """
    Executa todos os scrapers em paralelo e retorna proxies únicas (sem duplicatas).
    Registra número de proxies coletadas por fonte.
    """
    all_proxies: list[dict] = []

    with ThreadPoolExecutor(max_workers=len(ALL_FETCHERS)) as executor:
        future_to_name = {
            executor.submit(fn): fn.__name__ for fn in ALL_FETCHERS
        }
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                result = future.result()
                logger.info("[%s] → %d proxies coletadas", name, len(result))
                all_proxies.extend(result)
            except Exception as exc:  # pragma: no cover — apenas salvaguarda
                logger.error("[%s] Erro inesperado: %s", name, exc)

    # Deduplicação por host
    seen: set[str] = set()
    unique: list[dict] = []
    for proxy in all_proxies:
        if proxy["host"] not in seen:
            seen.add(proxy["host"])
            unique.append(proxy)

    logger.info("Total coletado: %d | Únicas: %d", len(all_proxies), len(unique))
    return unique
