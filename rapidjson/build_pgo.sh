#!/bin/sh
# Construit le module rapidjson en deux passes PGO pour l'interpréteur donné :
# 1. compilation instrumentée (-fprofile-generate) ;
# 2. exécution de la batterie de tests et de pgo_workload.py (profils .gcda
#    écrits dans le dossier de build) ;
# 3. recompilation guidée (-fprofile-use).
# Usage, depuis le dossier rapidjson/ : ./build_pgo.sh /chemin/vers/python3
set -e
PY="$1"
test -n "$PY" || { echo "usage : $0 /chemin/vers/python3" >&2; exit 1; }

touch rapidjson.cpp
SERIALIZEJSON_PGO=generate "$PY" setup.py build_ext --inplace >/dev/null

(
    cd ..
    # sortie NON masquée : un échec sortait d'ici en silence (set -e), en
    # laissant en place le .so INSTRUMENTÉ de la passe 1, qu'on croyait final
    "$PY" -m pytest tests/ -q -p no:typeguard
    "$PY" rapidjson/pgo_workload.py
    git checkout -- tests/serialized/ my_list.json 2>/dev/null || true
)

touch rapidjson.cpp
SERIALIZEJSON_PGO=use "$PY" setup.py build_ext --inplace >/dev/null
echo "PGO terminé pour $PY"
