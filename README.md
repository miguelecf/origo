# Mentor

Registro personal en 5 minutos por día: plata, deudas, cuerpo, listas y un check-in diario.
Todo queda expuesto por MCP para que un agente lo analice y te marque fallas.

FastAPI + SQLite + Jinja2 + HTMX/Alpine, CSS propio. MCP con FastMCP sobre la misma capa `app/services/`.

## Correr

```bash
uv sync
cp .env.example .env   # opcional en local
uv run uvicorn app.main:app --reload
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

Solo `GITHUB_ALLOWED_LOGIN` puede usar las tools. Sin esas variables, `/mcp` no se monta.

Tools: `get_overview`, `list_transactions`, `get_debts`, `get_weight_series`, `get_food_log`,
`get_checkins`, `get_market_trips`, `get_price_history`, `add_transaction`, `log_food`,
`log_weight`, `add_to_home_list`. Prompt: `weekly_review`.

## Deploy

Un solo proceso y un archivo SQLite: necesita un **volumen persistente** para `mentor.db`.
Poné `APP_PASSWORD` y `SECRET_KEY` siempre que esté en internet. Backup = copiar `mentor.db`.

No hay migraciones: las tablas se crean al arrancar. Si cambiás un modelo existente, sumá Alembic.
