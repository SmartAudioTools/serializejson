# La recette __getnewargs__/__getnewargs_ex__ (émission C) doit produire
# les mêmes octets que la voie Python (adaptateur fidèle autour de
# tuple_from_instance), et les recharges doivent restaurer les objets.
import collections

import serializejson


class SansRecette(serializejson.Encoder):
    def class_plan(self, class_):
        plan = serializejson.Encoder.class_plan(self, class_)
        if isinstance(plan, tuple) and plan[0] is None:
            return None
        return plan


class PointNew:
    def __init__(self, x=0, y=0):
        self.x, self.y = x, y

    def __getnewargs__(self):
        return (self.x, self.y)

    def __eq__(self, other):
        return (self.x, self.y) == (other.x, other.y)


class PointNewEx:
    def __init__(self, x=0, *, y=0):
        self.x, self.y = x, y

    def __getnewargs_ex__(self):
        return ((self.x,), {"y": self.y})

    def __eq__(self, other):
        return (self.x, self.y) == (other.x, other.y)


class AvecEtat:
    def __init__(self, x=0):
        self.x = x
        self.note = "n%d" % x

    def __getnewargs__(self):
        return (self.x,)

    def __eq__(self, other):
        return (self.x, self.note) == (other.x, other.note)


NT = collections.namedtuple("NT", "a b")


def fonction_libre():
    pass


def test_getnewargs_meme_octets_que_voie_python():
    p = PointNew(9, 9)
    cas = [
        [PointNew(1, 2), PointNew(3, 4)],
        [PointNewEx(5, y=6)],
        [AvecEtat(1), AvecEtat(2)],
        [NT(1, 2), NT("a", "b")],
        [PointNew(1, 2), PointNew(1, 2)],
        [p, p],
        {"f": fonction_libre, "g": fonction_libre, "cls": PointNew, "t": int,
         "tt": type},
    ]
    for donnees in cas:
        py = SansRecette(return_bytes=True)(donnees)
        c = serializejson.Encoder(return_bytes=True)(donnees)
        assert py == c, donnees


def test_getnewargs_recharge():
    donnees = [PointNew(1, 2), PointNewEx(5, y=6), AvecEtat(3), NT(7, 8)]
    dump = serializejson.Encoder(return_bytes=True)(donnees)
    module = __name__
    decoder = serializejson.Decoder(
        authorized_classes=[
            f"{module}.PointNew",
            f"{module}.PointNewEx",
            f"{module}.AvecEtat",
            f"{module}.NT",
        ]
    )
    recharge = decoder(dump)
    assert recharge == donnees
