"""Contrato portable y backup Docker: solo fixtures temporales, sin Docker daemon."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import time

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docker_backup", ROOT / "deploy/docker-backup.py")
docker_backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docker_backup)


def test_compose_is_private_and_persistent():
    config = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert set(config["services"]) == {"origo"}
    service = config["services"]["origo"]
    assert service["env_file"] == ["${ORIGO_ENV_FILE:-.env}"]
    assert service["ports"] == ["127.0.0.1:8000:8000"]
    assert service["volumes"] == ["origo-data:/data"]
    assert "origo-data" in config["volumes"]
    assert service["environment"]["DATABASE_URL"] == "sqlite:////data/origo.db"
    assert service["environment"]["ORIGO_DEV_OPEN"] == "0"
    assert service["environment"]["MCP_LOCAL_ONLY"] == "0"
    assert service["read_only"] is True
    assert service["restart"] == "unless-stopped"
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert any(mount.startswith("/tmp:") for mount in service["tmpfs"])
    assert "--no-proxy-headers" in service["command"]
    assert "--forwarded-allow-ips" not in service["command"]
    # Hereda UID no privilegiado y healthcheck de la imagen, sin override inseguro.
    image = (ROOT / "Dockerfile").read_text()
    assert "USER origo" in image and "--uid 10001" in image
    assert "HEALTHCHECK" in image
    assert "user" not in service and "healthcheck" not in service


def test_backup_live_wal_restores_committed_data(tmp_path):
    source = tmp_path / "origo.db"
    with sqlite3.connect(source) as live:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("CREATE TABLE records (value TEXT)")
        live.execute("INSERT INTO records VALUES ('committed')")
        live.commit()
        live.execute("INSERT INTO records VALUES ('not committed')")
        output = docker_backup.backup(tmp_path)
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
        assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
        with sqlite3.connect(output) as restored:
            assert restored.execute("SELECT value FROM records").fetchall() == [("committed",)]
            assert restored.execute("PRAGMA quick_check").fetchone() == ("ok",)
        live.rollback()
    assert not list(output.parent.glob(".backup-*"))


def test_backup_retention_and_missing_database(tmp_path):
    with pytest.raises(ValueError, match="No existe"):
        docker_backup.backup(tmp_path)
    assert not (tmp_path / "origo.db").exists()
    with sqlite3.connect(tmp_path / "origo.db") as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
    old = docker_backup.backup(tmp_path)
    timestamp = time.time() - 32 * 86400
    os.utime(old, (timestamp, timestamp))
    unrelated = old.parent / "keep.txt"
    unrelated.write_text("keep")
    os.utime(unrelated, (timestamp, timestamp))
    new = docker_backup.backup(tmp_path)
    assert new.exists() and not old.exists() and unrelated.exists()
    with pytest.raises(ValueError, match="retención"):
        docker_backup.backup(tmp_path, 0)


def test_backup_cli_runs_from_stdin(tmp_path):
    with sqlite3.connect(tmp_path / "origo.db") as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
    script = (ROOT / "deploy/docker-backup.py").read_text()
    result = subprocess.run([sys.executable, "-", "--data-dir", str(tmp_path)],
                            input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "Backup verificado:" in result.stdout
    assert len(list((tmp_path / "backups").glob("origo-*.db"))) == 1
