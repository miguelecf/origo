#!/bin/sh
# Backup consistente aun con la app en uso. No copiar la DB abierta con cp.
set -eu
umask 077
DATA_DIR=${MENTOR_DATA_DIR:-/var/lib/mentor}
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}
case "$RETENTION_DAYS" in ''|*[!0-9]*) echo 'Retención inválida' >&2; exit 1;; esac
[ "$RETENTION_DAYS" -ge 1 ] || exit 1
[ -f "$DATA_DIR/mentor.db" ] || { echo 'No existe la base de datos' >&2; exit 1; }
mkdir -p "$DATA_DIR/backups"
chmod 700 "$DATA_DIR/backups"
TEMP=$(mktemp "$DATA_DIR/backups/.backup-XXXXXX")
trap 'rm -f "$TEMP"' EXIT HUP INT TERM
# La ruta fija del despliegue no contiene comillas; rechazar rutas ambiguas.
case "$TEMP" in *"'"*) echo 'La ruta no puede contener comillas simples' >&2; exit 1;; esac
sqlite3 "$DATA_DIR/mentor.db" ".timeout 10000" ".backup '$TEMP'"
[ "$(sqlite3 "$TEMP" 'PRAGMA quick_check;')" = 'ok' ] || { echo 'Backup inválido' >&2; exit 1; }
chmod 600 "$TEMP" "$DATA_DIR/mentor.db"
mv "$TEMP" "$DATA_DIR/backups/mentor-$(date -u +%Y%m%dT%H%M%SZ).db"
find "$DATA_DIR/backups" -type f -name 'mentor-*.db' -mtime +"$RETENTION_DAYS" -delete
printf '%s\n' 'Backup de Mentor completado'
