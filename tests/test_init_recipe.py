import serializejson

PREFIX = __name__

traces = []


class Point:
    # constructeur à arguments, état entièrement porté par eux (forme
    # {"__class__": ..., "__init__": [x, y]} — celle des classes Qt)
    def __init__(self, x=0, y=0):
        traces.append(("Point", x, y))
        self.x = x
        self.y = y


class Widget:
    # __init__ PUIS attributs restants : la fusion doit préserver l'ordre
    # d'instance() — le constructeur d'abord, les attributs écrasent ensuite
    def __init__(self, titre=""):
        self.titre = titre
        self.interne = titre.upper()


def test_init_list_calls_constructor():
    decoder = serializejson.Decoder(authorized_classes=[Point])
    traces.clear()
    back = decoder('{"__class__":"%s.Point","__init__":[3,4]}' % PREFIX)
    assert (back.x, back.y) == (3, 4)
    assert traces == [("Point", 3, 4)], "le vrai __init__ doit être appelé"
    back = decoder('{"__class__":"%s.Point","__init__":[]}' % PREFIX)
    assert (back.x, back.y) == (0, 0)


def test_init_then_extra_attributes():
    decoder = serializejson.Decoder(authorized_classes=[Widget])
    back = decoder(
        '{"__class__":"%s.Widget","__init__":["abc"],"interne":"FORCE","extra":9}'
        % PREFIX
    )
    assert back.titre == "abc"
    assert back.interne == "FORCE", "l'attribut du JSON écrase celui du __init__"
    assert back.extra == 9


def test_init_shared_reference_and_nesting():
    decoder = serializejson.Decoder(authorized_classes=[Point])
    pair = decoder(
        '[{"__class__":"%s.Point","__init__":[1,2]},{"$ref":"root[0]"}]' % PREFIX
    )
    assert pair[0] is pair[1] and pair[0].x == 1
    nested = decoder(
        '{"__class__":"%s.Point","__init__":[{"__class__":"%s.Point","__init__":[5,6]},0]}'
        % (PREFIX, PREFIX)
    )
    assert nested.x.y == 6


if __name__ == "__main__":
    test_init_list_calls_constructor()
    test_init_then_extra_attributes()
    test_init_shared_reference_and_nesting()
    print("OK")
