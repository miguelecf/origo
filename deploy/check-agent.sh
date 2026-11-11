#!/bin/sh
# Revisa que el usuario del sistema con el que corre el agente no pueda tocar Origo por fuera del
# MCP: ni el código, ni la configuración, ni la base de datos. Solo lee, no cambia nada.
#   sudo sh /opt/origo/deploy/check-agent.sh hermes
set -u
AGENT=${1:-}
[ -n "$AGENT" ] || { echo 'Uso: sudo sh deploy/check-agent.sh <usuario-del-agente>' >&2; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo 'Correlo con sudo' >&2; exit 2; }
id "$AGENT" >/dev/null 2>&1 || { echo "No existe el usuario $AGENT" >&2; exit 2; }

fails=0
ok() { printf 'OK     %s\n' "$1"; }
bad() { printf 'FALLA  %s\n' "$1"; fails=$((fails + 1)); }
as_agent() { sudo -n -u "$AGENT" "$@" 2>/dev/null; }

for group in sudo wheel admin docker lxd; do
  if id -nG "$AGENT" | tr ' ' '\n' | grep -qx "$group"; then
    bad "$AGENT está en el grupo $group (equivale a root)"
  fi
done

rules=$(sudo -l -U "$AGENT" 2>/dev/null | sed -n '/may run the following/,$p' | tail -n +2)
others=$(printf '%s\n' "$rules" | grep -v '^[[:space:]]*$' | grep -v '/usr/local/sbin/origo-update' || true)
if [ -n "$others" ]; then
  bad "sudo permite más que origo-update:"
  printf '%s\n' "$others" | sed 's/^/         /'
else
  ok "sudo: como mucho, origo-update"
fi

for path in /opt/origo /opt/origo/app /opt/origo/.git /opt/origo/.venv /opt/origo/deploy \
            /etc/origo /var/lib/origo /etc/systemd/system /usr/local/sbin/origo-update; do
  [ -e "$path" ] || continue
  if as_agent test -w "$path"; then bad "puede escribir $path"; else ok "no escribe $path"; fi
done

for path in /etc/origo/origo.env /var/lib/origo/origo.db /var/lib/origo/backups; do
  [ -e "$path" ] || continue
  if as_agent test -r "$path"; then bad "puede leer $path"; else ok "no lee $path"; fi
done

if [ -e /usr/local/sbin/origo-update ]; then
  owner=$(stat -c '%U' /usr/local/sbin/origo-update 2>/dev/null || stat -f '%Su' /usr/local/sbin/origo-update)
  [ "$owner" = root ] && ok "origo-update es de root" || bad "origo-update es de $owner, tiene que ser de root"
fi

if [ "$fails" -eq 0 ]; then
  echo "Listo: $AGENT no puede tocar Origo por fuera del MCP."
else
  echo "$fails problema(s). Ver docs/agentes.md, \"Aislar al agente del código\"." >&2
  exit 1
fi
