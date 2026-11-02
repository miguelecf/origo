# Contribuir a Origo

Origo es un proyecto personal de código abierto ([MIT](LICENSE)): lo mantengo según lo que
uso, así que no prometo plazos ni que acepte todo. Un issue antes de un PR grande ahorra trabajo.

## Qué encaja y qué no

- Encaja: arreglos, tests, mejoras de seguridad, documentación, despliegue en casa o VPS,
  traducciones de la UI.
- No encaja: multiusuario o versión alojada. Cada instancia es de **un solo dueño**; los
  invitados con link solo ven Súper y Deudas.
- Cambios visuales o de marca (logo, colores, tipografías): abrí un issue primero.

## Cómo correrla

```bash
uv sync
cp .env.example .env && chmod 600 .env
uv run python -m app.cli create-user tu-usuario
uv run uvicorn app.main:app --host 127.0.0.1 --reload
uv run pytest
```

Los tests usan una base temporal (`tests/conftest.py`): no tocan la tuya.

## Reglas del código

- Toda la lógica va en `app/services/`. Las rutas web y las tools MCP solo llaman a servicios.
- Los servicios hacen `commit`; para operaciones compuestas usá helpers que no commitean
  (`finance.new_transaction`) y un solo `commit` al final.
- Plata en `Decimal` / `Numeric(14, 2)`, nunca `float` (salvo al serializar para MCP).
- Fechas con `app.core.clock.today()/now()`, no `date.today()`. Rangos siempre `[start, end)`.
- UI en español rioplatense; identificadores en inglés.
- Permisos en `app/web/auth.py`: todo es del dueño (`require_owner`) salvo Súper y Deudas
  (`require_scope`). Un invitado nunca ve Plata, Cuerpo ni Día.

## Datos y secretos

Nunca subas `.env`, bases `.db`, backups, tokens, capturas con datos reales ni links de
invitado. Los ejemplos del repo usan placeholders (`origo.example.com`, `Ana`); mantené eso en
issues, logs y PRs. Si pegás un log, revisá que no tenga cookies, bearer ni URLs `/g/...`.

## Pull requests

PRs chicos y enfocados, con tests cuando cambia el comportamiento y `uv run pytest` en verde.
Si cambia el despliegue, actualizá `docs/`. Al aportar aceptás que tu contribución se publica
bajo la licencia MIT del proyecto. Vulnerabilidades: no por issue público, mirá [SECURITY.md](SECURITY.md).
