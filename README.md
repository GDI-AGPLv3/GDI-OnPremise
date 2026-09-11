# GDI OnPremise

Instalador de **GDI Latam** — la plataforma de Gestión Documental Inteligente para gobiernos —
para correrla en el servidor del municipio, con los datos sin salir de su infraestructura.

> **Requiere licencia de GDI Latam.** Este repo es la *receta* (compose + manual) y es público
> para que se pueda auditar antes de contratar. Los *ingredientes* no: las imágenes de los 10
> servicios se bajan de `ghcr.io` con un token que entrega GDI Latam, y el archivo de licencia
> `.lic` habilita el BackOffice y la IA. Sin token no baja nada; sin licencia no se puede crear
> el municipio.

## Qué hay en este repo

- `docker-compose.yml` — el núcleo: base de datos, migraciones, backend, gateway MCP, portal,
  PDFs, firma y reverse proxy.
- `docker-compose.premium.yml` — BackOffice (administración) y AgenteLANG (IA).
- `docker-compose.minio.yml` — almacenamiento local con MinIO (alternativa a Cloudflare R2).
- `.env.example` — plantilla de configuración.
- `scripts/generar-claves.sh` — genera las claves internas.
- `INSTALL.md` — guía rápida.

En el servidor **no se compila nada**: todos los servicios son imágenes con una misma versión
(`IMAGE_VERSION`, formato `AAAA.MM.N`).

## Instalación

- **[docs/MANUAL.md](docs/MANUAL.md)** — manual completo paso a paso, para el técnico del municipio.
- **[docs/MANUAL-LLM.md](docs/MANUAL-LLM.md)** — el mismo manual optimizado para que un asistente de IA te guíe o ejecute los pasos.
- **[INSTALL.md](INSTALL.md)** — guía rápida resumida.

## Código fuente

GDI es software libre (AGPL-3.0). El código fuente correspondiente a la versión que tengas
instalada se entrega a pedido. La versión comunitaria se publica en
[GDI-AGPLv3](https://github.com/GDI-AGPLv3).

## Licencia

El contenido de este repositorio se distribuye bajo **AGPL-3.0**. El BackOffice y AgenteLANG
están sujetos a la licencia comercial de GDI Latam.
