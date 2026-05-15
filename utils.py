"""
utils.py — Utilitários compartilhados do ProxyHunter
Responsável por: logging, validações, IPs, headers aleatórios
"""

import logging
import random
import socket
import time

# ---------------------------------------------------------------------------
# Logger Centralizado
# ---------------------------------------------------------------------------
def setup_logger(name: str) -> logging.Logger:
    """Cria e retorna um logger estruturado com timestamp e nível."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)
    return logger


logger = setup_logger("utils")

# ---------------------------------------------------------------------------
# User Agents
# ---------------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 Safari/604.1",
]


def random_headers() -> dict:
    """Retorna headers HTTP com User-Agent aleatório."""
    return {"User-Agent": random.choice(USER_AGENTS)}


# ---------------------------------------------------------------------------
# Rede
# ---------------------------------------------------------------------------
def get_local_ip() -> str:
    """Descobre o IP LAN da máquina via socket UDP (sem enviar pacotes)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError as exc:
        logger.warning("Não foi possível detectar IP local: %s — usando 127.0.0.1", exc)
        return "127.0.0.1"


def current_time_utc() -> str:
    """Retorna o horário UTC atual no formato HH:MM:SS."""
    return time.strftime("%H:%M:%S", time.gmtime())


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------
def is_valid_port(port: int) -> bool:
    """Verifica se o valor de porta está dentro do intervalo válido."""
    return isinstance(port, int) and 1 <= port <= 65535
