"""Plan de décodage C des classes INSCRITES dans `serializejson.constructors`.

Ce registre sert deux rôles à la fois : registre des constructeurs
personnalisés, et cache de résolution des noms de classes
(`class_from_class_str_dict` EST `constructors`, tools.py). Une application qui
raccourcit les noms de ses classes y inscrit donc la CLASSE elle-même sous son
propre nom — c'est ce que fait SmartTeacher pour toutes les siennes, dans
`__init_subclass__`.

`decode_class_plan` rendait None dès que le nom figurait dans ce registre, sans
regarder ce qu'il désigne : ces classes perdaient le chemin rapide C alors que
la voie python se contente d'y lire la même classe (mesuré : −23 % de temps de
lecture sur un document applicatif réel de 450 objets).

Le plan n'est accordé que si le registre désigne une classe portant CE nom (un
raccourci de nom) ; une SUBSTITUTION (le registre désigne une autre classe, cas
réel de "bytes" -> bytesB64) ou une fabrique qui n'est pas une classe gardent
None, et donc la voie python inchangée.
"""

import pytest

import serializejson
from serializejson import Decoder, loads


class Raccourcie:
    def __init__(self, x=0):
        self.x = x


class AvecSetstate:
    def __init__(self, x=0):
        self.x = x

    def __setstate__(self, etat):
        # doit rester appelé même quand le plan C est accordé
        self.x = etat["x"] * 10


class Remplacante:
    def __init__(self, x=0):
        self.x = -x


def fabrique(x=0):
    return Raccourcie(x)


NOMS = ("Raccourcie", "AvecSetstate", "Substituee", "Fabriquee")


@pytest.fixture
def registre():
    """inscrit les quatre formes, et rend le registre tel qu'il était"""
    avant = {n: serializejson.constructors[n] for n in NOMS if n in serializejson.constructors}
    serializejson.constructors["Raccourcie"] = Raccourcie
    serializejson.constructors["AvecSetstate"] = AvecSetstate
    serializejson.constructors["Substituee"] = Remplacante  # classe d'un AUTRE nom
    serializejson.constructors["Fabriquee"] = fabrique  # pas une classe
    yield
    for nom in NOMS:
        serializejson.constructors.pop(nom, None)
    serializejson.constructors.update(avant)


def plan(nom):
    return Decoder(authorized_classes=list(NOMS)).decode_class_plan(nom)


def test_plan_accorde_a_une_classe_inscrite_sous_son_nom(registre):
    assert plan("Raccourcie") is Raccourcie


def test_plan_accorde_a_une_classe_a_setstate_inscrite_sous_son_nom(registre):
    assert plan("AvecSetstate") == (AvecSetstate, 2)


def test_plan_refuse_a_une_substitution_de_classe(registre):
    assert plan("Substituee") is None


def test_plan_refuse_a_une_fabrique_qui_n_est_pas_une_classe(registre):
    assert plan("Fabriquee") is None


def test_plan_refuse_a_la_substitution_bytes_du_greffon():
    # cas réel du paquet : constructors["bytes"] est bytesB64, qui décode le
    # base64 — le nom ne désigne pas la classe bytes
    assert serializejson.constructors["bytes"] is not bytes
    assert Decoder().decode_class_plan("bytes") is None


@pytest.mark.parametrize("nom,classe,attendu", [
    ("Raccourcie", Raccourcie, 3),
    ("AvecSetstate", AvecSetstate, 30),  # __setstate__ appelé malgré le plan
    ("Substituee", Remplacante, 3)])  # l'autre classe, son état posé tel quel
def test_relecture_d_un_etat_par_le_nom_inscrit(registre, nom, classe, attendu):
    # deux objets : le second est celui que le plan sert, le premier l'ayant
    # fait demander (le plan est demandé une fois par classe et par parse)
    json = ('[{"__class__": "%s", "x": 3}, {"__class__": "%s", "x": 3}]' % (nom, nom)).encode()
    objets = loads(json, authorized_classes=list(NOMS))
    assert [type(o) for o in objets] == [classe, classe]
    assert [o.x for o in objets] == [attendu, attendu]


def test_relecture_par_une_fabrique_inscrite(registre):
    # une fabrique ne se sert que de l'enveloppe à arguments : instance() y
    # appelle registre[nom](*args), elle ne saurait pas poser un état seul
    json = b'{"__class__": "Fabriquee", "__init__": [3]}'
    objet = loads(json, authorized_classes=list(NOMS))
    assert type(objet) is Raccourcie and objet.x == 3
