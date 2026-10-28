# Seguridad

Origo está pensado para exponerse a internet detrás de un túnel, con un solo dueño. Esto es lo que hace para que eso sea razonable.

## Usuarios

No existe registro web ni contraseña global `APP_PASSWORD`. Sin usuarios creados, nadie
entra como dueño. Todos los usuarios locales tienen rol de dueño y ven los mismos datos.
La administración requiere acceso local al servidor:

```bash
uv run python -m app.cli create-user ana
uv run python -m app.cli set-password ana
uv run python -m app.cli enable-totp ana
uv run python -m app.cli disable-totp ana
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
- CSP permite scripts solo del mismo origen. HTMX, Alpine y Chart.js se sirven desde
  `app/static/vendor/`, sin CDN externo. Conserva **`unsafe-inline`** por los scripts y
  handlers existentes y **`unsafe-eval`** por Alpine estándar; los estilos inline siguen
  permitidos. Las tipografías (Archivo y Outfit, licencia OFL) también se sirven desde la app. Es una limitación
  explícita frente a XSS, no una CSP estricta.
  No se permite embeber la app, ni plugins; HTML no se cachea. HSTS se activa en HTTPS.
- El registro propio emite JSON por evento, sin cuerpos, cookies ni autorización. Descarta
  todos los valores de query y reemplaza `/g/{token}` por `/g/***`. Las páginas de entrada
  con link usan `no-referrer`; el resto, `same-origin`. No habilites registros DEBUG del
  proxy o de bibliotecas HTTP: podrían capturar credenciales fuera del registro de Origo.
- `ORIGO_DEV_OPEN=1` es una excepción explícita para localhost HTTP. **No usar en el
  servidor**; la configuración se rechaza si `BASE_URL` es HTTPS o no es local.

## Invitados con link mágico

En **Inicio → Invitados con link** creás un link por persona y elegís qué ve:

- **Súper**: comparte la lista de casa y hace sus propias compras. Sus compras no se cargan como gasto tuyo; si la pagaste vos, tocá "La pagué yo".
- **Deudas**: ve solo las deudas que tiene con vos (no el lado del banco de una tarjeta prestada) y puede avisarte "ya te pagué esta y esta". Vos confirmás (entra la plata en Plata) o rechazás, y le llega la respuesta.

El link se muestra una sola vez. "Link nuevo" invalida el anterior; "Quitar" corta el acceso.
Los links usan `BASE_URL`, así que poné la dirección con la que entran desde el celular.
