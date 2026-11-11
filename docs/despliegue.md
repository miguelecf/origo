# Desplegar Origo

Origo es una sola app de Python con SQLite: corre en cualquier Linux con systemd. Esta guía
sirve igual para una laptop vieja en tu casa o para un VPS. La única diferencia es dónde vive
la máquina: los pasos son los mismos.

Origo es de **un solo dueño por instancia** (los invitados solo ven Súper y Deudas): cada
persona que la quiera corre la suya. No hay multiusuario ni versión alojada.

Origo siempre escucha en `127.0.0.1:8000` y delante va algo que da HTTPS. Elegí una ruta:

| Ruta | Cuándo | Guía |
|---|---|---|
| **Proxy HTTPS propio** (Caddy, nginx) | VPS o casa con IP/dominio propio. Sin cuentas de terceros | sección 4 |
| **Cloudflare Tunnel** | Casa, sin abrir puertos. Requiere cuenta y dominio en Cloudflare | sección 5 |
| **Tailscale Serve** | Solo tus dispositivos, sin dominio | [tailscale.md](tailscale.md) |

```
celular ──https──▶ proxy / túnel / Serve ──▶ 127.0.0.1:8000 (Origo) ──▶ SQLite
```

Todo lo demás (Hermes, Telegram, Cloudflare, Tailscale, modelos en la nube) es opcional.
El camino sin servicios propietarios obligatorios es systemd + proxy HTTPS propio + un modelo
local en Hermes. Hermes puede estar en otra máquina o no existir: la web funciona igual
([agentes.md](agentes.md)).

## 1. Preparar la máquina

Ubuntu Server LTS (o Debian) sin escritorio. En el instalador activá **OpenSSH server** y, si
querés, importá tu llave pública desde GitHub.

Desde tu computadora:

```bash
ssh-copy-id usuario@IP-DEL-SERVIDOR      # una vez
ssh usuario@IP-DEL-SERVIDOR
```

En el servidor:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git sqlite3 curl ufw

# Firewall: solo SSH entrante. Origo y el túnel no necesitan puertos abiertos.
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow OpenSSH && sudo ufw enable

# ANTES de quitar contraseñas, abrí OTRA terminal y verificá acceso con llave:
# ssh -o PreferredAuthentications=publickey -o PasswordAuthentication=no usuario@IP-DEL-SERVIDOR
# Solo si esa sesión nueva funciona, seguí. Conservá ambas sesiones abiertas.
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n' | sudo tee /etc/ssh/sshd_config.d/10-solo-llave.conf
sudo sshd -t && sudo systemctl restart ssh
```

### Si es una laptop en casa

```bash
# Que no se suspenda al cerrar la tapa ni por inactividad
sudo mkdir -p /etc/systemd/logind.conf.d
printf '[Login]\nHandleLidSwitch=ignore\nHandleLidSwitchExternalPower=ignore\nHandleLidSwitchDocked=ignore\n' | sudo tee /etc/systemd/logind.conf.d/tapa.conf
sudo systemctl restart systemd-logind
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Reservá su IP en el router (DHCP reservation) y, si el BIOS lo permite, activá "encender al
volver la luz". Por cable es más estable que por Wi-Fi.

## 2. Instalar uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
```

## 3. Instalar Origo con systemd

La máquina corre un solo proceso en **127.0.0.1:8000**. No abras ese puerto en el router ni
lo publiques con `0.0.0.0`. El proxy o el túnel termina TLS; `BASE_URL` debe ser el origen
público HTTPS aunque el tramo local sea HTTP. `SECRET_KEY` es obligatoria, aleatoria y de al menos
32 bytes: la app se niega a arrancar con un secreto vacío, corto o reconociblemente débil.

### Servicio y usuario

Necesitás Python 3.13+, `uv`, SQLite CLI y systemd. Instalá Python en una ruta legible para
`origo`: ni bajo `/root` ni bajo `/home` (el servicio usa `ProtectHome=true`). Si usás el
Python administrado por uv, instalalo con `UV_PYTHON_INSTALL_DIR=/opt/origo-python` y usá
esa misma variable al crear el entorno. Cloná el repo en `/opt/origo` (`sudo git clone https://github.com/miguelecf/origo.git /opt/origo`), con código y
entorno propiedad de root, sin permisos de escritura para el servicio:

```bash
sudo useradd --system --home-dir /var/lib/origo --shell /usr/sbin/nologin origo
sudo install -d -m 700 -o origo -g origo /var/lib/origo
sudo install -d -m 750 -o root -g origo /etc/origo
cd /opt/origo
sudo env UV_PYTHON_INSTALL_DIR=/opt/origo-python uv sync --frozen --no-dev
```

**Configuración.** Lo más simple es generar el archivo; crea uno nuevo con permisos 0600,
`SECRET_KEY` y `MCP_TOKEN` aleatorios que no se imprimen, falla si ya existe y no instala nada:

```bash
sudo python3 deploy/configure.py --base-url https://origo.example.com \
  --owner-name TuNombre --mode systemd --mcp-scope local --output /etc/origo/origo.env
sudo chown origo:origo /etc/origo/origo.env
```

`--mcp-scope local` deja `MCP_LOCAL_ONLY=1` (Hermes en esta misma máquina); usá `remote`
si Hermes está en otra. El archivo trae `TIMEZONE=America/Argentina/Buenos_Aires`: editalo si
vivís en otra zona. A mano también sirve: copiá `.env.example` a `/etc/origo/origo.env`
(`install -m 600 -o origo -g origo`) y completá `BASE_URL`, `DATABASE_URL=sqlite:////var/lib/origo/origo.db`,
`SECRET_KEY` y MCP, cada secreto con `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`.
Los secretos son tuyos: no uses valores de ejemplo, no los pongas en argumentos de comandos
ni los subas a Git.

La CLI lee `.env` del directorio actual; para que use exactamente el archivo de producción:

```bash
sudo -u origo ln -s /etc/origo/origo.env /var/lib/origo/.env
sudo -u origo sh -c 'cd /var/lib/origo && PYTHONPATH=/opt/origo /opt/origo/.venv/bin/python -m app.cli create-user "$1"' sh tu-usuario
sudo -u origo sh -c 'cd /var/lib/origo && PYTHONPATH=/opt/origo /opt/origo/.venv/bin/python -m app.cli enable-totp "$1"' sh tu-usuario
sudo chmod 600 /etc/origo/origo.env /var/lib/origo/origo.db
sudo cp /opt/origo/deploy/origo*.service /opt/origo/deploy/origo-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now origo.service origo-backup.timer
sudo journalctl -u origo -f
```

El servicio no usa root ni `--reload`; limita escritura a `/var/lib/origo`, aplica
`ProtectSystem=strict`, `NoNewPrivileges`, capacidades vacías y permisos privados.
Uvicorn confía en proxy headers **solo de 127.0.0.1**. Origo usa `CF-Connecting-IP` o
`X-Forwarded-For` únicamente si el peer aún es 127.0.0.1; si Uvicorn ya reescribió la IP,
usa la dirección validada por Uvicorn. No cambies `--forwarded-allow-ips` a `*`.
Los procesos locales, el proxy y cloudflared pertenecen al perímetro confiable.
El `cd` de los comandos administrativos se hace **dentro** de `sudo -u origo`: el usuario
SSH no puede entrar en `/var/lib/origo` (0700). No abras sus permisos para sortearlo.

## 4. Publicarlo con tu proxy HTTPS (ejemplo: Caddy)

Necesitás un dominio que apunte a la IP de la máquina y los puertos 80 y 443 alcanzables
(en un VPS, abrilos en su firewall; en casa, redirigilos en el router). Los comandos de
firewall y SSH de esta guía los corrés vos, a mano y revisándolos: nada acá los cambia solo.
Caddy pide y renueva el certificado Let's Encrypt por su cuenta. `Caddyfile` mínimo:

```
origo.example.com {
	# Con Hermes local, /mcp y OAuth no salen a internet. Borrá este bloque solo si querés MCP remoto.
	@mcp path /mcp /mcp/* /.well-known/* /authorize /token /register /revoke /consent /auth/callback
	respond @mcp 404

	reverse_proxy 127.0.0.1:8000
}
```

Con nginx u otro proxy, los requisitos son los mismos: `proxy_pass` a `127.0.0.1:8000`, conservar
el `Host` y **mandar `X-Forwarded-For`**. Sin ese header, Origo vería cada visita como local:
compartiría el límite de intentos de login y `MCP_LOCAL_ONLY` no distinguiría la llamada.
Caddy lo manda solo. No cambies `--forwarded-allow-ips` a `*` ni expongas el 8000.

Este ejemplo no se probó en el repo; verificá con la sección 7.

## 5. Alternativa: Cloudflare Tunnel (opcional)

Servicio propietario de un tercero: cómodo para casa porque no abre puertos, pero no es necesario.

Instalá `cloudflared` desde el paquete oficial para tu distribución. El dominio debe estar
en tu cuenta de Cloudflare:

```bash
cloudflared tunnel login
cloudflared tunnel create origo
cloudflared tunnel route dns origo origo.example.com
sudo install -d -m 700 /etc/cloudflared
sudo install -m 600 ~/.cloudflared/UUID.json /etc/cloudflared/UUID.json
sudo install -m 600 /opt/origo/deploy/cloudflared-config.example.yml /etc/cloudflared/config.yml
sudo editor /etc/cloudflared/config.yml
sudo cloudflared --config /etc/cloudflared/config.yml tunnel ingress validate
sudo cloudflared --config /etc/cloudflared/config.yml service install
sudo systemctl enable --now cloudflared
```

Reemplazá `UUID` y el dominio. No uses registros detallados de tráfico ni habilites caché
HTML en Cloudflare. El token del túnel y los archivos JSON también son secretos. La
redacción de Origo no controla logs, analíticas, historial del navegador o WhatsApp de
terceros; no exportes URLs completas de `/g/*` desde Cloudflare.

### Cloudflare Access (recomendado)

En Zero Trust → Access → Applications, creá una aplicación propia para
`origo.example.com` y permití únicamente tu identidad, con MFA. Access agrega una barrera;
**no reemplaza** el login de Origo.

Si tus invitados o clientes MCP no pueden pasar Access, creá aplicaciones más específicas
con política de omisión (*Bypass*) para `/g/*` y `/mcp` (también `/mcp/*`). Con OAuth,
incluí `/.well-known/*`, `/authorize`, `/token`, `/register`, `/revoke`, `/auth/callback`
y `/consent`. Para que un invitado pueda navegar después del link, también necesita
`/super`, `/super/*`, `/deudas`, `/deudas/*`, `/static/*`, `/login` y `/logout` fuera de
Access, o una política Access que admita su identidad. Origo sigue controlando cada
permiso; **no** omitas todo el dominio por comodidad. Comprobá la precedencia de las
aplicaciones específicas y probá desde incógnito y un cliente MCP real.

## 6. Backups y restauración

`origo-backup.timer` hace un backup diario a las 03:15 (con demora aleatoria y recuperación
si la laptop estaba apagada). Usa `sqlite3 .backup`, verifica `quick_check` y conserva 30
días en `/var/lib/origo/backups`, con directorio 700 y archivos 600. Cambiá la retención
mediante un override de `origo-backup.service`, no en el archivo de la app.

```bash
sudo systemctl start origo-backup.service
sudo systemctl list-timers origo-backup.timer
sudo -u origo sqlite3 /var/lib/origo/backups/origo-FECHA.db 'PRAGMA quick_check;'
```

Copiá además los backups **cifrados a otra máquina**: un backup en el mismo disco no cubre
robo o falla del disco. Con [restic](https://restic.net) (cifra por defecto) a un disco
externo, otra máquina por SFTP o un bucket; copiá la carpeta `backups/` (copias
consistentes), no la DB abierta:

```bash
export RESTIC_REPOSITORY=sftp:usuario@otra-maquina:/ruta/origo-restic   # o un disco montado
export RESTIC_PASSWORD_FILE=/root/.restic-origo                         # chmod 600, fuera de Git
sudo -E restic init                                                     # una sola vez
sudo -E restic backup /var/lib/origo/backups
```

Guardá la clave de restic en otro lugar: sin ella no recuperás nada. Guardá aparte
`/etc/origo/origo.env` y el estado OAuth de `/var/lib/origo`, con cifrado y acceso
restringido. La DB incluye secretos TOTP. Probá recuperar un backup de vez en cuando.

**Restaurar con prudencia.** Primero verificá la copia en un lugar descartable
(`sqlite3 copia.db 'PRAGMA quick_check;'`, debe decir `ok`). Después: detené Origo, guardá
una copia de la DB actual (no la borres), reemplazala por el backup, eliminá los archivos
`origo.db-wal`/`origo.db-shm` antiguos si existen y ajustá dueño y permisos. Antes de
arrancar, invalidá sesiones restauradas:

```bash
sudo -u origo sqlite3 /var/lib/origo/origo.db 'DELETE FROM web_sessions;'
sudo chmod 600 /var/lib/origo/origo.db
sudo systemctl start origo
```

Una restauración también puede revivir links antes revocados; rotalos si corresponde.
Al arrancar se crean las tablas nuevas y se agregan las columnas nuevas que falten (siempre
opcionales), sin borrar ni modificar datos existentes. Solo se admiten cambios aditivos: un cambio
que borre o transforme columnas necesitaría una migración explícita. Hacé un backup antes de actualizar.

## 7. Verificación mínima

Probá en incógnito: sin sesión redirige a `/login`, los datos incorrectos no enumeran
usuarios, cerrar sesión impide reutilizar la cookie y `/docs` devuelve 404. `/mcp` sin
bearer devuelve 401 incluso si tenés cookie web. Para probar formularios con curl agregá
`Origin: https://origo.example.com`; una escritura sin origen o con origen ajeno debe
responder 403. Verificá que la cookie tenga `Secure`, `HttpOnly` y `SameSite=Lax`.
Con `MCP_LOCAL_ONLY=1`, `/mcp` por la URL pública debe dar 404, también con bearer.

## Actualizar

```bash
sudo systemctl start origo-backup.service
cd /opt/origo && sudo git pull
sudo env UV_PYTHON_INSTALL_DIR=/opt/origo-python uv sync --frozen --no-dev
sudo systemctl restart origo
sudo journalctl -u origo -n 30
```

Si cambió algo en `deploy/`, volvé a copiar los `.service` y corré `sudo systemctl daemon-reload`.

Lo mismo en un solo comando, con vuelta atrás automática si algo falla: `deploy/update.sh`.
Instalado como `/usr/local/sbin/origo-update`, también lo puede correr un agente sin poder tocar
el código (ver [Aislar al agente del código](agentes.md#aislar-al-agente-del-código)).

## Alternativa: Docker

Para quien prefiera contenedores: el mismo Origo con `compose.yaml` (publica solo
`127.0.0.1:8000`, corre como UID 10001 y guarda todo en el volumen `/data`). No incluye
Hermes: si lo usás, ya lo tenés aparte. El proxy HTTPS (sección 4) o Tailscale van delante,
igual que con systemd.

```bash
python3 deploy/configure.py --mode docker --mcp-scope remote \
  --base-url https://origo.example.com --owner-name TuNombre --output .env
docker compose up -d --build
docker compose exec origo python -m app.cli create-user tu-usuario
```

Docker **exige `--mcp-scope remote`** (`MCP_LOCAL_ONLY=0`): las llamadas llegan desde la red de
Docker, no desde 127.0.0.1, así que `MCP_LOCAL_ONLY=1` bloquearía incluso a un Hermes que corre
en el mismo host. Como el bearer pasa a ser la única barrera de `/mcp`, mantené el puerto en
loopback y cortá `/mcp` en el proxy público (bloque `@mcp` de la sección 4) si no querés MCP
remoto. Hermes en el host usa `http://127.0.0.1:8000/mcp`.

El `.env` que lee `compose.yaml` es el que generó `configure.py` (otro archivo: `ORIGO_ENV_FILE`).
En Docker la base es `/data/origo.db`. Dentro del contenedor el proxy y los clientes llegan
desde la red de Docker: no se confía en proxy headers, así que el límite de intentos de login
por IP es compartido. Los redirects al host público conservan HTTPS desde `BASE_URL`, no
desde headers de terceros. `deploy/backup.sh` y los timers son para systemd; en Docker usá
`deploy/docker-backup.py`, que hace una copia consistente y la verifica:

```bash
docker compose exec -T origo python - < deploy/docker-backup.py
```

Deja los snapshots en `/data/backups`, **el mismo volumen**: sigue faltando copiarlos fuera
del host como en la sección 6 (por ejemplo con `docker cp` y restic) y programarlo vos (cron).

## Recomendado además

- **Monitoreo:** healthchecks.io (gratis) para enterarte si el servidor o el backup dejan de reportar.
- **Acceso remoto por SSH:** Tailscale es una opción para no abrir el 22 ([tailscale.md](tailscale.md)).
  Cambiar SSH o el firewall siempre a mano, con otra sesión abierta para no quedarte afuera.
