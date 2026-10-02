"""Classes à `__setstate__` : construites en C, état remis en UN appel C.

`decode_class_plan` leur rend `(classe, 3)`. Avant, le plan `(classe, 2)`
faisait construire l'instance en C puis décliner la fermeture vers la voie
python (`end_object` → `_inst_from_dict` → `instance()`), un aller-retour
python par objet. Le C appelle désormais `inst.__setstate__(etat)` lui-même,
avec la sémantique d'`instance()` : `__class__`/`__init__`/`__new__` retirés,
toutes les autres clés transmises (`~…` comprises), et aucun appel si l'état
est vide.
"""

import pytest

import serializejson
from serializejson import dumps, loads


class Etat:
    appels = 0

    def __init__(self, a=0, b=0):
        self.a = a
        self.b = b

    def __setstate__(self, etat):
        type(self).appels += 1
        self.recu = dict(etat)
        self.a = etat.get("a", 0) * 10
        self.b = etat.get("b", 0)


class Leve:
    def __setstate__(self, etat):
        raise KeyError("refus volontaire")


CLASSES = [Etat, Leve]


@pytest.fixture(autouse=True)
def compteur():
    Etat.appels = 0


def relis(json, rehydrate=True):
    return loads(json, authorized_classes=CLASSES, rehydrate=rehydrate)


def nom(cls):
    return serializejson.class_str_from_class(cls)


@pytest.mark.parametrize("rehydrate", [True, False])
def test_etat_remis_par_setstate(rehydrate):
    json = '[{"__class__": "%s", "a": 1, "b": 2}, {"__class__": "%s", "a": 3}]' % (nom(Etat), nom(Etat))
    objets = relis(json, rehydrate)
    assert [(o.a, o.b) for o in objets] == [(10, 2), (30, 0)]
    assert Etat.appels == 2


@pytest.mark.parametrize("rehydrate", [True, False])
def test_etat_vide_setstate_non_appele(rehydrate):
    # instance() n'appelle __setstate__ que si l'état est non vide
    objet = relis('{"__class__": "%s"}' % nom(Etat), rehydrate)
    assert type(objet) is Etat and Etat.appels == 0
    assert not hasattr(objet, "a")  # __init__ non rejoué


@pytest.mark.parametrize("rehydrate", [True, False])
def test_cles_tilde_transmises(rehydrate):
    objet = relis('{"__class__": "%s", "a": 1, "~x": 5}' % nom(Etat), rehydrate)
    assert objet.recu == {"a": 1, "~x": 5}


@pytest.mark.parametrize("rehydrate", [True, False])
def test_init_liste_puis_setstate(rehydrate):
    objet = relis('{"__class__": "%s", "__init__": [7, 8], "a": 2}' % nom(Etat), rehydrate)
    assert (objet.a, objet.b) == (20, 0) and objet.recu == {"a": 2}


@pytest.mark.parametrize("rehydrate", [True, False])
def test_enveloppe_stricte_constructeur_seul(rehydrate):
    objet = relis('{"__class__": "%s", "__init__": [7, 8]}' % nom(Etat), rehydrate)
    assert (objet.a, objet.b) == (7, 8) and Etat.appels == 0


@pytest.mark.parametrize("rehydrate", [True, False])
def test_aller_retour_identique(rehydrate):
    origine = Etat(4, 5)
    copie = relis(dumps(origine), rehydrate)
    assert (copie.a, copie.b) == (40, 5)


@pytest.mark.parametrize("rehydrate", [True, False])
def test_voie_c_sans_instance_python(monkeypatch, rehydrate):
    # preuve de la voie : la voie python passe par serializejson.instance ;
    # la neutraliser ne doit rien changer au résultat
    def interdit(*args, **kwargs):
        raise AssertionError("voie python prise")

    json = '[{"__class__": "%s", "a": 1}, {"__class__": "%s", "a": 2, "~y": 0}]' % (nom(Etat), nom(Etat))
    monkeypatch.setattr(serializejson, "instance", interdit)
    objets = relis(json, rehydrate)
    assert [o.a for o in objets] == [10, 20]


@pytest.mark.parametrize("rehydrate", [True, False])
def test_exception_de_setstate_propagee(rehydrate):
    with pytest.raises(KeyError, match="refus volontaire"):
        relis('{"__class__": "%s", "z": 1}' % nom(Leve), rehydrate)
