#!/bin/bash
# Consolidation : PGO x5 puis batterie complète (rapport PDF horodaté).
cd "$(dirname "$0")" || exit 1
bash build_pgo_tous.sh
cd .. || exit 1
/DATA/Python/SmartPython/CachyOS/versions/SmartPython-3.12.13_2026-07-26/bin/python3 tests/lance_batterie.py 2>&1 | tail -7
