# Seguridad

## Reportar una vulnerabilidad

No abras un issue público con los detalles. Usá el reporte privado de GitHub del repositorio
(pestaña **Security** → *Report a vulnerability*) si está habilitado. Si no ves esa opción, abrí un
issue que diga solo que querés reportar algo de seguridad, sin datos técnicos, y coordinamos un canal
privado. Incluí versión o commit, pasos para reproducir y el impacto. Nunca mandes secretos ni
datos reales.

Es un proyecto personal sin equipo ni SLA: respondo cuando puedo y no ofrezco recompensas.
Solo se corrige la rama `main`.

## Qué cubre

El diseño y los controles están en [docs/seguridad.md](docs/seguridad.md): un dueño por
instancia, contraseñas Argon2id, 2FA opcional, sesiones en el servidor, CSRF por origen, links
de invitado limitados a Súper y Deudas. Importa especialmente: saltear la autenticación, que
un invitado vea o toque datos que no son suyos, fugas de secretos en logs y `/mcp` accesible sin
el bearer.

## Qué es responsabilidad de quien la despliega

Origo no es un servicio: cada operador corre su instancia y se ocupa de lo suyo.

- `SECRET_KEY`, `MCP_TOKEN`, la base de datos y los backups son secretos de cada operador.
  Generalos con aleatoriedad fuerte, guardalos con permisos restrictivos y rotalos si se filtran.
  Los valores y dominios de la documentación son solo ejemplos.
- HTTPS, firewall, SSH, actualizaciones del sistema y backups fuera de la máquina.
- Proxys, túneles, Tailscale, Telegram y modelos en la nube son servicios de terceros fuera de
  este repositorio: ven el tráfico o los datos que les mandes.
- El `MCP_TOKEN` da acceso completo de dueño. No se comparte con invitados.

Un reporte sobre un servicio de terceros o una configuración de un operador no es una
vulnerabilidad de Origo, pero si la documentación induce al error, avisá y la corrijo.
