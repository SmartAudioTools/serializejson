import serializejson

PREFIX = __name__


class GS:
    def __init__(self):
        self.b = 2
        self.a = 1

    def __getstate__(self):
        # l'ordre du dict rendu fait foi : pas de tri pour les classes à
        # __getstate__ utilisateur
        return {"b": self.b, "a": self.a}


class GSDictReel:
    def __init__(self):
        self.v = 9

    def __getstate__(self):
        return self.__dict__


class GSNonDict:
    def __getstate__(self):
        return [1, 2]


class GSSetState:
    def __init__(self):
        self.x = 1

    def __getstate__(self):
        return {1: "un"}

    def __setstate__(self, state):
        self.x = state


def test_getstate_forms():
    encoder = serializejson.Encoder(return_bytes=True, indent=None)
    assert encoder(GS()) == ('{"__class__":"%s.GS","b":2,"a":1}' % PREFIX).encode()
    # état non-dict -> "__state__"
    assert b'"__state__":[1,2]' in encoder(GSNonDict())
    # clés non-str avec __setstate__ -> "__state__" (dict_non_str_keys)
    assert b'"__state__"' in encoder(GSSetState())


def test_getstate_shared_dict_rigor():
    encoder = serializejson.Encoder(return_bytes=True, indent=None)
    g = GS()
    assert encoder([g, g]).count(b'"$ref"') == 1
    d = GSDictReel()
    out = encoder([d, d.__dict__])
    assert out.count(b'"v":9') == 1 and b'.__dict__"' in out


def test_getstate_round_trip():
    encoder = serializejson.Encoder(return_bytes=True, indent=None)
    decoder = serializejson.Decoder(authorized_classes=[GS])
    back = decoder(encoder(GS()))
    assert (back.a, back.b) == (1, 2)


if __name__ == "__main__":
    test_getstate_forms()
    test_getstate_shared_dict_rigor()
    test_getstate_round_trip()
    print("OK")
