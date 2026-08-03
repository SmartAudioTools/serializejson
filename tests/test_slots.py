import serializejson

# le nom qualifié dépend du mode d'import (pytest : test_slots, exécution
# directe : __main__)
PREFIX = __name__


class Slotted:
    __slots__ = ("x", "name")

    def __init__(self, i=1):
        self.x = i
        self.name = "abc"


class SlottedPartial:
    __slots__ = ("x", "y")

    def __init__(self):
        self.x = 1


class SlottedHerit(Slotted):
    __slots__ = ("z", "_prive")

    def __init__(self):
        super().__init__()
        self.z = 3
        self._prive = 4


class SlottedPrive:
    __slots__ = ("__secret", "a")

    def __init__(self):
        self.__secret = 1
        self.a = 2


class SlottedDict:
    __slots__ = ("x", "__dict__")

    def __init__(self):
        self.x = 1
        self.extra = 2


def test_slots_round_trip():
    encoder = serializejson.Encoder(return_bytes=True, indent=None)
    decoder = serializejson.Decoder(
        authorized_classes=[Slotted, SlottedPartial, SlottedHerit, SlottedPrive,
                            SlottedDict]
    )
    assert encoder(Slotted()) == (
        '{"__class__":"%s.Slotted","name":"abc","x":1}' % PREFIX
    ).encode()
    back = decoder(encoder(Slotted(5)))
    assert (back.x, back.name) == (5, "abc")
    # slot jamais assigné : absent du JSON, absent de l'objet rechargé
    assert encoder(SlottedPartial()) == (
        '{"__class__":"%s.SlottedPartial","x":1}' % PREFIX
    ).encode()
    back = decoder(encoder(SlottedPartial()))
    assert back.x == 1 and not hasattr(back, "y")
    # héritage : slots du parent et de l'enfant ; le slot souligné est
    # filtré par le filtre des soulignés par défaut (comme les attributs
    # de __dict__)
    back = decoder(encoder(SlottedHerit()))
    assert (back.x, back.name, back.z) == (1, "abc", 3)
    assert not hasattr(back, "_prive")
    no_filter = serializejson.Encoder(return_bytes=True, indent=None,
                                      attributes_filter=False)
    back = decoder(no_filter(SlottedHerit()))
    assert back._prive == 4
    # slot privé : name mangling comme le __getstate__ par défaut (filtré
    # par le filtre soulignés par défaut)
    assert encoder(SlottedPrive()) == (
        '{"__class__":"%s.SlottedPrive","a":2}' % PREFIX
    ).encode()
    # __slots__ AVEC __dict__ : fusion des deux états (voie Python)
    back = decoder(encoder(SlottedDict()))
    assert (back.x, back.extra) == (1, 2)


def test_slots_shared_reference():
    encoder = serializejson.Encoder(return_bytes=True, indent=None)
    decoder = serializejson.Decoder(authorized_classes=[Slotted])
    shared = Slotted()
    pair = decoder(encoder([shared, shared]))
    assert pair[0] is pair[1]


class WithProp:
    def __init__(self):
        self.x = 1

    @property
    def double(self):
        return self.x * 2


def test_properties_gating_per_class():
    # properties=True ne coupe le chemin C QUE pour les classes qui ont
    # réellement des properties : les octets restent inchangés pour les autres
    encoder = serializejson.Encoder(return_bytes=True, indent=None,
                                    properties=True)
    plain = serializejson.Encoder(return_bytes=True, indent=None)
    assert encoder(Slotted()) == plain(Slotted())
    assert b'"double":2' in encoder(WithProp())
    assert b'"double"' not in plain(WithProp())


if __name__ == "__main__":
    test_slots_round_trip()
    test_slots_shared_reference()
    test_properties_gating_per_class()
    print("OK")
