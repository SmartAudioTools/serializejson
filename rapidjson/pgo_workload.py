# Charge de profil pour la compilation PGO (voir build_pgo.sh) : exerce les
# chemins chauds réels — encode et décode des six familles de données des
# benchmarks, avec et sans indentation, en str et en bytes.
import sys
import os

# sys.path[0] est le dossier du script (rapidjson/), où le .so masquerait le
# paquet : on le remplace par la racine du dépôt
sys.path[0] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
import rapidjson.rapidjson as rj

sys.modules["rapidjson"] = rj
import serializejson


class Point:
    def __init__(self, i=0):
        self.x = i * 1.5
        self.y = i * 2.5
        self.name = "point%d" % i
        self.active = i % 2 == 0


import collections
import datetime
import decimal

cases = [
    [Point(i) for i in range(5000)],
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
            authorized_classes=[Point, collections.defaultdict])
        decoder(dumped if isinstance(dumped, str) else dumped.decode())
        # entrée bytes : chemin direct sans conversion unicode
        decoder(dumped if isinstance(dumped, bytes) else dumped.encode())
print("charge PGO exécutée")
