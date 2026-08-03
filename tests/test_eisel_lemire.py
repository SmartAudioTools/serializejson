import random
import struct

import rapidjson


def _exactement(tokens):
    parsed = rapidjson.loads("[" + ",".join(tokens) + "]")
    for token, value in zip(tokens, parsed):
        reference = float(token)
        assert struct.pack("d", reference) == struct.pack("d", value), (
            token,
            reference,
            value,
        )


def test_parse_double_bords():
    # les cas qui départagent un parseur correctement arrondi d'un parseur
    # approché : sous-normaux extrêmes, seuils, mi-chemin entier exact
    _exactement(
        [
            "5e-324", "4.9e-324", "2.4e-324", "2.5e-324", "1e-323",
            "2.2250738585072014e-308", "2.2250738585072011e-308",
            "1.7976931348623157e308",
            "9007199254740993", "9007199254740992",
            "0.1", "0.2", "0.3", "1e22", "1e23",
            "123456789012345678901234567890e-25",
        ]
    )


def test_parse_double_aleatoire():
    # motifs binaires aléatoires reproduits : repr 17 chiffres, notation e,
    # chiffres longs tronqués — le parse doit égaler float() au bit près
    rng = random.Random(20260803)
    tokens = []
    while len(tokens) < 5000:
        bits = rng.getrandbits(64)
        d = struct.unpack("d", struct.pack("Q", bits))[0]
        if d != d or d in (float("inf"), float("-inf")):
            continue
        tokens.append(repr(d))
    tokens += [
        "%de%d" % (rng.getrandbits(rng.randint(1, 63)) or 1, rng.randint(-330, 300))
        for _ in range(5000)
    ]
    for _ in range(2000):
        nd = rng.randint(20, 40)
        s = "".join(rng.choice("0123456789") for _ in range(nd)).lstrip("0") or "1"
        tokens.append(s + "e%d" % rng.randint(-300, 280))
    # mi-chemins exacts : impair de 54 bits (règle du pair le plus proche)
    for _ in range(2000):
        odd = (1 << 53) | rng.getrandbits(53) | 1
        tokens.append(str(odd << rng.randint(0, 5)))
    _exactement(tokens)


if __name__ == "__main__":
    test_parse_double_bords()
    test_parse_double_aleatoire()
    print("OK")
