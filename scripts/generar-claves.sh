#!/usr/bin/env bash
# ============================================================
# Genera las claves internas y las escribe al .env.
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
# Clave Fernet: 32 bytes en base64 url-safe (44 caracteres con el '=' final).
gen_fernet() { openssl rand -base64 32 | tr '+/' '-_'; }

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

# Como set_key, pero SOLO si la clave falta o esta vacia. Para las que no se pueden
# rotar sin romper datos: regenerar CERT_MASTER_KEY deja ilegibles los certificados
# ya cargados. Correr este script dos veces no la toca.
set_key_si_falta() {
  local key="$1" val="$2"
  if grep -qE "^${key}=.+" .env; then
    echo "  ${key} ya existe: NO se toca"
  else
    set_key "$key" "$val"
  fi
}

echo "Generando claves internas en .env ..."
set_key INTERNAL_API_KEY    "$(gen)"
set_key PDFCOMPOSER_API_KEY "$(gen)"
set_key NOTARY_API_KEY      "$(gen)"
set_key AUTH0_SECRET        "$(gen)"
set_key_si_falta CERT_MASTER_KEY "$(gen_fernet)"

echo "Listo. Revisá el .env y completá el resto (BD, Auth0, almacenamiento)."
