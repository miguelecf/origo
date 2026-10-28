# AGENTS.md — origo

App personal de registro de vida (un solo usuario). Ver README para correrla.

- Toda la lógica vive en `app/services/`. Las rutas web (`app/routers/`) y las tools MCP
  (`app/mcp_server.py`) solo llaman a servicios; no dupliques reglas en ninguno de los dos.
- Los servicios hacen `commit`. Para operaciones compuestas usá los helpers que no commitean
  (`finance.new_transaction`) y un solo `commit` al final.
- Plata en `Decimal` / `Numeric(14, 2)`, nunca float (salvo al serializar para MCP).
- Fechas: usá `app.core.clock.today()/now()` (zona de `TIMEZONE`), no `date.today()`.
- Rangos de fechas: siempre `[start, end)`.
- UI en español rioplatense, identificadores en inglés.
- Permisos: `app/web/auth.py`. Todo es solo del dueño (`require_owner`) salvo Súper y Deudas
  (`require_scope`), donde también entran invitados con link mágico. Un invitado nunca ve
  Plata, Cuerpo ni Día, y solo toca su propia compra y sus propias deudas.
- Tests: `uv run pytest`. Los tests usan una DB temporal (ver `tests/conftest.py`).
