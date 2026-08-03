import serializejson


class FauxQPoint:
    # la forme des classes Qt : état entièrement porté par les arguments du
    # constructeur, via le protocole __serializejson__
    def __init__(self, x=0, y=0):
        self._x, self._y = x, y

    def __serializejson__(self):
        return ("FauxQPoint", (self._x, self._y), None)


class UnArgScalaire:
    def __serializejson__(self):
        return ("UnArgScalaire", ("seul",), None)


class UnArgListe:
    def __serializejson__(self):
        return ("UnArgListe", ([1, 2],), None)


class AvecEtat:
    def __serializejson__(self):
        return ("AvecEtat", (1,), {"a": 5})


class EtatVraiDict:
    def __init__(self):
        self.v = 7

    def __serializejson__(self):
        return ("EtatVraiDict", None, self.__dict__)


def test_serializejson_method_forms():
    encoder = serializejson.Encoder(return_bytes=True, indent=None)
    assert encoder(FauxQPoint(3, 4)) == b'{"__class__":"FauxQPoint","__init__":[3,4]}'
    # un argument scalaire s'écrit nu, une liste garde ses crochets
    assert encoder(UnArgScalaire()) == b'{"__class__":"UnArgScalaire","__init__":"seul"}'
    assert encoder(UnArgListe()) == b'{"__class__":"UnArgListe","__init__":[[1,2]]}'
    # l'état dict s'écrit à plat après __init__
    assert encoder(AvecEtat()) == b'{"__class__":"AvecEtat","__init__":1,"a":5}'
    # en indenté, les listes __init__ restent sur une ligne (single_line_init)
    indented = serializejson.Encoder(return_bytes=True)
    assert b'"__init__": [3,4]' in indented(FauxQPoint(3, 4))


def test_serializejson_method_memo():
    encoder = serializejson.Encoder(return_bytes=True, indent=None)
    p = FauxQPoint(1, 2)
    assert encoder([p, p]).count(b'"$ref"') == 1
    # rigueur du __dict__ réel partagé : écrit une seule fois, référencé ensuite
    e = EtatVraiDict()
    out = encoder([e, e.__dict__])
    assert out.count(b'"v":7') == 1 and b'.__dict__"' in out


def test_serializejson_method_dumped_classes():
    encoder = serializejson.Encoder(return_bytes=True, indent=None)
    encoder(FauxQPoint())
    assert "FauxQPoint" in encoder.get_dumped_classes()


if __name__ == "__main__":
    test_serializejson_method_forms()
    test_serializejson_method_memo()
    test_serializejson_method_dumped_classes()
    print("OK")
