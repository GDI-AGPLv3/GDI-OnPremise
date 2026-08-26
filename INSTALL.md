# GDI OnPremise — Instalación rápida

Guía corta. Para el paso a paso completo (Auth0, dominios, SSL, certificados de firma) ver la documentación completa de GDI.

## Requisitos

- Linux (Ubuntu 22.04+ recomendado). Windows solo con WSL2 (sin soporte oficial).
- Docker + Docker Compose v2.
- **Tier libre:** 6 GB RAM, 2 vCPU, 40 GB disco.
- **Tier Premium con IA:** 10 GB RAM, 4 vCPU, 80 GB disco.
- Un dominio apuntando al servidor (para HTTPS, que Auth0 requiere).

## 1. Descargar el código (tier libre)

Los 4 repos van en la misma carpeta:

```bash
mkdir /opt/gdi && cd /opt/gdi
git clone https://github.com/GDI-AGPLv3/GDI-OnPremise.git .
git clone https://github.com/GDI-AGPLv3/GDI-Backend.git
git clone https://github.com/GDI-AGPLv3/GDI-Frontend.git
git clone https://github.com/GDI-AGPLv3/GDI-BD.git
```

> Los microservicios (pdfcomposer, notary) vienen **dentro de GDI-Backend** (`microservices/`), no se clonan aparte.

## 2. Configurar

```bash
cp .env.example .env
./scripts/generar-claves.sh        # genera las 4 claves internas
nano .env                          # completá BD, Auth0 y almacenamiento
```

Mínimo a completar en `.env`:
- `DB_PASSWORD` — una contraseña segura.
- `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `AUTH0_FRONTEND_CLIENT_ID/SECRET` — ver guía completa, sección Auth0.
- Almacenamiento: R2 (`CF_R2_*`) **o** MinIO local (descomentar el bloque MinIO).
- `FRONTEND_URL`, `NEXT_PUBLIC_API_URL` — tus dominios.

## 3. Levantar

```bash
# Tier libre con MinIO local (recomendado para empezar):
docker compose -f docker-compose.yml -f docker-compose.minio.yml up -d --build

# Tier libre con Cloudflare R2:
docker compose up -d --build
```

## 4. Configurar dominio + SSL

1. Entrá a `http://TU-SERVIDOR:81` (panel de nginx-proxy-manager).
2. Login inicial: `admin@example.com` / `changeme` → **cambialo en el primer ingreso**.
3. Creá un Proxy Host para tu dominio del frontend → apunta a `frontend:3000`.
4. Creá otro para la API → apunta a `backend:8080`.
5. En cada uno: pestaña SSL → "Request a new SSL Certificate" (Let's Encrypt, automático).

## 5. Crear el primer municipio

Desde el BackOffice (tier Premium) o por el endpoint de onboarding. Ver guía completa.

## Tier Premium (módulos pagos)

Si tenés licencia, GDI te entrega un token de `ghcr.io` y el archivo `.lic`:

```bash
# Autenticarse al registro de imágenes (una vez)
echo "TU_TOKEN" | docker login ghcr.io -u TU_USUARIO --password-stdin

# Colocar la licencia
mkdir -p license && cp /ruta/a/tu-licencia.lic license/

# Levantar con los módulos pagos
docker compose -f docker-compose.yml -f docker-compose.premium.yml up -d
```

## Actualizar

> 🛑 **Nunca actualices sin backup.** La actualización aplica migraciones a la base y **eso no
> se revierte**: volver a la versión anterior de las imágenes deja el schema migrado contra
> código viejo. Ver *Backups* en [`docs/MANUAL.md`](docs/MANUAL.md#12-backups).

GDI Latam avisa por mail cuando sale una versión nueva. **No hay actualización automática:**
la corrés vos, en la ventana que elijas.

```bash
nano .env    # IMAGE_VERSION=<la versión nueva>
docker compose -f docker-compose.yml -f docker-compose.premium.yml pull
docker compose -f docker-compose.yml -f docker-compose.premium.yml up -d
```

El paso a paso completo (verificación, rollback, qué hacer si el `pull` da `denied`) está en
[`docs/MANUAL.md`](docs/MANUAL.md#11-actualizar-gdi).
