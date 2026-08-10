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
  - disque : de VRAIES écritures et relectures sur le volume du dépôt,
    mesurées et non projetées — écriture DURABLE (fsync compris) et
    relecture cache du noyau ÉVINCÉ, meilleur de 5 essais. Côté
    serializejson deux temps sont rendus : celui que `dump` bloque, et
    celui qu'il faut de plus au fil d'écriture pour finir ;
  - seuil de débit : le débit de stockage/réseau en dessous duquel
    serializejson devient AUSSI plus rapide que pickle, temps de
    lecture/écriture du support compris — (octets épargnés) / (surcoût
    de calcul). Au-dessus du seuil, pickle reste plus rapide en local ;
    en dessous (disque réseau, cloud, USB...), serializejson gagne sur
    les deux tableaux.
"""
import datetime
import os
import pickle
import shutil
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
from serializejson.tools import (bareme_smart,  # noqa: E402
                                 bareme_smart_defaut_fichier,
                                 bareme_smart_defaut_ram)
import numpy  # noqa: E402

sys.path.insert(0, str(RACINE / "tests"))
import bench_pyperformance_pickle  # noqa: E402  (benchs officiels répliqués)

perf = time.perf_counter

# les trois réglages comparés à pickle, dans l'ordre des colonnes du tableau
# et des figures : suffixe des clés de mesure → libellé. Ce sont les deux
# BOUTS du barème « smart » et le défaut, pris dans l'ordre CROISSANT du
# barème (choix de Baptiste, 07/08) : le niveau 0 (aucune compression, base64
# seul), le profil par défaut — qui, depuis le 10/08, dépend de la CIBLE :
# barreau RAM pour dumps/dumpb, barreau fichier pour dump/append —, puis le
# dernier barreau (le plus petit)
VARIANTES = {
    "b64": "profil «smart» niveau 0 (sans compression, base64 seul)",
    "sj": "profil «smart» par défaut (niveau"
          f" {bareme_smart_defaut_ram} en RAM, niveau"
          f" {bareme_smart_defaut_fichier} vers fichier)",
    "min": f"profil «smart» niveau {max(bareme_smart)} (bonne compression)",
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


# --- LE DISQUE, MESURÉ ------------------------------------------------------
# Les deux barres « disque » des figures étaient une PROJECTION : temps de
# calcul + octets / débit constructeur. Elles sont désormais MESURÉES, sur un
# vrai volume (demande de Baptiste, 08/08 : « je veux les temps réels avec de
# vraies écritures sur disque »). Un tmpfs ne mesurerait que de la mémoire,
# d'où un dossier pris sur un vrai support — par défaut celui du dépôt, mais
# `SERIALIZEJSON_BANC_DISQUE` permet de viser un AUTRE volume (08/08 : le
# dépôt vit sur un disque à plateaux, cf. `support_du_depot`) sans toucher au
# script à chaque changement de machine
_DOSSIER_DISQUE = Path(os.environ.get("SERIALIZEJSON_BANC_DISQUE")
                       or (RACINE / ".banc_disque"))


def _chemin_banc(nom):
    _DOSSIER_DISQUE.mkdir(exist_ok=True)
    return str(_DOSSIER_DISQUE / nom)


def _evince(chemin):
    # chasse du cache du noyau les pages du fichier — sans privilèges, mais
    # seulement les pages PROPRES : d'où le fsync systématique en fin
    # d'écriture, sans lequel la relecture mesurerait le cache et rien d'autre
    fd = os.open(chemin, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    finally:
        os.close(fd)


def _fsync(chemin):
    fd = os.open(chemin, os.O_WRONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fichiers_ecrits(chemin):
    # `serializejson.dump` peut déposer DEUX entrées : le json, et l'index
    # sidecar caché du même nom précédé d'un point (réglage `index="sidecar"`,
    # le défaut). Son write() était déjà compté — le fil d'écriture le pose
    # avant que `wait_writes` ne rende la main — mais pas son fsync, pas ses
    # octets et pas son éviction : trois faveurs faites à serializejson.
    # MESURÉ, A/B interlacé, avant de le croire grave : le sidecar n'existe que
    # si un chemin dépasse `index_threshold`, donc PAS sur un lot de quelques
    # kilo-octets comme ceux du catalogue de types (aucune faveur là où je la
    # craignais la plus grosse) ; sur un tableau de 4 Mo il pèse 74 octets et
    # son fsync coûte +0,34 ms, soit ×1,08 du geste durable. Petit, donc, mais
    # réel et gratuit à rendre — un rapport qui annonce « fsync compris » doit
    # synchroniser TOUT ce que la bibliothèque a écrit
    sidecar = serializejson.indexation.chemin_sidecar(chemin)
    return [c for c in (chemin, sidecar) if os.path.exists(c)]


def _efface(chemin):
    for ecrit in _fichiers_ecrits(chemin):
        os.unlink(ecrit)


def _ecrit_pickle(chemin, objet):
    # le geste ORDINAIRE de pickle, puis ce qu'il reste à payer pour que les
    # octets soient vraiment sur le disque. pickle n'a pas de fil d'écriture :
    # tout ce qu'il fait est bloquant, et seul le fsync est différé — par le
    # NOYAU, pas par la bibliothèque
    t0 = perf()
    f = open(chemin, "wb")
    pickle.dump(objet, f, protocol=4)
    f.flush()
    bloque = perf() - t0
    os.fsync(f.fileno())
    f.close()
    return bloque, perf() - t0


def _ecrit_sj(chemin, objet, args):
    # `dump` rend la main dès l'objet sérialisé (disk_write_mode
    # « fast_release », le défaut) : base64, compression et write() partent
    # dans le fil d'écriture. D'où les DEUX temps, et la barre coupée en deux
    # des figures — le bas est ce que l'appelant attend, le haut ce qui se
    # termine derrière lui
    t0 = perf()
    serializejson.dump(objet, chemin, **args)
    bloque = perf() - t0
    serializejson.wait_writes()
    for ecrit in _fichiers_ecrits(chemin):
        _fsync(ecrit)
    return bloque, perf() - t0


def sonde_disque_libre():
    # UNE écriture durable étalon (4 Mo + fsync), l'état du volume au moment
    # où le profil qui suit va être payé.
    #
    # Ce qu'elle mesure, VÉRIFIÉ et pas supposé (08/08) : le dépôt est sur un
    # disque À PLATEAUX de 3,6 To derrière VeraCrypt — 105 Mo écrits dans le
    # dépôt se retrouvent sur `sdb`/`dm-0`, ROTA=1, et rien sur le NVMe. Cache
    # du disque vide, 4 Mo durables se paient 7 ms (le disque ment, ils sont
    # dans sa DRAM) ; le cache saturé, 51 ms — 78 Mo/s, le plateau. Une
    # campagne qui écrit des gigaoctets sature donc son propre support, et
    # `/proc/diskstats` l'a montré : ZÉRO entrée-sortie étrangère pendant que
    # la sonde annonçait 51 ms. Attendre un volume « libre » avant de lancer ne
    # sert à rien — il ne l'est plus au premier profil. D'où la sonde par
    # PROFIL : elle ne dit pas « quelqu'un d'autre écrit », elle dit à quel
    # régime du support cette ligne-là a été payée
    chemin = _chemin_banc("etalon")
    donnees = os.urandom(4_000_000)
    temps = []
    for _ in range(3):
        burst()
        t0 = perf()
        f = open(chemin, "wb")
        f.write(donnees)
        f.flush()
        os.fsync(f.fileno())
        f.close()
        temps.append(perf() - t0)
    os.unlink(chemin)
    return min(temps)


def support_du_depot():
    # NOMMER le support au lieu de le supposer : c'est l'erreur que ce chantier
    # a payée le plus cher — les figures projetaient le disque à 3,5 Go/s de
    # NVMe alors que le dépôt vit sur un disque à plateaux USB derrière
    # VeraCrypt, quarante fois plus lent. Un rapport qui publie des temps de
    # disque doit dire SUR QUOI, et le lire au lieu de le croire. On stat le
    # dossier du BANC, pas RACINE : depuis SERIALIZEJSON_BANC_DISQUE, ce n'est
    # plus forcément le même volume
    try:
        _DOSSIER_DISQUE.mkdir(exist_ok=True)
        st = os.stat(_DOSSIER_DISQUE)
        noeud = Path("/sys/dev/block/%d:%d"
                     % (os.major(st.st_dev), os.minor(st.st_dev))).resolve()
        couches = [noeud.name]
        esclaves = sorted((noeud / "slaves").glob("*"))
        while esclaves:
            noeud = esclaves[0].resolve()
            couches.append(noeud.name)
            esclaves = sorted((noeud / "slaves").glob("*"))
        # une PARTITION n'a ni rotational ni taille : ces attributs sont sur le
        # disque parent, un cran au-dessus dans /sys
        disque = noeud if (noeud / "queue").is_dir() else noeud.parent
        rotatif = (disque / "queue/rotational").read_text().strip() == "1"
        octets = int((disque / "size").read_text()) * 512
        bus = "USB" if "/usb" in str(disque.resolve()) else "interne"
        chiffre = any(couche.startswith("dm-") for couche in couches)
        return ("%s, %.1f To, %s, %s%s"
                % (disque.name, octets / 1e12,
                   "à plateaux" if rotatif else "SSD/NVMe", bus,
                   ", derrière un conteneur chiffré" if chiffre else ""))
    except OSError:
        return "support non identifié"


def _gestes_disque(chemin, objet, args, args_lecture):
    # le couple écrire/relire d'un camp, par les fonctions de FICHIER
    # publiques des deux bibliothèques — celles qu'emploie une application.
    # `args is None` marque le camp pickle : le suffixe ne sert plus qu'à
    # nommer les clés et le fichier
    if args is None:
        def ecrit():
            return _ecrit_pickle(chemin, objet)

        def lit():
            with open(chemin, "rb") as f:
                return pickle.load(f)
    else:
        def ecrit():
            return _ecrit_sj(chemin, objet, args)

        def lit():
            return serializejson.load(chemin, **(args_lecture or {}))

    return ecrit, lit


ESSAIS_DISQUE = 5


def mesures_disque(m, objet, camps, prefixe, args_lecture=None):
    # un aller-retour disque RÉEL par camp, rangé dans `m` en clés SCALAIRES
    # (agrege_par_groupe additionne les valeurs, un couple ne s'additionnerait
    # pas).
    #
    # Les camps sont INTERLACÉS, un tour complet à la fois, et NON mesurés
    # l'un après l'autre. Une rafale d'écritures durables congestionne le
    # volume — chiffrement, journal, writeback — et dans une série consécutive
    # le dernier camp paie pour tous ceux qui l'ont précédé : mesuré sur un son
    # de 10,4 Mo, pickle en tête à 23 ms puis base64 en queue à 140, quand il
    # en vaut 30 mesuré seul, et la sonde étalon passée de 7 à 42 ms au sortir
    # de la campagne. Interlacés, tous les camps voient la même congestion
    # moyenne, et le minimum par camp retient le tour le plus calme de chacun.
    # C'est l'A/B interlacé du reste du rapport, appliqué au disque.
    # la sonde d'abord, et une par PROFIL : les deux bornes qui encadrent la
    # campagne entière condamnent douze minutes de mesures pour une fenêtre de
    # contention de deux. Placée avant les essais, elle rend l'état dans lequel
    # ce profil-ci va être payé — la queue du profil précédent comprise
    m["sonde_disque"] = sonde_disque_libre()
    gestes = {}
    for suffixe, args in camps:
        chemin = _chemin_banc(f"{prefixe}_{suffixe}")
        gestes[suffixe] = (chemin,
                           *_gestes_disque(chemin, objet, args, args_lecture))
    ecritures = {suffixe: [] for suffixe in gestes}
    for _ in range(ESSAIS_DISQUE):
        for suffixe, (chemin, ecrit, _) in gestes.items():
            _efface(chemin)   # chaque essai écrit du NEUF, dans les deux camps
            burst()
            ecritures[suffixe].append(ecrit())
    # les fichiers du DERNIER tour servent de matière à la relecture, elle
    # aussi interlacée — et cache du noyau évincé juste avant chaque essai
    lectures = {suffixe: [] for suffixe in gestes}
    for _ in range(ESSAIS_DISQUE):
        for suffixe, (chemin, _, lit) in gestes.items():
            for ecrit in _fichiers_ecrits(chemin):
                _evince(ecrit)
            burst()
            t0 = perf()
            lit()
            lectures[suffixe].append(perf() - t0)
    for suffixe, (chemin, _, _) in gestes.items():
        bloque, total = min(ecritures[suffixe], key=lambda paire: paire[1])
        m[f"ecrit_bloque_{suffixe}"] = bloque
        m[f"ecrit_total_{suffixe}"] = total
        m[f"relit_{suffixe}"] = min(lectures[suffixe])
        m[f"octets_disque_{suffixe}"] = sum(os.path.getsize(ecrit)
                                            for ecrit
                                            in _fichiers_ecrits(chemin))
        _efface(chemin)


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
    # Côté serializejson c'est le DERNIER barreau du barème qui est comparé
    # (choix de Baptiste, 07/08) : face à des codecs dont c'est le métier, le
    # réglage à opposer est le plus petit qu'on sache produire, pas le plus
    # rapide. Chaque corpus porte aussi le compte de ses images et de ses
    # pixels : les temps se rendent PAR IMAGE, pas par corpus (voir le rendu)
    import collections
    import io
    import shutil
    import subprocess
    import tempfile

    from PIL import Image

    if shutil.which("cjxl") is None or shutil.which("djxl") is None:
        return [], ["(cjxl/djxl introuvables : section sautée)"]

    encodeur = serializejson.Encoder(
        return_bytes=True, bytes_compression=("smart", max(bareme_smart)))

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
    definitions = {}
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
        j = encodeur(tableau)

        def encode_png():
            b = io.BytesIO()
            image.save(b, "PNG")

        hauteur, largeur = tableau.shape[:2]
        m = {
            "nbytes": tableau.nbytes,
            "pixels": hauteur * largeur,
            "taille_min": len(j),
            "taille_png": len(png),
            "taille_jxl": len(jxl),
            "enc_min": chrono(lambda: encodeur(tableau),
                              plafond=0.4, froid=True),
            "dec_min": chrono(lambda: serializejson.loads(j), plafond=0.4,
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
        definitions.setdefault(groupe, collections.Counter())[
            (largeur, hauteur)] += 1
    shutil.rmtree(dossier_tmp, ignore_errors=True)
    for groupe, cumul in groupes.items():
        compte = definitions[groupe]
        (largeur, hauteur), _ = compte.most_common(1)[0]
        cumul["definition"] = (largeur, hauteur)
        cumul["definition_constante"] = len(compte) == 1
        cumul["images"] = sum(compte.values())
        # facteur qui ramène le temps CUMULÉ du corpus au temps d'UNE image de
        # la définition la plus représentée, au prorata du nombre de pixels.
        # Quand la définition est constante il rend simplement la moyenne par
        # image ; sinon il rend ce que coûterait une image de cette définition
        cumul["par_image"] = largeur * hauteur / cumul["pixels"]
    return sorted(groupes.items()), ecartees


def _rien():
    pass


def _rafale(f, n):
    for _ in range(n):
        f()


def chrono_unitaire(f, repets=2000):
    # `chrono` mesure UN appel de f : sous la microseconde, elle mesurerait
    # surtout perf_counter et la dispersion de l'ordonnanceur. On chronomètre
    # donc une RAFALE de `repets` appels, et on retranche le coût de la rafale
    # à vide — même boucle, même niveau d'indirection, mesuré dans la foulée
    # et dans le même processus, seule façon qu'il se retranche vraiment.
    plein = chrono(lambda: _rafale(f, repets), plafond=0.4)
    vide = chrono(lambda: _rafale(_rien, repets), plafond=0.4)
    return max(0.0, plein - vide) / repets


def mesure_appel_unitaire():
    # Le COÛT FIXE d'un appel, que tout le reste du rapport masque à dessein :
    # partout ailleurs on mesure des LOTS, pour rapporter le prix d'un OBJET
    # et non celui de l'appel qui l'enveloppe. Sur un objet minuscule c'est
    # l'inverse qui domine — et c'est le régime d'une application qui range
    # un événement, une ligne de journal ou une trame, un par un.
    #
    # Trois étages sont chronométrés sur le MÊME objet, ce qui SITUE la
    # dépense au lieu de la constater : l'écrivain json nu (rapidjson.dumps,
    # sans aucun protocole serializejson), l'Encoder appelé directement, puis
    # la fonction de module (qui va chercher l'instance par défaut du thread).
    # L'écart entre les deux premiers EST le prix du protocole ; celui entre
    # le premier et pickle est le prix du FORMAT, texte contre opcodes.
    rapidjson = sys.modules["rapidjson"]
    objets = [
        ("entier", 12345),
        ("chaîne de 12 octets", "douze octets"),
        ("tuple de 2 entiers", (3, 7)),
        ("dict de 4 clés", {"i": 7, "nom": "maillon 7", "v": [7, 14, 21],
                            "ok": True}),
        ("dict de 30 clés", dict((str(i), i) for i in range(30))),
    ]
    encodeur = serializejson.Encoder(return_bytes=True)
    lignes = []
    for nom, objet in objets:
        encodeur(objet)   # peuple les caches (classes vues, motifs de bits)
        lignes.append((nom, {
            "octets_pickle": len(pickle.dumps(objet, protocol=4)),
            "octets_sj": len(encodeur(objet)),
            "pickle": chrono_unitaire(lambda: pickle.dumps(objet, protocol=4)),
            "json_nu": chrono_unitaire(lambda: rapidjson.dumps(objet)),
            "encodeur": chrono_unitaire(lambda: encodeur(objet)),
            "module": chrono_unitaire(lambda: serializejson.dumpb(objet)),
        }))
    return lignes


def mesure_incremental():
    # La sérialisation INCRÉMENTALE, sur le VRAI disque de la machine : des
    # objets rangés un par un dans un document qui reste valide à tout
    # instant. pickle a un équivalent — Pickler.dump() en boucle — mais il
    # écrit une CONCATÉNATION d'enregistrements : pas de document englobant,
    # pas d'index, pas d'accès direct, et une tranche relue par un Unpickler
    # neuf échoue dès que le mémo a partagé un objet entre deux dumps.
    #
    # Deux temps sont rendus, et c'est le premier qui décide de la latence
    # d'une application : le temps BLOQUÉ, celui que l'appel rend à
    # l'appelant, et le temps TOTAL, jusqu'à ce que tout soit parti vers le
    # noyau (fermeture comprise). serializejson délègue à son écrivain le
    # base64, la compression et le write() ; pickle fait tout dans le thread
    # appelant. AUCUN fsync d'aucun côté : on compare ce que les deux
    # bibliothèques font, pas la latence du matériel. Un tmpfs ne mesurerait
    # rien, d'où le dossier pris dans le dépôt.
    dossier = RACINE / ".banc_incremental"
    shutil.rmtree(dossier, ignore_errors=True)
    dossier.mkdir()

    def sj_append(objets, index):
        chemin = dossier / "sj.json"
        if chemin.exists():
            chemin.unlink()
        e = serializejson.Encoder(file=str(chemin), indent=None,
                                  index="sidecar" if index else None)
        t0 = perf()
        for o in objets:
            e.append(o)
        bloque = perf() - t0
        e.close()
        serializejson.wait_writes()
        return bloque, perf() - t0, chemin.stat().st_size

    def pk_dump(objets):
        chemin = dossier / "pk.pickle"
        f = open(chemin, "wb")
        p = pickle.Pickler(f, protocol=4)
        t0 = perf()
        for o in objets:
            p.dump(o)
        bloque = perf() - t0
        f.close()
        return bloque, perf() - t0, chemin.stat().st_size

    essais = [
        ("serializejson `append`", lambda o: sj_append(o, False)),
        ("serializejson `append` + index", lambda o: sj_append(o, True)),
        ("pickle `Pickler.dump()` en boucle", pk_dump),
    ]
    charges = [
        ("20 000 dicts de ~57 octets",
         [{"i": i, "nom": "maillon %d" % i, "v": [i, i * 2, i * 3],
           "ok": True} for i in range(20000)], 3),
        # bruit INCOMPRESSIBLE : le cas où compression, base64 et disque
        # pèsent tous les trois. Une vraie trame RVB 1920x1080 fait 6,2 Mo
        ("20 trames 1920×1080 RVB (6,2 Mo pièce)",
         [{"n": i, "img": os.urandom(1920 * 1080 * 3)} for i in range(20)], 2),
    ]
    lignes = []
    for titre, objets, tours in charges:
        scores = {}
        for _ in range(tours):
            for nom, fonction in essais:
                b, t, taille = fonction(objets)
                garde = scores.setdefault(nom, [[], [], taille])
                garde[0].append(b)
                garde[1].append(t)
        lignes.append((titre, len(objets),
                       [(nom, min(bs), min(ts), taille)
                        for nom, (bs, ts, taille) in scores.items()]))
    shutil.rmtree(dossier, ignore_errors=True)
    return lignes


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
            # le pendant str du même réglage : la barre `dumps` des figures
            encodeur_str = serializejson.Encoder()
            encodeur_str(objets)
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
            # le disque se mesure par les fonctions de FICHIER, pas par les
            # encodeurs ci-dessus : ce chemin-là doit lui aussi savoir rejouer
            # la catégorie, sans quoi elle est écartée comme les autres
            autorisees = list(encodeur.get_dumped_classes())
            essai = _chemin_banc("essai_types")
            serializejson.dump(lot, essai)
            serializejson.wait_writes()
            serializejson.load(essai, authorized_classes=autorisees)
            _efface(essai)
        except Exception:
            ecartees.append(categorie)
            continue
        # PAS de vidage de cache ici, contrairement aux gros tableaux : un lot
        # de quelques kilo-octets tient en cache DANS LA VRAIE VIE aussi, et
        # l'évincer ne mesurerait que le rechargement de l'interpréteur
        m = {
            "taille_pickle": len(p),
            "taille_sj": len(j),
            "dumps_pickle": chrono(lambda: pickle.dumps(lot, protocol=4),
                                   plafond=0.4),
            "dumps_sj": chrono(lambda: encodeur_str(lot), plafond=0.4),
            "dumpb_sj": chrono(lambda: encodeur(lot), plafond=0.4),
            "loads_pickle": chrono(lambda: pickle.loads(p), plafond=0.4),
            "loads_sj": chrono(lambda: decodeur(j), plafond=0.4),
        }
        mesures_disque(m, lot, [("pickle", None), ("sj", {})], "types",
                       {"authorized_classes": autorisees})
        lignes.append((categorie, m))
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
    # chaque variante s'écrit DEUX fois en RAM (demande de Baptiste, 10/08) :
    # vers un str (`dumps`, la sortie texte native) et vers des bytes
    # (`dumpb`, le camp de pickle.dumps) — depuis le zéro-copie str, les deux
    # sorties n'ont plus le même prix
    encodeur_min_str = serializejson.Encoder(
        bytes_compression=("smart", max(bareme_smart)))
    encodeur_b64_str = serializejson.Encoder(bytes_compression=None)
    # les clés `sj` = réglages PAR DÉFAUT, qui dépendent de la CIBLE depuis le
    # 10/08 : les clés RAM (dumps/dumpb/loads) mesurent le barreau RAM du
    # barème, les clés disque (mesures_disque) le barreau fichier
    m = {
        "nbytes": a.nbytes,
        "taille_pickle": len(p),
        "taille_sj": len(j),
        "taille_min": len(j_min),
        "taille_b64": len(j_b64),
        # froid=True : régime RAM, cache vidé avant chaque essai (voir chrono)
        "dumps_pickle": chrono(lambda: pickle.dumps(a, protocol=4), froid=True),
        "dumps_sj": chrono(lambda: serializejson.dumps(a), froid=True),
        "dumpb_sj": chrono(lambda: serializejson.dumpb(a), froid=True),
        "dumps_min": chrono(lambda: encodeur_min_str(a), froid=True),
        "dumpb_min": chrono(lambda: encodeur_min(a), froid=True),
        "dumps_b64": chrono(lambda: encodeur_b64_str(a), froid=True),
        "dumpb_b64": chrono(lambda: encodeur_b64(a), froid=True),
        "loads_pickle": chrono(lambda: pickle.loads(p), froid=True),
        "loads_sj": chrono(lambda: serializejson.loads(j), froid=True),
        "loads_min": chrono(lambda: serializejson.loads(j_min), froid=True),
        "loads_b64": chrono(lambda: serializejson.loads(j_b64), froid=True),
    }
    mesures_disque(m, a, [("pickle", None), ("sj", {}),
                          ("min", {"bytes_compression":
                                   ("smart", max(bareme_smart))}),
                          ("b64", {"bytes_compression": None})],
                   "profil")
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
            if cle == "seuil":
                continue                       # recalculé sur les sommes
            elif cle == "sonde_disque":
                # une congestion ne s'ADDITIONNE pas : le corpus a été payé au
                # pire de ce que ses fichiers ont vu
                cumul[cle] = max(cumul.get(cle, 0), valeur)
            else:
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
           "**Les barres des figures.** Chaque figure porte, sous le cadre"
           " bleu du poids, des rapports de temps : écrire en RAM deux"
           " fois — `dumps` (vers un str, la sortie texte native) puis `dumpb`"
           " (vers des bytes, le camp de `pickle.dumps`) —, relire depuis la"
           " RAM, puis écrire et relire SUR LE DISQUE. Les deux écritures"
           " mémoire n'ont plus le même prix depuis le zéro-copie str, d'où"
           " les deux barres (demande de Baptiste, 10/08) ; pickle n'a qu'une"
           " écriture, des bytes, qui sert de référence aux deux. Les deux"
           " régimes de CACHE ont été retirés : aucune application réelle ne"
           " les rencontre sur des données qu'elle produit ou range.",
           "",
           "**Le profil par défaut occupe deux figures** (demande de"
           " Baptiste, 10/08) : son barreau dépend désormais de la CIBLE —"
           f" barreau {bareme_smart_defaut_ram} pour `dumps`/`dumpb` (le"
           " premier qui compresse, le moins cher : l'appelant paie la"
           f" compression), barreau {bareme_smart_defaut_fichier} pour"
           " `dump`/`append` (le plus petit : la compression part au fil"
           " d'écriture, son surcoût ne bloque plus l'appelant). Une page qui"
           " mêlerait RAM et disque mêlerait donc deux barreaux : la page RAM"
           " porte les trois barres mémoire au barreau RAM, la page DISQUE"
           " porte l'aller-retour fichier seul au barreau fichier — son cadre"
           " bleu est le poids réellement ÉCRIT (index compris), pas le poids"
           " en mémoire. Les deux bouts du barème (niveau 0 et dernier"
           " barreau), mesurés à barreau FIXE, gardent leurs cinq barres sur"
           " une seule page.",
           "",
           "**Les deux barres de disque sont MESURÉES, pas projetées.** Elles"
           " l'étaient jusqu'au 08/08 : temps de calcul + octets / débit"
           " constructeur. Ce sont désormais de vraies écritures et de vraies"
           " relectures sur le volume du dépôt. L'écriture compte le geste"
           " DURABLE entier — jusqu'au `fsync`, sans lequel on ne mesurerait"
           " que le cache d'écriture du noyau ; la relecture est faite cache"
           " du noyau ÉVINCÉ (`posix_fadvise(DONTNEED)`, vérifié : 2 556 Mo/s"
           " à chaud contre 390 Mo/s après éviction). Meilleur de cinq essais"
           " et non médiane : sans fsync le noyau reporte, et ce qu'un essai"
           " ne paie pas, le suivant le paie (mesuré sur 210 Mo : 103 ms, puis"
           " 801, puis 2 540). Le modèle qui les remplaçait tablait sur 3,5"
           " Go/s ; le volume mesuré en rend 45 à 93 en écriture durable — la"
           " projection SOUS-ESTIMAIT donc largement l'avantage du poids. Seule"
           " la page pyperformance garde la projection, faute d'aller-retour"
           " disque sur ces charges, et ses barres le disent.",
           "",
           "**La barre d'écriture disque est coupée en deux** (demande de"
           " Baptiste, 08/08). Le segment FONCÉ du bas est ce que `dump`"
           " bloque, c'est-à-dire ce que l'appelant attend vraiment ; le"
           " segment CLAIR au-dessus est ce que le fil d'écriture termine"
           " derrière lui — base64, compression et `write()` — plus le `fsync`."
           " C'est le réglage par défaut `disk_write_mode=\"fast_release\"` :"
           " `dump` rend la main dès l'objet sérialisé. pickle n'a pas"
           " d'équivalent, tout son temps est bloquant sauf le `fsync` que le"
           " noyau diffère ; les deux segments empilés se comparent donc bien"
           " au temps durable total de pickle, qui est le dénominateur.",
           "",
           "| profil | sonde | pickle bloqué | pickle durable |"
           " serializejson bloqué | serializejson durable |"
           " relecture pickle | relecture serializejson |",
           "|---|---|---|---|---|---|---|---|"]
    for nom, m in resultats:
        sonde = fmt_ms(m["sonde_disque"])
        md.append(f"| {nom} |"
                  f" {sonde if m['sonde_disque'] < 0.012 else '**' + sonde + '**'}"
                  f" | {fmt_ms(m['ecrit_bloque_pickle'])}"
                  f" | {fmt_ms(m['ecrit_total_pickle'])}"
                  f" | {fmt_ms(m['ecrit_bloque_sj'])}"
                  f" | {fmt_ms(m['ecrit_total_sj'])}"
                  f" | {fmt_ms(m['relit_pickle'])}"
                  f" | {fmt_ms(m['relit_sj'])} |")
    md += ["",
           "Temps réels du tableau ci-dessus : réglages par défaut des deux"
           " côtés, fichiers écrits dans le dépôt puis relus cache évincé.",
           "",
           "La colonne « sonde » est l'état du support mesuré JUSTE AVANT ce"
           " profil-là : 4 Mo écrits durablement, fsync compris. Cache du"
           " disque encore vide, elle rend quelques millisecondes ; en GRAS,"
           " il était saturé et le support rendait son débit de plateau. Ce"
           " n'est donc PAS un indicateur de charge étrangère mais un régime :"
           " les millisecondes d'une ligne en gras ne se comparent pas à"
           " celles d'une ligne qui ne l'est pas. Les deux camps, eux, restent"
           " comparables ENTRE EUX sur chaque ligne : ils sont mesurés"
           " interlacés, donc sous le même régime.",
           "",
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
           " rechargement de l'interpréteur. Les trois premières barres de la"
           " figure sont donc des temps de cache.",
           "",
           "Les deux barres de disque, elles, sont mesurées comme partout"
           " ailleurs, et à ces tailles elles disent surtout ceci : le disque"
           " coûte un FORFAIT. Un `fsync` sur un fichier de quelques kilo-octets"
           " se paie de la milliseconde, cent fois le calcul des deux camps —"
           " les rapports d'écriture s'écrasent donc vers ×1 quel que soit le"
           " poids du document. Ce n'est pas que « le transfert est du bruit »,"
           " c'est l'inverse : c'est le calcul qui l'est. Ce que la barre coupée"
           " montre alors est la seule chose qui distingue encore les deux"
           " camps sur un petit document — la part que `dump` rend"
           " immédiatement à l'appelant.",
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
    md += ["",
           "## corpus d'images : face aux codecs d'images spécialisés",
           "",
           f"Le DERNIER barreau du barème (barreau {max(bareme_smart)}, le plus"
           " petit) contre PNG (PIL, réglages par défaut) et JPEG XL sans perte"
           " (cjxl -d 0 -e 3, la référence actuelle du compromis poids/vitesse ;"
           " ses temps incluent le lancement du processus). Poids en % des"
           " octets BRUTS ; ces codecs prédisent en 2D, notre chaîne générique"
           " non — c'est l'écart attendu sur les photos.",
           "",
           "Les temps sont donnés PAR IMAGE, pas par corpus : les corpus n'ont"
           " ni le même nombre d'images ni la même définition. Quand la"
           " définition est constante sur le corpus, c'est la moyenne par image"
           " et la définition est donnée telle quelle ; sinon le temps est"
           " ramené à la définition la plus représentée, au prorata du nombre de"
           " pixels (colonne « définition », mention « ramené »). La mise à"
           " l'échelle suppose un coût proportionnel aux pixels : elle est juste"
           " pour le calcul, optimiste pour JPEG XL dont le lancement de"
           " processus est un coût FIXE qu'elle réduit avec le reste.",
           "",
           "| corpus | images | définition | brut |"
           f" barreau {max(bareme_smart)} | PNG | JPEG XL |"
           " enc. sj | enc. PNG | enc. JXL |"
           " déc. sj | déc. PNG | déc. JXL |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for groupe, m in codecs_images:
        largeur, hauteur = m["definition"]
        pourcent = lambda cle: f"{100 * m[cle] / m['nbytes']:.0f} %"
        temps = lambda cle: fmt_ms(m[cle] * m["par_image"])
        md.append(
            f"| {groupe} | {m['images']}"
            f" | {largeur}×{hauteur}"
            + ("" if m["definition_constante"] else " (ramené)")
            + f" | {fmt_octets(m['nbytes'])}"
            f" | {pourcent('taille_min')} | {pourcent('taille_png')}"
            f" | {pourcent('taille_jxl')}"
            f" | {temps('enc_min')} | {temps('enc_png')} | {temps('enc_jxl')}"
            f" | {temps('dec_min')} | {temps('dec_png')} | {temps('dec_jxl')} |")
    if codecs_ecartes:
        md += ["", "Écartées : " + ", ".join(codecs_ecartes) + "."]
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
           "## coût FIXE d'un appel (objets minuscules)",
           "",
           "Tout le reste du rapport mesure des LOTS, pour rapporter le prix"
           " d'un OBJET et non celui de l'appel qui l'enveloppe. Ici c'est"
           " l'appel qu'on mesure, seul : un objet par appel, aussi petit que"
           " possible. C'est le régime d'une application qui range un"
           " événement, une ligne de journal ou une trame au fil de l'eau, et"
           " c'est le seul où le coût fixe décide de tout.",
           "",
           "Les trois colonnes serializejson SITUENT la dépense au lieu de la"
           " constater. `rapidjson.dumps` est l'écrivain json nu, sans aucun"
           " protocole serializejson : son écart à pickle est le prix du"
           " FORMAT (du texte lisible contre des opcodes binaires), et rien"
           " ne le fera disparaître. L'`Encoder` appelé directement ajoute le"
           " protocole (recettes, mémo des doublons, poussée des paramètres"
           " globaux). La fonction de module ajoute la recherche de"
           " l'instance par défaut du thread.",
           "",
           "| objet | pickle (µs) | `rapidjson.dumps` (µs) | `Encoder(o)`"
           " (µs) | `serializejson.dumpb(o)` (µs) | octets pickle |"
           " octets serializejson |",
           "|---|---|---|---|---|---|---|"]
    for nom, m in donnees["appel"]:
        gras = lambda v, r: f"**{v:.2f}**" if r else f"{v:.2f}"
        md.append(
            f"| {nom} | {m['pickle']*1e6:.2f}"
            f" | {gras(m['json_nu']*1e6, m['json_nu'] < m['pickle'])}"
            f" | {gras(m['encodeur']*1e6, m['encodeur'] < m['pickle'])}"
            f" | {gras(m['module']*1e6, m['module'] < m['pickle'])}"
            f" | {m['octets_pickle']} | {m['octets_sj']} |")
    md += ["",
           "## sérialisation incrémentale (disque réel)",
           "",
           "Ranger des objets UN PAR UN dans un document qui reste valide à"
           " tout instant. pickle a un équivalent — `Pickler.dump()` en"
           " boucle — mais il écrit une CONCATÉNATION d'enregistrements :"
           " pas de document englobant, pas d'index, pas d'accès direct, et"
           " une tranche relue par un `Unpickler` neuf échoue dès que le mémo"
           " a partagé un objet entre deux dumps. Le tableau compare donc des"
           " garanties inégales, à l'avantage de pickle.",
           "",
           "Deux temps, et c'est le premier qui décide de la latence : le"
           " temps **bloqué**, celui que l'appel rend à l'appelant, et le"
           " temps **total**, jusqu'à ce que tout soit parti vers le noyau."
           " serializejson délègue à son écrivain le base64, la compression et"
           " le `write()` ; pickle fait tout dans le thread appelant. Aucun"
           " `fsync` d'aucun côté : on compare ce que les deux bibliothèques"
           " font, pas la latence du matériel.",
           ""]
    for titre, combien, essais in donnees["incremental"]:
        md += [f"**{titre}** ({combien} objets)", "",
               "| écrivain | bloqué | total | bloqué par objet | octets |",
               "|---|---|---|---|---|"]
        for nom, bloque, total, taille in essais:
            md.append(f"| {nom} | {fmt_ms(bloque)} | {fmt_ms(total)}"
                      f" | {bloque / combien * 1e6:.1f} µs"
                      f" | {fmt_octets(taille)} |")
        md.append("")
    md += ["Lecture : sur les petits maillons, pickle écrit moins d'octets et"
           " reste devant — le format décide, comme partout ailleurs sur les"
           " micro-objets. Sur les trames, l'écart s'inverse et change"
           " d'ordre de grandeur : le temps rendu à l'appelant ne dépend plus"
           " que de la remise au fil d'écriture, alors que `Pickler.dump()`"
           " porte la recopie ET l'attente du disque dans le thread appelant.",
           "",
           "## machines réalistes (projection)",
           "",
           "Chaque CPU est apparié à un stockage de sa gamme, le calcul mis à"
           " l'échelle du CPU et le transfert des octets au débit du stockage —"
           " le temps TOTAL, celui que voit l'application. Rien de neuf n'est"
           " mesuré ici : les mesures précédentes sont projetées sur des couples"
           " du commerce, ce qui ferme le rapport comme les deux courbes de"
           " support des dernières pages. Profil d'ancrage : le plus gros profil"
           f" individuel du corpus, « {profil_machines} ».",
           "",
           "| machine | écriture | lecture |",
           "|---|---|---|"]
    for (nom, _, _), e, l in zip(MACHINES, machines["dumps"],
                                 machines["loads"]):
        rapport = lambda v: f"**×{v:.2f}**" if v < 1 else f"×{v:.2f}"
        md.append(f"| {nom.replace(chr(10), ' ')} | {rapport(e)}"
                  f" | {rapport(l)} |")
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
            ("i7 mobile (CPU mesuré)\n+ NVMe PCIe 3 (~3,5 Go/s)", 1.0, 3.5e9),
            ("MacBook Pro M4\n+ SSD interne (~6 Go/s)", 1.7, 6e9),
            ("tour Ryzen 9 9950X\n+ NVMe PCIe 5 (~14 Go/s)", 1.8, 14e9)]


# le disque HYPOTHÉTIQUE des seules figures encore projetées (pyperformance) —
# pris DANS la liste ci-dessus, pour qu'un changement n'ait qu'un seul endroit
# où se faire. ⚠ Ce n'est PAS le support réellement mesuré : le CPU de la
# machine de mesure est bien celui de cette ligne, son volume de travail non,
# et c'est `support_du_depot()` qui le nomme dans l'en-tête du rapport
_MACHINE_MESURE = next(m for m in MACHINES if "mesuré" in m[0])
DISQUE = _MACHINE_MESURE[0].split("+ ")[1]
DEBIT_DISQUE = _MACHINE_MESURE[2]


# les quatre régimes tracés sous le cadre de mémoire, dans l'ordre des barres :
# (libellé, couleur de la barre, couleur de son étiquette chiffrée). Les deux
# barres de RAM sont volontairement PÂLES — ce sont les deux barres de disque
# qui portent le cas d'usage réel, elles doivent sauter aux yeux les premières ;
# l'étiquette, elle, reste dans le ton soutenu, sinon elle ne se lirait plus
REGIMES = [("écrire vers la RAM, dumps (→ str)", "#fbd7b5", ORANGE),
           ("écrire vers la RAM, dumpb (→ bytes)", "#f8e3a8", "#975a16"),
           ("relire depuis la RAM", "#f0c3b4", "#9c4221"),
           ("temps bloquant du dump", "#2f855a", "#2f855a"),
           ("relire depuis le disque, MESURÉ (cache du noyau évincé)",
            "#22543d", "#22543d")]

# la moitié HAUTE de la barre d'écriture disque, quand elle est coupée en deux :
# ce que le fil d'écriture finit APRÈS que `dump` a rendu la main (demande de
# Baptiste, 08/08). Très pâle (demande de Baptiste, 10/08) : c'est le temps
# BLOQUANT du bas qui doit sauter aux yeux, le haut ne fait que compléter le
# total durable
VERT_CLAIR = "#ddf3e6"
LEGENDE_FIL = "finalisation de l'écriture sur disque par 2ème thread, dump déjà rendu"

# les figures qui n'ont PAS de mesure disque (pyperformance : les charges
# viennent des benchmarks officiels, en mémoire) gardent la PROJECTION —
# libellés distincts, pour que les deux sémantiques ne se confondent pas.
# Quatre barres seulement : la réplique officielle mesure l'écriture avec
# l'encodeur bytes, c'est donc la barre dumpb qu'elle porte
REGIMES_PROJETES = [REGIMES[1], REGIMES[2],
                    (f"écrire vers le disque, PROJETÉ, {DISQUE}",
                     "#4c9a77", "#2f855a"),
                    (f"relire depuis le disque, PROJETÉ, {DISQUE}",
                     "#3c7a5d", "#22543d")]


def rapports_regimes(reference, candidat):
    # les rapports candidat/référence tracés par `dispositif`, à partir de
    # deux n-uplets de TEMPS dans l'ordre des barres
    return [c / r for r, c in zip(reference, candidat)]


def quatre_regimes_projetes(reference, candidat):
    # la variante MODÉLISÉE, pour les charges dont on n'a pas d'aller-retour
    # disque mesuré : au temps de calcul s'ajoute celui du transfert des
    # octets au débit constructeur du disque de la machine de mesure
    (o_r, e_r, l_r), (o_c, e_c, l_c) = reference, candidat
    return rapports_regimes(
        (e_r, l_r, e_r + o_r / DEBIT_DISQUE, l_r + o_r / DEBIT_DISQUE),
        (e_c, l_c, e_c + o_c / DEBIT_DISQUE, l_c + o_c / DEBIT_DISQUE))


def quintuplet_mesure(m, suffixe):
    # les cinq temps d'un camp, dans l'ordre des barres — les deux écritures
    # mémoire (dumps → str puis dumpb → bytes ; pickle n'a qu'une écriture,
    # des bytes, prise pour les deux), la relecture, puis le disque réel
    # (l'écriture disque compte le geste DURABLE entier, fil d'écriture et
    # fsync compris)
    return (m[f"dumps_{suffixe}"],
            m.get(f"dumpb_{suffixe}", m[f"dumps_{suffixe}"]),
            m[f"loads_{suffixe}"],
            m[f"ecrit_total_{suffixe}"], m[f"relit_{suffixe}"])


def dispositif(noms, poids, regimes, titre, etiquette_poids, rotation=18,
               bloquants=None, libelles=REGIMES):
    # LE dispositif commun à toutes les figures de comparaison : les barres
    # de temps (écrire vers un str puis vers des bytes, relire, en RAM puis
    # sur le disque de la machine de mesure) surmontées du CADRE bleu du
    # poids, large comme les barres réunies et posé par-dessus elles. Son arête haute donne le poids, et rien
    # n'est jamais masqué — que le poids passe au-dessus ou en dessous des
    # temps, les deux restent lisibles. Une barre PETITE = avantage du candidat.
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgba

    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    x = numpy.arange(len(noms))
    # autant de barres que de régimes (4 projetés, 5 mesurés), serrées dans la
    # même emprise totale de 0,76
    n = len(libelles)
    LARGEUR = 0.76 / n
    # étiquettes de valeur debout quand les colonnes sont serrées, couchées
    # quand la place existe — couchées, elles se lisent même sur une barre
    # écrasée en bas de l'axe (face aux codecs d'images, ×0,03 contre ×0,07)
    debout = len(noms) > 6
    for rang, (valeurs, (etiquette, couleur, couleur_texte)) in enumerate(
            zip(regimes, libelles)):
        position = x + (rang - (n - 1) / 2) * LARGEUR
        # la barre d'ÉCRITURE DISQUE — l'avant-dernière — se coupe en deux
        # quand on sait où passe la main : en bas ce que `dump` bloque, en
        # haut ce que le fil d'écriture termine derrière l'appelant. Les deux
        # segments empilés font le temps durable total, celui qui se compare
        # à pickle
        if rang == n - 2 and bloquants is not None:
            ax.bar(position, bloquants, LARGEUR, color=couleur,
                   label=etiquette, zorder=2)
            ax.bar(position, valeurs - bloquants, LARGEUR, bottom=bloquants,
                   color=VERT_CLAIR, label=LEGENDE_FIL, zorder=2)
            for centre, b, v in zip(position, bloquants, valeurs):
                # le bloqué n'est annoté que s'il se distingue du total :
                # collées, les deux étiquettes ne se liraient plus
                if not numpy.isnan(b) and b < 0.75 * v:
                    ax.annotate(f"×{b:.2f}", (centre, b), ha="center",
                                va="bottom", fontsize=5.5 if debout else 6.5,
                                rotation=90 if debout else 0, color="#22543d",
                                zorder=6)
        else:
            ax.bar(position, valeurs, LARGEUR, color=couleur, label=etiquette,
                   zorder=2)
        for centre, v in zip(position, valeurs):
            # une case sans mesure vaut NaN : ni barre, ni étiquette
            if not numpy.isnan(v):
                ax.annotate(f"×{v:.2f}", (centre, v), ha="center",
                            va="bottom", fontsize=5.5 if debout else 7,
                            rotation=90 if debout else 0, color=couleur_texte,
                            zorder=6)
    # le poids en aplat bleu très translucide, PAR-DESSUS les barres de temps :
    # elles couvrent exactement la largeur du cadre, un fond passé dessous
    # serait entièrement caché. L'aplat teinte donc les temps qu'il recouvre,
    # d'où l'alpha très faible — assez pour voir jusqu'où monte le poids, pas
    # assez pour gêner la lecture des barres en dessous
    ax.bar(x, poids, LARGEUR * n, facecolor=to_rgba(BLEU, 0.13),
           edgecolor=BLEU, linewidth=2.2, zorder=4, label=etiquette_poids)
    for centre, v in zip(x, poids):
        # calée sur l'arête GAUCHE du cadre, là où elle ne tombe que sur la
        # première barre (pâle) ou sur le fond : le cartouche blanc qui la
        # rendait lisible au centre n'est alors plus nécessaire
        ax.annotate(f"×{v:.2f}", (centre - (n / 2 - 0.1) * LARGEUR, v),
                    ha="left", va="bottom", fontsize=7, color=BLEU,
                    weight="bold", zorder=6)
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
    # UNE figure par variante à barreau FIXE (les deux bouts du barème),
    # portant les cinq barres : la mémoire ne dépend ni du sens ni du support,
    # elle n'est donc tracée qu'une fois par profil
    resultats = donnees["profils"]
    regimes = numpy.array([
        rapports_regimes(quintuplet_mesure(m, "pickle"),
                         quintuplet_mesure(m, suffixe))
        for _, m in resultats]).T
    return dispositif(
        [nom for nom, _ in resultats],
        numpy.array([m[f"taille_{suffixe}"] / m["taille_pickle"]
                     for _, m in resultats]),
        regimes, titre, "mémoire  (poids serializejson / pickle)",
        bloquants=numpy.array([m[f"ecrit_bloque_{suffixe}"]
                               / m["ecrit_total_pickle"]
                               for _, m in resultats]))


def figure_ram(donnees, suffixe, titre):
    # la moitié RAM du profil PAR DÉFAUT (demande de Baptiste, 10/08 : depuis
    # que le barreau par défaut dépend de la cible, une figure qui mêlerait
    # RAM et disque mêlerait deux barreaux) : dumps → str, dumpb → bytes et
    # loads, au barreau RAM — le poids est celui du document en mémoire
    resultats = donnees["profils"]
    regimes = numpy.array([
        rapports_regimes(
            (m["dumps_pickle"], m["dumps_pickle"], m["loads_pickle"]),
            (m[f"dumps_{suffixe}"], m[f"dumpb_{suffixe}"],
             m[f"loads_{suffixe}"]))
        for _, m in resultats]).T
    return dispositif(
        [nom for nom, _ in resultats],
        numpy.array([m[f"taille_{suffixe}"] / m["taille_pickle"]
                     for _, m in resultats]),
        regimes, titre, "mémoire  (poids serializejson / pickle)",
        libelles=REGIMES[:3])


def figure_fichier(donnees, suffixe, titre):
    # la moitié FICHIER du profil PAR DÉFAUT : uniquement écrire vers le
    # disque (barre coupée : bloquant en bas, fil d'écriture en haut) et
    # relire depuis le disque, au barreau fichier — le poids est celui des
    # octets réellement écrits (index sidecar compris), pas celui du document
    # en mémoire, qui appartient à la page RAM
    resultats = donnees["profils"]
    regimes = numpy.array([
        rapports_regimes(
            (m["ecrit_total_pickle"], m["relit_pickle"]),
            (m[f"ecrit_total_{suffixe}"], m[f"relit_{suffixe}"]))
        for _, m in resultats]).T
    return dispositif(
        [nom for nom, _ in resultats],
        numpy.array([m[f"octets_disque_{suffixe}"]
                     / m["octets_disque_pickle"] for _, m in resultats]),
        regimes, titre,
        "poids écrit sur le disque  (serializejson / pickle)",
        bloquants=numpy.array([m[f"ecrit_bloque_{suffixe}"]
                               / m["ecrit_total_pickle"]
                               for _, m in resultats]),
        libelles=REGIMES[3:])


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
        rapports_regimes(quintuplet_mesure(m, "pickle"),
                         quintuplet_mesure(m, "sj"))
        for _, m in lignes]).T
    return dispositif(
        [nom for nom, _ in lignes],
        numpy.array([m["taille_sj"] / m["taille_pickle"] for _, m in lignes]),
        regimes, titre, "poids du document  (serializejson / pickle)",
        rotation=25,
        bloquants=numpy.array([m["ecrit_bloque_sj"] / m["ecrit_total_pickle"]
                               for _, m in lignes]))


# les trois camps de la comparaison aux codecs d'images, dans l'ordre des
# barres : libellé, suffixe des clés de mesure, couleur
CODECS_IMAGES = [(f"serializejson (barreau {max(bareme_smart)})", "min", BLEU),
                 ("PNG (PIL)", "png", "#4a9d6e"),
                 ("JPEG XL sans perte (cjxl -e 3)", "jxl", ORANGE)]


def fmt_ms(secondes):
    ms = 1e3 * secondes
    return f"{ms:.0f} ms" if ms >= 10 else (f"{ms:.1f} ms" if ms >= 1
                                            else f"{ms:.2f} ms")


def figure_codecs_images(donnees, sens, titre):
    # UNE SEULE figure pour toute la comparaison aux codecs d'images spécialisés
    # (choix de Baptiste, 07/08) : en haut le POIDS en % des octets bruts, en
    # bas les TEMPS. Ici la référence n'est pas pickle mais le brut, d'où le
    # pourcentage plutôt que le dispositif à cadre du reste du rapport.
    # Les temps sont rendus PAR IMAGE : les corpus n'ont ni le même nombre
    # d'images ni la même définition, un temps cumulé ne se comparerait pas
    # d'un corpus à l'autre. Quand la définition est constante sur le corpus,
    # c'est la moyenne par image et la définition est écrite telle quelle ;
    # sinon le temps est ramené à la définition la PLUS REPRÉSENTÉE, au prorata
    # du nombre de pixels (mention « ramené »)
    import matplotlib.pyplot as plt

    groupes = donnees["codecs"]
    noms = []
    for groupe, m in groupes:
        largeur, hauteur = m["definition"]
        noms.append(f"{groupe}\n{m['images']} images, {largeur}×{hauteur}"
                    + ("" if m["definition_constante"] else " (ramené)"))
    fig, (haut, bas) = plt.subplots(
        2, 1, figsize=(11.69, 8.27), sharex=True,
        gridspec_kw={"height_ratios": (1, 1.25), "hspace": 0.08})
    x = numpy.arange(len(groupes))
    for decalage, (etiquette, cle, couleur) in zip((-0.27, 0.0, 0.27),
                                                   CODECS_IMAGES):
        valeurs = [100 * m[f"taille_{cle}"] / m["nbytes"] for _, m in groupes]
        haut.bar(x + decalage, valeurs, 0.25, color=couleur, label=etiquette)
        for centre, v in zip(x + decalage, valeurs):
            haut.annotate(f"{v:.0f} %", (centre, v), ha="center", va="bottom",
                          fontsize=8)
    haut.axhline(100, color="gray", ls="--", lw=1)
    haut.annotate("octets bruts", (len(groupes) - 0.5, 100), fontsize=7,
                  color="gray", ha="right", va="bottom")
    haut.set_ylabel("poids (% des octets bruts)")
    haut.set_ylim(top=max(125, 1.18 * max(
        100 * m[f"taille_{cle}"] / m["nbytes"]
        for _, m in groupes for _, cle, _ in CODECS_IMAGES)))
    haut.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3,
                fontsize=9, frameon=False)
    # six barres par corpus : les trois camps à l'écriture, puis les trois à la
    # lecture. La couleur dit le camp (même que celle du poids au-dessus), la
    # hachure dit le sens — deux lectures possibles sans doubler la légende
    LARGEUR = 0.14
    for rang, (mesure, hachure) in enumerate((("enc", None), ("dec", "///"))):
        for i, (etiquette, cle, couleur) in enumerate(CODECS_IMAGES):
            valeurs = [m[f"{mesure}_{cle}"] * m["par_image"]
                       for _, m in groupes]
            position = x + (3 * rang + i - 2.5) * LARGEUR
            bas.bar(position, valeurs, LARGEUR, color=couleur, hatch=hachure,
                    edgecolor="white",
                    label=("écriture" if rang == 0 else "lecture")
                    if i == 0 else None)
            for centre, v in zip(position, valeurs):
                bas.annotate(fmt_ms(v), (centre, v), ha="center", va="bottom",
                             fontsize=6, rotation=90, color=couleur)
    bas.set_yscale("log")
    bas.set_ylabel("temps par image (échelle log)")
    bas.set_ylim(top=bas.get_ylim()[1] * 4)
    bas.set_xticks(x)
    bas.set_xticklabels(noms, fontsize=9)
    bas.legend(loc="upper left", fontsize=9, ncol=2)
    haut.set_title(titre + " — barre petite : meilleur", pad=34)
    fig.tight_layout()
    return fig


def rapports_pyperf(ligne):
    # une ligne pyperformance (une charge officielle et sa relecture) ramenée
    # aux quatre régimes du dispositif commun. Les temps y sont en µs, d'où la
    # mise en secondes avant `rapports_regimes`
    _, pk_e, sj_e, pk_l, sj_l, octets_pk, octets_sj = ligne
    return quatre_regimes_projetes((octets_pk, 1e-6 * pk_e, 1e-6 * pk_l),
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
        rotation=0, libelles=REGIMES_PROJETES)


def barres_groupees(noms, series, titre, etiquette_y, unite="µs"):
    # Le dispositif des deux pages de COÛT FIXE. Il ne trace PAS des rapports
    # mais des microsecondes ABSOLUES : ces deux pages ne comparent pas deux
    # formats sur une charge, elles décomposent la dépense d'un seul appel —
    # un rapport y cacherait justement ce qu'on vient lire, l'ordre de
    # grandeur. Échelle log, parce que l'écart va du simple au centuple.
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    x = numpy.arange(len(noms))
    largeur = 0.8 / len(series)
    hauts = []
    for rang, (etiquette, couleur, valeurs) in enumerate(series):
        position = x + (rang - (len(series) - 1) / 2) * largeur
        ax.bar(position, valeurs, largeur * 0.9, color=couleur,
               label=etiquette, zorder=2)
        hauts += [v for v in valeurs if v > 0]
        for centre, v in zip(position, valeurs):
            # virgule décimale, comme partout ailleurs dans le rapport
            ax.annotate((("%.2f" if v < 10 else "%.0f") % v).replace(".", ","),
                        (centre, v), ha="center", va="bottom", fontsize=7,
                        zorder=4)
    ax.set_yscale("log")
    ax.set_ylim(bottom=min(hauts) * 0.5, top=max(hauts) * 2.2)
    ax.set_xticks(x)
    ax.set_xticklabels(noms, fontsize=8)
    ax.set_ylabel(f"{etiquette_y} ({unite}, échelle log)")
    ax.set_title(titre, pad=34)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4,
              fontsize=8, frameon=False)
    fig.tight_layout()
    return fig


def figure_appel(donnees, sens, titre):
    lignes = donnees["appel"]
    # le plancher `rapidjson.dumps` (json nu, sans protocole serializejson)
    # reste dans le tableau markdown, où le texte qui l'entoure le situe —
    # seul, sur le graphique, il portait à confusion (demande de Baptiste,
    # 09/08 : lu comme si c'était une variante de serializejson.dumps)
    return barres_groupees(
        [nom for nom, _ in lignes],
        [("pickle", "#718096", [m["pickle"] * 1e6 for _, m in lignes]),
         ("Encoder(o)", BLEU, [m["encodeur"] * 1e6 for _, m in lignes]),
         ("serializejson.dumpb(o)", ORANGE,
          [m["module"] * 1e6 for _, m in lignes])],
        titre, "coût d'un appel, un objet par appel")


def figure_incremental(donnees, sens, titre):
    lignes = donnees["incremental"]
    ecrivains = [nom for nom, *_ in lignes[0][2]]
    couleurs = [BLEU, "#90cdf4", "#718096"]
    return barres_groupees(
        [titre_charge for titre_charge, _, _ in lignes],
        [(nom, couleur,
          [essais[rang][1] / combien * 1e6 for _, combien, essais in lignes])
         for rang, (nom, couleur) in enumerate(zip(ecrivains, couleurs))],
        titre, "temps BLOQUÉ par objet rangé")


# ordre des pages du rapport, fixé par Baptiste (07/08) : le catalogue de types
# python ouvre, puis les trois barreaux du barème dans l'ordre CROISSANT, puis
# les comparaisons hors pickle, et les deux scénarios de support ferment
FIGURES = [
    ("benchmark_types_objets", figure_types, "",
     "catalogue d'objets du dépôt, par catégorie de types python"),
    # les variantes du barème dans l'ordre CROISSANT. Le profil par défaut
    # dépendant de la CIBLE depuis le 10/08, il occupe DEUX pages (demande de
    # Baptiste, 10/08) : la RAM au barreau RAM, puis le disque seul au barreau
    # fichier ; les deux bouts du barème, à barreau fixe, gardent leurs cinq
    # barres sur une page
    ("benchmark_memoire_b64", figure_barres, "b64",
     f"Conversion de données binaires, {VARIANTES['b64']}"),
    ("benchmark_memoire_smart", figure_ram, "sj",
     "Conversion de données binaires EN RAM, profil «smart» niveau"
     f" {bareme_smart_defaut_ram} (le défaut de dumps et dumpb)"),
    ("benchmark_fichier_smart", figure_fichier, "sj",
     "Conversion de données binaires SUR LE DISQUE, profil «smart» niveau"
     f" {bareme_smart_defaut_fichier} (le défaut de dump et load fichier)"),
    ("benchmark_memoire_min", figure_barres, "min",
     f"Conversion de données binaires, {VARIANTES['min']}"),
    ("benchmark_codecs_images", figure_codecs_images, "",
     "corpus d'images : serializejson face aux codecs d'images spécialisés"),
    ("benchmark_pyperformance", figure_pyperformance, "",
     "benchmarks pickle officiels (pyperformance) : petits objets python"),
    # les deux pages du COÛT FIXE : le reste du rapport mesure des lots, ces
    # deux-là mesurent l'APPEL, en microsecondes absolues
    ("benchmark_appel_unitaire", figure_appel, "",
     "coût fixe d'un appel : un objet minuscule par appel"),
    ("benchmark_incremental", figure_incremental, "",
     "sérialisation incrémentale sur disque réel : temps rendu à l'appelant"),
    # les machines réalistes et les deux scénarios de support ne mesurent rien
    # de neuf : ils projettent les mesures précédentes sur des couples
    # CPU + stockage du commerce, puis sur toute la gamme des débits
    ("benchmark_machines", figure_machines, "",
     "machines réalistes (CPU + stockage de même gamme)"),
    ("benchmark_ecriture_support", figure_support, "dumps",
     "écriture sur un support (dumps + transfert)"),
    ("benchmark_lecture_support", figure_support, "loads",
     "lecture depuis un support (transfert + loads)"),
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
        pdf.savefig(fig)
        plt.close(fig)
        # le mode d'emploi sur sa PROPRE page : posé sous l'en-tête, il le
        # chevauchait dès que celui-ci gagnait une ligne — et il en a gagné
        # deux le 08/08 avec le régime disque et sa sonde
        fig, ax = plt.subplots(figsize=(11.69, 8.27))
        ax.axis("off")
        ax.text(0.05, 0.92,
                "Lecture des graphiques : toutes les valeurs sont des"
                " rapports serializejson / pickle —\nen dessous de la ligne"
                " ×1 (barre ou courbe PETITE), l'avantage est à"
                " serializejson.\n\n"
                "Le dispositif est le MÊME sur toutes les figures de"
                " comparaison : des barres de temps —\nécrire en RAM vers un"
                " texte (`dumps`) puis vers des octets (`dumpb`), relire de la"
                " RAM,\npuis écrire et relire SUR LE DISQUE — surmontées du"
                " CADRE bleu du poids,\nlarge comme les barres réunies."
                " Le profil PAR DÉFAUT, dont le barreau dépend de la cible\n"
                "depuis le 10/08 (un barreau pour dumps/dumpb, un autre pour"
                " dump vers fichier), occupe\nDEUX pages : la RAM seule, puis"
                " le disque seul — les deux bouts du barème, à barreau\nfixe,"
                " gardent leurs cinq barres sur une page."
                " Rien n'est masqué : que le poids passe au-dessus\nou en"
                " dessous des temps, les deux restent lisibles. Échelle"
                " linéaire sous ×1, logarithmique\nau-dessus.\n\n"
                "Les deux barres de disque sont MESURÉES, pas projetées : de"
                " vraies écritures et de vraies\nrelectures sur le volume qui"
                " porte le dépôt, écriture DURABLE (jusqu'au fsync) et"
                " relecture\ncache du noyau ÉVINCÉ, meilleur de cinq essais,"
                " les camps interlacés. La barre d'écriture\nest coupée en"
                " deux : le segment FONCÉ du bas est ce que `dump` bloque, ce"
                " que l'appelant\nattend vraiment ; le segment CLAIR au-dessus"
                " est ce que le fil d'écriture termine derrière lui.\n\n"
                "Les trois barres de RAM, elles, sont mesurées CACHE VIDÉ :"
                " c'est le seul régime qu'obtient\nune application sur des"
                " données qu'elle vient de produire ou qu'elle s'apprête à"
                " écrire.\nSur les petits objets python (catalogue,"
                " pyperformance), cache et RAM ne se distinguent\npas — c'est"
                " dit sur place.\n\n"
                "Quatre figures font exception au dispositif : pyperformance,"
                " dont la réplique officielle\nn'écrit que des octets (une"
                " seule barre de RAM en écriture, `dumpb`) et dont les charges"
                "\nne font aucun aller-retour disque — ses deux barres de"
                " disque restent donc PROJETÉES\n(ses barres le disent) ; les deux scénarios de support, qui portent le"
                " temps total en fonction du débit\nsur toute la gamme des"
                " stockages ; et les machines réalistes en dernière page, qui"
                "\nprojettent les mêmes mesures sur des couples CPU + stockage"
                " du commerce.",
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
        " serializejson défaut « smart », barreau dépendant de la CIBLE —"
        f" RAM (dumps/dumpb) : barreau {bareme_smart_defaut_ram} (chaîne"
        f" {bareme_smart[bareme_smart_defaut_ram][2]} →"
        f" {bareme_smart[bareme_smart_defaut_ram][0]} niveau"
        f" {bareme_smart[bareme_smart_defaut_ram][1]}) ; fichier"
        f" (dump/append) : barreau {bareme_smart_defaut_fichier} (chaîne"
        f" {bareme_smart[bareme_smart_defaut_fichier][2]} →"
        f" {bareme_smart[bareme_smart_defaut_fichier][0]} niveau"
        f" {bareme_smart[bareme_smart_defaut_fichier][1]}) — base64 et JSON"
        " compris",
        "- médiane de ~50 essais, burst de réveil CPU avant chaque chrono,"
        " mesures alternées dans le même processus",
        "- régime RAM : sur les tableaux et les images, le cache est VIDÉ"
        " avant chaque essai (96 Mo parcourus en lecture) — sur les petits"
        " objets python, cache et RAM ne se distinguent pas et le vidage"
        " ne mesurerait que le rechargement de l'interpréteur",
        "- régime DISQUE : de vraies écritures et relectures sur le volume du"
        " dépôt, écriture durable (fsync compris) et relecture cache du noyau"
        " évincé, meilleur de 5 essais — plus aucune projection, sauf sur la"
        " page pyperformance qui le signale dans ses barres",
        f"- support mesuré : {support_du_depot()} — les temps de disque de ce"
        " rapport valent POUR CE SUPPORT ; sur un NVMe ils seraient d'un tout"
        " autre ordre, mais le classement par POIDS écrit, lui, ne change pas",
    ]
    etalon_depart = sonde_disque_libre()
    print("sonde disque au départ : %.1f ms pour 4 Mo durables"
          % (1e3 * etalon_depart))
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
    print("coût fixe d'un appel (objets minuscules)...")
    appel = mesure_appel_unitaire()
    print("sérialisation incrémentale sur disque réel...")
    incremental = mesure_incremental()
    # les deux bornes disent de combien le support s'est DÉGRADÉ pendant la
    # campagne — au départ son cache est vide, à l'arrivée il a encaissé
    # plusieurs gigaoctets ; c'est cet écart que la sonde par profil ventile
    etalon_arrivee = sonde_disque_libre()
    print("sonde disque à l'arrivée : %.1f ms" % (1e3 * etalon_arrivee))
    entete.append(
        "- sonde disque (4 Mo écrits durablement, fsync compris) :"
        f" {1e3 * etalon_depart:.1f} ms au départ,"
        f" {1e3 * etalon_arrivee:.1f} ms à l'arrivée. Cet écart n'est pas une"
        " charge étrangère (vérifié : zéro entrée-sortie extérieure dans"
        " /proc/diskstats pendant que la sonde triplait) mais le support qui"
        " sature sous nos propres écritures — cache du disque plein, il rend"
        " son débit de plateau. La colonne « sonde » du tableau de disque dit,"
        " ligne par ligne, à quel régime chaque profil a été payé")
    shutil.rmtree(_DOSSIER_DISQUE, ignore_errors=True)
    donnees = {"profils": resultats, "pyperf": pyperf, "types": types_objets,
               "codecs": codecs_images, "appel": appel,
               "incremental": incremental}
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
