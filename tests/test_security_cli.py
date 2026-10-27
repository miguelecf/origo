import sys

import pyotp
import pytest

from app import cli
from app.services import security


def test_cli_user_password_and_totp(db, monkeypatch, capsys):
    from contextlib import nullcontext
    monkeypatch.setattr(cli, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(cli, "init_db", lambda: None)

    def run(*args, answers=()):
        responses = iter(answers)
        monkeypatch.setattr(sys, "argv", ["mentor", *args])
        monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(responses))
        cli.main()

    run("create-user", "miguel", answers=["long enough password", "long enough password"])
    user = security.find_user(db, "miguel")
    assert user and security.hasher.verify(user.password_hash, "long enough password")
    run("list-users")
    assert "miguel" in capsys.readouterr().out
    run("set-password", "miguel", answers=["a different long password", "a different long password"])
    assert security.hasher.verify(user.password_hash, "a different long password")
    secret = pyotp.random_base32()
    monkeypatch.setattr(cli.pyotp, "random_base32", lambda: secret)
    run("enable-totp", "miguel", answers=[pyotp.TOTP(secret).now()])
    assert user.totp_secret == secret
    assert "otpauth://totp/" in capsys.readouterr().out
    run("disable-totp", "miguel")
    assert user.totp_secret is None


@pytest.mark.parametrize("password", ["short", "x" * 1025])
def test_cli_password_policy(password, monkeypatch):
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: password)
    with pytest.raises(ValueError, match="12 y 1024"):
        cli.password_prompt()


def test_optional_log_file_has_private_permissions(tmp_path, monkeypatch):
    import logging
    from app.core import logging as mentor_logging
    from app.core.config import settings

    target = tmp_path / "mentor.log"
    monkeypatch.setattr(settings, "LOG_FILE", str(target))
    mentor_logging.configure_logging()
    mentor_logging.event("test_event", value="ok")
    for handler in mentor_logging.logger.handlers:
        handler.flush()
    assert target.stat().st_mode & 0o777 == 0o600
    assert '"event":"test_event"' in target.read_text()
    for handler in list(mentor_logging.logger.handlers):
        handler.close()
        mentor_logging.logger.removeHandler(handler)
    monkeypatch.setattr(settings, "LOG_FILE", "")
    mentor_logging.configure_logging()


def test_backup_consistency_and_permissions(tmp_path):
    import os
    import shutil
    import sqlite3
    import subprocess
    from pathlib import Path

    if not shutil.which("sqlite3"):
        pytest.skip("Requiere SQLite CLI")
    database = tmp_path / "mentor.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('dato')")
    script = Path(__file__).resolve().parents[1] / "deploy/backup.sh"
    subprocess.run(["sh", str(script)], env={**os.environ, "MENTOR_DATA_DIR": str(tmp_path)}, check=True, capture_output=True)
    backup, = (tmp_path / "backups").glob("mentor-*.db")
    assert backup.stat().st_mode & 0o777 == 0o600
    assert database.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("dato",)
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
