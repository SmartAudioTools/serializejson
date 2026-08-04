# Décision de format du 04/08/2026 : les dicts à clés non-str s'écrivent
# {"__class__": "dict", ...} (nom court, même convention que les objets) ;
# l'ancien nom "dict_non_str_keys" reste lu pour toujours.
import serializejson


def test_nouvelle_forme_ecrite():
    dump = serializejson.Encoder(return_bytes=True)({1: "a", 2: "b"})
    assert b'"__class__": "dict"' in dump
    assert b"dict_non_str_keys" not in dump


def test_les_deux_formes_sont_lues():
    donnees = {1: "a", -5: [1, 2], 2**70: "grand", b"oct": True, (1, 2): "t"}
    decoder = serializejson.Decoder()
    dump = serializejson.Encoder(return_bytes=True)(donnees)
    assert decoder(dump) == donnees
    ancien = dump.replace(b'"__class__": "dict"',
                          b'"__class__": "dict_non_str_keys"')
    assert decoder(ancien) == donnees


def test_imbrication_et_chemin_c():
    # le chemin C (clés toutes entières) et le chemin Python (clés mixtes)
    # doivent produire la même enveloppe
    donnees = {i: dict.fromkeys(range(3)) for i in range(20)}
    decoder = serializejson.Decoder()
    dump = serializejson.Encoder(return_bytes=True)(donnees)
    assert dump.count(b'"__class__": "dict"') == 21
    assert decoder(dump) == donnees
