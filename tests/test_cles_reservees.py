# Collision entre les clés RÉSERVÉES du format (__class__, $ref) et les
# dicts utilisateur légitimes qui les contiennent : ces dicts passent par
# l'enveloppe {"__class__": "dict", ...} avec la clé échappée entre
# apostrophes — le déballage d'apostrophes existant les restitue.
# Avant le 04/08/2026, les trois premiers cas étaient corrompus ou rejetés.
import serializejson


def test_dict_str_avec_cle_class():
    donnees = {"__class__": "algo_maison", "seuil": 3}
    dump = serializejson.Encoder(return_bytes=True)(donnees)
    assert b"\"'__class__'\"" in dump
    assert serializejson.Decoder()(dump) == donnees


def test_dict_mixte_avec_cle_class_ne_perd_plus_l_etiquette():
    # la clé utilisateur écrasait silencieusement l'étiquette de l'enveloppe
    donnees = {1: "un", "__class__": "algo_maison"}
    dump = serializejson.Encoder(return_bytes=True)(donnees)
    assert serializejson.Decoder()(dump) == donnees


def test_dict_ref_utilisateur():
    donnees = {"$ref": "un chemin utilisateur"}
    dump = serializejson.Encoder(return_bytes=True)(donnees)
    assert serializejson.Decoder()(dump) == donnees


def test_cas_ambigus_varies():
    decoder = serializejson.Decoder()
    encoder = serializejson.Encoder(return_bytes=True)
    cas = [
        {"__class__": "dict"},                      # la valeur imite le tag
        {"__class__": {"__class__": "imbriqué"}},   # collision en valeur
        {"objet": {"attr": {"__class__": "niché"}}},
        {"5": "chaine", "__class__": "x", "$ref": "y"},
        {"'__class__'": "déjà quoté"},              # double échappement
        {"''__class__''": "doublement quoté"},
        [{"__class__": "a"}, {"__class__": "a"}],   # doublons distincts
    ]
    for donnees in cas:
        assert decoder(encoder(donnees)) == donnees, donnees


def test_doublon_reference():
    # un même dict à clé réservée écrit deux fois doit rester partagé ($ref)
    d = {"__class__": "partagé"}
    recharge = serializejson.Decoder()(
        serializejson.Encoder(return_bytes=True)([d, d]))
    assert recharge == [d, d]
    assert recharge[0] is recharge[1]


def test_cles_complexes_contenant_du_json_objet():
    # une clé CHAÎNE dont le texte est le JSON d'un objet reste une chaîne
    donnees = {'{"__class__":"frozenset","__init__":[8,7]}': "value", 2: "v"}
    dump = serializejson.Encoder(return_bytes=True)(donnees)
    assert serializejson.Decoder()(dump) == donnees
