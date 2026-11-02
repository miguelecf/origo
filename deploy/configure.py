#!/usr/bin/env python3
"""Crea una configuración HTTPS de Origo, sin mostrar ni pisar secretos.

Solo usa la biblioteca estándar: se puede ejecutar antes de instalar Origo.
No instala servicios ni cambia la configuración de Tailscale.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit


def https_origin(value: str) -> str:
    url = urlsplit(value)
    host = url.hostname or ""
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    try:
        ipaddress.ip_address(host)
        valid_host = True
    except ValueError:
        valid_host = len(host) <= 253 and re.fullmatch(rf"{label}(?:\.{label})*", host)
    if (
        url.scheme != "https"
        or not valid_host
        or url.username is not None or url.password is not None
        or url.path not in {"", "/"} or url.query or url.fragment
        or any(char.isspace() or ord(char) < 32 for char in value)
        or "?" in value or "#" in value
    ):
        raise ValueError("Usá un origen HTTPS sin ruta, credenciales ni parámetros")
    port = url.port  # También rechaza puertos inválidos.
    if port is not None and port < 1:
        raise ValueError("El puerto debe estar entre 1 y 65535")
    authority = f"[{host}]" if ":" in host else host
    return f"https://{authority}" + (f":{port}" if port and port != 443 else "")


def write_env(output: Path, base_url: str, owner_name: str, *, mode: str = "systemd", mcp_scope: str = "local") -> None:
    base_url = https_origin(base_url)
    if mode not in {"systemd", "docker"} or mcp_scope not in {"local", "remote"}:
        raise ValueError("Modo o alcance MCP inválido")
    if mode == "docker" and mcp_scope == "local":
        raise ValueError("Hermes fuera del contenedor requiere --mcp-scope remote; usá HTTPS o loopback del host y bearer")
    database_dir = "/var/lib/origo" if mode == "systemd" else "/data"
    if not owner_name.strip() or "$" in owner_name or any(ord(char) < 32 or ord(char) == 127 for char in owner_name):
        # Compose interpola $VAR aun dentro de comillas dobles en env_file.
        raise ValueError("El nombre del dueño debe ser texto en una sola línea, sin '$'")
    content = (
        "# Configuración privada de Origo. No subir a Git.\n"
        f"DATABASE_URL=sqlite:///{database_dir}/origo.db\n"
        "TIMEZONE=America/Argentina/Buenos_Aires\n"
        f"OWNER_NAME={json.dumps(owner_name, ensure_ascii=False)}\n"
        f"BASE_URL={base_url}\n"
        f"SECRET_KEY={secrets.token_urlsafe(48)}\n"
        "ORIGO_DEV_OPEN=0\n"
        "SESSION_IDLE_SECONDS=1800\n"
        "SESSION_ABSOLUTE_SECONDS=86400\n"
        "GITHUB_CLIENT_ID=\nGITHUB_CLIENT_SECRET=\nGITHUB_ALLOWED_LOGIN=\n"
        f"MCP_TOKEN={secrets.token_urlsafe(48)}\n"
        f"MCP_LOCAL_ONLY={int(mcp_scope == 'local')}\n"
        "LOG_LEVEL=INFO\nLOG_FILE=\n"
    )
    # O_EXCL también rechaza symlinks: nunca sobreescribir una configuración activa.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Origen HTTPS del proxy (dominio propio o Tailscale)")
    parser.add_argument("--owner-name", default="Origo")
    parser.add_argument("--mode", choices=("systemd", "docker"), default="systemd")
    parser.add_argument("--mcp-scope", choices=("local", "remote"), default="local")
    parser.add_argument("--output", type=Path, default=Path("/etc/origo/origo.env"))
    args = parser.parse_args()
    try:
        write_env(args.output, args.base_url, args.owner_name, mode=args.mode, mcp_scope=args.mcp_scope)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"No se creó la configuración: {exc}\n")
    print("Configuración creada con permisos privados. No se mostraron secretos.")


if __name__ == "__main__":
    main()
