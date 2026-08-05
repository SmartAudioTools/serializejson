#!/usr/bin/env python3
"""Table « par catégorie de types » seule (rapide) : la boucle d'itération
du chantier « chaque type sous ×2 de pickle » (05/08/2026).

Usage :  python3 tests/types_seuls.py   (depuis la racine du dépôt)
"""
import importlib.util
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(RACINE)
sys.path.insert(0, ".")
sys.path.insert(0, "tests")
if "rapidjson" not in sys.modules:
    import rapidjson.rapidjson as rj

    sys.modules["rapidjson"] = rj
spec = importlib.util.spec_from_file_location("lb", "tests/lance_benchmarks.py")
lb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lb)

lignes, ecartees = lb.mesure_types_objets()
pires = []
for nom, pk_d, sj_d, pk_l, sj_l in lignes:
    rd, rl = sj_d / pk_d, sj_l / pk_l
    marque = " <== " if max(rd, rl) > 2 else "     "
    pires.append((max(rd, rl), nom))
    print(f"{nom:14s} dumps x{rd:6.2f} ({1e6 * pk_d:8.1f} -> {1e6 * sj_d:8.1f} us)"
          f"   loads x{rl:6.2f} ({1e6 * pk_l:8.1f} -> {1e6 * sj_l:8.1f} us){marque}")
if ecartees:
    print("écartées :", ", ".join(ecartees))
pires.sort(reverse=True)
print("\npriorités :", ", ".join(f"{n} (x{r:.1f})" for r, n in pires[:8]))
