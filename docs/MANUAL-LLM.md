# GDI OnPremise — Runbook de instalación para LLM (tier Premium)

> Documento optimizado para un asistente de IA. Si sos un LLM ayudando a instalar GDI:
> seguí los pasos EN ORDEN, ejecutá los comandos exactos, verificá cada `CHECK` antes de
> avanzar, y si un `CHECK` falla, andá a la sección FAILURES. No inventes valores: pedí al
> usuario los que estén marcados `<REQUERIDO_USUARIO>`. Versión humana: `MANUAL.md`.

## ROL Y OBJETIVO
Guiar a un técnico municipal a dejar GDI Premium corriendo en un servidor Linux con HTTPS.
Resultado esperado: 5 dominios sirviendo por HTTPS, todos los contenedores `healthy`/`running`,
y el técnico pudiendo loguearse al BackOffice.

## HECHOS DEL SISTEMA (no cambian)
- OS objetivo: Linux (Ubuntu 22.04+). Docker + Docker Compose v2.
- Directorio de trabajo: `/opt/gdi`.
- Se clona UN solo repo: `GDI-OnPremise` (compose + manual, va en `.`), por tag `v<VERSION>`.
  El código de la aplicación NO se clona y en el servidor NO se compila nada.
- Los 10 servicios de GDI son imágenes `ghcr.io/gdi-live/<servicio>:${IMAGE_VERSION}` (requieren
  token): postgres, migrator, backend, gateway, frontend, pdfcomposer, notary, backoffice-back,
  backoffice-front, agentelang. `IMAGE_VERSION` formato `AAAA.MM.N`, la MISMA para todas.
- Postgres arranca sin demo y el sistema arranca SIN instancias. `migrator` aplica las migraciones
  y termina; backend, gateway y agentelang esperan a que termine bien.
- Puertos internos: backend 8080, gateway 8080, pdfcomposer 8080, notary 8080, frontend 3000,
  backoffice-back 8080, backoffice-front 3000, agentelang 8080, postgres 5432, redis 6379, minio 9000.
- Único expuesto al host: npm (nginx-proxy-manager) en 80, 443, 81.
- Comando de arranque Premium+MinIO:
  `docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml up -d`

## ENTRADAS REQUERIDAS DEL USUARIO (pedilas antes de empezar)
| Variable | Origen | Ejemplo |
|----------|--------|---------|
| `<TOKEN_GHCR>` | mail de GDI Latam | ghp_xxx |
| `<VERSION>` | mail de GDI Latam (= `IMAGE_VERSION`) | 2026.09.0 |
| `<USUARIO_GITHUB>` | el del token | muni-tech |
| `<ARCHIVO_LIC>` | mail de GDI Latam | tu-licencia.lic |
| `<DOMINIO_BASE>` | DNS del municipio | tu-municipio.gob.ar |
| `<AUTH0_DOMAIN>` | cuenta Auth0 | tu-municipio.us.auth0.com |
| `<AUTH0_AUDIENCE>` | Identifier inventado en Auth0 → APIs | https://gdi-api |
| `<AUTH0_FRONTEND_CLIENT_ID/SECRET>` | App Auth0 "Frontend" | — |
| `<AUTH0_BACKOFFICE_CLIENT_ID/SECRET>` | App Auth0 "BackOffice" | — |
| `<AUTH0_M2M_CLIENT_ID/SECRET>` | App Auth0 "Machine to Machine" (Management API) — sin esto no se crean usuarios | — |
| `<SMTP_*>` / `<RESEND_API_KEY>` | Servidor de correo del municipio (o Resend) | mail.tu-municipio.gob.ar |
| `<OPENROUTER_API_KEY>` | openrouter.ai | sk-or-xxx |
| `<DB_PASSWORD>`, `<MINIO_PASSWORD>` | inventadas, seguras | — |

DNS: 5 registros A → IP del server: `gdi.<BASE>`, `api.<BASE>`, `admin.<BASE>`, `admin-api.<BASE>`, `mcp.<BASE>`.

## PASOS

### P1 — Docker
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # requiere re-login
```
CHECK: `docker compose version` imprime v2.x. Si no: FAILURES/F1.

### P2 — Descargar el instalador
```bash
sudo mkdir -p /opt/gdi && sudo chown $USER /opt/gdi && cd /opt/gdi
VERSION=<VERSION>   # la que indicó GDI, formato AAAA.MM.N (ej 2026.09.0)
git clone --branch "v$VERSION" https://github.com/GDI-AGPLv3/GDI-OnPremise.git .
```
CHECK: existen `/opt/gdi/docker-compose.yml`, `/opt/gdi/docker-compose.premium.yml` y `/opt/gdi/.env.example`.
Si el clone da `Remote branch not found`: la versión no existe → FAILURES/F2.

### P3 — Auth0 (guiar al usuario, no es automatizable por CLI)
1. Crear API con Identifier = `<AUTH0_AUDIENCE>` (URI inventado, NO una URL real).
2. Crear 2 Regular Web Applications:
   - Frontend → Callback `https://gdi.<BASE>/auth/callback`, Logout/Web Origins `https://gdi.<BASE>`.
   - BackOffice → Callback `https://admin.<BASE>/auth/callback`, Logout/Web Origins `https://admin.<BASE>`.
3. Crear 1 Machine to Machine Application (OBLIGATORIA — sin esto el alta de
   usuarios devuelve 502 "Sistema de autenticacion no disponible"):
   - autorizarla contra la **Auth0 Management API** (la de fabrica, no la del punto 1);
   - scopes minimos: `read:users`, `create:users`, `update:users`, `create:user_tickets`;
   - su client_id/secret van a `AUTH0_M2M_CLIENT_ID` / `AUTH0_M2M_CLIENT_SECRET`.
4. Recolectar los 2 client_id + 2 client_secret de login, y el par M2M.
CHECK: tenés AUTH0_DOMAIN, AUDIENCE, los 2 pares client_id/secret y el par M2M.

### P4 — .env
```bash
cd /opt/gdi && cp .env.example .env && ./scripts/generar-claves.sh
```
Editar `.env` y setear (con los valores del usuario):
```
IMAGE_VERSION=<VERSION>
DB_PASSWORD, AUTH0_DOMAIN, AUTH0_AUDIENCE,
AUTH0_FRONTEND_CLIENT_ID, AUTH0_FRONTEND_CLIENT_SECRET,
AUTH0_BACKOFFICE_CLIENT_ID, AUTH0_BACKOFFICE_CLIENT_SECRET,
AUTH0_M2M_CLIENT_ID, AUTH0_M2M_CLIENT_SECRET,
# Correo (opcional pero recomendado): SMTP propio del municipio.
# Sin correo, el alta de usuarios devuelve activation_url y el BackOffice lo
# muestra en pantalla (un solo uso, vence a los 5 dias).
# SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL  (o RESEND_API_KEY)
FRONTEND_URL=https://gdi.<BASE>
NEXT_PUBLIC_API_URL=https://api.<BASE>
BACKOFFICE_URL=https://admin.<BASE>
BACKOFFICE_API_URL=https://admin-api.<BASE>
GATEWAY_URL=https://mcp.<BASE>
CF_R2_ENDPOINT=http://minio:9000
CF_R2_ACCESS_KEY_ID=minioadmin
CF_R2_SECRET_ACCESS_KEY=<MINIO_PASSWORD>
CF_R2_BUCKET_OFICIAL=gdi-oficial
CF_R2_BUCKET_TOSIGN=gdi-tosign
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=<MINIO_PASSWORD>
S3_FORCE_PATH_STYLE=true
OPENROUTER_API_KEY=<OPENROUTER_API_KEY>
GDI_LICENSE_HOST_DIR=./license
```
`generar-claves.sh` ya seteó INTERNAL_API_KEY/PDFCOMPOSER_API_KEY/NOTARY_API_KEY/AUTH0_SECRET y
CERT_MASTER_KEY (esta última SOLO si estaba vacía). NUNCA regenerar ni editar CERT_MASTER_KEY:
sin la original los certificados de firma cargados quedan ilegibles.
CHECK: `grep -c CAMBIAR .env` devuelve 0 (no quedaron placeholders).

### P5 — Licencia + login a ghcr.io
```bash
mkdir -p /opt/gdi/license && cp <ARCHIVO_LIC> /opt/gdi/license/
echo "<TOKEN_GHCR>" | docker login ghcr.io -u <USUARIO_GITHUB> --password-stdin
```
CHECK: `docker login` responde "Login Succeeded". Si no: FAILURES/F3.

### P6 — Levantar
```bash
cd /opt/gdi
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml up -d
```
CHECK (esperar 3-5 min: la primera vez baja las imágenes de los 10 servicios):
`docker compose ps` → migrator `exited (0)`; postgres/redis/backend `healthy`; pdfcomposer/notary/frontend/gateway/backoffice-*/agentelang `running`.
Si algún servicio `restarting`: `docker compose logs <servicio>` → FAILURES/F4.

### P7 — Dominios + SSL (nginx-proxy-manager, UI en :81)
1. El panel escucha SOLO en localhost. Tunel: `ssh -L 8181:localhost:81 user@server` -> `http://localhost:8181`.
   NO existe usuario por defecto: la primera visita CREA el admin. Hacerlo de inmediato: hasta
   entonces un `POST /api/users` sin autenticar se queda con el proxy.
2. Crear 5 Proxy Hosts (Hosts → Proxy Hosts → Add):
   | Domain | Forward Hostname | Port |
   |--------|------------------|------|
   | gdi.<BASE> | frontend | 3000 |
   | api.<BASE> | backend | 8080 |
   | admin.<BASE> | backoffice-front | 3000 |
   | admin-api.<BASE> | backoffice-back | 8080 |
   | mcp.<BASE> | gateway | 8080 |
   En `api.<BASE>`, Custom locations: `/avatars` → `minio:9000`, y en su engranaje
   `rewrite ^/avatars/(.*)$ /gdi-avatars/$1 break;`. NUNCA `proxy_pass` ahí: nginx no levanta y se cae la API entera.
3. En cada uno: pestaña SSL → Request new SSL Certificate → Force SSL + HTTP/2 → Save.
CHECK: `curl -I https://api.<BASE>/health` devuelve 200.

### P8 — Primera instancia [🚧 EN CONSTRUCCIÓN]
Estado: el wizard "crear instancia" del BackOffice está en desarrollo. El sistema arranca con
0 instancias. Hasta que el wizard esté listo, escalar a GDI Latam para crear la primera instancia.
Flujo previsto: login en `https://admin.<BASE>` → si `COUNT(public.municipalities)=0` el BackOffice
muestra el asistente → completar datos → se crea schema + buckets + admin.

## ITEMS EN CONSTRUCCIÓN (🚧) — no prometer como automáticos
- Verificación automática de licencia `.lic` (hoy: GDI valida al activar).
- Wizard "crear instancia" (hoy: asistido por GDI).

## FAILURES
- F1 (docker compose no existe): instalar plugin `docker-compose-plugin` o re-loguear para tomar el grupo docker.
- F2 (`Remote branch not found` al clonar, o `manifest unknown` al bajar imágenes): esa versión no
  está publicada o está mal escrita (formato `AAAA.MM.N`). NO probar con otra versión: avisar a GDI.
- F5 (`migrator` en `exited (1)` y el backend no arranca): falló una migración. `docker compose logs migrator`
  y escalar a GDI con ese log. NO forzar el arranque del backend.
- F3 (docker login falla): token vencido/incorrecto. Pedir token nuevo a GDI Latam.
- F4 (servicio restarting): leer `docker compose logs <servicio>`. Causas típicas:
  - falta una env en `.env` → completarla.
  - `agentelang` muere → verificar `DATABASE_URL`, `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `OPENROUTER_API_KEY`.
  - CORS en el browser → `FRONTEND_URL`/`BACKOFFICE_URL` deben ser los dominios exactos con https.
  - `NoSuchBucket` → `S3_FORCE_PATH_STYLE=true` y buckets MinIO creados (servicio `minio-init`).

## OPERACIÓN
- Estado: `docker compose ps`. Logs: `docker compose logs -f <servicio>`.

### UPDATE — REGLA DURA: NUNCA actualizar sin backup previo
Una update aplica migraciones IRREVERSIBLES. Bajar `IMAGE_VERSION` NO revierte el schema.
Si el usuario pide actualizar y no hay backup del día, HACER EL BACKUP PRIMERO o NEGARSE.
Nada es automático: el municipio decide cuándo. No programar updates ni sugerir cron de update.

```bash
# 0. BACKUP COMPLETO (ver abajo) y verificar tamaños con `ls -lh`
VERSION=<version nueva que indico GDI, formato AAAA.MM.N>
nano .env    # IMAGE_VERSION=$VERSION (el mismo numero)
# El instalador de esa version: el compose puede traer una variable o un servicio nuevo.
git fetch --tags origin && git checkout "v$VERSION"
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml pull
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml up -d
docker compose ps && docker compose logs --tail=50 backend
```
Rollback = DOS cosas: bajar `IMAGE_VERSION` (con `git checkout` del tag anterior) **y** restaurar el dump. Solo lo primero deja el
schema migrado contra código viejo (sistema roto).

### DOS LLAVES DISTINTAS — no confundirlas al diagnosticar
- Token `ghcr.io` → controla si BAJAN las imágenes (`pull`). Falla = `denied`/`unauthorized`.
  También es lo que permite REINSTALAR: sin token activo no se baja ni la versión ya usada.
- Archivo `.lic` → controla si FUNCIONAN BackOffice e IA (al arrancar y cada 6 h). El núcleo
  (expedientes, documentos, firma) no se corta nunca por licencia.

### BACKUP — cinco cosas, no una
`gdi_postgres_data` (BD) · `gdi_minio_data` (documentos, solo si MinIO) · `.env` · `license/*.lic` ·
imágenes Docker (`docker save`, para poder reinstalar sin token).

```bash
mkdir -p backups && FECHA=$(date +%F)
docker compose exec -T postgres pg_dump -U postgres railway -Fc > backups/gdi-$FECHA.dump
docker run --rm -v gdi_minio_data:/data -v /opt/gdi/backups:/backup alpine   tar czf /backup/minio-$FECHA.tar.gz -C /data .
tar czf backups/config-$FECHA.tar.gz .env license/
# solo al actualizar, no a diario:
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml   images | awk 'NR>1 {print $2":"$3}' | sort -u > backups/imagenes-$FECHA.txt
docker save $(cat backups/imagenes-$FECHA.txt) | gzip > backups/imagenes-$FECHA.tar.gz
```
Verificar con `ls -lh backups/`: un dump de pocos KB NO es un backup. Copiar FUERA del servidor.
`.env` y `.lic` contienen secretos: tratarlos como contraseñas.
