#!/usr/bin/env python3
"""Benchmarks serializejson (défaut « smart ») contre pickle : rapport daté
en Markdown et PDF, destiné à étayer la documentation par des mesures.

Usage :  python3 tests/lance_benchmarks.py  [dossier_de_sortie]
(à lancer depuis la racine du dépôt, machine CALME ; par défaut les rapports
sont écrits dans tests/rapport_benchmarks_<date>.md et .pdf)

Ce qui est mesuré, de bout en bout et à réglages PAR DÉFAUT des deux côtés :
  - taille : len(pickle.dumps(x, protocole 4)) contre
    len(serializejson.dumps(x)) — base64 et enveloppe JSON COMPRIS ;
  - temps : dumps et loads complets, alternés dans le même processus,
    burst de réveil CPU avant chaque chrono, médiane de ~50 essais ;
  - seuil de débit : le débit de stockage/réseau en dessous duquel
    serializejson devient AUSSI plus rapide que pickle, temps de
    lecture/écriture du support compris — (octets épargnés) / (surcoût
    de calcul). Au-dessus du seuil, pickle reste plus rapide en local ;
    en dessous (disque réseau, cloud, USB...), serializejson gagne sur
    les deux tableaux.
"""
import datetime
import pickle
import statistics
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
if "rapidjson" not in sys.modules:
    import rapidjson.rapidjson as _rapidjson_compile

    sys.modules["rapidjson"] = _rapidjson_compile
import serializejson  # noqa: E402  (charge libblosc2)
import numpy  # noqa: E402

perf = time.perf_counter


def burst():
    # réveille le CPU (sortie des états d'économie) juste avant un chrono
    t0 = perf()
    x = 1.0
    while perf() - t0 < 0.01:
        x *= 1.0000001
    return x


def chrono(f, essais=50, plafond=2.0):
    # médiane de ~50 essais (robuste aux pointes de charge), plafond de
    # temps par case sans descendre sous 9 essais
    burst()
    f()
    t = perf()
    f()
    duree = perf() - t
    n = max(9, min(essais, int(plafond / max(1e-5, duree))))
    temps = []
    for _ in range(n):
        burst()
        t0 = perf()
        f()
        temps.append(perf() - t0)
    return statistics.median(temps)


def profils():
    # données synthétiques DÉTERMINISTES (mêmes octets à chaque run),
    # représentatives des usages : audio, mesures, images, et le pire cas
    # honnête (bruit incompressible)
    rng = numpy.random.default_rng(5)
    t = numpy.linspace(0, 60, 500_000)
    voix = numpy.zeros(400_000, numpy.int64)
    for debut in range(50_000, 400_000, 100_000):
        fin = debut + 50_000
        tt = numpy.arange(fin - debut)
        voix[debut:fin] = (8000 * numpy.sin(tt * 0.11)
                           + rng.integers(-40, 41, fin - debut))
    mid = (9000 * numpy.sin(t) + rng.integers(-200, 201, len(t)))
    side = rng.integers(-60, 61, len(t))
    stereo = numpy.stack([mid + side, mid - side], 1).astype(numpy.int16)
    a2496 = ((stereo[:250_000].astype(numpy.int32)) << 8) + rng.integers(
        -128, 128, (250_000, 2), dtype=numpy.int32)
    x, y = numpy.meshgrid(numpy.arange(2000), numpy.arange(1000))
    return [
        ("audio voix int16 (0,8 Mo)", voix.astype(numpy.int16)),
        ("audio stéréo int16 (2 Mo)", stereo),
        ("audio 24 bits/96 kHz int32 (2 Mo)", a2496),
        ("timestamps triés int64 (4 Mo)",
         (numpy.cumsum(rng.integers(100, 200, 500_000))
          + 1_700_000_000_000_000).astype(numpy.int64)),
        ("signal lisse int16 (4 Mo)",
         (10000 * numpy.sin(numpy.linspace(0, 60, 2_000_000))
          + rng.integers(-5, 5, 2_000_000)).astype(numpy.int16)),
        ("float64 lisse (8 Mo)",
         numpy.sin(numpy.linspace(0, 100, 1_000_000))
         + rng.normal(0, 1e-9, 1_000_000)),
        ("surface lisse int32 (8 Mo)",
         (1000 * numpy.sin(x / 50) + 800 * numpy.cos(y / 70)).astype(numpy.int32)),
        ("bruit int16, incompressible (1 Mo)",
         rng.integers(-30000, 30000, 500_000).astype(numpy.int16)),
    ]


def mesure(tableau):
    a = numpy.ascontiguousarray(tableau)
    p = pickle.dumps(a, protocol=4)
    j = serializejson.dumps(a)
    r = serializejson.loads(j)
    assert isinstance(r, numpy.ndarray) and numpy.array_equal(r, a)
    m = {
        "nbytes": a.nbytes,
        "taille_pickle": len(p),
        "taille_sj": len(j),
        "dumps_pickle": chrono(lambda: pickle.dumps(a, protocol=4)),
        "dumps_sj": chrono(lambda: serializejson.dumps(a)),
        "loads_pickle": chrono(lambda: pickle.loads(p)),
        "loads_sj": chrono(lambda: serializejson.loads(j)),
    }
    # seuil de débit (écriture) : en dessous, dump+écriture sur le support
    # est plus rapide avec serializejson malgré le calcul de compression
    surcout = m["dumps_sj"] - m["dumps_pickle"]
    epargne = m["taille_pickle"] - m["taille_sj"]
    m["seuil"] = (epargne / surcout) if (surcout > 0 and epargne > 0) else None
    return m


def fmt_octets(n):
    return f"{n / 1e6:.2f} Mo" if n >= 1e6 else f"{n / 1e3:.0f} Ko"


def geometrique(valeurs):
    valeurs = [v for v in valeurs if v]
    return float(numpy.exp(numpy.mean(numpy.log(valeurs)))) if valeurs else None


def rendu_markdown(resultats, entete):
    md = ["# serializejson (défaut « smart ») contre pickle — mesures", "",
          *entete, "",
          "| profil | pickle | serializejson | poids | dumps | loads |"
          " support plus lent que |",
          "|---|---|---|---|---|---|---|"]
    poids, dumps, loads = [], [], []
    for nom, m in resultats:
        rp = m["taille_sj"] / m["taille_pickle"]
        rd = m["dumps_sj"] / m["dumps_pickle"]
        rl = m["loads_sj"] / m["loads_pickle"]
        poids.append(rp)
        dumps.append(rd)
        loads.append(rl)
        gras = lambda texte, gagne: f"**{texte}**" if gagne else texte
        seuil = (f"{m['seuil'] / 1e6:.0f} Mo/s" if m["seuil"]
                 else "— (déjà plus rapide)" if m["dumps_sj"] <= m["dumps_pickle"]
                 else "—")
        md.append(
            f"| {nom} | {fmt_octets(m['taille_pickle'])}"
            f" | {fmt_octets(m['taille_sj'])}"
            f" | {gras(f'{100 * rp:.0f} %', rp < 1)}"
            f" | {gras(f'×{rd:.2f}', rd < 1)}"
            f" | {gras(f'×{rl:.2f}', rl < 1)}"
            f" | {seuil} |")
    md += ["",
           f"**Synthèse (moyennes géométriques)** : poids"
           f" **{100 * geometrique(poids):.0f} %** de pickle, dumps"
           f" ×{geometrique(dumps):.2f}, loads ×{geometrique(loads):.2f}.",
           "",
           "Lecture du tableau : poids en % de pickle et temps en rapport"
           " ×t/t_pickle (moins de 100 % / ×1,00 = serializejson gagne, en"
           " gras). « Support plus lent que » : débit de stockage ou de"
           " réseau en dessous duquel serializejson est AUSSI plus rapide"
           " que pickle en écriture, temps de transfert compris — pickle ne"
           " fait qu'une recopie mémoire (~20 Go/s en cache), il reste donc"
           " devant sur machine locale chaude ; dès que les octets doivent"
           " traverser un disque, un réseau ou un cloud, le poids gagné fait"
           " gagner le temps total.",
           "",
           "Avantages non mesurables ici, pour mémoire : JSON lisible et"
           " diffable, chargement sans exécution de code arbitraire"
           " (contrairement à pickle), fichiers relisibles depuis d'autres"
           " langages, mise à jour d'objets existants, ajout en fin de"
           " fichier (append).", ""]
    return "\n".join(md)


def rendu_pdf(texte_markdown, chemin):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    lignes = texte_markdown.replace("**", "").splitlines()
    with PdfPages(chemin) as pdf:
        for debut in range(0, len(lignes), 48):
            fig, ax = plt.subplots(figsize=(11.69, 8.27))  # A4 paysage
            ax.axis("off")
            ax.text(0.01, 0.99, "\n".join(lignes[debut:debut + 48]),
                    fontsize=7, family="monospace", va="top", wrap=True)
            pdf.savefig(fig)
            plt.close(fig)


if __name__ == "__main__":
    date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    commit = subprocess.run(["git", "log", "--oneline", "-1"], cwd=RACINE,
                            capture_output=True, text=True).stdout.strip()
    charge = Path("/proc/loadavg").read_text().split()[0] \
        if Path("/proc/loadavg").exists() else "?"
    entete = [
        f"- date : {date} — commit : {commit}",
        f"- Python {sys.version.split()[0]}, charge machine au départ"
        f" (loadavg 1 min) : {charge}",
        "- réglages PAR DÉFAUT des deux côtés : pickle protocole 4 ;"
        " serializejson défaut (chaîne « smart » : dérivée par blocs →"
        " zigzag → bitshuffle → zstd niveau 1, base64 et JSON compris)",
        "- médiane de ~50 essais, burst de réveil CPU avant chaque chrono,"
        " mesures alternées dans le même processus",
    ]
    resultats = []
    for nom, tableau in profils():
        print("profil :", nom)
        resultats.append((nom, mesure(tableau)))
    markdown = rendu_markdown(resultats, entete)
    horodatage = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    dossier = Path(sys.argv[1]) if len(sys.argv) > 1 else RACINE / "tests"
    chemin_md = dossier / f"rapport_benchmarks_{horodatage}.md"
    chemin_pdf = dossier / f"rapport_benchmarks_{horodatage}.pdf"
    chemin_md.write_text(markdown)
    rendu_pdf(markdown, chemin_pdf)
    print(markdown)
    print("->", chemin_md)
    print("->", chemin_pdf)
