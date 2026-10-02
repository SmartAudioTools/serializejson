# Charge de profil pour la compilation PGO (voir build_pgo.sh) : exerce les
# chemins chauds réels — encode et décode des six familles de données des
# benchmarks, avec et sans indentation, en str et en bytes.
import sys
import os
import random

# sys.path[0] est le dossier du script (rapidjson/), où le .so masquerait le
# paquet : on le remplace par le paquet construit (setup.py, variable posée par
# build_ext) ou par la racine du dépôt (build_pgo.sh)
if os.environ.get("SERIALIZEJSON_PGO_LIB"):
    sys.path[0] = os.environ["SERIALIZEJSON_PGO_LIB"]
else:
    sys.path[0] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests")
    import conftest  # noqa: F401 — le binaire INSTRUMENTÉ, sous les deux noms
import serializejson


class Point:
    def __init__(self, i=0):
        self.x = i * 1.5
        self.y = i * 2.5
        self.name = "point%d" % i
        self.active = i % 2 == 0


class Objet:
    """Un objet APPLICATIF, écrit par le crochet `__serializejson__` : l'état filtré de ses
    valeurs par défaut par `etat_sans_defauts` (C). C'est le chemin chaud de toute application
    qui sérialise ses propres classes — et le seul endroit où cette fonction, appelée une fois
    par objet, est exercée ici ; sans ce cas elle serait compilée comme code froid."""

    DEFAUTS = {"nom": "", "x": 0.0, "y": 0.0, "poids": 1.0, "actif": True,
               "etiquettes": (), "reponse": None, "commentaire": "", "saisie": ""}
    PROPRIETES = ["saisie"]

    def __init__(self, i=0):
        self.__dict__.update({nom: valeur for nom, valeur in self.DEFAUTS.items()
                              if nom != "saisie"})
        self.nom = "objet%d" % i
        self.x, self.y = i * 1.5, i * 2.5
        self.actif = i % 2 == 0
        self.etiquettes = ["a", "b"] if i % 3 else ()
        self._saisie = "s%d" % i if i % 2 else ""

    @property
    def saisie(self):
        return self.__dict__.get("_saisie", "")

    @saisie.setter
    def saisie(self, valeur):
        self.__dict__["_saisie"] = valeur

    def __serializejson__(self):
        return ("Objet", None,
                serializejson.etat_sans_defauts(self, self.DEFAUTS, self.PROPRIETES))


serializejson.constructors["Objet"] = Objet   # le nom écrit par le crochet, pour la relecture

import collections
import datetime
import decimal

try:
    import numpy
except ModuleNotFoundError:
    numpy = None

cases = [
    [Point(i) for i in range(5000)],
    [Objet(i) for i in range(5000)],
    [{"a": [1, 2.5, "x"], "b": {"c": list(range(10)), "d": "hello"}} for _ in range(5000)],
    ["chaine numéro %d avec du texte" % i for i in range(20000)],
    list(range(200000)),
    [i * 1.5 for i in range(50000)],
    # graphies décimales LONGUES (17 chiffres) : sans elles, le chemin complet
    # de dtoa est compilé comme code froid — mesuré ×1,7 sur une liste de
    # flottants quelconques alors que les x.5 ci-dessus restaient rapides
    [i * 0.7071067811865476 for i in range(50000)],
    {("cle%d" % i): i for i in range(30000)},
    # familles à enveloppe (set/tuple/datetime/Decimal/bytes/defaultdict) :
    # exercent EnvelopeHead, les branches natives et leurs lectures
    [{i, i + 1, i + 2} for i in range(3000)],
    [(i, i * 1.5) for i in range(3000)],
    [datetime.datetime(2020, 1, 1 + i % 27, i % 24, i % 60) for i in range(3000)],
    [decimal.Decimal("%d.25" % i) for i in range(3000)],
    [bytes([i % 256]) * 24 for i in range(2000)],
    [collections.defaultdict(list, {"k": [i]}) for i in range(2000)],
]

import io

for _ in range(3):
    for obj in cases:
        for encoder in (
            serializejson.Encoder(return_bytes=True),
            serializejson.Encoder(indent=None),
        ):
            dumped = encoder(obj)
        # sortie flux : sans elle le chemin PyWriteStreamWrapper serait
        # compilé comme code froid (mesuré +50 % avant son ajout ici)
        serializejson.Encoder(return_bytes=True)(obj, fp=io.BytesIO())
        decoder = serializejson.Decoder(
            authorized_classes=[Point, collections.defaultdict, "Objet"])
        decoder(dumped if isinstance(dumped, str) else dumped.decode())
        # entrée bytes : chemin direct sans conversion unicode
        decoder(dumped if isinstance(dumped, bytes) else dumped.encode())
# dumps FICHIER : exercent FdWriteStream et le fil d'écriture — la voie
# préfixe propre (index par défaut) et la voie entière avec échappement
# dans le fil (index=None), qui sans cela compileraient froides
import tempfile

gros_fichier = [
    {"propre": "x" * 300_000},
    {"dense": "ab\n" * 100_000},
    {"disperse": ("w" * 5000 + "\n") * 60},
    # bytes volumineux : remise différée + ecritBase64 dans le fil
    {"octets": bytes(range(256)) * 1200},
]
# document à nombreuses entrées d'index ET échappements : exerce la
# correction par deltas (sj_index_corrige) sur un vrai parcours d'entrées
indexe = {"e%d" % i: {"txt": "l\n" * 600, "n": list(range(20))}
          for i in range(40)}
with tempfile.TemporaryDirectory() as dossier:
    cible = os.path.join(dossier, "pgo.json")
    cible_app = os.path.join(dossier, "pgo_append.json")
    for _ in range(3):
        for obj in gros_fichier:
            serializejson.dump(obj, cible)
            serializejson.dump(obj, cible, index=None)
        serializejson.dump(indexe, cible, index_threshold=16)
        # bytes compressés au fil d'écriture (BloscDiffere → ecritCompresse) :
        # les deux étiquettes, gagnante et perdante, et l'élagage d'index
        serializejson.dump({"z": bytes(range(256)) * 1200,
                            "b": random.Random(0).randbytes(80_000)},
                           cible, bytes_compression="blosc2_zstd",
                           bytes_size_compression_threshold=512)
        # tableaux numpy différés au fil : charge + bloc Etiquette, chaîne
        # dérivée (préfiltre, contexte jetable) ET repli brut "b64"
        if numpy is not None:
            serializejson.dump(
                {"img": (numpy.arange(120_000, dtype=numpy.uint8)
                         .reshape(400, 300) % 251),
                 "brut": numpy.frombuffer(
                     random.Random(1).randbytes(60_000), dtype=numpy.uint8)},
                cible, bytes_compression="blosc2_zstd",
                bytes_size_compression_threshold=512)
        # appends à grands str : la voie Echappe des maillons et la
        # correction de leurs entrées à la fermeture (sj_append_ferme)
        if os.path.exists(cible_app):
            os.remove(cible_app)
        encodeur = serializejson.Encoder(cible_app, index="sidecar",
                                         index_threshold=16)
        for obj in gros_fichier:
            encodeur.append(obj)
        encodeur.close()
    serializejson.wait_writes()
print("charge PGO exécutée")
