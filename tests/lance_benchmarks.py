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

sys.path.insert(0, str(RACINE / "tests"))
import bench_pyperformance_pickle  # noqa: E402  (benchs officiels répliqués)

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


def _images_classiques():
    # les images des benchmarks de compression sont lues dans
    # images_benchmarks/ : tout fichier déposé là entre dans la matrice
    # (.png/.tif/.bmp... via PIL, .npy via numpy — le .npy porte les
    # profondeurs que PNG/PIL ne savent pas écrire, comme le RVB 10 bits).
    # Le dépôt fournit classiques/ (cameraman, moon, astronaut en 8/10/16
    # bits), kodak/ et usc_sipi/ — AUCUNE donnée synthétique : que du corpus
    dossier = RACINE / "images_benchmarks"
    images = []
    if dossier.is_dir():
        # un SOUS-DOSSIER par corpus (classiques/, kodak/, clic/...) : le nom
        # du corpus préfixe le profil ; les fichiers à la racine passent aussi
        for chemin in sorted(dossier.rglob("*")):
            if not chemin.is_file():
                continue
            try:
                if chemin.suffix == ".npy":
                    tableau = numpy.load(chemin)
                elif chemin.suffix.lower() in (".png", ".tif", ".tiff",
                                               ".bmp", ".pgm", ".ppm"):
                    from PIL import Image

                    tableau = numpy.asarray(Image.open(chemin))
                else:
                    continue
            except Exception:
                continue
            corpus = chemin.parent.relative_to(dossier)
            prefixe = f"{corpus} " if str(corpus) != "." else ""
            nom = prefixe + chemin.stem.replace("_", " ")
            images.append((f"{nom} ({tableau.nbytes / 1e6:.1f} Mo)",
                           numpy.ascontiguousarray(tableau)))
    return images


def _sons_classiques():
    # sons CLASSIQUES des benchmarks de codecs (corpus EBU SQAM : glockenspiel,
    # castagnettes, voix...) : non redistribuables avec le dépôt — déposer des
    # .wav / .flac dans sons_benchmarks/ (télécharger sur tech.ebu.ch) et ils
    # entrent d'eux-mêmes dans la matrice ; sans dossier, rien n'est ajouté
    dossier = RACINE / "sons_benchmarks"
    if not dossier.is_dir():
        return []
    try:
        import soundfile
    except Exception:
        return []
    sons = []
    # un SOUS-DOSSIER par corpus (sqam/...), comme pour les images
    for chemin in sorted(dossier.rglob("*")):
        if not chemin.is_file() or chemin.suffix.lower() not in (".wav",
                                                                 ".flac"):
            continue
        try:
            donnees, _ = soundfile.read(chemin, dtype="int16")
        except Exception:
            continue
        corpus = chemin.parent.relative_to(dossier)
        prefixe = f"{corpus} " if str(corpus) != "." else ""
        sons.append((f"{prefixe}{chemin.stem} int16"
                     f" ({donnees.nbytes / 1e6:.1f} Mo)",
                     numpy.ascontiguousarray(donnees)))
    return sons


def profils():
    # QUE des données de CORPUS (demande de Baptiste, 05/08 soir) : les
    # images de images_benchmarks/ et les sons de sons_benchmarks/ — aucune
    # donnée synthétique pour évaluer la compression binaire. Un profil
    # HORS CACHE est bâti en concaténant les images du corpus répétées
    # jusqu'à ~200 Mo APRÈS dérangement de l'ordre des blocs (une répétition
    # à l'identique serait un cadeau irréaliste fait à zstd)
    liste = [*_images_classiques(), *_sons_classiques()]
    if not liste:
        raise SystemExit(
            "aucun corpus : déposer des images dans images_benchmarks/ et"
            " des sons dans sons_benchmarks/ (voir les commentaires du"
            " script) — les données synthétiques ont été retirées")
    rng = numpy.random.default_rng(5)
    morceaux = []
    total = 0
    sources = [t for _, t in liste]
    while total < 200_000_000:
        tableau = sources[rng.integers(0, len(sources))]
        octets = numpy.frombuffer(tableau.tobytes(), dtype=numpy.uint8)
        decalage = int(rng.integers(0, len(octets)))
        morceaux.append(numpy.roll(octets, decalage))
        total += len(octets)
    hors_cache = numpy.concatenate(morceaux)
    liste.append((f"corpus concaténé, hors cache"
                  f" ({hors_cache.nbytes / 1e6:.0f} Mo)", hors_cache))
    return liste


def mesure_types_objets():
    # le catalogue d'objets du dépôt (tests/objects/basic_objects.py, celui
    # de test_serialize_vs_pickle) : chaque CATÉGORIE de types python est
    # sérialisée en bloc, pickle contre serializejson, dumps et loads —
    # les catégories que l'un des deux camps ne sait pas rejouer aux
    # réglages par défaut sont écartées (et nommées dans le rapport)
    from objects import basic_objects  # tests/ est sur le chemin

    lignes, ecartees = [], []
    for categorie, objets in basic_objects.objects.items():
        try:
            p = pickle.dumps(objets, protocol=4)
            encodeur = serializejson.Encoder(return_bytes=True)
            j = encodeur(objets)
            decodeur = serializejson.Decoder(
                authorized_classes=list(encodeur.get_dumped_classes()))
            pickle.loads(p)
            decodeur(j)
        except Exception:
            ecartees.append(categorie)
            continue
        lignes.append((
            categorie,
            chrono(lambda: pickle.dumps(objets, protocol=4), plafond=0.4),
            chrono(lambda: encodeur(objets), plafond=0.4),
            chrono(lambda: pickle.loads(p), plafond=0.4),
            chrono(lambda: decodeur(j), plafond=0.4),
        ))
    return lignes, ecartees


def mesure(tableau):
    a = numpy.ascontiguousarray(tableau)
    p = pickle.dumps(a, protocol=4)
    j = serializejson.dumps(a)
    r = serializejson.loads(j)
    assert isinstance(r, numpy.ndarray) and numpy.array_equal(r, a)
    # variante « standard » : octet_shuffle → zstd, sans l'étage dérivée
    # de la chaîne smart (bytes_compression_diff_dtypes=None)
    encodeur_std = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=None)
    j_std = encodeur_std(a)
    assert numpy.array_equal(serializejson.loads(j_std), a)
    m = {
        "nbytes": a.nbytes,
        "taille_pickle": len(p),
        "taille_sj": len(j),
        "taille_std": len(j_std),
        "dumps_pickle": chrono(lambda: pickle.dumps(a, protocol=4)),
        "dumps_sj": chrono(lambda: serializejson.dumps(a)),
        "dumps_std": chrono(lambda: encodeur_std(a)),
        "loads_pickle": chrono(lambda: pickle.loads(p)),
        "loads_sj": chrono(lambda: serializejson.loads(j)),
        "loads_std": chrono(lambda: serializejson.loads(j_std)),
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


def rendu_markdown(resultats, pyperf, types_objets, types_ecartes, entete):
    md = ["# serializejson (défaut « smart ») contre pickle — mesures", "",
          *entete, "",
          "| profil | pickle | serializejson | poids | dumps | loads |"
          " poids std | dumps std | loads std | support plus lent que |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    poids, dumps, loads = [], [], []
    poids_std, dumps_std, loads_std = [], [], []
    for nom, m in resultats:
        rp = m["taille_sj"] / m["taille_pickle"]
        rd = m["dumps_sj"] / m["dumps_pickle"]
        rl = m["loads_sj"] / m["loads_pickle"]
        rp2 = m["taille_std"] / m["taille_pickle"]
        rd2 = m["dumps_std"] / m["dumps_pickle"]
        rl2 = m["loads_std"] / m["loads_pickle"]
        poids.append(rp)
        dumps.append(rd)
        loads.append(rl)
        poids_std.append(rp2)
        dumps_std.append(rd2)
        loads_std.append(rl2)
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
            f" | {gras(f'{100 * rp2:.0f} %', rp2 < 1)}"
            f" | {gras(f'×{rd2:.2f}', rd2 < 1)}"
            f" | {gras(f'×{rl2:.2f}', rl2 < 1)}"
            f" | {seuil} |")
    md += ["",
           f"**Synthèse (moyennes géométriques)** : défaut smart — poids"
           f" **{100 * geometrique(poids):.0f} %** de pickle, dumps"
           f" ×{geometrique(dumps):.2f}, loads ×{geometrique(loads):.2f} ;"
           f" variante octet_shuffle → zstd (« std », sans dérivée) — poids"
           f" {100 * geometrique(poids_std):.0f} %, dumps"
           f" ×{geometrique(dumps_std):.2f}, loads"
           f" ×{geometrique(loads_std):.2f}.",
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
           "## catalogue d'objets du dépôt, par catégorie de types python",
           "",
           "Les objets de `tests/objects/basic_objects.py` (ceux de"
           " `test_serialize_vs_pickle`), sérialisés par catégorie, réglages"
           " par défaut des deux côtés (Decoder avec les classes autorisées"
           " du dump).",
           "",
           "| catégorie | dumps pickle (µs) | dumps serializejson (µs) |"
           " rapport | loads pickle (µs) | loads serializejson (µs) |"
           " rapport |",
           "|---|---|---|---|---|---|---|"]
    for nom, pk_d, sj_d, pk_l, sj_l in types_objets:
        rd, rl = sj_d / pk_d, sj_l / pk_l
        td = f"×{rd:.2f}"
        tl = f"×{rl:.2f}"
        md.append(f"| {nom} | {1e6 * pk_d:.1f} | {1e6 * sj_d:.1f} |"
                  f" {'**' + td + '**' if rd < 1 else td}"
                  f" | {1e6 * pk_l:.1f} | {1e6 * sj_l:.1f} |"
                  f" {'**' + tl + '**' if rl < 1 else tl} |")
    if types_ecartes:
        md.append("")
        md.append("Catégories écartées (non rejouables aux réglages par"
                  " défaut d'un des deux camps) : "
                  + ", ".join(types_ecartes) + ".")
    md += ["",
           "## benchmarks pickle officiels (pyperformance, petits objets)",
           "",
           "Les cinq charges de `bm_pickle` de la suite pyperformance,"
           " répliquées à l'identique (mêmes objets, mêmes boucles, meilleur"
           " temps) : une myriade de PETITS dicts, tuples et listes — le"
           " terrain de jeu historique de pickle, sans binaire à compresser.",
           "",
           "| charge officielle | pickle (µs) | serializejson (µs) |"
           " rapport de temps |",
           "|---|---|---|---|"]
    for nom, pk_us, sj_us in pyperf:
        r = sj_us / pk_us
        texte = f"×{r:.2f}"
        md.append(f"| {nom} | {pk_us:.1f} | {sj_us:.1f} |"
                  f" {'**' + texte + '**' if r < 1 else texte} |")
    md += ["",
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


def figure_barres(donnees, sens, titre):
    # deux barres par profil : rapport de mémoire (bleu) et de temps
    # (orange), échelle log — une barre PETITE = avantage serializejson
    import matplotlib.pyplot as plt

    resultats = donnees["profils"]
    noms = [nom for nom, _ in resultats]
    poids_smart = numpy.array(
        [m["taille_sj"] / m["taille_pickle"] for _, m in resultats])
    poids_std = numpy.array(
        [m["taille_std"] / m["taille_pickle"] for _, m in resultats])
    temps_smart = numpy.array(
        [m[f"{sens}_sj"] / m[f"{sens}_pickle"] for _, m in resultats])
    temps_std = numpy.array(
        [m[f"{sens}_std"] / m[f"{sens}_pickle"] for _, m in resultats])
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    x = numpy.arange(len(noms))
    series = [
        (x - 0.30, poids_smart, BLEU, "mémoire, défaut smart"
         "  (poids serializejson / pickle)"),
        (x - 0.10, poids_std, "#93b8dc", "mémoire, octet_shuffle → zstd"),
        (x + 0.10, temps_smart, ORANGE, f"temps {sens}, défaut smart"
         "  (temps serializejson / pickle)"),
        (x + 0.30, temps_std, "#f0b287", f"temps {sens},"
         " octet_shuffle → zstd"),
    ]
    for position, valeurs, couleur, etiquette in series:
        barres = ax.bar(position, valeurs, 0.19, color=couleur,
                        label=etiquette)
        for barre in barres:
            v = barre.get_height()
            ax.annotate(f"×{v:.2f}",
                        (barre.get_x() + barre.get_width() / 2, v),
                        ha="center", va="bottom", fontsize=5.5, rotation=90)
    ax.axhline(1.0, color="gray", ls="--", lw=1)
    ax.text(-0.45, 1.04, "égalité ×1", color="gray", fontsize=8, ha="left")
    ax.set_yscale("log")
    tous = numpy.concatenate([poids_smart, poids_std, temps_smart, temps_std])
    ax.set_ylim(bottom=tous.min() * 0.5, top=tous.max() * 2.8)
    ax.set_yticks([0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10])
    ax.set_yticklabels(["×0,05", "×0,1", "×0,2", "×0,5", "×1", "×2", "×5",
                        "×10"])
    ax.set_xticks(x)
    ax.set_xticklabels(noms, rotation=18, ha="right", fontsize=8)
    ax.set_title(titre + " — en dessous de ×1 : avantage serializejson")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    return fig


def figure_support(donnees, sens, titre):
    # temps TOTAL (calcul + transfert) selon le débit du support :
    # l'avantage de poids se change en avantage de temps dès que le
    # support est le goulot
    import matplotlib.pyplot as plt

    resultats = donnees["profils"]
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


def figure_machines(donnees, sens, titre):
    # UN graphique, une machine réaliste (couple CPU + stockage de même
    # gamme) par position : deux barres — temps total d'écriture et de
    # lecture (calcul mis à l'échelle du CPU + transfert au débit du
    # stockage) — une barre PETITE = avantage serializejson
    import matplotlib.pyplot as plt

    # profil d'ancrage : le plus gros profil individuel du corpus (le
    # concaténé hors cache exclu — il représente un autre régime)
    profil, m = max(
        (ligne for ligne in donnees["profils"]
         if "hors cache" not in ligne[0]),
        key=lambda ligne: ligne[1]["nbytes"])
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


def figure_types(donnees, sens, titre):
    # le catalogue d'objets du dépôt, par catégorie de types python : deux
    # barres (dumps, loads) — une barre PETITE = avantage serializejson
    import matplotlib.pyplot as plt

    lignes = donnees["types"]
    noms = [nom for nom, *_ in lignes]
    r_dumps = numpy.array([sj / pk for _, pk, sj, _, _ in lignes])
    r_loads = numpy.array([sj / pk for _, _, _, pk, sj in lignes])
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    x = numpy.arange(len(noms))
    b1 = ax.bar(x - 0.21, r_dumps, 0.4, color=BLEU,
                label="rapport de temps dumps  (serializejson / pickle)")
    b2 = ax.bar(x + 0.21, r_loads, 0.4, color=ORANGE,
                label="rapport de temps loads  (serializejson / pickle)")
    for barres in (b1, b2):
        for barre in barres:
            v = barre.get_height()
            ax.annotate(f"×{v:.2f}",
                        (barre.get_x() + barre.get_width() / 2, v),
                        ha="center", va="bottom", fontsize=6)
    ax.axhline(1.0, color="gray", ls="--", lw=1)
    ax.text(-0.45, 1.04, "égalité ×1", color="gray", fontsize=8, ha="left")
    ax.set_yscale("log")
    ax.set_ylim(bottom=min(r_dumps.min(), r_loads.min()) * 0.55,
                top=max(r_dumps.max(), r_loads.max()) * 2.4)
    ax.set_yticks([0.2, 0.5, 1, 2, 5, 10, 50, 200])
    ax.set_yticklabels(["×0,2", "×0,5", "×1", "×2", "×5", "×10", "×50",
                        "×200"])
    ax.yaxis.set_minor_formatter(plt.NullFormatter())
    ax.set_xticks(x)
    ax.set_xticklabels(noms, rotation=25, ha="right", fontsize=8)
    ax.set_title(titre + " — sous ×1 : avantage serializejson")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    return fig


def figure_pyperformance(donnees, sens, titre):
    # les cinq charges des benchmarks pickle OFFICIELS (pyperformance,
    # bm_pickle) répliquées : myriade de PETITS objets python (dicts,
    # tuples, listes) — une barre PETITE = avantage serializejson
    import matplotlib.pyplot as plt

    lignes = donnees["pyperf"]
    noms = [nom.split("(")[0].strip() for nom, _, _ in lignes]
    ratios = numpy.array([sj / pk for _, pk, sj in lignes])
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    x = numpy.arange(len(noms))
    barres = ax.bar(x, ratios, 0.55, color=ORANGE,
                    label="rapport de temps  (serializejson / pickle)")
    for barre in barres:
        v = barre.get_height()
        ax.annotate(f"×{v:.2f}",
                    (barre.get_x() + barre.get_width() / 2, v),
                    ha="center", va="bottom", fontsize=9)
    ax.axhline(1.0, color="gray", ls="--", lw=1)
    ax.text(-0.4, 1.02, "égalité ×1", color="gray", fontsize=8, ha="left")
    ax.set_ylim(0, max(2.0, ratios.max() * 1.25))
    ax.set_xticks(x)
    ax.set_xticklabels(noms, fontsize=10)
    ax.set_title(titre + " — sous ×1 : avantage serializejson")
    ax.legend(loc="upper right", fontsize=9)
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
    ("benchmark_types_objets", figure_types, "",
     "catalogue d'objets du dépôt, par catégorie de types python"),
    ("benchmark_pyperformance", figure_pyperformance, "",
     "benchmarks pickle officiels (pyperformance) : petits objets python"),
]


def rendu_pdf_et_svg(donnees, entete, chemin_pdf, dossier_svg):
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
            fig = fabrique(donnees, sens, titre)
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
    print("catalogue d'objets du dépôt (par catégorie de types)...")
    types_objets, types_ecartes = mesure_types_objets()
    print("benchmarks officiels pyperformance (petits objets)...")
    pyperf = bench_pyperformance_pickle.mesures()
    donnees = {"profils": resultats, "pyperf": pyperf, "types": types_objets}
    markdown = rendu_markdown(resultats, pyperf, types_objets, types_ecartes,
                              entete)
    horodatage = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    dossier = (Path(sys.argv[1]) if len(sys.argv) > 1
               else RACINE / "rapports_benchmarks")
    chemin_md = dossier / f"rapport_benchmarks_{horodatage}.md"
    chemin_pdf = dossier / f"rapport_benchmarks_{horodatage}.pdf"
    dossier_svg = RACINE / "docs_source" / "images"
    dossier_svg.mkdir(parents=True, exist_ok=True)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin_md.write_text(markdown)
    rendu_pdf_et_svg(donnees, entete, chemin_pdf, dossier_svg)
    print(markdown)
    print("->", chemin_md)
    print("->", chemin_pdf)
