#!/bin/bash
# Construit serializejson pour WebAssembly (Pyodide 0.29.3 : Python 3.13.2, emscripten 4.0.9), dans
# dist_wasm/serializejson : le paquet python, le module rapidjson compilé en side module wasm et le fork
# déterministe de blosc2 (libblosc2_serializejson.so, wasm lui aussi), que tools.py charge par dlopen.
# Le chiffrement ne dépend d'aucun paquet à télécharger : libsodium (clone épinglé dans libsodium/) est
# LIÉE dans le module rapidjson, comme en natif (rapidjson/libsodium_statique.py).
# Hors ligne : les outils viennent de scripts/installer_outils_wasm.sh (à lancer une fois, avec le réseau),
# et les sources de lz4/zlib-ng/zstd du dossier _deps de la construction native de c-blosc2.
# Les .so natifs de rapidjson/ ne sont pas touchés.
set -euo pipefail

OUTILS=/DATA/Python/outils_wasm
DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
SORTIE="$DEPOT/dist_wasm"
TRAVAIL="$(mktemp -d)"
trap 'rm -rf "$TRAVAIL"' EXIT

source "$OUTILS/emsdk/emsdk_env.sh" > /dev/null
export EM_CACHE="${EM_CACHE:-$OUTILS/em_cache_$(id -un)}"
SITE="$(ls -d "$OUTILS"/venv-pyodide/lib/python3.*/site-packages)"
RACINE="$OUTILS/xbuildenv/0.29.3/xbuildenv/pyodide-root"
PY_INCLUDE="$(ls -d "$RACINE"/cpython/installs/python-*/include/python3.*)"

# drapeaux des side modules de Pyodide (pyodide config get cflags / ldflags)
export SIDE_MODULE_CFLAGS="-O2 -g0 -fPIC -fwasm-exceptions -sSUPPORT_LONGJMP"
export SIDE_MODULE_LDFLAGS="-O2 -g0 -s WASM_BIGINT -fwasm-exceptions -sSUPPORT_LONGJMP -s SIDE_MODULE=1"

# --- blosc2. WITH_RUNTIME_CPU_DETECTION=OFF est INDISPENSABLE : la table de fonctions de zlib-ng
# (functable) appelle adler32_stub avec un argument de moins que sa signature, ce que x86 tolère et que
# wasm refuse à la compilation du module (« not enough arguments on the stack »). Le symptôme est
# trompeur : wasm-opt échoue au lien, et un lien en -O0 qui le contourne donne un module invalide,
# que dlopen rejette au chargement — tools.py conclut alors « symboles blosc2 introuvables ».
B="$DEPOT/c-blosc2"
DEPS="$B/build/_deps"
for d in lz4-src zlib_ng-src zstd-src; do
    [ -d "$DEPS/$d" ] || { echo "manque $DEPS/$d : construire d'abord c-blosc2 en natif" >&2; exit 1; }
done
cmake -S "$B" -B "$TRAVAIL/blosc2" \
    -DCMAKE_TOOLCHAIN_FILE="$SITE/pyodide_build/tools/cmake/Modules/Platform/Emscripten.cmake" \
    -DCMAKE_CROSSCOMPILING_EMULATOR="$(command -v node)" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED=ON -DBUILD_STATIC=OFF -DBUILD_SHARED_LIBS=OFF \
    -DBUILD_TESTS=OFF -DBUILD_FUZZERS=OFF -DBUILD_BENCHMARKS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_PLUGINS=OFF \
    -DPREFER_EXTERNAL_ZSTD=OFF -DPREFER_EXTERNAL_ZLIB=OFF -DPREFER_EXTERNAL_LZ4=OFF \
    -DDEACTIVATE_SSE2=ON -DDEACTIVATE_AVX2=ON -DDEACTIVATE_AVX512=ON \
    -DWITH_OPTIM=OFF -DWITH_NATIVE_INSTRUCTIONS=OFF -DWITH_RUNTIME_CPU_DETECTION=OFF -DZLIB_ENABLE_TESTS=OFF \
    -DBLOSC_LZ4_SOURCE_DIR="$DEPS/lz4-src" \
    -DBLOSC_ZLIBNG_SOURCE_DIR="$DEPS/zlib_ng-src" \
    -DBLOSC_ZSTD_SOURCE_DIR="$DEPS/zstd-src" > "$TRAVAIL/cmake.log"
cmake --build "$TRAVAIL/blosc2" --parallel "$(nproc)" > "$TRAVAIL/build.log"

# --- libsodium, recette de son dist-build/emscripten.sh (sans pthreads, sans asm), hors de l'arbre source.
# Seules scrypt et l'AEAD ChaCha20-Poly1305 servent : le lien n'en garde que ~15 Kio. sodium_init n'est
# jamais appelé (son randombytes passe par EM_ASM) : les implémentations de référence sont celles par défaut
S="$DEPOT/libsodium"
SODIUM_COMMIT=77e1ce5d6dee871c49ef211222ba18ef0c486bda   # 1.0.22-RELEASE
[ "$(git -c safe.directory='*' -C "$S" rev-parse HEAD)" = "$SODIUM_COMMIT" ] || {
    echo "libsodium/ n'est pas au commit $SODIUM_COMMIT :" >&2
    echo "git clone --branch 1.0.22-RELEASE https://github.com/jedisct1/libsodium.git $S" >&2; exit 1; }
mkdir -p "$TRAVAIL/sodium"
(cd "$TRAVAIL/sodium" && emconfigure "$S/configure" --disable-shared --without-pthreads --disable-ssp \
    --disable-asm --disable-pie CFLAGS="$SIDE_MODULE_CFLAGS" > configure.log && emmake make -j"$(nproc)" > make.log)

# --- le module rapidjson, libsodium liée dedans
SRC="$DEPOT/rapidjson"
em++ -c $SIDE_MODULE_CFLAGS -I"$PY_INCLUDE" -I"$SRC" \
    -DPYTHON_RAPIDJSON_VERSION="\"$(cat "$SRC/version.txt")\"" \
    "$SRC/rapidjson.cpp" -o "$TRAVAIL/rapidjson.o"
SUFFIXE=.cpython-313-wasm32-emscripten.so

# --- le paquet : sources python, puis les deux modules wasm à côté (tools.py cherche la libblosc2
# dans le dossier du module rapidjson)
PAQUET="$TRAVAIL/paquet"
mkdir -p "$PAQUET"
cp -r "$DEPOT/serializejson" "$PAQUET/"
find "$PAQUET" \( -name __pycache__ -o -name .claude \) -prune -exec rm -rf {} +
find "$PAQUET" -name "*.so" -delete
em++ $SIDE_MODULE_LDFLAGS "$TRAVAIL/rapidjson.o" "$TRAVAIL/sodium/src/libsodium/.libs/libsodium.a" -o "$PAQUET/serializejson/rapidjson$SUFFIXE"
cp -L "$TRAVAIL/blosc2/blosc/libblosc2.so" "$PAQUET/serializejson/libblosc2_serializejson.so"

# un module wasm invalide ne se voit qu'au chargement : le compiler ici
NODE="$(command -v node)"
for so in "$PAQUET"/serializejson/*.so; do
    "$NODE" -e 'new WebAssembly.Module(require("fs").readFileSync(process.argv[1]))' "$so"
done

# --- la roue : c'est par elle que Pyodide (loadPackage) précharge les .so de façon ASYNCHRONE. Un .so
# simplement dépaqueté serait compilé au premier import, en synchrone, ce que Chrome refuse sur le fil
# principal au-delà de 8 Mo
VERSION="$(sed -n "s/^Version //p" "$DEPOT/CHANGELOG.rst" | head -1 | tr -d "\r")"
rm -rf "$SORTIE"
mkdir -p "$SORTIE"
"$OUTILS/venv-pyodide/bin/python" - "$PAQUET" "$SORTIE" "$VERSION" <<'PY'
import base64, hashlib, sys, zipfile
from pathlib import Path
paquet, sortie, version = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
info = f"serializejson-{version}.dist-info"
roue = sortie / f"serializejson-{version}-cp313-cp313-pyemscripten_2025_0_wasm32.whl"
meta = {f"{info}/METADATA": f"Metadata-Version: 2.1\nName: serializejson\nVersion: {version}\nRequires-Dist: apply\n",
        f"{info}/WHEEL": "Wheel-Version: 1.0\nGenerator: construit_wasm.sh\nRoot-Is-Purelib: false\n"
                         "Tag: cp313-cp313-pyemscripten_2025_0_wasm32\n"}
record = []
with zipfile.ZipFile(roue, "w", zipfile.ZIP_DEFLATED) as z:
    def ecrit(nom, octets):
        z.writestr(nom, octets)
        empreinte = base64.urlsafe_b64encode(hashlib.sha256(octets).digest()).rstrip(b"=").decode()
        record.append(f"{nom},sha256={empreinte},{len(octets)}")
    for f in sorted(paquet.rglob("*")):
        if f.is_file():
            ecrit(str(f.relative_to(paquet)), f.read_bytes())
    for nom, texte in meta.items():
        ecrit(nom, texte.encode())
    z.writestr(f"{info}/RECORD", "\n".join(record + [f"{info}/RECORD,,"]) + "\n")
print(roue, roue.stat().st_size // 1024, "Kio")
PY
