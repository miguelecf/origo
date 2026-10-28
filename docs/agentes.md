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
`get_weight_series`, `get_food_log`, `get_checkins`, `get_market_trips`, `get_price_history`,
`get_home_list`, `get_subscriptions`. De escritura: `add_transaction`, `add_debt`, `lend_card`, `set_installment_paid`,
`resolve_payment_claim`, `save_checkin`, `log_food`, `log_weight`, `set_weight_goal`,
`add_to_home_list`, `toggle_home_item`, `add_subscription`, `mark_subscription_charged`,
`set_subscription_active`, `delete_transaction`. Prompt: `weekly_review`.

## Hermes por Telegram

Hermes corre en el mismo server que Origo, habla con vos por un bot de Telegram y usa Origo por
MCP en `127.0.0.1`, sin que `/mcp` quede publicado en internet.

**En Origo** (`/etc/origo/origo.env`), y reiniciá el servicio:

```
MCP_TOKEN=<python3 -c "import secrets; print(secrets.token_urlsafe(48))">
MCP_LOCAL_ONLY=1
```

Con `MCP_LOCAL_ONLY=1`, `/mcp` responde 404 a todo lo que llega por el túnel o desde otra IP. El
ejemplo de `deploy/cloudflared-config.example.yml` además corta `/mcp` en Cloudflare: son dos
barreras independientes.

**El bot.** En @BotFather: `/newbot`, después `/setjoingroups` → *Disable* (nadie lo puede sumar a
un grupo) y `/setprivacy` → *Enable*. Tu ID numérico te lo da @userinfobot.

**En Hermes**, con el usuario que lo corre:

1. `~/.hermes/.env` (y `chmod 600`):
   ```
   TELEGRAM_BOT_TOKEN=<token de BotFather>
   TELEGRAM_ALLOWED_USERS=<tu ID numérico>
   ```
   No definas `TELEGRAM_GROUP_ALLOWED_USERS` ni `TELEGRAM_GROUP_ALLOWED_CHATS`. Sin lista de
   permitidos Hermes rechaza a todos, así que un error acá cierra, no abre.
2. Copiá `hermes/config.example.yaml` dentro de `~/.hermes/config.yaml`, poné el `MCP_TOKEN` y tu
   ID, y `chmod 600 ~/.hermes/config.yaml`. Deja la lista de tools cerrada y suma el skill desde
   `/opt/origo/hermes/skills`, así se actualiza con cada `git pull`.
3. `hermes gateway` (o instalalo como servicio) y mandale "¿cómo vengo este mes?" al bot.
   Si no ve las tools, `/reload-mcp`.

El skill `hermes/skills/origo/SKILL.md` le enseña qué tool usar para cada cosa, a confirmar
cada alta con su id y a no borrar nada sin un "sí" tuyo. Para avisos de vencimientos, pedile
"todos los días a las 9 avisame las cuotas que vencen en 3 días" y arma un cron a Telegram.

**Qué tan privado es.** Nadie más puede hablarle al bot y Origo no se expone. Pero un chat con
un bot de Telegram no tiene cifrado de punta a punta: Telegram guarda los mensajes en sus
servidores, y el proveedor del modelo que use Hermes ve lo que le pasás. Si querés que los datos
no salgan de casa, usá un modelo local en Hermes; Telegram igual ve los mensajes del chat.
