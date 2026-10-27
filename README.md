# Mentor

Registro personal en 5 minutos por día: plata, deudas, cuerpo, listas y un check-in diario.
Todo queda expuesto por MCP para que un agente lo analice y te marque fallas.

FastAPI + SQLite + Jinja2 + HTMX/Alpine, CSS propio. MCP con FastMCP sobre la misma capa `app/services/`.

## Correr

```bash
uv sync
cp .env.example .env
chmod 600 .env
uv run python -m app.cli create-user miguel
uv run uvicorn app.main:app --host 127.0.0.1 --reload --no-access-log
```

Abrí http://localhost:8000. En el celular: "Agregar a pantalla de inicio" (es una PWA).

Tests: `uv run pytest`

## Qué hay

| Sección | Qué hace |
|---|---|
| Inicio | Balance del mes, deudas, peso desde que arrancaste, promedios de 7 días, alertas de tarjeta |
| Plata | Ingresos y gastos por categoría, en una página por mes |
| Deudas | Me deben / debo, en cuotas. "Presté la tarjeta" crea los dos lados (la persona te debe, vos le debés al banco) y avisa si una cuota vence y no te pagaron. Marcar una cuota la registra en Plata |
| Cuerpo | Comidas en texto libre (Enter y listo), peso con gráfico, meta |
| Súper | Lista de casa (se manda por WhatsApp) y la compra: escribís precios (con o sin nombre) y el total se suma solo. Recuerda precios y avisa cuánto subieron. Al terminar se carga como gasto en Súper. Funciona sin señal |
| Día | Sueño, ánimo 1–5, minutos de movimiento, una línea. Revisión semanal |

## Invitados con link mágico

En **Inicio → Invitados con link** creás un link por persona y elegís qué ve:

- **Súper**: comparte la lista de casa y hace sus propias compras. Sus compras no se cargan como gasto tuyo; si la pagaste vos, tocá "La pagué yo".
- **Deudas**: ve solo las deudas que tiene con vos (no el lado del banco de una tarjeta prestada) y puede avisarte "ya te pagué esta y esta". Vos confirmás (entra la plata en Plata) o rechazás, y le llega la respuesta.

El link se muestra una sola vez. "Link nuevo" invalida el anterior; "Quitar" corta el acceso.
Los links usan `BASE_URL`, así que poné la dirección con la que entran desde el celular.

## MCP

**Local** (Claude Code, Claude Desktop): ya está configurado en `.mcp.json`.
Para otro cliente: `uv run --directory /ruta/a/mentor python -m app.mcp_server` (stdio).

**Remoto** (Claude.ai, ChatGPT, apps del celular): necesita la app publicada con HTTPS.

1. Creá una OAuth App en GitHub (Settings → Developer settings → OAuth Apps):
   - Homepage URL: tu `BASE_URL`
   - Authorization callback URL: `<BASE_URL>/auth/callback`
2. Completá en `.env`: `BASE_URL`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_ALLOWED_LOGIN` (tu usuario) y un `SECRET_KEY` largo.
3. En Claude.ai → Conectores → agregar conector personalizado: `<BASE_URL>/mcp`.

Solo `GITHUB_ALLOWED_LOGIN` puede usar las herramientas con OAuth; se valida antes de aceptar HTTP.
Como alternativa, configurá `MCP_TOKEN` con al menos 32 bytes aleatorios y enviá
`Authorization: Bearer <MCP_TOKEN>`. Se pueden usar ambos modos a la vez. El token tiene
acceso completo de dueño; no es un permiso de invitado. Rotarlo requiere reiniciar el servicio.
Sin OAuth completo ni token estático, el transporte remoto no se monta y `/mcp` responde 401.
El transporte stdio sigue siendo local, sin OAuth: protegé el acceso al usuario del sistema.

Tools: `get_overview`, `list_transactions`, `get_debts`, `get_weight_series`, `get_food_log`,
`get_checkins`, `get_market_trips`, `get_price_history`, `add_transaction`, `log_food`,
`log_weight`, `add_to_home_list`. Prompt: `weekly_review`.

## Usuarios y seguridad

No existe registro web ni contraseña global `APP_PASSWORD`. Sin usuarios creados, nadie
entra como dueño. Todos los usuarios locales tienen rol de dueño y ven los mismos datos.
La administración requiere acceso local al servidor:

```bash
uv run python -m app.cli create-user miguel
uv run python -m app.cli set-password miguel
uv run python -m app.cli enable-totp miguel
uv run python -m app.cli disable-totp miguel
uv run python -m app.cli list-users
```

Las contraseñas se piden sin eco (mínimo 12 caracteres) y se guardan con Argon2id.
`enable-totp` muestra un URI para importar en el autenticador y exige un código antes de
activarlo. No hay recuperación por correo: si perdés el autenticador, usá `disable-totp`
localmente. Cambiar contraseña o TOTP invalida todas las sesiones de ese usuario.

- Sesiones opacas con hash en SQLite: 30 minutos de inactividad y 24 horas absolutas por
  defecto; rotación al ingresar, cierre por POST e invalidación inmediata en servidor.
- Cookie `HttpOnly`, `SameSite=Lax` y `Secure` cuando `BASE_URL` usa HTTPS.
- Quinto intento por IP o usuario: pausa inicial de 30 segundos, duplicada por cada intento
  posterior hasta una hora; los contadores sobreviven reinicios y se reinician tras un día
  sin actividad. Un login correcto limpia el contador de ese usuario y descuenta su intento
  válido de la cuota por IP, sin borrar los fallos anteriores.
  Los links de invitado admiten 20 intentos por IP antes de la misma pausa creciente.
- Links con 192 bits aleatorios, almacenados como SHA256. Rotar o revocar corta también
  las sesiones abiertas. El servicio `create_guest(..., expires_at=...)` admite vencimiento
  opcional en la zona de `TIMEZONE`; el formulario actual no agrega un campo de vencimiento.
- CSRF: toda escritura web requiere `Origin` del mismo origen que `BASE_URL`, o `Referer`
  si falta `Origin`; rechaza `Sec-Fetch-Site: cross-site`. No usa campos nuevos ni modifica
  HTMX o el guardado PUT del súper. MCP/OAuth usan sus propios controles y están excluidos.
- `/docs`, `/redoc` y `/openapi.json` están deshabilitados. Se admite el host de `BASE_URL`,
  `localhost` y `127.0.0.1`. Los errores internos no exponen trazas.
- CSP permite scripts propios y `cdn.jsdelivr.net`. Conserva **`unsafe-inline`** por los
  scripts/handlers existentes y **`unsafe-eval`** por Alpine estándar; estilos inline
  también siguen permitidos, junto con las hojas y fuentes de Google Fonts ya usadas por
  la interfaz. Es una limitación explícita frente a XSS, no una CSP estricta.
  No se permite embeber la app, ni plugins; HTML no se cachea. HSTS se activa en HTTPS.
- El registro propio emite JSON por evento, sin cuerpos, cookies ni autorización. Descarta
  todos los valores de query y reemplaza `/g/{token}` por `/g/***`. Las páginas de entrada
  con link usan `no-referrer`; el resto, `same-origin`. No habilites registros DEBUG del
  proxy o de bibliotecas HTTP: podrían capturar credenciales fuera del registro de Mentor.
- `MENTOR_DEV_OPEN=1` es una excepción explícita para localhost HTTP. **No usar en el
  servidor**; la configuración se rechaza si `BASE_URL` es HTTPS o no es local.

## Despliegue en Linux con Cloudflare Tunnel

La laptop corre un solo proceso en **127.0.0.1:8000**. No abras ese puerto en el router ni
lo publiques con `0.0.0.0`. Cloudflare termina TLS; `BASE_URL` debe ser el origen público
HTTPS aunque el tramo local sea HTTP. `SECRET_KEY` es obligatoria, aleatoria y de al menos
32 bytes: la app se niega a arrancar con un secreto vacío, corto o reconociblemente débil.

### 1. Instalar el servicio

Necesitás Python 3.13+, `uv`, SQLite CLI y systemd. Instalá Python en una ruta legible para
`mentor`, no en el directorio personal de otro usuario (`ProtectHome=true`). Si usás el
Python administrado por uv, instalalo con `UV_PYTHON_INSTALL_DIR=/opt/mentor-python` y usá
esa misma variable al crear el entorno. Copiá el proyecto a `/opt/mentor`, con código y
entorno propiedad de root, sin permisos de escritura para el servicio:

```bash
sudo useradd --system --home-dir /var/lib/mentor --shell /usr/sbin/nologin mentor
sudo install -d -m 700 -o mentor -g mentor /var/lib/mentor
sudo install -d -m 750 -o root -g mentor /etc/mentor
cd /opt/mentor
sudo env UV_PYTHON_INSTALL_DIR=/opt/mentor-python uv sync --frozen --no-dev
sudo install -m 600 -o mentor -g mentor .env.example /etc/mentor/mentor.env
sudo -u mentor editor /etc/mentor/mentor.env
```

Completá `BASE_URL=https://mentor.example.com`,
`DATABASE_URL=sqlite:////var/lib/mentor/mentor.db`, `SECRET_KEY`, y MCP si lo necesitás.
Generá cada secreto por separado con `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`.
No pongas credenciales en argumentos de comandos ni las subas a Git.
La CLI lee `.env` del directorio actual; para que use exactamente el archivo de producción:

```bash
sudo -u mentor ln -s /etc/mentor/mentor.env /var/lib/mentor/.env
cd /var/lib/mentor
sudo -u mentor env PYTHONPATH=/opt/mentor /opt/mentor/.venv/bin/python -m app.cli create-user miguel
sudo -u mentor env PYTHONPATH=/opt/mentor /opt/mentor/.venv/bin/python -m app.cli enable-totp miguel
sudo chmod 600 /etc/mentor/mentor.env /var/lib/mentor/mentor.db
sudo cp /opt/mentor/deploy/mentor*.service /opt/mentor/deploy/mentor-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mentor.service mentor-backup.timer
sudo journalctl -u mentor -f
```

El servicio no usa root ni `--reload`; limita escritura a `/var/lib/mentor`, aplica
`ProtectSystem=strict`, `NoNewPrivileges`, capacidades vacías y permisos privados.
Uvicorn confía en proxy headers **solo de 127.0.0.1**. Mentor usa `CF-Connecting-IP` o
`X-Forwarded-For` únicamente si el peer aún es 127.0.0.1; si Uvicorn ya reescribió la IP,
usa la dirección validada por Uvicorn. No cambies `--forwarded-allow-ips` a `*`.
Los procesos locales y cloudflared pertenecen al perímetro confiable.

### 2. Crear el túnel

Instalá `cloudflared` desde el paquete oficial para tu distribución. El dominio debe estar
en tu cuenta de Cloudflare:

```bash
cloudflared tunnel login
cloudflared tunnel create mentor
cloudflared tunnel route dns mentor mentor.example.com
sudo install -d -m 700 /etc/cloudflared
sudo install -m 600 ~/.cloudflared/UUID.json /etc/cloudflared/UUID.json
sudo install -m 600 /opt/mentor/deploy/cloudflared-config.example.yml /etc/cloudflared/config.yml
sudo editor /etc/cloudflared/config.yml
sudo cloudflared --config /etc/cloudflared/config.yml tunnel ingress validate
sudo cloudflared --config /etc/cloudflared/config.yml service install
sudo systemctl enable --now cloudflared
```

Reemplazá `UUID` y el dominio. No uses registros detallados de tráfico ni habilites caché
HTML en Cloudflare. El token del túnel y los archivos JSON también son secretos. La
redacción de Mentor no controla logs, analíticas, historial del navegador o WhatsApp de
terceros; no exportes URLs completas de `/g/*` desde Cloudflare.

### 3. Cloudflare Access (recomendado)

En Zero Trust → Access → Applications, creá una aplicación propia para
`mentor.example.com` y permití únicamente tu identidad, con MFA. Access agrega una barrera;
**no reemplaza** el login de Mentor.

Si tus invitados o clientes MCP no pueden pasar Access, creá aplicaciones más específicas
con política de omisión (*Bypass*) para `/g/*` y `/mcp` (también `/mcp/*`). Con OAuth,
incluí `/.well-known/*`, `/authorize`, `/token`, `/register`, `/revoke`, `/auth/callback`
y `/consent`. Para que un invitado pueda navegar después del link, también necesita
`/super`, `/super/*`, `/deudas`, `/deudas/*`, `/static/*`, `/login` y `/logout` fuera de
Access, o una política Access que admita su identidad. Mentor sigue controlando cada
permiso; **no** omitas todo el dominio por comodidad. Comprobá la precedencia de las
aplicaciones específicas y probá desde incógnito y un cliente MCP real.

### 4. Backups y restauración

`mentor-backup.timer` hace un backup diario a las 03:15 (con demora aleatoria y recuperación
si la laptop estaba apagada). Usa `sqlite3 .backup`, verifica `quick_check` y conserva 30
días en `/var/lib/mentor/backups`, con directorio 700 y archivos 600. Cambiá la retención
mediante un override de `mentor-backup.service`, no en el archivo de la app.

```bash
sudo systemctl start mentor-backup.service
sudo systemctl list-timers mentor-backup.timer
sudo -u mentor sqlite3 /var/lib/mentor/backups/mentor-FECHA.db 'PRAGMA quick_check;'
```

Copiá además los backups **cifrados a otra máquina**: un backup en el mismo disco no cubre
robo o falla del disco. Guardá aparte `/etc/mentor/mentor.env` y el estado OAuth de
`/var/lib/mentor` con cifrado y acceso restringido. La DB incluye secretos TOTP.
Para restaurar: detené Mentor, guardá una copia de la DB actual, reemplazala por el backup,
eliminá los archivos `mentor.db-wal`/`mentor.db-shm` antiguos si existen y ajustá dueño y
permisos. Antes de arrancar, invalidá sesiones restauradas:

```bash
sudo -u mentor sqlite3 /var/lib/mentor/mentor.db 'DELETE FROM web_sessions;'
sudo chmod 600 /var/lib/mentor/mentor.db
sudo systemctl start mentor
```

Una restauración también puede revivir links antes revocados; rotalos si corresponde.
Al arrancar se crean las tablas nuevas y se agrega `guests.expires_at` si falta, sin borrar
datos existentes. Esta es una migración aditiva puntual; futuros cambios de esquema
requieren migraciones explícitas. Hacé un backup antes de actualizar.

### Verificación mínima

Probá en incógnito: sin sesión redirige a `/login`, los datos incorrectos no enumeran
usuarios, cerrar sesión impide reutilizar la cookie y `/docs` devuelve 404. `/mcp` sin
bearer devuelve 401 incluso si tenés cookie web. Para probar formularios con curl agregá
`Origin: https://mentor.example.com`; una escritura sin origen o con origen ajeno debe
responder 403. Verificá que la cookie tenga `Secure`, `HttpOnly` y `SameSite=Lax`.
