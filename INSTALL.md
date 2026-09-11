# GDI OnPremise — Instalación rápida

Guía corta. El paso a paso completo (Auth0, dominios, SSL, correo, backups) está en
[`docs/MANUAL.md`](docs/MANUAL.md).

> **Requiere licencia.** GDI Latam te entrega dos cosas: un **token** para bajar las imágenes
> de `ghcr.io` y un archivo de **licencia `.lic`**. Sin el token no baja nada; sin la licencia
> no se puede crear el municipio.

## Requisitos

- Linux (Ubuntu 22.04+ recomendado). Windows solo con WSL2 (sin soporte oficial).
- Docker + Docker Compose v2.
- 4 GB RAM (medido: 2 GB en uso con todo arriba), 4 vCPU, 80 GB de disco.
- 5 subdominios apuntando al servidor (`gdi.`, `api.`, `admin.`, `admin-api.`, `mcp.`).
  HTTPS es obligatorio: Auth0 lo exige.

## 1. Descargar el instalador

En tu servidor **no se compila nada ni se clona el código de la aplicación**: los 10 servicios
bajan como imágenes. Lo único que se descarga es este repo (compose + manual), en la versión
que te indicó GDI:

```bash
sudo mkdir -p /opt/gdi && sudo chown $USER /opt/gdi && cd /opt/gdi
VERSION=2026.09.0   # la versión que te indicó GDI (la misma para los 10 servicios)
git clone --branch "v$VERSION" https://github.com/GDI-AGPLv3/GDI-OnPremise.git .
```

## 2. Configurar

```bash
cp .env.example .env
./scripts/generar-claves.sh        # genera las claves internas
nano .env                          # IMAGE_VERSION, BD, Auth0, dominios y almacenamiento
mkdir -p license && cp /ruta/a/tu-licencia.lic license/
echo "TU_TOKEN" | docker login ghcr.io -u TU_USUARIO --password-stdin
```

Mínimo a completar en `.env`:
- `IMAGE_VERSION` — la misma versión del paso 1 (formato `AAAA.MM.N`).
- `DB_PASSWORD` — una contraseña segura.
- Auth0 — dominio, audience, las dos apps de login y la Machine to Machine (manual, paso 4).
- Los dominios de tu instalación (están todos juntos en el `.env.example`).
- Almacenamiento — MinIO local (recomendado) o Cloudflare R2.

## 3. Levantar

```bash
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml up -d
```

La primera vez baja las imágenes de los 10 servicios. Con Cloudflare R2 en lugar de MinIO,
sacá el `-f docker-compose.minio.yml`.

## 4. Dominios + SSL

El panel de nginx-proxy-manager escucha solo en `localhost`: entrá por túnel SSH
(`ssh -L 8181:localhost:81 usuario@servidor` y abrí `http://localhost:8181`). La primera vez
**creás vos** el usuario administrador; hacelo enseguida.

| Dominio | Apunta a |
|---|---|
| `gdi.` | `frontend:3000` |
| `api.` | `backend:8080` (más la ubicación `/avatars`: manual, paso 8) |
| `admin.` | `backoffice-front:3000` |
| `admin-api.` | `backoffice-back:8080` |
| `mcp.` | `gateway:8080` |

En cada uno: pestaña SSL → "Request a new SSL Certificate" (Let's Encrypt, automático).

## 5. Crear el primer municipio

Entrá a `https://admin.<tu-dominio>`: con el sistema vacío, el BackOffice te muestra el
asistente "Crear instancia". Manual, paso 9.

## Actualizar

> 🛑 **Nunca actualices sin backup.** La actualización aplica migraciones a la base y **eso no
> se revierte**: volver a la versión anterior de las imágenes deja el schema migrado contra
> código viejo. Ver *Backups* en [`docs/MANUAL.md`](docs/MANUAL.md#12-backups).

GDI Latam avisa por mail cuando sale una versión nueva. **No hay actualización automática:**
la corrés vos, en la ventana que elijas.

```bash
VERSION=2026.09.1                                   # la versión nueva
nano .env                                           # IMAGE_VERSION=2026.09.1 (el mismo número)
git fetch --tags origin && git checkout "v$VERSION" # el instalador de esa versión
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml pull
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml up -d
```

Las migraciones las aplica solo el servicio `migrator`, antes de que arranque el backend.
El paso a paso completo (verificación, rollback, qué hacer si el `pull` da `denied`) está en
[`docs/MANUAL.md`](docs/MANUAL.md#11-actualizar-gdi).
