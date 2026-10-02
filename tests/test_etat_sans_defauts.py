"""serializejson.etat_sans_defauts : même résultat, ordre des clés compris, que le Python qu'elle remplace."""
import inspect

import pytest

import serializejson

VIDE = inspect.Parameter.empty


def _defaut(valeur, defaut):
    return (valeur == defaut or (defaut is None and not valeur and valeur != 0)
            or (isinstance(defaut, tuple) and valeur == list(defaut)))


def reference(obj, defauts, proprietes):
    etat = {n: v for n, v in vars(obj).items() if n in defauts and not _defaut(v, defauts[n])}
    for nom in proprietes:
        if nom not in etat:
            valeur = getattr(obj, nom)
            if not _defaut(valeur, defauts[nom]):
                etat[nom] = valeur
    return etat


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    @property
    def saisie(self):
        return self.__dict__.get("_saisie", "")

    @property
    def vide(self):
        return []


DEFAUTS = {"a": 0, "b": None, "c": (1, 2), "d": "x", "e": VIDE, "f": 1.0, "saisie": "", "vide": None, "g": False}
CAS = [
    {},
    {"a": 0, "b": None, "c": (1, 2), "d": "x", "f": 1},               # tout par défaut
    {"a": 1, "b": 0, "c": [1, 2], "d": "y", "e": 5},                  # b=0 vs None : gardé ; c liste == tuple : défaut
    {"b": "", "c": [1, 3], "g": 0, "inconnu": 7},                     # b="" défaut ; g=0 == False ; inconnu ignoré
    {"b": [], "e": VIDE, "f": 1.5, "_saisie": "oui"},                 # b=[] défaut ; e est le défaut VIDE
    {"b": 0.0, "d": "x", "a": False},                                 # 0.0 != 0 faux : gardé ; False == 0
    {"c": (1, 2), "b": {}, "_saisie": ""},
]


@pytest.mark.parametrize("attributs", CAS)
def test_identique_a_la_reference(attributs):
    obj = Obj(**attributs)
    obtenu = serializejson.etat_sans_defauts(obj, DEFAUTS, ["saisie", "vide"])
    attendu = reference(obj, DEFAUTS, ["saisie", "vide"])
    assert obtenu == attendu
    assert list(obtenu) == list(attendu)       # l'ordre : vars d'abord, puis les properties
    assert all(type(obtenu[k]) is type(attendu[k]) for k in obtenu)


def test_property_deja_dans_vars_pas_relue():
    class Compte(Obj):
        lu = 0

        @property
        def a(self):
            Compte.lu += 1
            return 9
    obj = Compte(a=3)
    assert serializejson.etat_sans_defauts(obj, {"a": 0}, ["a"]) == {"a": 3} and Compte.lu == 0


def test_valeurs_rendues_sont_les_memes_objets():
    liste = [1]
    obj = Obj(b=liste)
    assert serializejson.etat_sans_defauts(obj, {"b": None}, [])["b"] is liste


def test_ordre_vars_puis_properties():
    obj = Obj(d="y", a=1, _saisie="s")
    assert list(serializejson.etat_sans_defauts(obj, DEFAUTS, ["saisie"])) == ["d", "a", "saisie"]


def test_exceptions_propagees():
    class Boom:
        def __eq__(self, autre):
            raise ValueError("boom")
    with pytest.raises(ValueError, match="boom"):
        serializejson.etat_sans_defauts(Obj(a=Boom()), {"a": 0}, [])

    class Sans(Obj):
        @property
        def p(self):
            raise AttributeError("sans")
    with pytest.raises(AttributeError, match="sans"):
        serializejson.etat_sans_defauts(Sans(), {"p": 0}, ["p"])
    with pytest.raises(KeyError):                      # property absente de defauts, comme defauts[nom]
        serializejson.etat_sans_defauts(Obj(), {}, ["saisie"])
    with pytest.raises(TypeError):                     # pas de __dict__, comme vars()
        serializejson.etat_sans_defauts(1, {}, [])
    with pytest.raises(TypeError):                     # __dict__ non-dict (mappingproxy d'une classe)
        serializejson.etat_sans_defauts(Obj, {}, [])


def test_comparaison_non_booleenne():
    """numpy : valeur == défaut rend un tableau, sa vérité lève ValueError comme dans le `or` python."""
    np = pytest.importorskip("numpy")
    obj = Obj(a=np.zeros(3))
    with pytest.raises(ValueError):
        serializejson.etat_sans_defauts(obj, {"a": 0}, [])
    with pytest.raises(ValueError):
        reference(obj, {"a": 0}, [])
    assert serializejson.etat_sans_defauts(Obj(a=np.int64(0)), {"a": 0}, []) == {}


def test_pas_de_fuite_de_references():
    import sys
    obj, d = Obj(a=object(), b=[1]), {"a": 0, "b": None}
    a = obj.a
    avant = (sys.getrefcount(a), sys.getrefcount(obj.b), sys.getrefcount(d))
    for _ in range(100):
        serializejson.etat_sans_defauts(obj, d, [])
    assert (sys.getrefcount(a), sys.getrefcount(obj.b), sys.getrefcount(d)) == avant
