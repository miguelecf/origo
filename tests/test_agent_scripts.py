"""Los scripts para que el agente actualice sin tocar el código: sintaxis y negativas tempranas."""
import os
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


@pytest.mark.parametrize("name", ["update.sh", "check-agent.sh"])
def test_scripts_are_valid_posix_sh(name):
    subprocess.run(["sh", "-n", str(DEPLOY / name)], check=True)


@pytest.mark.skipif(os.geteuid() == 0, reason="la prueba es sin root")
def test_update_refuses_without_root():
    result = subprocess.run(["sh", str(DEPLOY / "update.sh")], capture_output=True, text=True)
    assert result.returncode == 1 and "sudo" in result.stderr


def test_update_never_rewrites_history_or_local_changes():
    script = (DEPLOY / "update.sh").read_text()
    assert "--ff-only" in script and "merge-base --is-ancestor" in script
    assert "git status --porcelain" in script and "origo-backup.service" in script
    assert "push" not in script and "--force" not in script
