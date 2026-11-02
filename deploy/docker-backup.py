#!/usr/bin/env python3
"""Backup consistente dentro del contenedor, usando solamente Python estándar.

Desde el checkout del host:
    docker compose exec -T origo python - < deploy/docker-backup.py

Guarda snapshots en /data/backups (el mismo volumen, NO una copia fuera del host).
BACKUP_RETENTION_DAYS permite cambiar los 30 días de retención por defecto.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import time


def backup(data_dir: Path, retention_days: int = 30) -> Path:
    if retention_days < 1:
        raise ValueError("La retención debe ser de al menos un día")
    source = data_dir / "origo.db"
    if not source.is_file():
        raise ValueError("No existe la base de datos de Origo")
    destination = data_dir / "backups"
    destination.mkdir(mode=0o700, exist_ok=True)
    destination.chmod(0o700)
    fd, name = tempfile.mkstemp(prefix=".backup-", dir=destination)
    os.close(fd)
    temporary = Path(name)
    try:
        # mode=ro evita crear silenciosamente una DB vacía si falta el origen.
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(temporary)) as dst:
                src.backup(dst)
                # El origen puede usar WAL: el snapshot debe ser un único archivo
                # cerrado, no depender de sidecars con el nombre temporal.
                dst.execute("PRAGMA journal_mode=DELETE")
                if dst.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise ValueError("El backup no pasó la verificación de integridad")
        # Marca temporal operativa en UTC, no una fecha de negocio de la app.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = destination / f"origo-{stamp}.db"
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    cutoff = time.time() - retention_days * 86400
    for old in destination.glob("origo-*.db"):
        if old != output and not old.is_symlink() and old.is_file() and old.stat().st_mtime < cutoff:
            old.unlink()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--retention-days", type=int, default=os.environ.get("BACKUP_RETENTION_DAYS", "30"))
    args = parser.parse_args()
    try:
        output = backup(args.data_dir, args.retention_days)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"No se completó el backup: {exc}\n")
    print(f"Backup verificado: {output}")


if __name__ == "__main__":
    main()
