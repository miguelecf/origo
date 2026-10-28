# Desplegar Origo

Origo es una sola app de Python con SQLite: corre en cualquier Linux con systemd. Esta guía
sirve igual para una laptop vieja en tu casa o para un VPS. La única diferencia es dónde vive
la máquina: los pasos son los mismos.

```
celular ──https──▶ Cloudflare ──túnel──▶ cloudflared ──▶ 127.0.0.1:8000 (Origo) ──▶ SQLite
```

Origo nunca escucha en una IP pública ni necesita puertos abiertos: el túnel sale desde tu
máquina hacia Cloudflare.

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

# SSH solo con llave (probá entrar desde otra terminal antes de cerrar la sesión)
printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n' | sudo tee /etc/ssh/sshd_config.d/10-solo-llave.conf
sudo systemctl restart ssh
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

La laptop corre un solo proceso en **127.0.0.1:8000**. No abras ese puerto en el router ni
lo publiques con `0.0.0.0`. Cloudflare termina TLS; `BASE_URL` debe ser el origen público
HTTPS aunque el tramo local sea HTTP. `SECRET_KEY` es obligatoria, aleatoria y de al menos
32 bytes: la app se niega a arrancar con un secreto vacío, corto o reconociblemente débil.

### Servicio y usuario

Necesitás Python 3.13+, `uv`, SQLite CLI y systemd. Instalá Python en una ruta legible para
`origo`, no en el directorio personal de otro usuario (`ProtectHome=true`). Si usás el
Python administrado por uv, instalalo con `UV_PYTHON_INSTALL_DIR=/opt/origo-python` y usá
esa misma variable al crear el entorno. Cloná el repo en `/opt/origo` (`sudo git clone https://github.com/miguelecf/origo.git /opt/origo`), con código y
entorno propiedad de root, sin permisos de escritura para el servicio:

```bash
sudo useradd --system --home-dir /var/lib/origo --shell /usr/sbin/nologin origo
sudo install -d -m 700 -o origo -g origo /var/lib/origo
sudo install -d -m 750 -o root -g origo /etc/origo
cd /opt/origo
sudo env UV_PYTHON_INSTALL_DIR=/opt/origo-python uv sync --frozen --no-dev
sudo install -m 600 -o origo -g origo .env.example /etc/origo/origo.env
sudo -u origo editor /etc/origo/origo.env
```

Completá `BASE_URL=https://origo.example.com`,
`DATABASE_URL=sqlite:////var/lib/origo/origo.db`, `SECRET_KEY`, y MCP si lo necesitás.
Generá cada secreto por separado con `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`.
No pongas credenciales en argumentos de comandos ni las subas a Git.
La CLI lee `.env` del directorio actual; para que use exactamente el archivo de producción:

```bash
sudo -u origo ln -s /etc/origo/origo.env /var/lib/origo/.env
cd /var/lib/origo
sudo -u origo env PYTHONPATH=/opt/origo /opt/origo/.venv/bin/python -m app.cli create-user tu-usuario
sudo -u origo env PYTHONPATH=/opt/origo /opt/origo/.venv/bin/python -m app.cli enable-totp tu-usuario
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
Los procesos locales y cloudflared pertenecen al perímetro confiable.

## 4. Publicarlo con Cloudflare Tunnel

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

## 5. Backups y restauración

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
robo o falla del disco. Guardá aparte `/etc/origo/origo.env` y el estado OAuth de
`/var/lib/origo` con cifrado y acceso restringido. La DB incluye secretos TOTP.
Para restaurar: detené Origo, guardá una copia de la DB actual, reemplazala por el backup,
eliminá los archivos `origo.db-wal`/`origo.db-shm` antiguos si existen y ajustá dueño y
permisos. Antes de arrancar, invalidá sesiones restauradas:

```bash
sudo -u origo sqlite3 /var/lib/origo/origo.db 'DELETE FROM web_sessions;'
sudo chmod 600 /var/lib/origo/origo.db
sudo systemctl start origo
```

Una restauración también puede revivir links antes revocados; rotalos si corresponde.
Al arrancar se crean las tablas nuevas y se agrega `guests.expires_at` si falta, sin borrar
datos existentes. Esta es una migración aditiva puntual; futuros cambios de esquema
requieren migraciones explícitas. Hacé un backup antes de actualizar.

## 6. Verificación mínima

Probá en incógnito: sin sesión redirige a `/login`, los datos incorrectos no enumeran
usuarios, cerrar sesión impide reutilizar la cookie y `/docs` devuelve 404. `/mcp` sin
bearer devuelve 401 incluso si tenés cookie web. Para probar formularios con curl agregá
`Origin: https://origo.example.com`; una escritura sin origen o con origen ajeno debe
responder 403. Verificá que la cookie tenga `Secure`, `HttpOnly` y `SameSite=Lax`.

## Actualizar

```bash
sudo systemctl start origo-backup.service
cd /opt/origo && sudo git pull
sudo env UV_PYTHON_INSTALL_DIR=/opt/origo-python uv sync --frozen --no-dev
sudo systemctl restart origo
sudo journalctl -u origo -n 30
```

Si cambió algo en `deploy/`, volvé a copiar los `.service` y corré `sudo systemctl daemon-reload`.

## Alternativa: Docker

Hay un `Dockerfile` para quien prefiera contenedores. Los datos quedan en el volumen `/data`:

```bash
docker build -t origo .
docker run -d --name origo --env-file origo.env -v origo-data:/data \
  -p 127.0.0.1:8000:8000 --restart unless-stopped --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges origo
docker exec -it origo python -m app.cli create-user tu-usuario
```

Con Docker, `MCP_LOCAL_ONLY=1` no sirve para un agente que corre fuera del contenedor (las
llamadas llegan desde la red de Docker, no desde 127.0.0.1). Si vas a usar un agente local,
preferí systemd.

## Recomendado además

- **Copia fuera de la máquina:** con `restic` a un disco externo o a un bucket. Un backup en el
  mismo disco no te salva si se rompe o te la roban.
- **Acceso remoto por SSH:** Tailscale, sin abrir puertos.
- **Monitoreo:** healthchecks.io (gratis) para enterarte si el servidor o el backup dejan de reportar.
