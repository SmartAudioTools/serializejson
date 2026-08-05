#!/usr/bin/env python3
"""Batterie de tests serializejson : pytest sur les cinq Pythons, identité
des goldens entre versions, et rapport PDF horodaté.

Usage :  python3 tests/lance_batterie.py  [chemin_du_pdf]
(à lancer depuis la racine du dépôt ; par défaut le PDF est écrit dans
tests/rapport_batterie_<date>.pdf)
"""
import datetime
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
VERSIONS = ["3.10.20", "3.11.15", "3.12.13", "3.13.14", "3.14.6"]
VENV = "/DATA/Python/SmartPython/CachyOS/versions/SmartPython-{v}_2026-07-26/bin/python3"
# les goldens régénérés à chaque run : seuls comptent les octets d'une run
# fraîche, comparés ENTRE versions (times et pickle exclus : sorties de
# pickle lui-même, différentes par version)
EXCLUS = re.compile(r"times|^pickle")


def restaurer_goldens():
    subprocess.run(["git", "checkout", "--", "tests/serialized/", "my_list.json"],
                   cwd=RACINE, capture_output=True)


def lancer():
    resultats = []
    reference = None
    dossier_ref = Path(tempfile.mkdtemp(prefix="batterie_goldens_"))
    for v in VERSIONS:
        restaurer_goldens()
        t0 = time.perf_counter()
        p = subprocess.run([VENV.format(v=v), "-m", "pytest", "-q",
                            "-p", "no:typeguard"],
                           cwd=RACINE, capture_output=True, text=True)
        duree = time.perf_counter() - t0
        derniere = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else p.stderr.strip()[-120:]
        m = re.search(r"(\d+) passed", derniere)
        passes = int(m.group(1)) if m else 0
        m = re.search(r"(\d+) failed", derniere)
        echecs = int(m.group(1)) if m else 0
        # goldens de CETTE run, comparés à la première version
        diffs = []
        for f in sorted((RACINE / "tests/serialized").glob("*.txt")):
            if EXCLUS.search(f.name):
                continue
            if reference is None:
                shutil.copy(f, dossier_ref / f.name)
            else:
                ref = dossier_ref / f.name
                if not ref.exists() or ref.read_bytes() != f.read_bytes():
                    diffs.append(f.name)
        if reference is None:
            reference = v
        resultats.append({"version": v, "passes": passes, "echecs": echecs,
                          "duree": duree, "diffs": diffs,
                          "retour": p.returncode, "ligne": derniere})
    restaurer_goldens()
    shutil.rmtree(dossier_ref, ignore_errors=True)
    return resultats


def rapport_pdf(resultats, chemin):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    commit = subprocess.run(["git", "log", "--oneline", "-1"], cwd=RACINE,
                            capture_output=True, text=True).stdout.strip()
    tout_vert = all(r["retour"] == 0 and not r["echecs"] and not r["diffs"]
                    for r in resultats)

    fig, ax = plt.subplots(figsize=(8.27, 11.69))  # A4 portrait
    ax.axis("off")
    ax.text(0.5, 0.97, "serializejson — rapport de batterie",
            ha="center", fontsize=17, weight="bold")
    ax.text(0.5, 0.935, date, ha="center", fontsize=11)
    ax.text(0.5, 0.91, f"{platform.node()} — {commit}",
            ha="center", fontsize=8, color="gray")
    verdict = "TOUT VERT" if tout_vert else "ÉCHECS — voir détail"
    ax.text(0.5, 0.865, verdict, ha="center", fontsize=14, weight="bold",
            color="green" if tout_vert else "red")

    lignes = [["Python", "tests passés", "échecs", "durée",
               f"goldens ≠ {resultats[0]['version']}"]]
    for r in resultats:
        lignes.append([r["version"], str(r["passes"]), str(r["echecs"]),
                       f"{r['duree']:.1f} s",
                       "—" if not r["diffs"] else f"{len(r['diffs'])} fichier(s)"])
    table = ax.table(cellText=lignes[1:], colLabels=lignes[0],
                     loc="center", bbox=[0.05, 0.55, 0.9, 0.25])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (i, j), cellule in table.get_celld().items():
        if i == 0:
            cellule.set_text_props(weight="bold")
        elif j in (2, 4):
            r = resultats[i - 1]
            rouge = (j == 2 and r["echecs"]) or (j == 4 and r["diffs"])
            if rouge:
                cellule.set_facecolor("#ffdddd")

    y = 0.5
    for r in resultats:
        ax.text(0.05, y, f"{r['version']} : {r['ligne']}", fontsize=7,
                family="monospace")
        y -= 0.018
        for f in r["diffs"]:
            ax.text(0.08, y, f"golden divergent : {f}", fontsize=7,
                    color="red", family="monospace")
            y -= 0.018
    ax.text(0.05, 0.06,
            "Batterie : pytest -q -p no:typeguard sur chaque venv, goldens\n"
            "restaurés entre les runs (git checkout), identité octet à octet\n"
            "des goldens d'une run fraîche entre les cinq versions\n"
            "(times et pickle exclus : sorties de pickle lui-même).",
            fontsize=8, color="gray")
    fig.savefig(chemin, format="pdf")
    return tout_vert


if __name__ == "__main__":
    resultats = lancer()
    defaut = RACINE / "tests" / (
        "rapport_batterie_"
        + datetime.datetime.now().strftime("%Y-%m-%d_%H%M") + ".pdf")
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else defaut
    vert = rapport_pdf(resultats, chemin)
    for r in resultats:
        print(f"{r['version']} : {r['ligne']}"
              + (f"  [goldens ≠ : {', '.join(r['diffs'])}]" if r["diffs"] else ""))
    print(("TOUT VERT — " if vert else "ÉCHECS — ") + str(chemin))
    sys.exit(0 if vert else 1)
