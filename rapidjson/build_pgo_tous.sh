#!/bin/bash
# Reconstruit l'extension en PGO pour les cinq versions de Python.
# (Vit dans le dépôt : un script d'outillage posé dans /tmp peut être
# moissonné par le nettoyeur en cours de nuit — vécu le 05/08/2026.)
cd "$(dirname "$0")" || exit 1
for v in 3.10.20 3.11.15 3.12.13 3.13.14 3.14.6; do
    echo "=== PGO $v ==="
    bash build_pgo.sh \
        "/DATA/Python/SmartPython/CachyOS/versions/SmartPython-${v}_2026-07-26/bin/python3" \
        2>&1 | grep -iE "error|erreur :|FAIL" | grep -v BLOSC_TRACE | head -5
done
echo TERMINE
