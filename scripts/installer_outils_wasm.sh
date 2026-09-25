#!/bin/bash
# Outils pour compiler serializejson (rapidjson + blosc2) en WebAssembly pour le Pyodide-Qt du lecteur web
# (QCM/web/pyqt6/pyodide-qt : Pyodide 0.29.3 / 0.30.0-dev, Python 3.13.2, plateforme emscripten_4_0_9).
# À lancer depuis le compte principal : il faut le réseau, que le bac à sable de Claude n'a pas.
# Tout va sous /DATA/Python/outils_wasm, lisible ensuite par Claude, qui compile hors ligne.
set -euo pipefail
D=/DATA/Python/outils_wasm
PY=/DATA/Python/SmartPython/CachyOS/versions/SmartPython/bin/python   # 3.13, comme la cible
mkdir -p "$D"
cd "$D"

[ -d emsdk ] || git clone https://github.com/emscripten-core/emsdk.git
emsdk/emsdk install 4.0.9
emsdk/emsdk activate 4.0.9

[ -d venv-pyodide ] || "$PY" -m venv venv-pyodide
venv-pyodide/bin/pip install -U pyodide-build
venv-pyodide/bin/pyodide xbuildenv install 0.29.3 --path "$D/xbuildenv"

echo "--- vérification"
emsdk/upstream/emscripten/emcc --version | head -1
venv-pyodide/bin/pyodide config get emscripten_version
venv-pyodide/bin/pyodide config get python_version
