# GDI OnPremise — Manual de instalación (tier Premium)

Guía paso a paso para instalar GDI en el servidor de tu municipio. Pensada para el **técnico del municipio** que recibió la licencia de GDI Latam.

> **¿Tenés un asistente de IA?** Hay una versión de este manual optimizada para pegarle a un LLM y que te guíe o ejecute los pasos: [`MANUAL-LLM.md`](MANUAL-LLM.md).

---

## ⚠️ Estado de implementación

Este manual describe el flujo Premium completo. Algunas automatizaciones están **en construcción** y se marcan con 🚧 a lo largo del documento:
- 🚧 Verificación automática de licencia `.lic`
- 🚧 Wizard visual "crear instancia" en el BackOffice
- 🚧 Runner de migraciones de BD al arranque

Donde veas 🚧, el paso final puede requerir asistencia de GDI Latam por ahora.

---

## 0. Qué te entrega GDI Latam

Al contratar el plan Premium, GDI te manda por mail:
1. **Un token de acceso a `ghcr.io`** — la llave para descargar las imágenes de los módulos pagos (BackOffice, AgenteLANG).
2. **Tu archivo de licencia `.lic`** — desbloquea los módulos pagos y define cuántas instancias podés correr.

Guardá los dos en un lugar seguro. Los vas a usar en los pasos 6 y 7.

---

## 1. Requisitos del servidor

| Recurso | Mínimo (Premium con IA) |
|---------|-------------------------|
| Sistema | Linux (Ubuntu 22.04+). Windows solo con WSL2, sin soporte oficial |
| RAM | 10 GB |
| CPU | 4 vCPU |
| Disco | 80 GB |
| Red | Un **dominio** apuntando al servidor (HTTPS es obligatorio — Auth0 lo exige) |

Vas a necesitar 4 subdominios apuntando a la IP del servidor (registros DNS tipo A):
- `gdi.tu-municipio.gob.ar` — portal de usuarios (frontend)
- `api.tu-municipio.gob.ar` — API del backend
- `admin.tu-municipio.gob.ar` — BackOffice (administración)
- `admin-api.tu-municipio.gob.ar` — API del BackOffice

---

## 2. Instalar Docker

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Cerrá sesión y volvé a entrar para que tome el grupo docker.
docker --version && docker compose version
```

---

## 3. Descargar el código

Los repos van todos en la misma carpeta:

```bash
sudo mkdir -p /opt/gdi && sudo chown $USER /opt/gdi && cd /opt/gdi

git clone https://github.com/GDI-APGLv3/GDI-OnPremise.git .
git clone https://github.com/GDI-APGLv3/GDI-Backend.git
git clone https://github.com/GDI-APGLv3/GDI-Frontend.git
git clone https://github.com/GDI-APGLv3/GDI-BD.git
```

> Los microservicios (pdfcomposer, notary) vienen **dentro de GDI-Backend** (`microservices/`). No se clonan aparte.
> El BackOffice y AgenteLANG NO se clonan: vienen como imágenes pre-armadas desde `ghcr.io` (paso 7).

---

## 4. Configurar Auth0 (autenticación)

GDI usa Auth0 para el login. Es gratis hasta 25.000 usuarios activos.

### 4.1. Crear la cuenta y el tenant
1. Entrá a [auth0.com](https://auth0.com) y creá una cuenta.
2. Anotá tu **dominio Auth0**: algo como `tu-municipio.us.auth0.com`.

### 4.2. Crear la API
1. En el menú izquierdo: **Applications → APIs → Create API**.
2. **Name:** GDI API (lo que quieras).
3. **Identifier:** un URI que **vos inventás**, por ejemplo `https://gdi-api`.
   - ⚠️ **No es una URL real**, es solo un identificador. Anotalo exacto: lo vas a poner en `.env` como `AUTH0_AUDIENCE`.
4. Dejá el resto por default y creá.

### 4.3. Crear 2 aplicaciones
Necesitás dos **Regular Web Applications** (una para el portal, otra para el BackOffice):

**App 1 — Frontend (portal de usuarios):**
- Applications → Create Application → Regular Web Application.
- En **Settings**, configurá:
  - **Allowed Callback URLs:** `https://gdi.tu-municipio.gob.ar/auth/callback`
  - **Allowed Logout URLs:** `https://gdi.tu-municipio.gob.ar`
  - **Allowed Web Origins:** `https://gdi.tu-municipio.gob.ar`
- Anotá el **Client ID** y **Client Secret** → van a `AUTH0_FRONTEND_CLIENT_ID/SECRET`.

**App 2 — BackOffice (administración):**
- Otra Regular Web Application.
- **Allowed Callback URLs:** `https://admin.tu-municipio.gob.ar/auth/callback`
- **Allowed Logout URLs:** `https://admin.tu-municipio.gob.ar`
- **Allowed Web Origins:** `https://admin.tu-municipio.gob.ar`
- Anotá su **Client ID** y **Client Secret** → van a `AUTH0_BACKOFFICE_CLIENT_ID/SECRET`.

---

## 5. Configurar el `.env`

```bash
cd /opt/gdi
cp .env.example .env
./scripts/generar-claves.sh    # genera las 4 claves internas automáticamente
nano .env
```

Completá estos valores (el resto podés dejarlos por default):

```env
# Base de datos
DB_PASSWORD=una-password-larga-y-segura

# Auth0 (del paso 4)
AUTH0_DOMAIN=tu-municipio.us.auth0.com
AUTH0_AUDIENCE=https://gdi-api
AUTH0_FRONTEND_CLIENT_ID=...
AUTH0_FRONTEND_CLIENT_SECRET=...
AUTH0_BACKOFFICE_CLIENT_ID=...
AUTH0_BACKOFFICE_CLIENT_SECRET=...

# Dominios
FRONTEND_URL=https://gdi.tu-municipio.gob.ar
NEXT_PUBLIC_API_URL=https://api.tu-municipio.gob.ar
BACKOFFICE_URL=https://admin.tu-municipio.gob.ar
BACKOFFICE_API_URL=https://admin-api.tu-municipio.gob.ar

# Almacenamiento: MinIO local (recomendado para empezar)
CF_R2_ENDPOINT=http://minio:9000
CF_R2_ACCESS_KEY_ID=minioadmin
CF_R2_SECRET_ACCESS_KEY=una-password-minio-segura
CF_R2_BUCKET_OFICIAL=gdi-oficial
CF_R2_BUCKET_TOSIGN=gdi-tosign
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=una-password-minio-segura
S3_FORCE_PATH_STYLE=true

# IA (AgenteLANG)
OPENROUTER_API_KEY=sk-or-...     # crear cuenta en openrouter.ai

# Licencia
GDI_LICENSE_HOST_DIR=./license
```

> 💡 **Email:** es opcional. Si querés que el sistema mande mails, completá `RESEND_API_KEY` (de resend.com) **o** el bloque `SMTP_*`. Si dejás todo vacío, el sistema funciona igual, sin mandar correos.

---

## 6. Colocar la licencia

```bash
mkdir -p /opt/gdi/license
cp /ruta/donde/guardaste/tu-licencia.lic /opt/gdi/license/
```

🚧 La verificación automática de la licencia está en construcción. Por ahora, si tenés dudas, GDI valida tu licencia al activar.

---

## 7. Iniciar GDI

Primero autenticate al registro de imágenes con el token que te dio GDI:

```bash
echo "TU_TOKEN_GHCR" | docker login ghcr.io -u TU_USUARIO_GITHUB --password-stdin
```

Y levantá todo (premium + MinIO local):

```bash
cd /opt/gdi
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml up -d --build
```

La primera vez tarda varios minutos (compila el backend y el frontend, baja las imágenes). Mirá el progreso con:

```bash
docker compose ps
docker compose logs -f backend
```

---

## 8. Configurar dominios y certificados SSL

El reverse proxy (nginx-proxy-manager) tiene una interfaz web. **No hace falta tocar archivos ni comandos certbot.**

1. Entrá a `http://IP-DE-TU-SERVIDOR:81`.
2. Login inicial: `admin@example.com` / `changeme`.
   - ⚠️ **Cambiá el email y la password apenas entres.** Ese panel queda expuesto.
3. Para cada uno de los 4 dominios, creá un **Proxy Host** (pestaña Hosts → Proxy Hosts → Add Proxy Host):

| Domain Name | Forward Hostname | Forward Port |
|-------------|------------------|--------------|
| gdi.tu-municipio.gob.ar | `frontend` | 3000 |
| api.tu-municipio.gob.ar | `backend` | 8080 |
| admin.tu-municipio.gob.ar | `backoffice-front` | 3000 |
| admin-api.tu-municipio.gob.ar | `backoffice-back` | 8080 |

4. En cada Proxy Host, pestaña **SSL** → "Request a new SSL Certificate" → tildá "Force SSL" y "HTTP/2 Support" → Save. (Let's Encrypt emite el certificado solo.)

---

## 9. Crear tu primer municipio (instancia)

🚧 El wizard visual "crear instancia" está en construcción. El flujo previsto:

1. Entrá a `https://admin.tu-municipio.gob.ar` (BackOffice) y logueate con Auth0.
2. Como el sistema arranca **sin ninguna instancia**, el BackOffice te muestra el asistente "Crear instancia" en lugar del dashboard.
3. Completás los datos de tu municipio (nombre, color, etc.). El sistema crea el schema, los buckets de almacenamiento y el usuario administrador.

Mientras el wizard se termina, GDI Latam te asiste para crear la primera instancia.

---

## 10. Empezar a usar

- **Portal de usuarios:** `https://gdi.tu-municipio.gob.ar` — donde trabajan los empleados (expedientes, documentos, firmas).
- **BackOffice:** `https://admin.tu-municipio.gob.ar` — donde el administrador gestiona usuarios, sellos, tipos de documento y reparticiones.

Desde el BackOffice → Usuarios, cargás a la gente de tu municipio.

---

## 11. Actualizar GDI

Cuando GDI publica una versión nueva:

```bash
cd /opt/gdi
# Código abierto (backend, frontend, BD)
git -C GDI-Backend pull && git -C GDI-Frontend pull && git -C GDI-BD pull
# Imágenes pagas: subí IMAGE_VERSION en el .env y bajá las nuevas
nano .env   # IMAGE_VERSION=1.1.0
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml pull
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml up -d --build
```

🚧 Las migraciones de base de datos se aplicarán solas al reiniciar el backend (runner en construcción). Por ahora, GDI te avisa si una actualización requiere correr migraciones a mano.

---

## 12. Backups

Los datos viven en volúmenes Docker:
- `gdi_postgres_data` — la base de datos (lo más importante).
- `gdi_minio_data` — los documentos (si usás MinIO).

Backup manual de la base:

```bash
docker compose exec -T postgres pg_dump -U postgres railway -Fc > /opt/gdi/backups/gdi-$(date +%F).dump
```

> ⚠️ Sos responsable de copiar estos backups a un lugar **fuera del servidor** (otro disco, nube, etc.).

---

## 13. Problemas comunes

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| El login da error de "callback mismatch" | La Callback URL en Auth0 no coincide con tu dominio | Revisá el paso 4.3 (debe ser `https://tu-dominio/auth/callback`) |
| El frontend carga pero la API da error de CORS | `FRONTEND_URL` mal seteado en `.env` | Debe ser exactamente tu dominio del portal, con `https://` |
| "NoSuchBucket" al subir un documento | Los buckets de MinIO no existen o `S3_FORCE_PATH_STYLE` no está en `true` | Verificá el bloque MinIO del `.env` |
| Un contenedor reinicia en loop | Falta una variable en `.env` | `docker compose logs <servicio>` para ver cuál |
| No baja una imagen paga | Token de ghcr.io vencido o mal | Volvé a hacer `docker login ghcr.io` (paso 7) |

Para ver el estado de todo: `docker compose ps` y `docker compose logs -f <servicio>`.

---

¿Trabado en algo? Escribinos a soporte de GDI Latam con la salida de `docker compose logs`.
