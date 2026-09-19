#!/bin/bash
# Construit rapidjson/libblosc2_serializejson.so : fork déterministe de
# c-blosc2 (commit épinglé + rapidjson/blosc2_determinisme.patch), chargé par
# dlopen à côté du module compilé (serializejson/tools.py).
# Lancé par cibuildwheel (before-all, dans le conteneur manylinux) pour que la
# bibliothèque livrée dans la roue soit compatible manylinux ; utilisable aussi
# à la main, depuis n'importe quel dossier.
set -euo pipefail

BLOSC2_COMMIT=d52cbeec8afb35ada7ea62f04168e5d970d9c40b  # v3.2.3
DEPOT="$(cd "$(dirname "$0")/.." && pwd)"
TRAVAIL="$(mktemp -d)"

git clone --quiet https://github.com/Blosc/c-blosc2 "$TRAVAIL/c-blosc2"
git -C "$TRAVAIL/c-blosc2" checkout --quiet "$BLOSC2_COMMIT"
git -C "$TRAVAIL/c-blosc2" apply "$DEPOT/rapidjson/blosc2_determinisme.patch"

cmake -S "$TRAVAIL/c-blosc2" -B "$TRAVAIL/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED=ON -DBUILD_STATIC=OFF \
    -DBUILD_TESTS=OFF -DBUILD_FUZZERS=OFF -DBUILD_BENCHMARKS=OFF \
    -DBUILD_EXAMPLES=OFF -DBUILD_PLUGINS=OFF \
    -DPREFER_EXTERNAL_ZSTD=OFF -DPREFER_EXTERNAL_ZLIB=OFF -DPREFER_EXTERNAL_LZ4=OFF
cmake --build "$TRAVAIL/build" --parallel "$(nproc)"

cp -L "$TRAVAIL/build/blosc/libblosc2.so" "$DEPOT/rapidjson/libblosc2_serializejson.so"
rm -rf "$TRAVAIL"
