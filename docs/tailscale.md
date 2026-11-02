# Origo con Tailscale

Tailscale es **una opción**, no una dependencia: Origo funciona igual con tu propio proxy HTTPS
o con Cloudflare Tunnel ([despliegue](despliegue.md)). Sirve cuando querés Origo accesible
solo desde tus dispositivos, con HTTPS y sin abrir puertos.

```
celular/PC (con Tailscale) ──WireGuard──▶ tailscale serve ──▶ 127.0.0.1:8000 (Origo)
```

Dos cosas para saber antes de elegirla: el cliente de Tailscale es de código abierto, pero el
servidor de coordinación es un servicio de terceros (Headscale es una alternativa libre del
servidor de control; esta guía no la probó). Y los certificados HTTPS de `.ts.net` se emiten
con Let's Encrypt, así que el nombre de tu máquina y de tu tailnet queda en los registros
públicos de transparencia de certificados.

## Requisitos

- Usuario, directorios y entorno de Origo preparados según [despliegue, sección 3](despliegue.md).
  Elegí el origen de Tailscale **antes** de generar `/etc/origo/origo.env`. Si ya existe,
  editá solo `BASE_URL` y el alcance MCP: no regeneres ni rotes secretos por accidente.
- Tailscale instalado y la máquina dentro de tu tailnet.
- En la consola de admin de Tailscale: MagicDNS y **HTTPS Certificates** activados.

## 1. Revisar qué publica ya Serve

Si esa máquina ya sirve otra cosa por Tailscale, no la pises:

```bash
tailscale serve status
```

- Sin nada en el 443: usá el 443 (más abajo).
- Con el 443 ocupado: usá otro puerto, por ejemplo `--https=8443`, y ponelo en `BASE_URL`
  (`https://nodo.tailnet.ts.net:8443`).

## 2. Configurar Origo

`BASE_URL` es el nombre **exacto** del nodo en tu tailnet (`nodo.tailnet.ts.net`): sale de la
consola de admin o de la URL que imprime `tailscale serve status`. Generá el archivo de
entorno nuevo (falla si ya existe; no muestra los secretos):

```bash
cd /opt/origo
sudo python3 deploy/configure.py --base-url https://nodo.tailnet.ts.net \
  --owner-name TuNombre --mode systemd --mcp-scope local --output /etc/origo/origo.env
sudo chown origo:origo /etc/origo/origo.env
```

Usá `--mcp-scope remote` si Hermes corre en otra máquina (ver más abajo). Después seguí la
sección 3 de [despliegue.md](despliegue.md): dueño del archivo, usuario, servicio.

## 3. Publicar con Serve (no con Funnel)

```bash
sudo tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve status
```

**No uses `tailscale funnel`**: Funnel publica el servicio en internet abierto. Revisá que
`serve status` no diga "Funnel on". Para sacar la publicación:
`sudo tailscale serve --https=443 off` (con el mismo puerto que usaste).

Origo sigue pidiendo su login: **no confía en los headers `Tailscale-User-*`** para
autenticar a nadie. Estar en la tailnet te deja llegar a la pantalla de login, no te hace dueño.

## Invitados

Un invitado con link mágico también necesita llegar a la URL `.ts.net`: tiene que estar en tu
tailnet o tener el nodo compartido con él (*Share*), con Tailscale activo en su celular. Si
no querés eso, publicá Origo por una ruta pública (proxy HTTPS o Cloudflare) en vez de por
Tailscale. Los invitados siguen limitados a Súper y Deudas.

## Hermes y MCP

| Hermes corre... | En Origo | URL en Hermes |
|---|---|---|
| En la misma máquina | `MCP_LOCAL_ONLY=1` + `MCP_TOKEN` | `http://127.0.0.1:8000/mcp` (no pasa por Serve) |
| En otra PC de la tailnet | `MCP_LOCAL_ONLY=0` + `MCP_TOKEN` dedicado | `https://nodo.tailnet.ts.net/mcp` |

Con `MCP_LOCAL_ONLY=1`, lo que llega por Serve recibe 404 en `/mcp`: es lo esperado.
Con `MCP_LOCAL_ONLY=0` el bearer es la **única** barrera de `/mcp`, así que:

- Restringí en la política de acceso de Tailscale qué identidades/dispositivos pueden
  alcanzar el puerto HTTPS de Origo (443 o el que elegiste). Permití solo tus clientes y
  la máquina de Hermes. Revisá también las reglas amplias existentes: sumar una regla
  restrictiva no cancela permisos más amplios. No pegues una política nueva encima de la
  actual; seguí la [guía oficial de control de acceso](https://tailscale.com/docs/features/access-control).
- El `MCP_TOKEN` es de dueño: nunca se lo des a un invitado. Cómo cargarlo en Hermes sin
  mostrarlo: [agentes.md](agentes.md).

## Qué no se probó

Esta guía sigue la documentación de Tailscale y el código de Origo; no hay tests de
integración con una tailnet real en el repo. Probá el login, un invitado y `/mcp` (con y sin
bearer) desde un dispositivo autorizado y desde uno que no lo esté.

## Referencias

- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).
- [CLI, persistencia y desactivación](https://tailscale.com/docs/reference/tailscale-cli/serve).
