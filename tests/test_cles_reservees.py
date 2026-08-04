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


class ObjetFautif:
    pass


class ObjetSetstate:
    def __setstate__(self, state):
        self.__dict__.update(state)


def test_attribut_au_nom_porteur():
    # un ATTRIBUT d'objet nommé comme un champ d'enveloppe (__class__,
    # __init__, ..., $ref) ne peut pas être aplati : l'état part sous
    # __state__, et l'enveloppe dict échappe la clé au besoin
    noms = ("__class__", "__init__", "__new__", "__state__", "__items__",
            "__dict__", "$ref")
    encoder = serializejson.Encoder(return_bytes=True,
                                    attributes_filter=False)
    decoder = serializejson.Decoder(
        authorized_classes=[f"{__name__}.ObjetFautif",
                            f"{__name__}.ObjetSetstate"])
    for classe in (ObjetFautif, ObjetSetstate):
        for nom in noms:
            objet = classe()
            objet.__dict__[nom] = "valeur piégée"
            objet.__dict__["normal"] = 42
            recharge = decoder(encoder([objet, objet]))
            assert recharge[0].__dict__ == objet.__dict__, (classe, nom)
            assert recharge[0] is recharge[1]


def test_attribut_ref_passe_le_filtre_par_defaut():
    # "$ref" ne commence pas par "_" : il échappe au filtre d'attributs par
    # défaut et doit quand même revenir intact
    objet = ObjetFautif()
    objet.__dict__["$ref"] = "piégé"
    objet.normal = 42
    decoder = serializejson.Decoder(
        authorized_classes=[f"{__name__}.ObjetFautif"])
    recharge = decoder(serializejson.Encoder(return_bytes=True)(objet))
    assert recharge.__dict__ == objet.__dict__


def test_objet_sain_reste_aplati():
    objet = ObjetFautif()
    objet.a = 1
    objet.b = "x"
    dump = serializejson.Encoder(return_bytes=True)(objet)
    assert b"__state__" not in dump


class SlotsStricts:
    __slots__ = ("x",)


class ProprieteSansSetter:
    @property
    def v(self):
        return 0


def test_erreur_setattr_enrichie():
    # les échecs de restauration (slot inconnu, property sans setter)
    # doivent dire la classe et la clé fautive, avec la cause chaînée
    import pytest
    cas = [
        ('{"__class__": "%s.SlotsStricts", "zombie": 9}' % __name__,
         [f"{__name__}.SlotsStricts"], "zombie"),
        ('{"__class__": "%s.ProprieteSansSetter", "v": 5}' % __name__,
         [f"{__name__}.ProprieteSansSetter"], "v"),
    ]
    for json, classes, cle in cas:
        with pytest.raises(AttributeError) as excinfo:
            serializejson.Decoder(authorized_classes=classes)(json)
        message = str(excinfo.value)
        assert "serializejson" in message
        assert repr(cle) in message
        assert excinfo.value.__cause__ is not None
