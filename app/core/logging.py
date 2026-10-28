"""Registro estructurado: solo campos explícitos, nunca requests ni excepciones crudas."""
import json
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from urllib.parse import unquote, urlsplit

from app.core.config import settings

logger = logging.getLogger("origo")


def redact_path(path: str) -> str:
    path = unquote(urlsplit(path).path)
    path = re.sub(r"(?i)/g/.*", "/g/***", path)
    # No registrar ningún valor de query, incluso con nombres inesperados.
    return path[:500]


def event(name: str, **fields) -> None:
    logger.info(json.dumps({"event": name, **fields}, ensure_ascii=True, separators=(",", ":")))


class DropSensitiveLogs(logging.Filter):
    def filter(self, record):
        # Uvicorn incluye rutas sin redacción; errores de librerías pueden incluir tokens.
        return False


def configure_logging() -> None:
    # Permisos restrictivos también para el archivo opcional y sus rotaciones.
    os.umask(0o077)
    logger.setLevel(settings.LOG_LEVEL.upper())
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    if settings.LOG_FILE:
        handler = RotatingFileHandler(settings.LOG_FILE, maxBytes=5_000_000, backupCount=5)
        os.chmod(settings.LOG_FILE, 0o600)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    # Estas librerías registran URLs/credenciales incluso en DEBUG. No habilitarlas en producción.
    for name in ("uvicorn.access", "uvicorn.error", "httpx", "httpx2", "httpcore"):
        logging.getLogger(name).addFilter(DropSensitiveLogs())
    for name in ("fastmcp", "mcp"):
        lib = logging.getLogger(name)
        lib.handlers = [logging.NullHandler()]
        lib.propagate = False
        lib.setLevel(logging.CRITICAL + 1)
