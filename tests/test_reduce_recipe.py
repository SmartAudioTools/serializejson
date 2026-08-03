import serializejson

PREFIX = __name__


def usine(v):
    o = RParUsine.__new__(RParUsine)
    o.v = v
    return o


class RArgs:
    def __init__(self, a=1, b=2):
        self.a, self.b = a, b

    def __reduce__(self):
        return (self.__class__, (self.a, self.b))


class REtat:
    def __init__(self):
        self.x = 5

    def __reduce__(self):
        return (self.__class__, (), {"x": self.x})


class RParUsine:
    v = 0

    def __reduce__(self):
        # callable qui n'est pas la classe : hors recette, voie Python
        return (usine, (self.v,))


def test_reduce_forms():
    encoder = serializejson.Encoder(return_bytes=True, indent=None)
    assert encoder(RArgs(3, 4)) == (
        '{"__class__":"%s.RArgs","__init__":[3,4]}' % PREFIX
    ).encode()
    assert encoder(REtat()) == (
        '{"__class__":"%s.REtat","__init__":[],"x":5}' % PREFIX
    ).encode()
    # repli voie Python : le nom émis est celui du callable
    assert b"usine" in encoder(RParUsine())


def test_reduce_round_trip_and_ref():
    encoder = serializejson.Encoder(return_bytes=True, indent=None)
    decoder = serializejson.Decoder(authorized_classes=[RArgs, REtat])
    back = decoder(encoder(RArgs(7, 8)))
    assert (back.a, back.b) == (7, 8)
    back = decoder(encoder(REtat()))
    assert back.x == 5
    r = RArgs()
    pair = decoder(encoder([r, r]))
    assert pair[0] is pair[1]


if __name__ == "__main__":
    test_reduce_forms()
    test_reduce_round_trip_and_ref()
    print("OK")
