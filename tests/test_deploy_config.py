"""Contrato del despliegue privado; no necesita un daemon de Tailscale ni systemd."""
import stat
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
import pytest

from app.core.config import Settings
from deploy.configure import https_origin, write_env

ROOT = Path(__file__).resolve().parents[1]


def test_private_env_is_valid_and_does_not_overwrite(tmp_path):
    output = tmp_path / "origo.env"
    write_env(output, "https://server.tail123.ts.net/", 'Miguel "Migue" Caraballo')
    original = output.read_bytes()
    config = Settings(_env_file=None, **dotenv_values(output))
    assert config.BASE_URL == "https://server.tail123.ts.net"
    assert config.OWNER_NAME == 'Miguel "Migue" Caraballo'
    assert config.DATABASE_URL == "sqlite:////var/lib/origo/origo.db"
    assert config.MCP_LOCAL_ONLY and not config.ORIGO_DEV_OPEN
    assert config.remote_mcp_enabled and not config.oauth_enabled
    assert len(config.SECRET_KEY) >= 64 and len(config.MCP_TOKEN) >= 64
    assert config.SECRET_KEY != config.MCP_TOKEN
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_env(output, config.BASE_URL, "Otro")
    assert output.read_bytes() == original


def test_existing_symlink_is_not_followed(tmp_path):
    target = tmp_path / "existing"
    target.write_text("keep")
    output = tmp_path / "origo.env"
    output.symlink_to(target)
    with pytest.raises(FileExistsError):
        write_env(output, "https://server.tail123.ts.net", "Miguel")
    assert target.read_text() == "keep"


@pytest.mark.parametrize("value", [
    "http://server.tail123.ts.net", "https://bad_host.example.com",
    "https://", "https://server.tail123.ts.net/path",
    "https://user:pass@server.tail123.ts.net", "https://server.tail123.ts.net?x=1",
    "https://server.tail123.ts.net#frag", "https://server.tail123.ts.net\n",
    "https://server.tail123.ts.net:99999", "https://server.tail123.ts.net:0",
])
def test_reject_invalid_origin(value, tmp_path):
    output = tmp_path / "origo.env"
    with pytest.raises(ValueError):
        write_env(output, value, "Miguel")
    assert not output.exists()


def test_custom_https_port():
    assert https_origin("https://server.tail123.ts.net:8443/") == "https://server.tail123.ts.net:8443"


@pytest.mark.parametrize("base_url", ["https://origo.example.com", "https://[::1]:8443", "https://100.64.0.1"])
def test_portable_docker_remote_config(tmp_path, base_url):
    output = tmp_path / "origo.env"
    write_env(output, base_url, "Owner", mode="docker", mcp_scope="remote")
    config = Settings(_env_file=None, **dotenv_values(output))
    assert config.BASE_URL == base_url
    assert config.DATABASE_URL == "sqlite:////data/origo.db"
    assert not config.MCP_LOCAL_ONLY and config.MCP_TOKEN


def test_docker_rejects_host_hermes_with_local_only(tmp_path):
    with pytest.raises(ValueError, match="--mcp-scope remote"):
        write_env(tmp_path / "origo.env", "https://origo.example.com", "Owner", mode="docker")


@pytest.mark.parametrize("name", ["Miguel\nORIGO_DEV_OPEN=1", "Owner ${PRIVATE_VALUE}", "Owner $PRIVATE_VALUE"])
def test_reject_env_injection(tmp_path, name):
    output = tmp_path / "origo.env"
    with pytest.raises(ValueError):
        write_env(output, "https://server.tail123.ts.net", name)
    assert not output.exists()


def test_cli_does_not_print_secrets(tmp_path):
    output = tmp_path / "origo.env"
    command = [sys.executable, str(ROOT / "deploy/configure.py"),
               "--base-url", "https://server.tail123.ts.net", "--output", str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0
    config = dotenv_values(output)
    for key in ("SECRET_KEY", "MCP_TOKEN"):
        assert config[key] not in result.stdout + result.stderr
    assert subprocess.run(command, capture_output=True).returncode == 1


def test_systemd_keeps_backend_private():
    service = (ROOT / "deploy/origo.service").read_text()
    assert "--host 127.0.0.1 --port 8000" in service
    assert "--forwarded-allow-ips 127.0.0.1" in service
    assert "User=origo" in service
    assert "EnvironmentFile=/etc/origo/origo.env" in service


def test_private_files_are_excluded_from_docker_context():
    rules = (ROOT / ".dockerignore").read_text().splitlines()
    for pattern in (".env", ".env.*", "*.env", "*.db", "*.db-*", "*.sqlite", "*.sqlite3",
                    "hermes/config.yaml", "hermes/config.yml", "secrets", "backups", "*.key", "*.pem"):
        assert pattern in rules
