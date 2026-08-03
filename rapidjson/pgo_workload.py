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


cases = [
    [Point(i) for i in range(5000)],
    [{"a": [1, 2.5, "x"], "b": {"c": list(range(10)), "d": "hello"}} for _ in range(5000)],
    ["chaine numéro %d avec du texte" % i for i in range(20000)],
    list(range(200000)),
    [i * 1.5 for i in range(50000)],
    {("cle%d" % i): i for i in range(30000)},
]

for _ in range(3):
    for obj in cases:
        for encoder in (
            serializejson.Encoder(return_bytes=True),
            serializejson.Encoder(indent=None),
        ):
            dumped = encoder(obj)
        decoder = serializejson.Decoder(authorized_classes=[Point])
        decoder(dumped if isinstance(dumped, str) else dumped.decode())
print("charge PGO exécutée")
