# Agentes: MCP y Hermes

Todo lo que hace la app también está disponible por MCP, sobre la misma capa de servicios: un agente anota y consulta con las mismas reglas que la web.

## MCP

**Local** (Claude Code, Claude Desktop): ya está configurado en `.mcp.json`.
Para otro cliente: `uv run --directory /ruta/a/origo python -m app.mcp_server` (stdio).

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

Tools de lectura: `get_overview`, `list_transactions`, `get_debts`, `get_due_payments`,
`get_weight_series`, `get_weight_goals`, `get_food_log`, `get_checkins`, `get_market_trips`,
`get_price_history`, `get_home_list`, `get_subscriptions`, `get_diet_plan`, `get_routine`,
`get_workout_history`.

De escritura: `add_transaction`, `add_debt`, `lend_card`, `set_installment_paid`,
`resolve_payment_claim`, `save_checkin`, `log_food`, `log_weight` (con composición opcional),
`set_weight_goal` (meta final), `add_weight_milestone`, `add_to_home_list`, `toggle_home_item`,
`add_subscription`, `mark_subscription_charged`, `set_subscription_active`, `set_meal`,
`copy_diet_day`, `set_diet_targets`, `add_routine_item`, `update_routine_item`,
`move_routine_item`, `set_routine_day_title`.

De borrado (pedí confirmación antes): `delete_transaction`, `delete_food_entry`, `clear_meal`,
`delete_weight_milestone`, `delete_routine_item`.

Límites a propósito: el MCP no marca entrenamientos como hechos (eso lo tocás vos en el gym),
la rutina y la dieta son fijas por día de semana y no rotan solas, la dieta lleva una sola
comida por momento y por día (el formato exacto lo devuelve `get_diet_plan` en `format`), y los objetivos del plan (kcal, macros) se
guardan tal cual: Origo no los calcula ni los toma como comidas consumidas.
Prompt: `weekly_review`.

## Límites del agente

Origo decide qué puede hacer el agente, del lado del servidor. Valen aunque el cliente del agente
esté mal configurado, y se suman a la lista `tools.include` de Hermes, no la reemplazan.

| Variable | Por defecto | Qué hace |
|---|---|---|
| `MCP_ACCESS` | `write` | `read` deja al agente en solo lectura: no ve ni puede llamar tools que escriben. |
| `MCP_DENY` | vacío | Tools prohibidas, separadas por coma, con comodines: `delete_*,clear_meal`. No aparecen en la lista y si las llama, falla. |
| `MCP_MAX_WRITES_PER_HOUR` | `60` | Tope de escrituras por hora. `0` = sin tope. |
| `MCP_MAX_BACKDATE_DAYS` | `45` | Cuántos días para atrás puede fechar algo (`date`). Nunca a futuro. |
| `MCP_MAX_AMOUNT` | `0` | Tope por monto (`amount`, `total`, `amount_ars`). `0` = sin tope. Lo que lo supere se carga desde la web. |

Además, un peso que se aleja más de un 8 % del último registro se rechaza: el agente tiene que
confirmarlo con vos y lo cargás desde la web.

Cada escritura, hecha o rechazada, queda registrada con sus datos. Se ve en la web, en
**Inicio → 🤖 Agente**, junto con los límites activos. Las lecturas no se registran.

Cuando una tool rechaza algo, el agente recibe el motivo ("una comida va en un solo renglón",
"el agente no puede cargar fechas a futuro") para poder corregir. Los errores internos siguen
ocultos.

Estos límites cubren lo que el agente hace **dentro de Origo**. Que no pueda tocar el código ni
la base de datos por otro lado se resuelve en el sistema: ver
[Aislar al agente](#aislar-al-agente-del-código).

## Aislar al agente del código

Un agente como Hermes suele tener terminal propia. El MCP no le da acceso al código, pero si el
agente corre con tu usuario, y tu usuario tiene `sudo`, puede editar Origo o leer la base por
fuera del MCP. Eso se corta en el sistema, no en Origo:

1. **Un usuario propio para el agente**, sin `sudo` general y fuera de los grupos `sudo`, `wheel`,
   `docker` y `lxd` (todos equivalen a root):

   ```bash
   sudo useradd --create-home --shell /bin/bash hermes
   ```

   Instalá y corré el agente con ese usuario. El token del MCP va en la configuración del agente
   (por ejemplo `~/.hermes/.env`), no en `/etc/origo`.

2. **El código, la configuración y la base no son suyos.** Con la instalación de
   [despliegue.md](despliegue.md) ya es así: `/opt/origo` es de root, `/etc/origo` y
   `/var/lib/origo` son del usuario `origo` y no se pueden leer desde otro.

3. **Que se pueda actualizar, y nada más.** `deploy/update.sh` hace backup, avanza a lo último de
   `origin/main` (solo fast-forward: si el código instalado tiene cambios locales o la historia
   cambió, no hace nada), corre `uv sync`, reinicia y comprueba que Origo responda. Si falla,
   vuelve a la versión anterior. No recibe argumentos. Instalalo fuera del repo y dale permiso
   solo a ese comando:

   ```bash
   sudo install -m 755 -o root -g root /opt/origo/deploy/update.sh /usr/local/sbin/origo-update
   echo 'hermes ALL=(root) NOPASSWD: /usr/local/sbin/origo-update ""' | sudo tee /etc/sudoers.d/origo-update
   sudo chmod 440 /etc/sudoers.d/origo-update && sudo visudo -c
   ```

   El `""` final prohíbe pasarle argumentos. El agente actualiza con `sudo origo-update`. Lo que
   instala sale de GitHub, no de algo que el agente pueda escribir. Si una versión cambia
   `deploy/update.sh`, el script lo avisa y la copia en `/usr/local/sbin` la reinstala una persona.

4. **Comprobalo:**

   ```bash
   sudo sh /opt/origo/deploy/check-agent.sh hermes
   ```

   Revisa grupos, reglas de `sudo` y que el usuario no pueda escribir el código, la configuración
   ni los servicios, ni leer la base, el `.env` o los backups. Cada línea dice `OK` o `FALLA`.

Si tu agente permite apagar sus herramientas de terminal o de archivos, también sirve, pero no
alcanza solo: una opción del agente se puede cambiar desde el propio agente. Los permisos del
sistema, no.

## Hermes como compañero

Hermes es el agente que uso con Origo, pero Origo no lo necesita: **la web sigue funcionando
completa si Hermes se cae o no lo instalás**. Esta guía no instala Hermes ni toca su
configuración: solo conecta uno que ya tengas. Cualquier otro cliente MCP sirve igual.

| Dónde corre Hermes | En Origo | URL del MCP |
|---|---|---|
| Misma máquina, Origo con systemd | `MCP_LOCAL_ONLY=1` + `MCP_TOKEN` | `http://127.0.0.1:8000/mcp` |
| Otra máquina | `MCP_LOCAL_ONLY=0` + `MCP_TOKEN` dedicado | HTTPS privado, p. ej. [Tailscale](tailscale.md) o tu proxy |
| Origo en Docker (incluso con Hermes en el host) | `MCP_LOCAL_ONLY=0` + `MCP_TOKEN` | `http://127.0.0.1:8000/mcp` |

`deploy/configure.py` arma esos valores con `--mcp-scope local|remote`. Docker exige `remote`:
las llamadas llegan desde la red de Docker, no desde loopback.

Con `MCP_LOCAL_ONLY=1`, `/mcp` responde 404 a todo lo que llega por un proxy, túnel o desde
otra IP. Con `MCP_LOCAL_ONLY=0` el bearer es la única barrera: restringí quién llega a la URL
(ACL de Tailscale, firewall) y, si no querés MCP remoto, cortá `/mcp` en el proxy (ejemplos en
[despliegue.md](despliegue.md)). El token es de dueño: nunca para invitados.

### Conectar Hermes sin pisar su configuración

1. Prepará el archivo privado con el usuario que corre Hermes (no con root):
   ```bash
   umask 077
   mkdir -p ~/.hermes
   touch ~/.hermes/.env
   chmod 600 ~/.hermes/.env
   ```
   En un editor local, agregá o actualizá **una sola** entrada `ORIGO_MCP_TOKEN` con el
   `MCP_TOKEN` de Origo. Conservá las demás variables. Si está en otra máquina, transferí el
   secreto por un canal seguro (por ejemplo tu gestor de contraseñas), nunca por chat con
   un agente, logs, argumentos de comandos ni un archivo versionado.
2. Hacé una copia de `~/.hermes/config.yaml`, abrilo y sumá **solo** la clave
   `mcp_servers.origo` de [`hermes/config.example.yaml`](../hermes/config.example.yaml). Si ya
   tenés `mcp_servers`, agregá `origo` adentro; no reemplaces el archivo.
3. La doc oficial de Hermes ([referencia](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/mcp-config-reference.md),
   [guía](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md))
   documenta `${VAR}` en `url` y `headers`, resuelto desde `~/.hermes/.env`, y que falla
   cerrado si la variable no existe. Podés usar `Authorization: "Bearer ${ORIGO_MCP_TOKEN}"` y
   no dejar el token en el YAML. Si tu versión no lo resuelve, pegá el token en el YAML
   (`chmod 600`). Esta guía no lo probó con una versión concreta.
4. En una sesión de Hermes corré `/reload-mcp` y pedile "¿cómo vengo este mes?".

`tools.include` es una lista cerrada: las tools nuevas de Origo no aparecen hasta que las
sumes. Para que no pueda borrar, sacá las tres `delete_*`.

### Skill y recordatorios

El skill `hermes/skills/origo/SKILL.md` le enseña qué tool usar para cada cosa, a confirmar
cada alta con su id y a no borrar nada sin un "sí" tuyo. Si Hermes corre en otra PC, copiá
esa carpeta allá. Para avisos, pedile "todos los días a las 9 avisame las cuotas que vencen en 3 días".

### Telegram (opcional)

Si Hermes te atiende por Telegram: en @BotFather `/newbot`, después `/setjoingroups` → *Disable*
y `/setprivacy` → *Enable*. Tu ID numérico te lo da @userinfobot. En `~/.hermes/.env` van
`TELEGRAM_BOT_TOKEN` y `TELEGRAM_ALLOWED_USERS=<tu ID>`; no definas
`TELEGRAM_GROUP_ALLOWED_USERS` ni `TELEGRAM_GROUP_ALLOWED_CHATS`. Verificá para tu versión la política de acceso del bot y probá que un usuario no permitido
quede rechazado antes de usar datos reales; estas claves no están verificadas por los tests de Origo.

### Qué tan privado es

El MCP en loopback no sale de la máquina. Entre nodos Tailscale puede cruzar internet,
pero viaja cifrado; no confundir red privada con ausencia de tránsito por internet. Pero Telegram no cifra de punta
a punta y guarda los mensajes en sus servidores, y un modelo en la nube ve lo que Hermes le
pasa. Si querés que los datos no salgan de tu red, usá un **modelo local** en Hermes y no uses
Telegram. Telegram, los modelos cloud, Tailscale y Cloudflare son opcionales y varios son
servicios propietarios: Origo + systemd + tu proxy HTTPS + un modelo local no depende de ninguno.
