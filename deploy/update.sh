#!/bin/sh
# Actualiza Origo a lo último de origin/main. Sin argumentos a propósito: se instala como
# /usr/local/sbin/origo-update para que un agente lo corra con sudo y pueda actualizar sin poder
# escribir código. Ver docs/agentes.md, "Aislar al agente del código".
#
# Hace: backup, avance fast-forward (nunca reescribe historia ni aplica cambios locales),
# uv sync, reinicio y chequeo. Si algo falla después del pull, vuelve a la versión anterior.
set -eu
umask 022
REPO=/opt/origo
BRANCH=main
HEALTH=http://127.0.0.1:8000/login
export UV_PYTHON_INSTALL_DIR=/opt/origo-python

[ "$(id -u)" -eq 0 ] || { echo 'Correlo con sudo' >&2; exit 1; }
[ "$#" -eq 0 ] || { echo 'origo-update no recibe argumentos' >&2; exit 1; }
command -v uv >/dev/null || { echo 'uv no está en el PATH de root (instalalo en /usr/local/bin)' >&2; exit 1; }

exec 9>/run/origo-update.lock
flock -n 9 || { echo 'Ya hay una actualización en curso' >&2; exit 1; }

cd "$REPO"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo 'El código instalado tiene cambios locales: no actualizo. Que lo revise una persona.' >&2
  exit 1
fi

OLD=$(git rev-parse HEAD)
git fetch --quiet origin "$BRANCH"
NEW=$(git rev-parse "origin/$BRANCH")
if [ "$OLD" = "$NEW" ]; then
  echo "Origo ya está al día ($(git describe --tags --always))"
  exit 0
fi
if ! git merge-base --is-ancestor "$OLD" "$NEW"; then
  echo "origin/$BRANCH no sigue a la versión instalada (historia reescrita): no actualizo." >&2
  exit 1
fi

systemctl start origo-backup.service

rollback() {
  echo 'Falló la actualización: vuelvo a la versión anterior.' >&2
  git reset --quiet --hard "$OLD"
  uv sync --frozen --no-dev --quiet || true
  systemctl restart origo || true
  exit 1
}

git merge --ff-only --quiet "$NEW"
uv sync --frozen --no-dev --quiet || rollback
systemctl restart origo || rollback
tries=0
until curl -fsS -o /dev/null "$HEALTH"; do
  tries=$((tries + 1))
  [ "$tries" -lt 30 ] || rollback
  sleep 1
done

if ! git diff --quiet "$OLD" "$NEW" -- deploy/; then
  echo 'Aviso: cambió deploy/. Puede que haya que copiar los .service o reinstalar origo-update (lo hace una persona).'
fi
echo "Origo actualizado: $(git rev-parse --short "$OLD") -> $(git describe --tags --always)"
