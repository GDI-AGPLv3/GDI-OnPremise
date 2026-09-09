# GDI OnPremise — Manual de instalación (tier Premium)

Guía paso a paso para instalar GDI en el servidor de tu municipio. Pensada para el **técnico del municipio** que recibió la licencia de GDI Latam.

> **¿Tenés un asistente de IA?** Hay una versión de este manual optimizada para pegarle a un LLM y que te guíe o ejecute los pasos: [`MANUAL-LLM.md`](MANUAL-LLM.md).

---

## ⚠️ Estado de implementación

Este manual describe el flujo Premium completo. Algunas automatizaciones están **en construcción** y se marcan con 🚧 a lo largo del documento:
- 🚧 Verificación automática de licencia `.lic`
- 🚧 Wizard visual "crear instancia" en el BackOffice
- 🚧 Runner de migraciones de BD al arranque
- 🚧 Runner de migraciones: hoy el esquema queda en el estado del instalador inicial.
- ℹ️ La instalación es **híbrida y así funciona**: 7 servicios se compilan en tu servidor
  (backend, gateway, portal, base de datos y los 2 microservicios) y 3 bajan como imagen
  desde el registro de GDI (BackOffice, BackOffice-Front y AgenteLANG). Los pasos 3, 7 y 11
  reflejan esa realidad: por eso actualizar necesita `git pull` **y** `--build`, no solo `pull`.

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
| RAM | 4 GB (medido: 2 GB en uso con los 13 contenedores) |
| CPU | 4 vCPU |
| Disco | 80 GB |
| Red | Un **dominio** apuntando al servidor (HTTPS es obligatorio — Auth0 lo exige) |

Vas a necesitar 5 subdominios apuntando a la IP del servidor (registros DNS tipo A):
- `gdi.tu-municipio.gob.ar` — portal de usuarios (frontend)
- `api.tu-municipio.gob.ar` — API del backend
- `admin.tu-municipio.gob.ar` — BackOffice (administración)
- `admin-api.tu-municipio.gob.ar` — API del BackOffice
- `mcp.tu-municipio.gob.ar` — gateway MCP (para conectar asistentes de IA)

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

**Todo GDI se instala en una versión, y es una sola para las 10 piezas.** Te la indica
GDI en el mail de entrega, con el formato `AAAA.MM`. La misma que después va en
`IMAGE_VERSION` (paso 5).

```bash
sudo mkdir -p /opt/gdi && sudo chown $USER /opt/gdi && cd /opt/gdi

# La versión que te indicó GDI. Cambiala por la tuya:
VERSION=2026.09

git clone --branch "v$VERSION" https://github.com/GDI-AGPLv3/GDI-OnPremise.git .
git clone --branch "v$VERSION" https://github.com/GDI-AGPLv3/GDI-Backend.git
git clone --branch "v$VERSION" https://github.com/GDI-AGPLv3/GDI-Frontend.git
git clone --branch "v$VERSION" https://github.com/GDI-AGPLv3/GDI-BD.git
```

> ⚠️ **No clones sin `--branch`.** Sin la versión te traés la rama principal, que es
> "lo último publicado" y puede no coincidir con las imágenes del paso 7: tendrías un
> backend de una versión hablándole a módulos de otra. Si el clone falla con
> `Remote branch not found`, esa versión todavía no se publicó: avisale a GDI antes
> de seguir, no lo destrabes sacando el `--branch`.

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

### 4.3. Crear 2 aplicaciones de login
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

### 4.4. Crear la aplicación Machine to Machine (OBLIGATORIA)

> 🔴 **Sin este paso no vas a poder dar de alta ni un solo usuario.** El alta va a
> fallar con *"Sistema de autenticación no disponible"*.

Las dos aplicaciones anteriores sirven para que las personas **entren**. Esta sirve
para que GDI pueda **crear** usuarios en Auth0 por vos (cuando das de alta un
empleado desde el BackOffice, GDI le crea la identidad y le manda el mail de
activación). Es una aplicación sin persona detrás: el sistema hablándole a Auth0.

1. Applications → **Create Application** → elegí **Machine to Machine Applications**.
2. Cuando te pregunte contra qué API autorizarla, elegí **Auth0 Management API**
   (la que viene de fábrica, NO la que creaste en el paso 4.2).
3. En la lista de permisos (scopes), marcá al menos:
   - `read:users`
   - `create:users`
   - `update:users`
   - `create:user_tickets`
4. Anotá el **Client ID** y el **Client Secret** → van a `AUTH0_M2M_CLIENT_ID` y
   `AUTH0_M2M_CLIENT_SECRET` en el `.env`.

**Cómo verificar que quedó bien:** después de levantar GDI (paso 7), mirá el arranque
del BackOffice con `docker compose logs backoffice-back | head -40`. Tiene que decir:

```
[OK] Alta de usuarios: credenciales de Auth0 presentes
```

Si falta algo, el propio log te dice qué variable es:

```
[FALTA] Alta de usuarios DESHABILITADA: falta AUTH0_M2M_CLIENT_SECRET.
```

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
# Versión del set de imágenes — te la indica GDI en el mail de entrega.
# Si no coincide con una versión publicada, el paso 7 falla con "manifest unknown".
IMAGE_VERSION=2026.08

# Base de datos
DB_PASSWORD=una-password-larga-y-segura

# Auth0 (del paso 4)
AUTH0_DOMAIN=tu-municipio.us.auth0.com
AUTH0_AUDIENCE=https://gdi-api
AUTH0_FRONTEND_CLIENT_ID=...
AUTH0_FRONTEND_CLIENT_SECRET=...
AUTH0_BACKOFFICE_CLIENT_ID=...
AUTH0_BACKOFFICE_CLIENT_SECRET=...

# Auth0 Machine to Machine (del paso 4.4) — SIN ESTO NO SE PUEDEN CREAR USUARIOS
AUTH0_M2M_CLIENT_ID=...
AUTH0_M2M_CLIENT_SECRET=...

# Correo: el servidor SMTP del municipio (ver sección 5.1)
SMTP_HOST=mail.tu-municipio.gob.ar
SMTP_PORT=587
SMTP_USER=noreply@tu-municipio.gob.ar
SMTP_PASSWORD=...
FROM_EMAIL=Municipio <noreply@tu-municipio.gob.ar>

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

### 5.1. Correo (recomendado, no obligatorio)

GDI manda mails en dos momentos que importan: cuando das de alta un usuario (con el
enlace para que se ponga su contraseña) y cuando invitás a un administrador.

Tenés dos opciones:

| Opción | Cuándo conviene | Qué completás |
|---|---|---|
| **Tu servidor SMTP** | Lo normal en un municipio: ya tenés casilla institucional y los datos no salen del país | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `FROM_EMAIL` |
| **Resend** | Si no tenés servidor propio y no te molesta un servicio externo | `RESEND_API_KEY` (de resend.com) y `FROM_EMAIL` |

Si ponés las dos, manda por Resend.

**`FROM_EMAIL` es obligatorio si configurás correo.** Es el remitente que van a ver
tus empleados, y tiene que ser una dirección tuya: `Municipio <noreply@tu-municipio.gob.ar>`.

Notas de puertos: `SMTP_PORT=587` usa STARTTLS (lo más común). Para el puerto 465
poné `SMTP_SSL=true`. Para el 25 sin cifrado, `SMTP_TLS=false`.

**¿Y si no configurás correo?** El sistema funciona igual. Cuando des de alta un
usuario, el BackOffice te va a mostrar **el enlace de activación en pantalla**, con un
botón para copiarlo, y se lo hacés llegar por el medio que quieras. Ojo: ese enlace
sirve **una sola vez** y **vence a los 5 días** — tratalo como una contraseña.

Para confirmar cómo quedó, mirá el arranque: `docker compose logs backoffice-back | head -40`

```
[OK] Correo: SMTP mail.tu-municipio.gob.ar:587 (STARTTLS, con usuario, remitente: Municipio <noreply@tu-municipio.gob.ar>)
```

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

1. El panel **no se publica a internet** a propósito: escucha solo en `localhost`.
   Abrí un túnel SSH desde tu máquina y entrá por ahí:

   ```bash
   ssh -L 8181:localhost:81 usuario@IP-DE-TU-SERVIDOR
   # dejá esa terminal abierta y andá a http://localhost:8181
   ```

2. La primera vez te pide **crear el usuario administrador**. Poné un mail real del
   municipio y una password fuerte.
   - ⚠️ **Hacelo apenas levantes el sistema, no lo dejes para después.** Hasta que ese
     usuario exista, cualquiera que alcance el panel puede crearlo y quedarse con el
     proxy — y con él, con el control de a dónde apunta cada dominio.
3. Para cada uno de los 5 dominios, creá un **Proxy Host** (pestaña Hosts → Proxy Hosts → Add Proxy Host):

| Domain Name | Forward Hostname | Forward Port |
|-------------|------------------|--------------|
| gdi.tu-municipio.gob.ar | `frontend` | 3000 |
| api.tu-municipio.gob.ar | `backend` | 8080 |
| admin.tu-municipio.gob.ar | `backoffice-front` | 3000 |
| admin-api.tu-municipio.gob.ar | `backoffice-back` | 8080 |
| mcp.tu-municipio.gob.ar | `gateway` | 8080 |

> ℹ️ **Si más adelante cambiás alguno de los 4 dominios**, no alcanza con reiniciar:
> el portal lleva la dirección de la API incrustada desde que se compiló. Hay que
> actualizar el `.env` y recompilarlo:
> `docker compose ... up -d --build frontend`

4. En el Proxy Host de **`api.tu-municipio.gob.ar`**, pestaña **Custom locations**,
   agregá una entrada. Es la que sirve las **fotos de perfil**: las pide el navegador
   del usuario, así que necesitan una dirección pública. Sin esto, cargar una foto
   falla con *"Bucket de avatares no configurado"*.

   | Campo | Valor |
   |-------|-------|
   | Location | `/avatars` |
   | Forward Hostname | `minio` |
   | Forward Port | `9000` |

   Y en el engranaje de esa location, pegá esta línea para que apunte al bucket:

   ```
   rewrite ^/avatars/(.*)$ /gdi-avatars/$1 break;
   ```

   > ⚠️ Tiene que ser `rewrite`, **no** `proxy_pass`. El panel ya genera su propio
   > `proxy_pass`; si agregás otro, nginx no puede levantar la configuración y
   > **te quedás sin la API entera**, no solo sin los avatares.

   > Solo se publica ese bucket, que el sistema crea con lectura pública al levantar.
   > **Los documentos siguen privados**: MinIO no queda expuesto.

5. En cada Proxy Host, pestaña **SSL** → "Request a new SSL Certificate" → tildá "Force SSL" y "HTTP/2 Support" → Save. (Let's Encrypt emite el certificado solo.)

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

> ## 🛑 ANTES DE ACTUALIZAR: BACKUP
>
> Una actualización **aplica migraciones a la base de datos, y eso no tiene vuelta atrás**:
> volver a la imagen anterior **no** revierte el schema. Si algo sale mal, lo único que te
> devuelve el sistema es la copia que hiciste antes.
>
> **Hacé el backup completo de la [sección 12](#12-backups) ahora, no después.**

GDI Latam te avisa **por mail** cuando hay una versión nueva. **Nada se actualiza solo:**
actualizás vos, el día y la hora que elijas. Es a propósito — actualizar el sistema de
expedientes de un municipio es un acto administrativo, no algo que deba pasar de madrugada
sin que nadie lo haya decidido.

### Antes de empezar

- Hacé el backup completo (sección 12) y **verificá que el dump no quedó vacío**
  (`ls -lh` sobre el archivo: si pesa unos pocos KB, algo falló).
- Elegí una ventana fuera del horario de atención y avisá a los usuarios.
- Leé la nota de la versión que te mandamos: ahí decimos si hay algo que requiere atención.

### Actualizar

```bash
cd /opt/gdi

# 1. La versión nueva (la que dice el mail de GDI). Es UNA sola para las 10 piezas.
VERSION=2026.09
nano .env                      # IMAGE_VERSION=2026.09  (el mismo número)

# 2. Traer el código nuevo de los servicios que se compilan en tu servidor
#    (backend, gateway, frontend, base de datos y los microservicios).
#    Estás parado en una versión, no en una rama: se cambia de versión, no se hace pull.
for r in . GDI-Backend GDI-Frontend GDI-BD; do
  git -C "$r" fetch --tags origin && git -C "$r" checkout "v$VERSION" || {
    echo "ERROR: la version v$VERSION no existe en $r. NO sigas: avisale a GDI."; break; }
done

# 3. Bajar las imágenes nuevas de los módulos Premium
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml pull

# 4. Recompilar y reemplazar los contenedores por los de la versión nueva
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml up -d --build
```

> ⚠️ **Los pasos 2 y 4 no son opcionales.** De los 10 servicios de GDI, solo 3
> (BackOffice, BackOffice-Front y AgenteLANG) bajan como imagen. Los otros 7 se
> compilan en tu servidor, así que un `pull` solo **no los actualiza**: te quedarías
> con los módulos Premium nuevos hablándole a un backend viejo.

Si usás Cloudflare R2 en lugar de MinIO, sacá el `-f docker-compose.minio.yml` de los dos comandos.

### Verificar que quedó bien

```bash
docker compose ps                       # todos "running", ninguno reiniciando
docker compose logs --tail=50 backend   # el arranque termina sin errores
```

Entrá al portal y al BackOffice y abrí un expediente. Si algo quedó mal, es **ahora** cuando
querés enterarte, con el backup fresco y la ventana todavía abierta.

### Si hay que volver atrás

Volver a la versión anterior son **dos** cosas, y las dos son necesarias:

```bash
nano .env    # IMAGE_VERSION=<la versión anterior, formato AAAA.MM>
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml up -d
```

...y **restaurar el dump de la base** (sección 12). Bajar solo la versión de las imágenes
deja el schema migrado contra un código viejo: eso no es "volver atrás", es un sistema roto
de otra manera.

### Por qué a veces no baja una imagen

Hay dos llaves distintas y conviene no confundirlas:

| | Qué controla | Cuándo actúa |
|---|---|---|
| **Token de `ghcr.io`** | si podés **bajar** imágenes | al hacer `pull` |
| **Archivo `.lic`** | si **funcionan** BackOffice e IA | al arrancar y cada 6 h |

Si el `pull` da `denied` o `unauthorized`, es el **token** (vencido, revocado, o se perdió la
sesión de `docker login`): rehacé el paso 7 y, si sigue, escribinos. Si las imágenes bajan y
levantan pero el BackOffice te avisa de la licencia, es el **`.lic`**, y se resuelve renovando
el contrato — el núcleo (expedientes, documentos, firma) sigue funcionando igual.

> ⚠️ El token es también lo que te permite **reinstalar**. Si algún día se te muere el servidor
> y el token ya no está activo, no vas a poder bajar ni la versión que estabas usando. Por eso
> la sección 12 pide guardar una **copia local de las imágenes**: con eso el sistema se levanta
> de nuevo aunque no tengas acceso al registro.

🚧 Las migraciones de base de datos se aplican solas al arrancar el backend (runner en
construcción). Por ahora, GDI te avisa si una actualización requiere correr migraciones a mano.

---

## 12. Backups

### Qué hay que copiar

No alcanza con la base. Un servidor que se pierde se recupera con **cinco** cosas:

| Qué | Dónde vive | Sin esto... |
|---|---|---|
| **Base de datos** | volumen `gdi_postgres_data` | no hay nada: expedientes, usuarios, todo |
| **Documentos** | volumen `gdi_minio_data` (si usás MinIO) | la base referencia archivos que no existen |
| **`.env`** | `/opt/gdi/.env` | no podés levantar: claves, Auth0, contraseñas |
| **Licencia `.lic`** | `/opt/gdi/license/` | arranca sin BackOffice ni IA |
| **Imágenes Docker** | el registro… o tu copia local | si el token no está activo, no podés reinstalar |

> Si usás **Cloudflare R2** en lugar de MinIO, los documentos ya están afuera del servidor y
> no entran en este backup.

### Backup completo

```bash
mkdir -p /opt/gdi/backups && cd /opt/gdi
FECHA=$(date +%F)

# 1. Base de datos
docker compose exec -T postgres pg_dump -U postgres railway -Fc > backups/gdi-$FECHA.dump

# 2. Documentos (solo si usás MinIO)
docker run --rm -v gdi_minio_data:/data -v /opt/gdi/backups:/backup alpine \
  tar czf /backup/minio-$FECHA.tar.gz -C /data .

# 3. Configuración y licencia
tar czf backups/config-$FECHA.tar.gz .env license/

# 4. Imágenes (una vez por versión, no todos los días)
docker compose -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml \
  images | awk 'NR>1 {print $2":"$3}' | sort -u > backups/imagenes-$FECHA.txt
docker save $(cat backups/imagenes-$FECHA.txt) | gzip > backups/imagenes-$FECHA.tar.gz
```

Verificá que los archivos pesen algo razonable:

```bash
ls -lh backups/
```

Un dump de unos pocos KB **no es un backup**: es un error que no miraste.

### Restaurar

```bash
cd /opt/gdi

# Imágenes, si no tenés acceso al registro
gunzip -c backups/imagenes-AAAA-MM-DD.tar.gz | docker load

# Configuración
tar xzf backups/config-AAAA-MM-DD.tar.gz

# Base de datos (con el sistema abajo salvo postgres)
docker compose up -d postgres
docker compose exec -T postgres pg_restore -U postgres -d railway --clean --if-exists \
  < backups/gdi-AAAA-MM-DD.dump

# Documentos
docker run --rm -v gdi_minio_data:/data -v /opt/gdi/backups:/backup alpine \
  tar xzf /backup/minio-AAAA-MM-DD.tar.gz -C /data
```

### Reglas mínimas

- **Automatizá el backup diario** (un `cron` con los pasos 1 a 3). El paso 4 solo cuando actualizás.
- ⚠️ **Copiá los backups fuera del servidor** — otro disco, otra máquina, la nube. Un backup que
  vive en el mismo servidor que la base no sirve para el caso en que más lo vas a necesitar.
- **Probá una restauración** al menos una vez, en otra máquina. Un backup que nunca se restauró
  es una suposición, no una copia.
- El `.env` y el `.lic` tienen **secretos**: guardá esas copias con el mismo cuidado que las
  contraseñas del municipio.

---

## 13. Problemas comunes

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| El login da error de "callback mismatch" | La Callback URL en Auth0 no coincide con tu dominio | Revisá el paso 4.3 (debe ser `https://tu-dominio/auth/callback`) |
| El frontend carga pero la API da error de CORS | `FRONTEND_URL` mal seteado en `.env` | Debe ser exactamente tu dominio del portal, con `https://` |
| "NoSuchBucket" al subir un documento | Los buckets de MinIO no existen o `S3_FORCE_PATH_STYLE` no está en `true` | Verificá el bloque MinIO del `.env` |
| Un contenedor reinicia en loop | Falta una variable en `.env` | `docker compose logs <servicio>` para ver cuál |
| Al crear un usuario: "Sistema de autenticación no disponible" | Falta la aplicación Machine to Machine de Auth0 | Paso 4.4. Confirmá con `docker compose logs backoffice-back \| grep FALTA` |
| El usuario nunca recibe el mail de activación | No hay correo configurado, o el SMTP rechaza | Paso 5.1. Mientras tanto, usá el enlace que muestra el BackOffice en pantalla al crear el usuario |
| El mail sale pero el botón lleva al lugar equivocado | Falta `AUTH0_FRONTEND_CLIENT_ID` o `AUTH0_BACKOFFICE_CLIENT_ID` | Paso 4.3; el log de arranque los reporta |
| No baja una imagen paga | Token de ghcr.io vencido o mal | Volvé a hacer `docker login ghcr.io` (paso 7) |

Para ver el estado de todo: `docker compose ps` y `docker compose logs -f <servicio>`.

---

¿Trabado en algo? Escribinos a soporte de GDI Latam con la salida de `docker compose logs`.
