# GDI OnPremise

Despliegue auto-alojado de **GDI Latam** — la plataforma de Gestión Documental Inteligente para gobiernos — con `docker-compose`. Pensado para que un municipio corra GDI en su propio servidor, con sus datos sin salir de su infraestructura.

## Tiers

| | Tier Libre | Tier Premium |
|---|---|---|
| Licencia | AGPL (open source) | Comercial (archivo `.lic`) |
| Cómo se obtiene | `git clone` + build local | Imágenes en `ghcr.io` (token de GDI) |
| Instancias (tenants) | 1 | 2 (producción + pruebas) |
| Módulos | Backend, Frontend, BD, firma, PDFs | + BackOffice (administración) + AgenteLANG (IA) |
| Almacenamiento | MinIO local o Cloudflare R2 | igual |

## Qué hay en este repo

Solo la **receta** de despliegue (no el código de la aplicación):

- `docker-compose.yml` — tier libre (buildea todo localmente).
- `docker-compose.premium.yml` — overlay con los módulos pagos (imágenes de ghcr.io).
- `docker-compose.minio.yml` — overlay de almacenamiento local con MinIO.
- `.env.example` — plantilla de configuración.
- `scripts/generar-claves.sh` — genera las claves internas.
- `INSTALL.md` — guía rápida de instalación.

El código de la aplicación vive en los repos que se clonan al lado: `GDI-Backend`, `GDI-Frontend`, `GDI-BD`.

## Instalación

- **[docs/MANUAL.md](docs/MANUAL.md)** — manual completo paso a paso (tier Premium), para el técnico del municipio.
- **[docs/MANUAL-LLM.md](docs/MANUAL-LLM.md)** — el mismo manual optimizado para que un asistente de IA te guíe o ejecute los pasos.
- **[INSTALL.md](INSTALL.md)** — guía rápida resumida.

## Seguridad del modelo

El `docker-compose` es público a propósito: no contiene secretos. La protección del tier pago está en (1) las imágenes privadas de `ghcr.io` (requieren token) y (2) el archivo de licencia `.lic`. Sin licencia válida, los módulos premium no funcionan.

## Licencia

El contenido de este repositorio se distribuye bajo **AGPL-3.0**. Los módulos del tier Premium están sujetos a licencia comercial de GDI Latam.
