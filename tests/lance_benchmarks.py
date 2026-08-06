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
from serializejson.tools import bareme_smart, bareme_smart_defaut  # noqa: E402
import numpy  # noqa: E402

sys.path.insert(0, str(RACINE / "tests"))
import bench_pyperformance_pickle  # noqa: E402  (benchs officiels répliqués)

perf = time.perf_counter

# les trois réglages comparés à pickle, dans l'ordre des colonnes du tableau
# et des figures : suffixe des clés de mesure → libellé. Ce sont les deux
# BOUTS du barème « smart » et le défaut : le barreau par défaut (le plus
# rapide qui compresse), le dernier barreau (le plus petit), et le niveau 0
# (aucune compression, base64 seul)
VARIANTES = {
    "sj": f"défaut « smart » (barreau {bareme_smart_defaut})",
    "min": f"barreau {max(bareme_smart)}, le plus petit du barème",
    "b64": "niveau 0, SANS compression (base64 seul)",
}


def burst():
    # réveille le CPU (sortie des états d'économie) juste avant un chrono
    t0 = perf()
    x = 1.0
    while perf() - t0 < 0.01:
        x *= 1.0000001
    return x


# tampon d'ÉVICTION : le PARCOURIR en lecture chasse des caches tout ce
# qui s'y trouvait. Il faut des lectures ordinaires — un memset de numpy
# passerait en écritures non temporelles, qui contournent le cache et ne
# chasseraient rien. 96 Mo : plusieurs fois le L3 de n'importe quel CPU visé
_EVICTION = numpy.ones(96_000_000, dtype=numpy.uint8)


def vide_cache():
    return _EVICTION.sum(dtype=numpy.uint64)


def chrono(f, essais=50, plafond=2.0, froid=False):
    # médiane de ~50 essais (robuste aux pointes de charge), plafond de
    # temps par case sans descendre sous 9 essais.
    # froid=True : cache vidé AVANT chaque essai — c'est le régime RAM, le
    # seul qu'une application obtienne sur des données qu'elle vient de
    # produire ou qu'elle s'apprête à écrire ; à chaud, pickle est crédité
    # d'une vitesse de cache L2/L3 (mesuré : 16 Go/s contre 1,7 Go/s en RAM)
    burst()
    f()
    t = perf()
    f()
    duree = perf() - t
    # un vidage coûte ~5 ms : à froid on plafonne plus tôt, essais compris
    n = max(9, min(essais, int(plafond / max(1e-5, duree + 0.005 * froid))))
    temps = []
    for _ in range(n):
        burst()
        if froid:
            vide_cache()
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
            corpus = str(chemin.parent.relative_to(dossier))
            groupe = f"images {corpus}" if corpus != "." else "images"
            nom = chemin.stem.replace("_", " ")
            images.append((f"{nom} ({tableau.nbytes / 1e6:.1f} Mo)",
                           numpy.ascontiguousarray(tableau), groupe))
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
        # les sons restent DÉTAILLÉS par piste (une ligne chacun) : le
        # troisième champ « groupe » None les laisse tels quels
        sons.append((f"{prefixe}{chemin.stem} int16"
                     f" ({donnees.nbytes / 1e6:.1f} Mo)",
                     numpy.ascontiguousarray(donnees), None))
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
    sources = [t for _, t, _ in liste]
    while total < 200_000_000:
        tableau = sources[rng.integers(0, len(sources))]
        octets = numpy.frombuffer(tableau.tobytes(), dtype=numpy.uint8)
        decalage = int(rng.integers(0, len(octets)))
        morceaux.append(numpy.roll(octets, decalage))
        total += len(octets)
    hors_cache = numpy.concatenate(morceaux)
    liste.append((f"corpus concaténé, hors cache"
                  f" ({hors_cache.nbytes / 1e6:.0f} Mo)", hors_cache, None))
    return liste


def mesure_codecs_images():
    # face aux codecs d'images SPÉCIALISÉS, sur les corpus d'images : PNG
    # (PIL, niveau par défaut) et JPEG XL sans perte (cjxl -d 0 -e 3, la
    # référence actuelle du compromis poids/vitesse ; temps = processus
    # complet, lancement compris). Les profondeurs que PNG/PIL ne porte pas
    # (RVB 16 bits) sont écartées et nommées. Agrégé par corpus.
    import io
    import shutil
    import subprocess
    import tempfile

    from PIL import Image

    if shutil.which("cjxl") is None or shutil.which("djxl") is None:
        return [], ["(cjxl/djxl introuvables : section sautée)"]

    def minimum(fonction, essais=3):
        temps = []
        for _ in range(essais):
            burst()
            vide_cache()   # même régime RAM que les chronos in-process
            t0 = perf()
            fonction()
            temps.append(perf() - t0)
        return min(temps)

    groupes = {}
    ecartees = []
    dossier_tmp = Path(tempfile.mkdtemp(prefix="codecs_images_"))
    for nom, tableau, groupe in _images_classiques():
        if tableau.dtype == numpy.uint16 and tableau.ndim == 3:
            ecartees.append(f"{nom} (RVB 16 bits : hors PNG/PIL)")
            continue
        try:
            image = Image.fromarray(tableau)
            tampon = io.BytesIO()
            image.save(tampon, "PNG")
        except Exception:
            ecartees.append(nom)
            continue
        png = tampon.getvalue()
        chemin_png = dossier_tmp / "image.png"
        chemin_png.write_bytes(png)
        chemin_jxl = dossier_tmp / "image.jxl"
        commande_cjxl = ["cjxl", str(chemin_png), str(chemin_jxl),
                         "-d", "0", "-e", "3", "--quiet"]
        subprocess.run(commande_cjxl, check=True, capture_output=True)
        jxl = chemin_jxl.read_bytes()
        chemin_sortie = dossier_tmp / "sortie.png"
        commande_djxl = ["djxl", str(chemin_jxl), str(chemin_sortie),
                         "--quiet"]
        subprocess.run(commande_djxl, check=True, capture_output=True)
        j = serializejson.dumps(tableau)

        def encode_png():
            b = io.BytesIO()
            image.save(b, "PNG")

        m = {
            "nbytes": tableau.nbytes,
            "taille_sj": len(serializejson.dumps(tableau)),
            "taille_png": len(png),
            "taille_jxl": len(jxl),
            "enc_sj": chrono(lambda: serializejson.dumps(tableau),
                             plafond=0.4, froid=True),
            "dec_sj": chrono(lambda: serializejson.loads(j), plafond=0.4,
                             froid=True),
            "enc_png": chrono(encode_png, plafond=0.4, froid=True),
            "dec_png": chrono(lambda: Image.open(io.BytesIO(png)).load(),
                              plafond=0.4, froid=True),
            "enc_jxl": minimum(lambda: subprocess.run(
                commande_cjxl, check=True, capture_output=True)),
            "dec_jxl": minimum(lambda: subprocess.run(
                commande_djxl, check=True, capture_output=True)),
        }
        cumul = groupes.setdefault(groupe, {})
        for cle, valeur in m.items():
            cumul[cle] = cumul.get(cle, 0) + valeur
    shutil.rmtree(dossier_tmp, ignore_errors=True)
    return sorted(groupes.items()), ecartees


def mesure_types_objets():
    # le catalogue d'objets du dépôt (tests/objects/basic_objects.py, celui
    # de test_serialize_vs_pickle) : chaque CATÉGORIE de types python est
    # sérialisée en bloc, pickle contre serializejson, dumps et loads —
    # les catégories que l'un des deux camps ne sait pas rejouer aux
    # réglages par défaut sont écartées (et nommées dans le rapport)
    from objects import basic_objects  # tests/ est sur le chemin

    # LOTS de N répliques par catégorie, pour mesurer le coût PAR OBJET et
    # non le coût fixe d'un appel (dominant sur un document minuscule). Le
    # lot est fabriqué côté JSON (répétition textuelle : aucune référence
    # $ref possible), puis RECHARGÉ — ce qui donne N objets python égaux
    # mais distincts, que le mémo de dédoublonnage ne fusionne pas
    N = 32
    lignes, ecartees = [], []
    for categorie, objets in basic_objects.objects.items():
        try:
            encodeur = serializejson.Encoder(return_bytes=True)
            encodeur(objets)   # peuple les classes vues par l'encodeur
            decodeur = serializejson.Decoder(
                authorized_classes=list(encodeur.get_dumped_classes()))
            # côté objets : clones par pickle (objets frais à chaque load,
            # y compris les immuables — deepcopy rendrait le MÊME bytes et
            # le cache de valeurs du décodeur les MÊMES str, que le mémo
            # transformerait en $ref au re-dump) ; la lecture se mesure sur
            # le dump RÉEL du lot (une répétition textuelle du document
            # unitaire casserait ses chemins $ref internes)
            graine = pickle.dumps(objets, protocol=4)
            lot = [pickle.loads(graine) for _ in range(N)]
            p = pickle.dumps(lot, protocol=4)
            j = encodeur(lot)
            # les singletons du lot (b"", objets type...) sont dédupliqués
            # par les DEUX camps ($ref chez serializejson, memo chez
            # pickle) : la comparaison reste équitable, on ne l'interdit pas
            pickle.loads(p)
            decodeur(j)
        except Exception:
            ecartees.append(categorie)
            continue
        # PAS de vidage de cache ici, contrairement aux gros tableaux : un lot
        # de quelques kilo-octets tient en cache DANS LA VRAIE VIE aussi, et
        # l'évincer ne mesurerait que le rechargement de l'interpréteur
        lignes.append((categorie, {
            "taille_pickle": len(p),
            "taille_sj": len(j),
            "dumps_pickle": chrono(lambda: pickle.dumps(lot, protocol=4),
                                   plafond=0.4),
            "dumps_sj": chrono(lambda: encodeur(lot), plafond=0.4),
            "loads_pickle": chrono(lambda: pickle.loads(p), plafond=0.4),
            "loads_sj": chrono(lambda: decodeur(j), plafond=0.4),
        }))
    return lignes, ecartees


def mesure(tableau):
    a = numpy.ascontiguousarray(tableau)
    p = pickle.dumps(a, protocol=4)
    j = serializejson.dumps(a)
    r = serializejson.loads(j)
    assert isinstance(r, numpy.ndarray) and numpy.array_equal(r, a)
    # dernier barreau du barème : le plus petit, et le plus cher à écrire —
    # l'autre bout de l'échelle que le défaut ouvre
    encodeur_min = serializejson.Encoder(
        return_bytes=True, bytes_compression=("smart", max(bareme_smart)))
    j_min = encodeur_min(a)
    assert numpy.array_equal(serializejson.loads(j_min), a)
    # variante « brute » : AUCUNE compression, la charge part telle quelle en
    # base64 — c'est le plancher de coût du format, ce que paie tout objet
    # dont on ne veut pas payer la compression
    encodeur_b64 = serializejson.Encoder(
        return_bytes=True, bytes_compression=None)
    j_b64 = encodeur_b64(a)
    assert numpy.array_equal(serializejson.loads(j_b64), a)
    m = {
        "nbytes": a.nbytes,
        "taille_pickle": len(p),
        "taille_sj": len(j),
        "taille_min": len(j_min),
        "taille_b64": len(j_b64),
        # froid=True : régime RAM, cache vidé avant chaque essai (voir chrono)
        "dumps_pickle": chrono(lambda: pickle.dumps(a, protocol=4), froid=True),
        "dumps_sj": chrono(lambda: serializejson.dumps(a), froid=True),
        "dumps_min": chrono(lambda: encodeur_min(a), froid=True),
        "dumps_b64": chrono(lambda: encodeur_b64(a), froid=True),
        "loads_pickle": chrono(lambda: pickle.loads(p), froid=True),
        "loads_sj": chrono(lambda: serializejson.loads(j), froid=True),
        "loads_min": chrono(lambda: serializejson.loads(j_min), froid=True),
        "loads_b64": chrono(lambda: serializejson.loads(j_b64), froid=True),
    }
    return _avec_seuil(m)


def _avec_seuil(m):
    # seuil de débit (écriture) : en dessous, dump+écriture sur le support
    # est plus rapide avec serializejson malgré le calcul de compression
    surcout = m["dumps_sj"] - m["dumps_pickle"]
    epargne = m["taille_pickle"] - m["taille_sj"]
    m["seuil"] = (epargne / surcout) if (surcout > 0 and epargne > 0) else None
    return m


def agrege_par_groupe(lignes):
    # UNE métrique par corpus (demande de Baptiste, 05/08 soir) : les lignes
    # portant un même groupe fusionnent — tailles et temps ADDITIONNÉS
    # (sérialiser le corpus entier), rapports recalculés sur les sommes
    sortie = []
    groupes = {}
    for nom, m, groupe in lignes:
        if groupe is None:
            sortie.append((nom, m))
            continue
        if groupe not in groupes:
            groupes[groupe] = {"n": 0}
            sortie.append((groupe, groupes[groupe]))
        cumul = groupes[groupe]
        cumul["n"] += 1
        for cle, valeur in m.items():
            if cle != "seuil":
                cumul[cle] = cumul.get(cle, 0) + valeur
    for groupe, cumul in groupes.items():
        n = cumul.pop("n")
        _avec_seuil(cumul)
        # renomme avec le compte et le volume du corpus
        for i, (nom, m) in enumerate(sortie):
            if m is cumul:
                sortie[i] = (f"{groupe} ({n} fichiers,"
                             f" {cumul['nbytes'] / 1e6:.0f} Mo)", cumul)
    return sortie


def fmt_octets(n):
    return f"{n / 1e6:.2f} Mo" if n >= 1e6 else f"{n / 1e3:.0f} Ko"


def geometrique(valeurs):
    valeurs = [v for v in valeurs if v]
    return float(numpy.exp(numpy.mean(numpy.log(valeurs)))) if valeurs else None


def rendu_markdown(donnees, types_ecartes, codecs_ecartes, entete):
    # `donnees` est le MÊME dictionnaire de mesures que celui des figures :
    # texte et graphiques ne peuvent pas diverger
    resultats, codecs_images = donnees["profils"], donnees["codecs"]
    types_objets, pyperf = donnees["types"], donnees["pyperf"]
    profil_machines, machines = rapports_machines(donnees)
    # un triplet de colonnes par variante, dans l'ordre de VARIANTES : le
    # tableau suit le barème sans qu'on ait à recompter les tirets
    colonnes = [f"{mesure} {suffixe}"
                for suffixe in VARIANTES
                for mesure in ("poids", "dumps", "loads")]
    md = ["# serializejson (défaut « smart ») contre pickle — mesures", "",
          *entete, "",
          "| profil | pickle | serializejson | " + " | ".join(colonnes)
          + " | support plus lent que |",
          "|" + "---|" * (len(colonnes) + 4)]
    rapports = {suffixe: {mesure: [] for mesure in ("taille", "dumps", "loads")}
                for suffixe in VARIANTES}
    for nom, m in resultats:
        gras = lambda texte, gagne: f"**{texte}**" if gagne else texte
        cellules = []
        for suffixe in VARIANTES:
            for mesure, gabarit in (("taille", "{:.0f} %"), ("dumps", "×{:.2f}"),
                                    ("loads", "×{:.2f}")):
                r = m[f"{mesure}_{suffixe}"] / m[f"{mesure}_pickle"]
                rapports[suffixe][mesure].append(r)
                echelle = 100 * r if mesure == "taille" else r
                cellules.append(gras(gabarit.format(echelle), r < 1))
        seuil = (f"{m['seuil'] / 1e6:.0f} Mo/s" if m["seuil"]
                 else "— (déjà plus rapide)" if m["dumps_sj"] <= m["dumps_pickle"]
                 else "—")
        md.append(
            f"| {nom} | {fmt_octets(m['taille_pickle'])}"
            f" | {fmt_octets(m['taille_sj'])} | "
            + " | ".join(cellules)
            + f" | {seuil} |")
    moyennes = {
        suffixe: {mesure: geometrique(valeurs)
                  for mesure, valeurs in mesures.items()}
        for suffixe, mesures in rapports.items()}
    md += ["",
           "**Synthèse (moyennes géométriques)** : "
           + " ; ".join(
               f"{VARIANTES[suffixe]} — poids"
               f" {100 * moyennes[suffixe]['taille']:.0f} %, dumps"
               f" ×{moyennes[suffixe]['dumps']:.2f}, loads"
               f" ×{moyennes[suffixe]['loads']:.2f}"
               for suffixe in VARIANTES) + ".",
           "",
           "Lecture du tableau : poids en % de pickle et temps en rapport"
           " ×t/t_pickle (moins de 100 % / ×1,00 = serializejson gagne, en"
           " gras). « Support plus lent que » : débit de stockage ou de"
           " réseau en dessous duquel serializejson est AUSSI plus rapide"
           " que pickle en écriture, temps de transfert compris — pickle ne"
           " fait qu'une recopie mémoire, il reste donc devant tant que tout"
           " se passe en mémoire ; dès que les octets doivent traverser un"
           " disque, un réseau ou un cloud, le poids gagné fait gagner le"
           " temps total.",
           "",
           "**Régime de mesure : la RAM, pas le cache.** Les temps ci-dessus"
           " sont mesurés cache VIDÉ avant chaque essai (96 Mo parcourus en"
           " lecture). C'est le seul régime qu'obtient une application sur des"
           " données qu'elle vient de produire ou qu'elle s'apprête à écrire ;"
           " à chaud, pickle est crédité d'une vitesse de cache que le calcul"
           " ne rencontre jamais en vrai. L'écart n'est pas anecdotique : sur"
           " un tableau de 1,6 Mo, pickle mesure 13,2 Go/s en cache et 7,3"
           " Go/s en RAM, et le rapport tombe de ×14 à ×7. Il n'explique"
           " toutefois pas TOUT l'écart avec les gros profils (1,7 Go/s à 200"
           " Mo) : le reste vient de l'allocation elle-même, un tampon de 200"
           " Mo se paie en défauts de page, un tampon recyclé de 1,6 Mo non.",
           "",
           "**Les quatre barres des figures.** Chaque figure porte, sous le"
           " cadre bleu du poids, quatre rapports de temps : écrire et relire"
           " en RAM, puis écrire et relire sur le disque de la machine de"
           f" mesure ({DISQUE}), temps de transfert des octets compris. Les"
           " deux régimes de CACHE ont été retirés : aucune application réelle"
           " ne les rencontre sur des données qu'elle produit ou range.",
           "",
           "**Machines réalistes.** Chaque CPU est apparié à un stockage de"
           " sa gamme, le calcul mis à l'échelle du CPU et le transfert des"
           " octets au débit du stockage — le temps TOTAL, celui que voit"
           " l'application. Profil d'ancrage : le plus gros profil individuel"
           f" du corpus, « {profil_machines} ».",
           "",
           "| machine | écriture | lecture |",
           "|---|---|---|"]
    for (nom, _, _), e, l in zip(MACHINES, machines["dumps"],
                                 machines["loads"]):
        rapport = lambda v: f"**×{v:.2f}**" if v < 1 else f"×{v:.2f}"
        md.append(f"| {nom.replace(chr(10), ' ')} | {rapport(e)}"
                  f" | {rapport(l)} |")
    md += ["",
           "## corpus d'images : face aux codecs d'images spécialisés",
           "",
           "PNG (PIL, réglages par défaut) et JPEG XL sans perte (cjxl -d 0"
           " -e 3, la référence actuelle du compromis poids/vitesse ; ses"
           " temps incluent le lancement du processus). Poids en % des"
           " octets BRUTS ; ces codecs prédisent en 2D, notre chaîne"
           " générique non — c'est l'écart attendu sur les photos.",
           "",
           "| corpus | brut | smart | PNG | JPEG XL |"
           " enc. smart | enc. PNG | enc. JXL |"
           " déc. smart | déc. PNG | déc. JXL |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for groupe, m in codecs_images:
        md.append(
            f"| {groupe} | {fmt_octets(m['nbytes'])}"
            f" | {100 * m['taille_sj'] / m['nbytes']:.0f} %"
            f" | {100 * m['taille_png'] / m['nbytes']:.0f} %"
            f" | {100 * m['taille_jxl'] / m['nbytes']:.0f} %"
            f" | {1e3 * m['enc_sj']:.0f} ms | {1e3 * m['enc_png']:.0f} ms"
            f" | {1e3 * m['enc_jxl']:.0f} ms"
            f" | {1e3 * m['dec_sj']:.0f} ms | {1e3 * m['dec_png']:.0f} ms"
            f" | {1e3 * m['dec_jxl']:.0f} ms |")
    if codecs_ecartes:
        md += ["", "Écartées : " + ", ".join(codecs_ecartes) + "."]
    md += ["",
           "## catalogue d'objets du dépôt, par catégorie de types python",
           "",
           "Les objets de `tests/objects/basic_objects.py` (ceux de"
           " `test_serialize_vs_pickle`), sérialisés par catégorie, réglages"
           " par défaut des deux côtés (Decoder avec les classes autorisées"
           " du dump).",
           "",
           "Ces lots pèsent quelques kilo-octets : le cache et la RAM n'y sont"
           " PAS distinguables — un lot de cette taille tient en cache dans la"
           " vraie vie aussi, et l'en évincer ne mesurerait que le"
           " rechargement de l'interpréteur. Les deux premières barres de la"
           " figure sont donc des temps de cache, et les deux barres de disque"
           " n'y ajoutent presque rien : à ces tailles, le transfert est du"
           " bruit devant le calcul.",
           "",
           "| catégorie | dumps pickle (µs) | dumps serializejson (µs) |"
           " rapport | loads pickle (µs) | loads serializejson (µs) |"
           " rapport |",
           "|---|---|---|---|---|---|---|"]
    for nom, m in types_objets:
        pk_d, sj_d = m["dumps_pickle"], m["dumps_sj"]
        pk_l, sj_l = m["loads_pickle"], m["loads_sj"]
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
    # les deux charges à citer en exemple sont CALCULÉES, pas écrites en dur :
    # celle que le transfert soulage le plus, celle qu'il pénalise le plus
    # chaque charge donne deux cas (écriture, lecture) ; on cite celui que le
    # transfert soulage le plus et celui qu'il pénalise le plus
    ecarts = []
    for ligne in pyperf:
        ram_e, ram_l, disque_e, disque_l = rapports_pyperf(ligne)
        court = ligne[0].split("(")[0].strip()
        poids_charge = ligne[-1] / ligne[-2]
        ecarts.append((f"{court} en écriture", ram_e, disque_e, poids_charge))
        ecarts.append((f"{court} en lecture", ram_l, disque_l, poids_charge))
    aide = min(ecarts, key=lambda e: e[2] - e[1])
    dessert = max(ecarts, key=lambda e: e[2] - e[1])

    def _exemple(e):
        nom, ram, disque, poids_charge = e
        fr = lambda v: f"×{v:.2f}".replace(".", ",")
        return (f"{nom} : {fr(ram)} en RAM, {fr(disque)} sur disque, pour un"
                f" poids de {fr(poids_charge)}")

    md += ["",
           "## benchmarks pickle officiels (pyperformance, petits objets)",
           "",
           "Les charges de `bm_pickle` de la suite pyperformance, répliquées à"
           " l'identique (mêmes objets, mêmes boucles, meilleur temps) : une"
           " myriade de PETITS dicts, tuples et listes — le terrain de jeu"
           " historique de pickle, sans binaire à compresser. Chaque charge"
           " officielle est réunie ici avec sa relecture, pour se lire comme"
           " le reste du rapport ; pyperformance ne fournissant pas de"
           " `unpickle_dict`, la lecture du troisième groupe a été ajoutée sur"
           " sa charge d'écriture officielle.",
           "",
           "Même remarque que pour le catalogue : à ces tailles le régime RAM"
           " ne se distingue pas du cache. Ici le poids joue CONTRE"
           " serializejson — du json lisible contre des opcodes binaires — et"
           " c'est ce qui rend les barres de disque instructives : le transfert"
           " tire toujours le rapport vers celui des POIDS, ce qui l'améliore"
           " quand le calcul coûtait plus cher que les octets"
           f" ({_exemple(aide)}) et l'AGGRAVE dans le cas contraire"
           f" ({_exemple(dessert)}). C'est le seul endroit du rapport où le"
           " disque dessert serializejson — ailleurs, le poids gagné fait"
           " gagner le temps.",
           "",
           "| charge officielle | écriture pickle (µs) |"
           " écriture serializejson (µs) | rapport | lecture pickle (µs) |"
           " lecture serializejson (µs) | rapport |",
           "|---|---|---|---|---|---|---|"]
    for nom, pk_e, sj_e, pk_l, sj_l, _, _ in pyperf:
        r_e, r_l = sj_e / pk_e, sj_l / pk_l
        gras = lambda r: f"**×{r:.2f}**" if r < 1 else f"×{r:.2f}"
        md.append(f"| {nom} | {pk_e:.1f} | {sj_e:.1f} | {gras(r_e)}"
                  f" | {pk_l:.1f} | {sj_l:.1f} | {gras(r_l)} |")
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


# le disque de la MACHINE DE MESURE, celui sur lequel sont calculées les deux
# barres « disque » de toutes les figures — pris DANS la liste ci-dessus, pour
# qu'un changement de machine n'ait qu'un seul endroit où se faire
_MACHINE_MESURE = next(m for m in MACHINES if "mesure" in m[0])
DISQUE = _MACHINE_MESURE[0].split("+ ")[1]
DEBIT_DISQUE = _MACHINE_MESURE[2]


# les quatre régimes tracés sous le cadre de mémoire, dans l'ordre des barres :
# (libellé, couleur de la barre, couleur de son étiquette chiffrée). Les deux
# barres de RAM sont volontairement PÂLES — ce sont les deux barres de disque
# qui portent le cas d'usage réel, elles doivent sauter aux yeux les premières ;
# l'étiquette, elle, reste dans le ton soutenu, sinon elle ne se lirait plus
REGIMES = [("écrire vers la RAM", "#fbd7b5", ORANGE),
           ("relire depuis la RAM", "#f0c3b4", "#9c4221"),
           (f"écrire vers le disque, {DISQUE}", "#2f855a", "#2f855a"),
           (f"relire depuis le disque, {DISQUE}", "#22543d", "#22543d")]


def quatre_regimes(reference, candidat):
    # les quatre rapports candidat/référence tracés par `dispositif`, à partir
    # de deux triplets (octets, temps d'écriture, temps de lecture) : écrire et
    # relire en RAM, puis les deux mêmes sur le disque de la machine de mesure,
    # où s'ajoute le temps de transfert des octets — c'est là que le poids
    # gagné se change en temps gagné
    (o_r, e_r, l_r), (o_c, e_c, l_c) = reference, candidat
    return [e_c / e_r, l_c / l_r,
            (e_c + o_c / DEBIT_DISQUE) / (e_r + o_r / DEBIT_DISQUE),
            (l_c + o_c / DEBIT_DISQUE) / (l_r + o_r / DEBIT_DISQUE)]


def dispositif(noms, poids, regimes, titre, etiquette_poids, rotation=18):
    # LE dispositif commun à toutes les figures de comparaison : quatre barres
    # de temps (écrire puis relire, en RAM puis sur le disque de la machine de
    # mesure) surmontées du CADRE bleu du poids, large comme les quatre barres
    # réunies et posé par-dessus elles. Son arête haute donne le poids, et rien
    # n'est jamais masqué — que le poids passe au-dessus ou en dessous des
    # temps, les deux restent lisibles. Une barre PETITE = avantage du candidat.
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgba

    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    x = numpy.arange(len(noms))
    LARGEUR = 0.19
    # étiquettes de valeur debout quand les colonnes sont serrées, couchées
    # quand la place existe — couchées, elles se lisent même sur une barre
    # écrasée en bas de l'axe (face aux codecs d'images, ×0,03 contre ×0,07)
    debout = len(noms) > 6
    for rang, (valeurs, (etiquette, couleur, couleur_texte)) in enumerate(
            zip(regimes, REGIMES)):
        position = x + (rang - 1.5) * LARGEUR
        ax.bar(position, valeurs, LARGEUR, color=couleur, label=etiquette,
               zorder=2)
        for centre, v in zip(position, valeurs):
            # une case sans mesure vaut NaN : ni barre, ni étiquette
            if not numpy.isnan(v):
                ax.annotate(f"×{v:.2f}", (centre, v), ha="center",
                            va="bottom", fontsize=5.5 if debout else 7,
                            rotation=90 if debout else 0, color=couleur_texte,
                            zorder=6)
    # le poids en aplat bleu très translucide, PAR-DESSUS les quatre barres :
    # elles couvrent exactement la largeur du cadre, un fond passé dessous
    # serait entièrement caché. L'aplat teinte donc les temps qu'il recouvre,
    # d'où l'alpha très faible — assez pour voir jusqu'où monte le poids, pas
    # assez pour gêner la lecture des barres en dessous
    ax.bar(x, poids, LARGEUR * 4, facecolor=to_rgba(BLEU, 0.13),
           edgecolor=BLEU, linewidth=2.2, zorder=4, label=etiquette_poids)
    for centre, v in zip(x, poids):
        # calée sur l'arête GAUCHE du cadre, là où elle ne tombe que sur la
        # première barre (pâle) ou sur le fond : le cartouche blanc qui la
        # rendait lisible au centre n'est alors plus nécessaire
        ax.annotate(f"×{v:.2f}", (centre - 1.9 * LARGEUR, v), ha="left",
                    va="bottom", fontsize=7, color=BLEU, weight="bold",
                    zorder=6)
    ax.axhline(1.0, color="gray", ls="--", lw=1, zorder=1)
    # LINÉAIRE sous ×1, LOGARITHMIQUE au-dessus : le poids, qui se joue à
    # quelques pour cent sous ×1, se lit à la même finesse que les temps, qui
    # eux s'étalent sur deux décades. Raccord C¹ en ×1 (pente 1 des deux
    # côtés), et le zéro reste à distance finie donc les barres partent du bas.
    ax.set_yscale("function", functions=(
        lambda y: numpy.where(y <= 1.0, y, 1.0 + numpy.log(
            numpy.where(y > 1.0, y, 1.0))),
        lambda v: numpy.where(v <= 1.0, v, numpy.exp(
            numpy.where(v > 1.0, v, 1.0) - 1.0)),
    ))
    # nanmax : une case sans mesure (charge à sens unique) vaut NaN
    haut = float(numpy.nanmax(numpy.concatenate([poids, *regimes]))) * 1.6
    ax.set_ylim(bottom=0, top=haut)
    # la moitié gagnante et la moitié perdante de l'axe, teintées très pâle :
    # de quoi situer une barre d'un coup d'oeil sans avoir à suivre le trait
    # de ×1 jusqu'à elle. Sous les barres, et assez pâle pour ne rien voiler
    ax.axhspan(0, 1, color="#38a169", alpha=0.07, zorder=0)
    ax.axhspan(1, haut, color="#e53e3e", alpha=0.07, zorder=0)
    graduations =[0, 0.2, 0.4, 0.6, 0.8, 1] + [
        t for t in (1.5, 2, 3, 5, 10, 20, 50, 100, 200) if t <= haut]
    ax.set_yticks(graduations)
    ax.set_yticklabels(
        [("×%g" % t).replace(".", ",") for t in graduations])
    ax.set_xticks(x)
    ax.set_xticklabels(noms, rotation=rotation, ha="right" if rotation else
                       "center", fontsize=8)
    # légende HORS du cadre, sous le titre : dedans elle masquait les barres
    # les plus hautes, qui sont justement celles qu'on vient regarder
    ax.set_title(titre + " — en dessous de ×1 : avantage serializejson",
                 pad=38)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3,
              fontsize=8, frameon=False)
    fig.tight_layout()
    return fig


def figure_barres(donnees, suffixe, titre):
    # UNE figure par variante de compression, portant les quatre régimes : la
    # mémoire ne dépend ni du sens ni du support, elle n'est donc tracée qu'une
    # fois par profil
    resultats = donnees["profils"]
    regimes = numpy.array([
        quatre_regimes(
            (m["taille_pickle"], m["dumps_pickle"], m["loads_pickle"]),
            (m[f"taille_{suffixe}"], m[f"dumps_{suffixe}"],
             m[f"loads_{suffixe}"]))
        for _, m in resultats]).T
    return dispositif(
        [nom for nom, _ in resultats],
        numpy.array([m[f"taille_{suffixe}"] / m["taille_pickle"]
                     for _, m in resultats]),
        regimes, titre, "mémoire  (poids serializejson / pickle)")


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


def rapports_machines(donnees):
    # rend (profil d'ancrage, {"dumps": rapports, "loads": rapports}) : le
    # temps TOTAL serializejson / pickle sur chaque machine réaliste, calcul
    # mis à l'échelle du CPU et transfert des octets au débit du stockage.
    # UNE seule fois, pour la figure ET pour le tableau du rapport.
    # Profil d'ancrage : le plus gros profil individuel du corpus (le
    # concaténé hors cache exclu — il représente un autre régime)
    profil, m = max(
        (ligne for ligne in donnees["profils"]
         if "hors cache" not in ligne[0]),
        key=lambda ligne: ligne[1]["nbytes"])
    rapports = {}
    for cle in ("dumps", "loads"):
        rapports[cle] = numpy.array(
            [(m[f"{cle}_sj"] / facteur + m["taille_sj"] / debit)
             / (m[f"{cle}_pickle"] / facteur + m["taille_pickle"] / debit)
             for _, facteur, debit in MACHINES])
    return profil, rapports


def figure_machines(donnees, sens, titre):
    # UN graphique, une machine réaliste (couple CPU + stockage de même
    # gamme) par position : deux barres — temps total d'écriture et de
    # lecture — une barre PETITE = avantage serializejson
    import matplotlib.pyplot as plt

    profil, rapports = rapports_machines(donnees)
    noms = [nom for nom, _, _ in MACHINES]
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
    # le catalogue d'objets du dépôt, par catégorie de types python, au même
    # dispositif que les tableaux — à ceci près que le régime RAM n'y a pas de
    # sens (quelques kilo-octets tiennent en cache dans la vraie vie aussi) :
    # les deux premières barres sont donc des temps de cache
    lignes = donnees["types"]
    regimes = numpy.array([
        quatre_regimes((m["taille_pickle"], m["dumps_pickle"],
                        m["loads_pickle"]),
                       (m["taille_sj"], m["dumps_sj"], m["loads_sj"]))
        for _, m in lignes]).T
    return dispositif(
        [nom for nom, _ in lignes],
        numpy.array([m["taille_sj"] / m["taille_pickle"] for _, m in lignes]),
        regimes, titre, "poids du document  (serializejson / pickle)",
        rotation=25)


def figure_codecs_images(donnees, sens, titre):
    # poids par corpus, en % des octets bruts : serializejson smart contre
    # PNG et JPEG XL sans perte — barre PETITE = meilleur
    import matplotlib.pyplot as plt

    groupes = donnees["codecs"]
    noms = [groupe for groupe, _ in groupes]
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    x = numpy.arange(len(noms))
    series = [("serializejson (défaut smart)", "taille_sj", BLEU),
              ("PNG (PIL)", "taille_png", "#4a9d6e"),
              ("JPEG XL sans perte (cjxl -e 3)", "taille_jxl", ORANGE)]
    for decalage, (etiquette, cle, couleur) in zip((-0.27, 0.0, 0.27),
                                                   series):
        valeurs = numpy.array(
            [100 * m[cle] / m["nbytes"] for _, m in groupes])
        barres = ax.bar(x + decalage, valeurs, 0.25, color=couleur,
                        label=etiquette)
        for barre in barres:
            v = barre.get_height()
            ax.annotate(f"{v:.0f} %",
                        (barre.get_x() + barre.get_width() / 2, v),
                        ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("poids compressé (% des octets bruts)")
    ax.set_xticks(x)
    ax.set_xticklabels(noms, fontsize=9)
    ax.set_title(titre + " — barre petite : meilleur")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    return fig


def figure_codecs_dispositif(donnees, codec, titre):
    # le même dispositif que les autres figures, UNE page par codec : ici la
    # référence n'est plus pickle mais le codec d'images spécialisé, et le
    # candidat reste serializejson au défaut smart
    groupes = donnees["codecs"]
    regimes = numpy.array([
        quatre_regimes((m[f"taille_{codec}"], m[f"enc_{codec}"],
                        m[f"dec_{codec}"]),
                       (m["taille_sj"], m["enc_sj"], m["dec_sj"]))
        for _, m in groupes]).T
    return dispositif(
        [groupe for groupe, _ in groupes],
        numpy.array([m["taille_sj"] / m[f"taille_{codec}"]
                     for _, m in groupes]),
        regimes, titre, f"poids  (serializejson / {codec.upper()})",
        rotation=0)


def rapports_pyperf(ligne):
    # une ligne pyperformance (une charge officielle et sa relecture) ramenée
    # aux quatre régimes du dispositif commun. Les temps y sont en µs, d'où la
    # mise en secondes avant `quatre_regimes`
    _, pk_e, sj_e, pk_l, sj_l, octets_pk, octets_sj = ligne
    return quatre_regimes((octets_pk, 1e-6 * pk_e, 1e-6 * pk_l),
                          (octets_sj, 1e-6 * sj_e, 1e-6 * sj_l))


def figure_pyperformance(donnees, sens, titre):
    # les charges des benchmarks pickle OFFICIELS (pyperformance, bm_pickle)
    # répliquées : myriade de PETITS objets python (dicts, tuples, listes).
    # Écriture et lecture d'une même charge sont réunies en UNE colonne, au
    # dispositif commun à tout le rapport
    lignes = donnees["pyperf"]
    regimes = numpy.array([rapports_pyperf(ligne) for ligne in lignes]).T
    return dispositif(
        [nom.split("(")[0].strip() for nom, *_ in lignes],
        numpy.array([octets_sj / octets_pk
                     for *_, octets_pk, octets_sj in lignes]),
        regimes, titre, "poids du document  (serializejson / pickle)",
        rotation=0)


FIGURES = [
    # les trois variantes du barème, titrées par VARIANTES (une seule source)
    *[(f"benchmark_memoire_{'smart' if suffixe == 'sj' else suffixe}",
       figure_barres, suffixe, f"conversion en mémoire, {libelle}")
      for suffixe, libelle in VARIANTES.items()],
    ("benchmark_ecriture_support", figure_support, "dumps",
     "écriture sur un support (dumps + transfert)"),
    ("benchmark_lecture_support", figure_support, "loads",
     "lecture depuis un support (transfert + loads)"),
    ("benchmark_codecs_images", figure_codecs_images, "",
     "corpus d'images : serializejson face aux codecs d'images spécialisés"),
    ("benchmark_codecs_png", figure_codecs_dispositif, "png",
     "corpus d'images : serializejson face à PNG (PIL)"),
    ("benchmark_codecs_jxl", figure_codecs_dispositif, "jxl",
     "corpus d'images : serializejson face à JPEG XL sans perte"),
    ("benchmark_types_objets", figure_types, "",
     "catalogue d'objets du dépôt, par catégorie de types python"),
    ("benchmark_pyperformance", figure_pyperformance, "",
     "benchmarks pickle officiels (pyperformance) : petits objets python"),
    # les machines réalistes ferment le rapport : elles ne mesurent rien de
    # neuf, elles projettent les mesures précédentes sur des couples
    # CPU + stockage du commerce
    ("benchmark_machines", figure_machines, "",
     "machines réalistes (CPU + stockage de même gamme)"),
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
                "Le dispositif est le MÊME sur toutes les figures de"
                " comparaison : quatre barres de temps —\nécrire puis relire"
                " en RAM, écrire puis relire sur le disque de la machine de"
                f" mesure\n({DISQUE}), temps de transfert compris — surmontées"
                " du CADRE bleu du poids,\nlarge comme les quatre barres"
                " réunies. Rien n'est masqué : que le poids passe au-dessus\n"
                "ou en dessous des temps, les deux restent lisibles. Échelle"
                " linéaire sous ×1, logarithmique\nau-dessus.\n\n"
                "Les temps sont mesurés CACHE VIDÉ : c'est le seul régime"
                " qu'obtient une application sur\ndes données qu'elle vient de"
                " produire ou qu'elle s'apprête à écrire. Sur les petits"
                " objets\npython (catalogue, pyperformance), cache et RAM ne"
                " se distinguent pas — c'est dit sur place.\n\n"
                "Trois figures font exception au dispositif : les deux"
                " scénarios de support, qui portent le temps\ntotal en"
                " fonction du débit sur toute la gamme des stockages, et les"
                " machines réalistes en\ndernière page, qui projettent les"
                " mêmes mesures sur des couples CPU + stockage du commerce.",
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
        # le défaut est LU dans le barème : la ligne d'en-tête ne peut pas
        # décrire un réglage que le code n'applique plus
        "- réglages PAR DÉFAUT des deux côtés : pickle protocole 4 ;"
        " serializejson défaut, barreau"
        f" {bareme_smart_defaut} du barème « smart » (chaîne"
        f" {bareme_smart[bareme_smart_defaut][2]} →"
        f" {bareme_smart[bareme_smart_defaut][0]} niveau"
        f" {bareme_smart[bareme_smart_defaut][1]}, base64 et JSON compris)",
        "- médiane de ~50 essais, burst de réveil CPU avant chaque chrono,"
        " mesures alternées dans le même processus",
        "- régime RAM : sur les tableaux et les images, le cache est VIDÉ"
        " avant chaque essai (96 Mo parcourus en lecture) — sur les petits"
        " objets python, cache et RAM ne se distinguent pas et le vidage"
        " ne mesurerait que le rechargement de l'interpréteur",
    ]
    lignes = []
    for nom, tableau, groupe in profils():
        print("profil :", nom)
        lignes.append((nom, mesure(tableau), groupe))
    resultats = agrege_par_groupe(lignes)
    print("catalogue d'objets du dépôt (par catégorie de types)...")
    types_objets, types_ecartes = mesure_types_objets()
    print("codecs d'images spécialisés (PNG, JPEG XL)...")
    codecs_images, codecs_ecartes = mesure_codecs_images()
    print("benchmarks officiels pyperformance (petits objets)...")
    pyperf = bench_pyperformance_pickle.mesures()
    donnees = {"profils": resultats, "pyperf": pyperf, "types": types_objets,
               "codecs": codecs_images}
    markdown = rendu_markdown(donnees, types_ecartes, codecs_ecartes,
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
