#!/usr/bin/env bash
# ============================================================
# Genera las 4 claves internas y las escribe al .env.
# Cada clave es un valor único; el MISMO valor se reusa entre
# los servicios que se autentican entre sí (no generar una por servicio).
#
# Uso:
#   ./scripts/generar-claves.sh
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "No existe .env. Copialo primero:  cp .env.example .env"
  exit 1
fi

gen() { openssl rand -hex 32; }

# Reemplaza (o agrega) una clave KEY=valor en el .env
set_key() {
  local key="$1" val="$2"
  if grep -qE "^${key}=" .env; then
    # Reemplazo in-place portable (Linux y macOS)
    sed -i.bak -E "s|^${key}=.*|${key}=${val}|" .env && rm -f .env.bak
  else
    echo "${key}=${val}" >> .env
  fi
  echo "  ${key} actualizada"
}

echo "Generando claves internas en .env ..."
set_key INTERNAL_API_KEY    "$(gen)"
set_key PDFCOMPOSER_API_KEY "$(gen)"
set_key NOTARY_API_KEY      "$(gen)"
set_key AUTH0_SECRET        "$(gen)"

echo "Listo. Revisá el .env y completá el resto (BD, Auth0, almacenamiento)."
