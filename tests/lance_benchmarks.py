#!/usr/bin/env python3
"""Benchmarks serializejson (défaut « smart ») contre pickle : rapport daté
en Markdown et PDF, destiné à étayer la documentation par des mesures.

Usage :  python3 tests/lance_benchmarks.py  [dossier_de_sortie]
(à lancer depuis la racine du dépôt, machine CALME ; par défaut les rapports
datés .md et .pdf sont écrits dans rapports_benchmarks/)

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


BLEU, ORANGE = "#2b6cb0", "#dd6b20"

# supports de stockage POPULAIRES, débits séquentiels constructeurs
# approximatifs — repères verticaux des graphiques de scénario
SUPPORTS = [("Seagate BarraCuda\n(disque dur, ~190 Mo/s)", 190e6),
            ("Samsung 870 EVO\n(SSD SATA, ~560 Mo/s)", 560e6),
            ("Samsung 970 EVO Plus\n(NVMe PCIe 3, ~3,5 Go/s)", 3.5e9),
            ("WD Black SN850X\n(NVMe PCIe 4, ~7 Go/s)", 7e9),
            ("Crucial T705\n(NVMe PCIe 5, ~14 Go/s)", 14e9)]

# machines RÉALISTES : couples CPU + stockage d'une même gamme. Facteur de
# calcul approximatif relatif à la machine de mesure (indices publics), et
# débit du stockage TEL QUE VU par la machine — un NVMe sur Raspberry Pi 5
# est bridé par l'unique ligne PCIe 2.0 du HAT (~450 Mo/s), un MacBook M4
# a son SSD soudé (~6 Go/s), la tour PCIe 5 exploite un Crucial T705
MACHINES = [("Raspberry Pi 5\n+ microSD (~90 Mo/s)", 0.25, 90e6),
            ("Raspberry Pi 5 + NVMe\nsur HAT PCIe 2.0 (~450 Mo/s)", 0.25,
             450e6),
            ("portable 2018 i5-8250U\n+ SSD SATA (~560 Mo/s)", 0.55, 560e6),
            ("i7 mobile (mesure)\n+ NVMe PCIe 3 (~3,5 Go/s)", 1.0, 3.5e9),
            ("MacBook Pro M4\n+ SSD interne (~6 Go/s)", 1.7, 6e9),
            ("tour Ryzen 9 9950X\n+ NVMe PCIe 5 (~14 Go/s)", 1.8, 14e9)]


def figure_barres(resultats, sens, titre):
    # deux barres par profil : rapport de mémoire (bleu) et de temps
    # (orange), échelle log — une barre PETITE = avantage serializejson
    import matplotlib.pyplot as plt

    noms = [nom for nom, _ in resultats]
    rapport_poids = numpy.array(
        [m["taille_sj"] / m["taille_pickle"] for _, m in resultats])
    rapport_temps = numpy.array(
        [m[f"{sens}_sj"] / m[f"{sens}_pickle"] for _, m in resultats])
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    x = numpy.arange(len(noms))
    b1 = ax.bar(x - 0.21, rapport_poids, 0.4, color=BLEU,
                label="rapport de mémoire"
                      "  (poids serializejson / poids pickle)")
    b2 = ax.bar(x + 0.21, rapport_temps, 0.4, color=ORANGE,
                label=f"rapport de temps {sens}"
                      f"  (temps serializejson / temps pickle)")
    for barres in (b1, b2):
        for barre in barres:
            v = barre.get_height()
            ax.annotate(f"×{v:.2f}",
                        (barre.get_x() + barre.get_width() / 2, v),
                        ha="center", va="bottom", fontsize=7)
    ax.axhline(1.0, color="gray", ls="--", lw=1)
    ax.text(-0.45, 1.04, "égalité ×1", color="gray", fontsize=8, ha="left")
    ax.set_yscale("log")
    ax.set_ylim(bottom=min(rapport_poids.min(), rapport_temps.min()) * 0.55,
                top=max(rapport_poids.max(), rapport_temps.max()) * 2.4)
    ax.set_yticks([0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10])
    ax.set_yticklabels(["×0,05", "×0,1", "×0,2", "×0,5", "×1", "×2", "×5",
                        "×10"])
    ax.set_xticks(x)
    ax.set_xticklabels(noms, rotation=18, ha="right", fontsize=8)
    ax.set_title(titre + " — en dessous de ×1 : avantage serializejson")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    return fig


def figure_support(resultats, sens, titre):
    # temps TOTAL (calcul + transfert) selon le débit du support :
    # l'avantage de poids se change en avantage de temps dès que le
    # support est le goulot
    import matplotlib.pyplot as plt

    debits = numpy.logspace(numpy.log10(80e6), numpy.log10(17e9), 200)
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    for (nom, m), couleur in zip(
            resultats, plt.cm.tab10(numpy.linspace(0, 1, len(resultats)))):
        t_pk = m[f"{sens}_pickle"] + m["taille_pickle"] / debits
        t_sj = m[f"{sens}_sj"] + m["taille_sj"] / debits
        ax.plot(debits / 1e6, t_sj / t_pk, color=couleur, label=nom)
    ax.axhline(1.0, color="gray", ls="--", lw=1)
    ax.set_xscale("log")
    ax.set_yscale("log")
    for etiquette, debit in SUPPORTS:
        ax.axvline(debit / 1e6, color="lightgray", lw=0.8)
        ax.annotate(etiquette, (debit / 1e6, 0.015), xycoords=("data",
                    "axes fraction"), fontsize=7, color="gray",
                    ha="center", va="bottom")
    ax.set_yticks([0.1, 0.2, 0.5, 1, 2, 5])
    ax.set_yticklabels(["×0,1", "×0,2", "×0,5", "×1", "×2", "×5"])
    ax.set_xlabel("débit du support (Mo/s, échelle log)")
    ax.set_ylabel("temps total serializejson / temps total pickle")
    ax.set_title(titre + " — en dessous de ×1 : avantage serializejson")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    return fig


def figure_machines(resultats, sens, titre):
    # UN graphique, une machine réaliste (couple CPU + stockage de même
    # gamme) par position : deux barres — temps total d'écriture et de
    # lecture (calcul mis à l'échelle du CPU + transfert au débit du
    # stockage) — une barre PETITE = avantage serializejson
    import matplotlib.pyplot as plt

    profil = "signal lisse int16 (4 Mo)"
    m = dict(resultats)[profil]
    noms = [nom for nom, _, _ in MACHINES]
    rapports = {}
    for cle in ("dumps", "loads"):
        valeurs = []
        for _, facteur, debit in MACHINES:
            t_pk = m[f"{cle}_pickle"] / facteur + m["taille_pickle"] / debit
            t_sj = m[f"{cle}_sj"] / facteur + m["taille_sj"] / debit
            valeurs.append(t_sj / t_pk)
        rapports[cle] = numpy.array(valeurs)
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    x = numpy.arange(len(noms))
    b1 = ax.bar(x - 0.21, rapports["dumps"], 0.4, color=BLEU,
                label="écriture  (temps total serializejson / pickle)")
    b2 = ax.bar(x + 0.21, rapports["loads"], 0.4, color=ORANGE,
                label="lecture  (temps total serializejson / pickle)")
    for barres in (b1, b2):
        for barre in barres:
            v = barre.get_height()
            ax.annotate(f"×{v:.2f}",
                        (barre.get_x() + barre.get_width() / 2, v),
                        ha="center", va="bottom", fontsize=8)
    ax.axhline(1.0, color="gray", ls="--", lw=1)
    ax.text(-0.45, 1.03, "égalité ×1", color="gray", fontsize=8, ha="left")
    ax.set_yscale("log")
    ax.set_ylim(bottom=min(rapports["dumps"].min(),
                           rapports["loads"].min()) * 0.55,
                top=max(rapports["dumps"].max(),
                        rapports["loads"].max()) * 1.9)
    ax.set_yticks([0.2, 0.5, 1, 2])
    ax.set_yticklabels(["×0,2", "×0,5", "×1", "×2"])
    ax.yaxis.set_minor_formatter(plt.NullFormatter())
    ax.set_xticks(x)
    ax.set_xticklabels(noms, fontsize=8)
    ax.set_title(titre + f" — profil « {profil} » —"
                 " sous ×1 : avantage serializejson", fontsize=11)
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    return fig


FIGURES = [
    ("benchmark_dumps", figure_barres, "dumps",
     "conversion vers bytes (dumps)"),
    ("benchmark_loads", figure_barres, "loads",
     "conversion depuis bytes (loads)"),
    ("benchmark_ecriture_support", figure_support, "dumps",
     "écriture sur un support (dumps + transfert)"),
    ("benchmark_lecture_support", figure_support, "loads",
     "lecture depuis un support (transfert + loads)"),
    ("benchmark_machines", figure_machines, "",
     "machines réalistes (CPU + stockage de même gamme)"),
]


def rendu_pdf_et_svg(resultats, entete, chemin_pdf, dossier_svg):
    # chaque figure part dans le PDF daté ET en SVG à nom STABLE (référencé
    # par la documentation : chaque run les rafraîchit sans casser les liens)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(chemin_pdf) as pdf:
        fig, ax = plt.subplots(figsize=(11.69, 8.27))
        ax.axis("off")
        ax.text(0.5, 0.9, "serializejson (défaut « smart ») contre pickle",
                ha="center", fontsize=18, weight="bold")
        ax.text(0.05, 0.78, "\n\n".join(ligne.lstrip("- ") for ligne in entete),
                fontsize=10, va="top", wrap=True)
        ax.text(0.05, 0.30,
                "Lecture des graphiques : toutes les valeurs sont des"
                " rapports serializejson / pickle —\nen dessous de la ligne"
                " ×1 (barre ou courbe PETITE), l'avantage est à"
                " serializejson.\n\n"
                "Pages 2-3 : conversion vers puis depuis bytes (mémoire et"
                " temps de calcul purs).\nPages 4-5 : scénarios"
                " d'écriture puis de lecture sur un support, temps de\n"
                "transfert compris, en fonction du débit (disque dur,"
                " SSD SATA, NVMe...).",
                fontsize=10, va="top")
        pdf.savefig(fig)
        plt.close(fig)
        for nom_svg, fabrique, sens, titre in FIGURES:
            fig = fabrique(resultats, sens, titre)
            pdf.savefig(fig)
            if dossier_svg is not None:
                fig.savefig(dossier_svg / f"{nom_svg}.svg", format="svg")
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
    dossier = (Path(sys.argv[1]) if len(sys.argv) > 1
               else RACINE / "rapports_benchmarks")
    chemin_md = dossier / f"rapport_benchmarks_{horodatage}.md"
    chemin_pdf = dossier / f"rapport_benchmarks_{horodatage}.pdf"
    dossier_svg = RACINE / "docs_source" / "images"
    dossier_svg.mkdir(parents=True, exist_ok=True)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin_md.write_text(markdown)
    rendu_pdf_et_svg(resultats, entete, chemin_pdf, dossier_svg)
    print(markdown)
    print("->", chemin_md)
    print("->", chemin_pdf)
