#!/usr/bin/env python3
"""
Verifica que el docker-compose le pase a cada servicio las variables que su
codigo realmente exige.

Existe porque el mismo error nos mordio tres veces: la configuracion real de
cada servicio vive en su fly.toml (infra nuestra, no se publica) y el compose
on-premise es una copia hecha a mano. Cuando el codigo suma una variable, en
Fly sigue andando y solo se rompe en el servidor de un municipio.

Que detecta:

  1. OBLIGATORIA_FALTANTE  el codigo hace os.environ["X"] (sin default) y el
                           compose no se la pasa -> el contenedor no arranca.
                           Caso real: notary pedia PORT, GUNICORN_WORKERS y
                           GUNICORN_TIMEOUT y no los recibia (KeyError en bucle,
                           sin firma digital).

  2. VACIA_ANULA_DEFAULT   el compose declara la variable vacia (${X:-}) y el
                           codigo la lee con os.getenv("X", default). El default
                           de getenv aplica SOLO si la variable no existe: vacia
                           la anula. Caso real: AUTH0_ISSUERS tiraba el backend.

  3. PUERTO_DESALINEADO    el compose apunta a http://servicio:PUERTO pero a ese
                           servicio le pasa un PORT distinto (o ninguno, y su
                           default es otro). El contenedor figura Up y no atiende.
                           Caso real: el backend hablaba a pdfcomposer:8080 y
                           pdfcomposer escuchaba en :8000.

  4. ENVIRON_SIN_DEFAULT   os.environ["X"] en un servicio que se distribuye.
                           Es un crash duro en casa del municipio; deberia ser
                           os.getenv con un default razonable. Se reporta como
                           aviso salvo que se pase --estricto.

Uso:
    python scripts/verificar-env.py --repos /opt/gdi \\
        -f docker-compose.yml -f docker-compose.premium.yml -f docker-compose.minio.yml

    # como lo corre el CI (falla si hay algun hallazgo de tipo 1, 2 o 3):
    python scripts/verificar-env.py --repos . -f docker-compose.yml ...

Salida: 0 si esta todo bien, 1 si hay hallazgos que rompen el arranque.
"""

import argparse
import ast
import os
import re
import sys
from pathlib import Path

import yaml

# os.environ["X"] / os.environ['X']  -> obligatoria, sin default posible
RE_ENVIRON = re.compile(r"""os\.environ\[\s*["']([A-Z0-9_]+)["']\s*\]""")
# os.getenv("X") / os.environ.get("X")  -> sin default: devuelve None
RE_GETENV_SOLO = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*["']([A-Z0-9_]+)["']\s*\)"""
)
# os.getenv("X", algo)  -> tiene default
RE_GETENV_DEFAULT = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*["']([A-Z0-9_]+)["']\s*,"""
)
# os.getenv("X", "")  -> el default es vacio: equivale a NO tener default. Pasarla
# vacia desde el compose no anula nada, y si despues hay un raise es obligatoria.
RE_GETENV_VACIO = re.compile(
    r"""os\.(?:getenv|environ\.get)\(\s*["']([A-Z0-9_]+)["']\s*,\s*(?:""|'')\s*\)"""
)
# http://servicio:puerto  dentro de un valor del compose
RE_URL_INTERNA = re.compile(r"""https?://([a-z0-9][a-z0-9_-]*):(\d{2,5})""")
# Linea que lanza una excepcion nombrando una variable: la vuelve obligatoria de
# hecho aunque se lea con os.getenv. Ej: pdfcomposer hace
#   raise ValueError("API_KEY environment variable must be set")
RE_RAISE = re.compile(r"""^.*\braise\b.*$""", re.MULTILINE)

# Puerto en el que escucha un servicio si nadie le pasa PORT. Sale de leer su
# gunicorn_conf.py; se declara aca para no depender de encontrar el archivo.
PUERTO_DEFAULT_CONOCIDO = {
    "pdfcomposer": 8000,
    "notary": None,  # no tiene default: os.environ["PORT"] revienta
}

IGNORAR_DIRS = {
    ".git", "node_modules", ".next", "__pycache__", ".venv", "venv",
    "tests", "test", ".pytest_cache", "dist", "build",
}


def leer_compose(archivos):
    """Combina varios docker-compose.yml como lo hace docker compose -f a -f b."""
    combinado = {}
    for a in archivos:
        with open(a, encoding="utf-8") as fh:
            datos = yaml.safe_load(fh) or {}
        for nombre, cfg in (datos.get("services") or {}).items():
            destino = combinado.setdefault(nombre, {})
            for clave, valor in (cfg or {}).items():
                if clave == "environment" and isinstance(valor, dict):
                    destino.setdefault("environment", {}).update(valor)
                else:
                    destino[clave] = valor
    return combinado


def env_del_servicio(cfg):
    """Devuelve {VAR: valor_crudo} del bloque environment (dict o lista)."""
    entorno = cfg.get("environment") or {}
    if isinstance(entorno, list):
        salida = {}
        for item in entorno:
            if "=" in item:
                k, v = item.split("=", 1)
                salida[k.strip()] = v
            else:
                salida[item.strip()] = None
        return salida
    return {k: ("" if v is None else str(v)) for k, v in entorno.items()}


# Modelo de imagenes (GDI-305): el compose ya no tiene `build:`. El codigo de cada imagen
# PROPIA se ubica por su nombre en ghcr.io/gdi-live. Sin este mapa todos los servicios
# caerian en "baja como imagen, no tenemos su fuente" y el chequeo daria un verde vacio.
# (repos candidatos, Dockerfile) — el primer repo que exista bajo --repos.
FUENTE_DE_IMAGEN = {
    "postgres": (("GDI-BD",), "Dockerfile.prd"),
    "migrator": (("GDI-BD",), "Dockerfile.migrator"),
    "backend": (("GDI-Backend",), "Dockerfile"),
    "gateway": (("GDI-Backend",), "Dockerfile.gateway"),
    "frontend": (("GDI-FRONTEND", "GDI-Frontend"), "Dockerfile"),
    "pdfcomposer": (("GDI-PDFComposer",), "Dockerfile"),
    "notary": (("GDI-Notary",), "Dockerfile"),
    "backoffice-back": (("GDI-BackOffice-Back",), "Dockerfile"),
    "backoffice-front": (("GDI-BackOffice-Front",), "Dockerfile"),
    "agentelang": (("GDI-AgenteLANG",), "Dockerfile"),
}
RE_IMAGEN_PROPIA = re.compile(r"^ghcr\.io/gdi-live/([a-z0-9-]+):")


def imagen_propia(cfg):
    """Nombre de la imagen si es nuestra (ghcr.io/gdi-live/<nombre>:...), si no None."""
    m = RE_IMAGEN_PROPIA.match(str(cfg.get("image") or ""))
    return m.group(1) if m else None


def ruta_del_build(cfg, raiz):
    """
    Ruta al codigo fuente del servicio: su contexto de build o, si baja como imagen
    propia, el repo del que sale. None solo para imagenes de terceros (redis, minio...).
    """
    build = cfg.get("build")
    if build:
        contexto = build if isinstance(build, str) else build.get("context", ".")
        return (raiz / contexto).resolve()
    nombre = imagen_propia(cfg)
    if nombre is None:
        return None
    if nombre not in FUENTE_DE_IMAGEN:
        # Imagen nuestra que el mapa no conoce: ruta inexistente => SIN_VERIFICAR, no verde.
        return (raiz / f"<imagen {nombre} sin fuente conocida>").resolve()
    repos, _ = FUENTE_DE_IMAGEN[nombre]
    for repo in repos:
        if (raiz / repo).exists():
            return (raiz / repo).resolve()
    return (raiz / repos[0]).resolve()


def nombre_dockerfile(cfg):
    build = cfg.get("build")
    if isinstance(build, dict):
        return build.get("dockerfile", "Dockerfile")
    nombre = imagen_propia(cfg)
    if nombre in FUENTE_DE_IMAGEN:
        return FUENTE_DE_IMAGEN[nombre][1]
    return "Dockerfile"


def rutas_que_copia(dockerfile):
    """
    Rutas del contexto que el Dockerfile mete en la imagen.

    Escanear el contexto entero sobrestima: GDI-Backend es contexto de backend,
    de gateway y de los dos microservicios a la vez, y GDI-BD (postgres) solo
    copia SQL aunque el repo tenga scripts .py. Lo que corre es lo que se copia.

    Devuelve [] si no se pudo leer el Dockerfile.
    """
    if not dockerfile.exists():
        return []
    rutas = []
    for linea in dockerfile.read_text(encoding="utf-8", errors="ignore").splitlines():
        linea = linea.strip()
        if not linea.upper().startswith(("COPY ", "ADD ")):
            continue
        partes = [p for p in linea.split()[1:] if not p.startswith("--")]
        if len(partes) < 2:
            continue
        rutas.extend(partes[:-1])  # el ultimo es el destino
    return rutas


RE_CMD_MODULO = re.compile(r"""([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+):[a-zA-Z_]""")


def modulo_de_arranque(dockerfile):
    """
    El modulo que levanta el CMD, ej. 'api_gateway.http_server' de
    `uvicorn api_gateway.http_server:app`. None si no se puede deducir.

    Hace falta porque varios servicios comparten repo y Dockerfile con `COPY . .`:
    backend y gateway copian TODO GDI-Backend, pero cada uno importa una parte.
    Sin esto se le reclaman al gateway variables de modulos que nunca carga.
    """
    if not dockerfile.exists():
        return None
    for linea in dockerfile.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not linea.strip().upper().startswith(("CMD", "ENTRYPOINT")):
            continue
        m = RE_CMD_MODULO.search(linea)
        if m:
            return m.group(1)
    return None


def archivos_alcanzables(contexto, modulo):
    """
    Los .py que el servicio realmente carga: arranca en el modulo del CMD y sigue
    los imports que resuelven a archivos dentro del contexto.

    Devuelve None si no se pudo ubicar el modulo (el llamador usa el fallback).
    """
    def a_ruta(nombre):
        base = contexto / Path(*nombre.split("."))
        for cand in (base.with_suffix(".py"), base / "__init__.py"):
            if cand.exists():
                return cand
        return None

    inicio = a_ruta(modulo)
    if inicio is None:
        return None

    vistos, pendientes = set(), [inicio]
    while pendientes:
        archivo = pendientes.pop()
        if archivo in vistos:
            continue
        vistos.add(archivo)
        try:
            arbol = ast.parse(archivo.read_text(encoding="utf-8", errors="ignore"))
        except (SyntaxError, OSError):
            continue
        for nodo in ast.walk(arbol):
            nombres = []
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module and not nodo.level:
                nombres = [nodo.module] + [f"{nodo.module}.{a.name}" for a in nodo.names]
            for nombre in nombres:
                destino = a_ruta(nombre)
                if destino and destino not in vistos:
                    pendientes.append(destino)
    return sorted(vistos)


def py_montados(cfg, raiz):
    """.py que entran por volumen en vez de por COPY (el migrator hace eso)."""
    salida = []
    for v in cfg.get("volumes") or []:
        if not isinstance(v, str) or ":" not in v:
            continue
        origen = v.split(":", 1)[0]
        if not origen.endswith(".py"):
            continue
        ruta = (raiz / origen.lstrip("./")).resolve()
        if ruta.exists():
            salida.append(ruta)
    return salida


def archivos_py(contexto, rutas, subcontextos=()):
    """
    Los .py que el Dockerfile copia. Si copia todo ('.'), el contexto entero.

    `subcontextos` son carpetas que son contexto de build de OTRO servicio y caen
    dentro de este (GDI-Backend contiene microservices/notary y /pdfcomposer):
    su codigo no corre en esta imagen aunque el COPY . lo arrastre.
    """
    vistos = set()
    for ruta in rutas:
        if ruta in (".", "./"):
            candidatos = contexto.rglob("*.py")
        else:
            origen = (contexto / ruta.lstrip("./")).resolve()
            if origen.is_dir():
                candidatos = origen.rglob("*.py")
            elif origen.suffix == ".py" and origen.exists():
                candidatos = [origen]
            else:
                continue
        for archivo in candidatos:
            if any(p in IGNORAR_DIRS for p in archivo.parts):
                continue
            if any(archivo.is_relative_to(sub) for sub in subcontextos):
                continue
            vistos.add(archivo)
    return sorted(vistos)


def escanear_codigo(archivos):
    """Lee los .py y clasifica cada variable en obligatoria / con default / sin default."""
    obligatorias, con_default, sin_default, por_raise = set(), set(), set(), set()
    for archivo in archivos:
        try:
            texto = archivo.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        obligatorias |= set(RE_ENVIRON.findall(texto))
        vacio_aca = set(RE_GETENV_VACIO.findall(texto))
        con_default |= set(RE_GETENV_DEFAULT.findall(texto)) - vacio_aca
        leidas_sin_default = set(RE_GETENV_SOLO.findall(texto)) | vacio_aca
        sin_default |= leidas_sin_default

        # Una variable que se lee sin default y despues aparece en un raise es
        # obligatoria igual: el servicio decide morir si falta.
        lineas_raise = "\n".join(RE_RAISE.findall(texto))
        if lineas_raise:
            por_raise |= {v for v in leidas_sin_default if v in lineas_raise}
    return obligatorias, con_default, sin_default, por_raise


def valor_es_vacio(crudo):
    """True si el compose le pasa la variable pero vacia: ${X:-} o cadena vacia."""
    if crudo is None:
        return False
    crudo = crudo.strip()
    if crudo == "":
        return True
    return bool(re.fullmatch(r"\$\{[A-Z0-9_]+:-\s*\}", crudo))


def puerto_declarado(entorno):
    """El PORT que el compose le pasa al servicio, si se lo pasa literal."""
    crudo = entorno.get("PORT")
    if crudo is None:
        return None
    m = re.search(r"\d{2,5}", str(crudo))
    return int(m.group()) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos", default=".",
                    help="carpeta donde estan los repos de las 10 imagenes (GDI-Backend, "
                           "GDI-FRONTEND, GDI-BD, GDI-PDFComposer, GDI-Notary, "
                           "GDI-BackOffice-Back, GDI-BackOffice-Front, GDI-AgenteLANG)")
    ap.add_argument("-f", "--file", action="append", dest="archivos", required=True,
                    help="docker-compose a verificar (repetible, como docker compose -f)")
    ap.add_argument("--estricto", action="store_true",
                    help="tambien falla por os.environ[...] sin default (capa 2)")
    args = ap.parse_args()

    raiz = Path(args.repos).resolve()
    servicios = leer_compose(args.archivos)

    rompen = []          # tipos 1, 2 y 3: la instalacion no funciona
    avisos = []          # tipo 4: estilo, crashea feo en casa del municipio
    no_verificados = []  # no se pudo mirar: NO es un verde

    # Contextos de build de todos los servicios: si el de A cae dentro del de B,
    # el codigo de A no debe contarse como parte de B.
    contextos = {}
    for n, c in servicios.items():
        r = ruta_del_build(c, raiz)
        if r is not None:
            contextos[n] = r

    # Mapa servicio -> PORT que el compose le pasa (lo usa el chequeo 3)
    puertos = {n: puerto_declarado(env_del_servicio(c)) for n, c in servicios.items()}

    for nombre, cfg in sorted(servicios.items()):
        entorno = env_del_servicio(cfg)
        codigo = ruta_del_build(cfg, raiz)
        if codigo is None:
            continue  # imagen de terceros (redis, minio, npm): no es codigo nuestro

        # Un chequeo que no encuentra el codigo NO puede pasar en verde: seria
        # exactamente el falso verde que este script existe para evitar.
        if not codigo.exists():
            no_verificados.append(
                f"[SIN_VERIFICAR] {nombre}: no existe {codigo}. Clona los repos "
                f"(o pasa --repos donde esten) antes de confiar en este resultado."
            )
            continue

        dockerfile = codigo / nombre_dockerfile(cfg)
        montados = py_montados(cfg, raiz)

        # 1o: seguir los imports desde el modulo del CMD (lo que el servicio CARGA).
        modulo = modulo_de_arranque(dockerfile)
        archivos = archivos_alcanzables(codigo, modulo) if modulo else None

        # 2o: si no se pudo, mirar lo que el Dockerfile copia, sacando los
        #     subdirectorios que son contexto de otro servicio.
        if archivos is None:
            rutas = rutas_que_copia(dockerfile)
            if not rutas and not montados:
                no_verificados.append(
                    f"[SIN_VERIFICAR] {nombre}: no pude deducir que codigo corre "
                    f"(ni CMD con modulo, ni COPY en {dockerfile.name}, ni volumenes)."
                )
                continue
            subcontextos = [r for n, r in contextos.items()
                            if n != nombre and r != codigo and r.is_relative_to(codigo)]
            archivos = archivos_py(codigo, rutas, subcontextos)

        archivos = sorted(set(archivos) | set(montados))
        obligatorias, con_default, sin_default, por_raise = escanear_codigo(archivos)
        if not (obligatorias or con_default or sin_default or por_raise):
            # El Dockerfile no mete Python (ej. postgres copia solo SQL). Correcto.
            continue

        # 1b. las que el codigo valida y lanza excepcion si faltan o vienen vacias
        for var in sorted(por_raise - obligatorias):
            crudo = entorno.get(var)
            if var not in entorno or valor_es_vacio(crudo):
                rompen.append(
                    f"[EXIGIDA_POR_CODIGO] {nombre}: {var} se lee sin default y el "
                    f"codigo lanza una excepcion si falta o esta vacia; el compose "
                    f"{'no se la pasa' if var not in entorno else 'se la pasa vacia'}."
                )

        # 1. obligatorias que el compose no pasa
        for var in sorted(obligatorias - set(entorno)):
            rompen.append(
                f"[OBLIGATORIA_FALTANTE] {nombre}: el codigo hace "
                f'os.environ["{var}"] y el compose no se la pasa -> KeyError '
                f'al arrancar, o al ejecutarse el proceso que la usa.'
            )

        # 2. vacias que anulan el default del codigo
        for var, crudo in sorted(entorno.items()):
            if valor_es_vacio(crudo) and var in con_default:
                rompen.append(
                    f"[VACIA_ANULA_DEFAULT] {nombre}: el compose declara {var} vacia "
                    f"y el codigo la lee con un default. Vacia NO usa el default: "
                    f"o le das un valor, o sacas la linea del compose."
                )

        # 4. estilo: os.environ sin default en algo que se distribuye
        for var in sorted(obligatorias):
            avisos.append(
                f"[ENVIRON_SIN_DEFAULT] {nombre}: os.environ[\"{var}\"] revienta si "
                f"falta. En on-premise conviene os.getenv con un default razonable."
            )

    # 3. URLs internas que apuntan a un puerto donde el servicio no escucha
    for nombre, cfg in sorted(servicios.items()):
        for var, crudo in sorted(env_del_servicio(cfg).items()):
            for destino, puerto_url in RE_URL_INTERNA.findall(str(crudo or "")):
                if destino not in servicios:
                    continue
                puerto_url = int(puerto_url)
                real = puertos.get(destino)
                if real is None:
                    real = PUERTO_DEFAULT_CONOCIDO.get(destino, "sin default")
                    if real is None:
                        continue  # no arranca; ya lo reporta el chequeo 1
                    if real == "sin default":
                        continue  # no sabemos su puerto: no inventamos
                if real != puerto_url:
                    rompen.append(
                        f"[PUERTO_DESALINEADO] {nombre}.{var} apunta a "
                        f"{destino}:{puerto_url}, pero {destino} escucha en :{real}. "
                        f"El contenedor figura Up y no atiende."
                    )

    for linea in no_verificados:
        print(linea)
    for linea in rompen:
        print(linea)
    for linea in avisos:
        print(linea)

    print()
    print(f"Rompen el arranque: {len(rompen)}   "
          f"Avisos: {len(avisos)}   Sin verificar: {len(no_verificados)}")

    if no_verificados:
        print("FALLA: hubo servicios que no se pudieron verificar. "
              "Un verde parcial no sirve: arregla eso primero.")
        return 1
    if rompen:
        return 1
    if args.estricto and avisos:
        return 1
    print("OK: cada servicio recibe las variables que su codigo exige.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
