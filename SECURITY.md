# Seguridad

## Reportar una vulnerabilidad

No abras un issue público con los detalles. Usá el reporte privado de GitHub del repositorio
(pestaña **Security** → *Report a vulnerability*) si está habilitado. Si no ves esa opción, abrí un
issue que diga solo que querés reportar algo de seguridad, sin datos técnicos, y coordinamos un canal
privado. Incluí versión o commit, pasos para reproducir y el impacto. Nunca mandes secretos ni
datos reales.

Es un proyecto personal sin equipo ni SLA: respondo cuando puedo y no ofrezco recompensas.
Solo se corrige la rama `main`.

Importa especialmente: saltear la autenticación, que un invitado vea o toque datos que no son
suyos, fugas de secretos en logs y `/mcp` accesible sin el bearer.

## Qué hace Origo

Una instancia, un dueño. No hay registro web: los usuarios se crean desde la terminal del
servidor (`python -m app.cli create-user | set-password | enable-totp | disable-totp | list-users`).

- Contraseñas de 12+ caracteres con Argon2id y 2FA (TOTP) opcional. Sin recuperación por correo:
  si perdés el autenticador, `disable-totp` desde el servidor.
- Sesiones guardadas en el servidor: vencen por inactividad (30 min) y a las 24 h, y se cortan al
  cambiar contraseña o 2FA. Cookie `HttpOnly`, `SameSite=Lax` y `Secure` con HTTPS.
- Pausas crecientes ante intentos fallidos de login o de links de invitado, que sobreviven reinicios.
- CSRF por origen: toda escritura web exige `Origin` (o `Referer`) igual a `BASE_URL`.
- CSP solo del mismo origen, sin CDN externos. Mantiene `unsafe-inline` y `unsafe-eval` (Alpine):
  no es una CSP estricta frente a XSS.
- Logs sin cuerpos, cookies, query ni tokens de invitado.
- Invitados con link: 192 bits aleatorios guardados como hash, limitados a Súper y Deudas, y
  solo a lo suyo. "Link nuevo" invalida el anterior; "Quitar" corta el acceso.
- MCP: por stdio es local y sin auth (protegé el usuario del sistema). Por HTTP exige
  `MCP_TOKEN` u OAuth, y con `MCP_LOCAL_ONLY=1` solo responde a loopback.
- `ORIGO_DEV_OPEN=1` abre la app sin login solo en localhost HTTP. Nunca en un servidor.

## ¿Hace falta el login si ya uso Tailscale o una red privada?

Sí, dejalo. Estar en la red privada no es estar autenticado en Origo:

- **La red deja llegar, no identifica.** Tailscale Serve no autentica ante Origo, y Origo no
  confía en los headers `Tailscale-User-*`. Cualquier dispositivo de la tailnet al que le
  permitas el puerto llega a la app: un celular compartido, una máquina de otra persona que
  agregaste o un nodo comprometido. Un cambio de configuración (Funnel, una ACL amplia, un proxy
  nuevo) la expone más de lo que pensás.
- **El navegador es otro canal.** Un celular robado sin bloqueo, una sesión abierta en una PC
  ajena o una extensión maliciosa llegan a todo lo que ve el dueño. El login, con sesiones que
  vencen y 2FA, acota ese daño.
- **Web y MCP se autentican por separado.** Que el agente tenga acceso por MCP no inicia sesión
  en el navegador, ni al revés. El `MCP_TOKEN` da acceso de dueño: quien lo tenga lee y escribe
  todo. Si el agente corre en la misma máquina, dejá `MCP_LOCAL_ONLY=1`.
- **El host es la frontera real.** Quien tenga acceso al usuario del sistema, a la base SQLite o
  a los backups no necesita login. Corré Origo con un usuario propio, base y backups en `0600`,
  y cifrá los backups que salgan de la máquina.

Lo más simple que sigue protegiendo: login con contraseña larga en un gestor de contraseñas, 2FA
activado y la app instalada en el celular para no tipear seguido. Confiar en la identidad que
manda un proxy solo es razonable si el proxy autentica de verdad y Origo no es alcanzable por
otro camino; hoy Origo no lo soporta.

**Probalo y sabé cómo cortar todo:** desde un dispositivo sin sesión tiene que pedir login;
`/mcp` sin bearer responde 401 (o 404 con `MCP_LOCAL_ONLY=1`); un invitado no ve Plata ni Cuerpo.
Si perdés un dispositivo: `set-password` corta todas las sesiones, rotá `MCP_TOKEN` y reiniciá, y
sacá el dispositivo de la tailnet.

## Qué es responsabilidad de quien la despliega

Origo no es un servicio: cada operador corre su instancia y se ocupa de lo suyo.

- `SECRET_KEY`, `MCP_TOKEN`, la base de datos y los backups son secretos de cada operador.
  Generalos con aleatoriedad fuerte, guardalos con permisos restrictivos y rotalos si se filtran.
- HTTPS, firewall, SSH, actualizaciones del sistema y backups fuera de la máquina.
- Proxys, túneles, Tailscale, Telegram y modelos en la nube son servicios de terceros fuera de
  este repositorio: ven el tráfico o los datos que les mandes.

Un reporte sobre un servicio de terceros o una configuración de un operador no es una
vulnerabilidad de Origo, pero si la documentación induce al error, avisá y la corrijo.
