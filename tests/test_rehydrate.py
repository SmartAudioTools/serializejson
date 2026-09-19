"""Mode rehydrate=True (sans Qt) : chaque objet est construit ou ADOPTÉ au fil
du parse, dès son enveloppe lue, avant ses attributs — pas d'arbre de dicts
intermédiaire. Avec obj=, l'homologue vivant de chaque objet est retrouvé par
la chaîne des clés depuis la racine et adopté si sa classe correspond : les
identités sont conservées, __init__ n'est jamais rejoué.
"""

import tracemalloc

import pytest

from serializejson import Decoder, dumps, loads
from serializejson.tools import class_str_from_class


class Fils:
    def __init__(self, n=0):
        self.n = n


class Parent:
    inits = 0

    def __init__(self):
        self.a = Fils(1)
        self.b = Fils(2)
        self.liste = [Fils(3), Fils(4)]
        self.d = {"k": Fils(5)}
        Parent.inits += 1


class AvecSetstate:
    def __init__(self):
        self.x = 0

    def __setstate__(self, state):
        self.x = state["x"] * 10


class Valeur:
    # enveloppe-valeur (comme Decimal, QColor) : sans état ; adoptée si son
    # argument est égal, ou modifiée sur place (attribut homonyme inscriptible)
    def __init__(self, x):
        self.x = x

    def __serializejson__(self):
        return class_str_from_class(Valeur), (self.x,), None


class Enfant:
    # parenté par son __init__ (comme un enfant Qt anonyme) : son argument,
    # le parent, est égal par identité → adopté même sans état
    def __init__(self, parent):
        self.parent = parent

    def __serializejson__(self):
        return class_str_from_class(Enfant), {"parent": self.parent}, None


class Segment:
    # enveloppe-valeur dont un argument est lui-même CONSTRUIT (Valeur) :
    # l'argument construit diffère du vivant, il est posé par son nom
    def __init__(self, debut, fin):
        self.debut, self.fin = debut, fin

    def __serializejson__(self):
        return class_str_from_class(Segment), (self.debut, self.fin), None


class Trace:
    # écrite avec __init__ : recréée, elle crée un Segment vivant sous elle
    def __init__(self):
        self.segment = Segment(0, Valeur(0))

    def __serializejson__(self):
        return class_str_from_class(Trace), (), {"segment": self.segment}


CLASSES = [Parent, Fils, AvecSetstate, Valeur, Enfant, Segment, Trace]


def _parent():
    p = Parent()
    p.a.n = 11
    p.liste[1].n = 44
    p.d["k"].n = 55
    p.ss = AvecSetstate()
    p.ss.x = 3
    return p


def _identites(p):
    return [id(o) for o in (p.a, p.b, p.liste[0], p.liste[1], p.d["k"], p.ss)]


def test_rehydrate_adopte_et_applique():
    p = _parent()
    json = dumps(p)
    p.a.n = p.liste[1].n = p.d["k"].n = 0
    p.ss.x = 0
    ids = _identites(p)
    Parent.inits = 0
    assert loads(json, obj=p, rehydrate=True, authorized_classes=CLASSES) is p
    assert _identites(p) == ids
    assert (p.a.n, p.liste[1].n, p.d["k"].n) == (11, 44, 55)
    assert p.ss.x == 30
    assert Parent.inits == 0


def test_rehydrate_remplace_sur_classe_differente():
    p = _parent()
    json = dumps(p)
    p.b = "pas un Fils"
    loads(json, obj=p, rehydrate=True, authorized_classes=CLASSES)
    assert isinstance(p.b, Fils) and p.b.n == 2


def test_rehydrate_sans_etat_reconcilie_par_argument():
    p = _parent()
    p.egale = Valeur(9)
    p.modifiee = Valeur(9)
    p.enfant = Enfant(p)
    json = dumps(p)
    p.modifiee.x = 0
    egale, modifiee, enfant = p.egale, p.modifiee, p.enfant
    loads(json, obj=p, rehydrate=True, authorized_classes=CLASSES)
    assert p.egale is egale and p.egale.x == 9  # égale : adoptée telle quelle
    assert p.modifiee is modifiee and p.modifiee.x == 9  # modifiée sur place
    assert p.enfant is enfant  # adopté


def test_rehydrate_argument_construit_ferme_n_ancre_pas():
    t = Trace()
    t.segment = Segment(0, Valeur(5))
    q = loads(dumps(t), authorized_classes=CLASSES)
    assert q.segment.fin.x == 5


def test_rehydrate_updatables_classes_restreint_l_adoption():
    p = _parent()
    a = p.a
    loads(dumps(p), obj=p, rehydrate=True, authorized_classes=CLASSES,
          updatables_classes=[Parent])
    assert p.a is not a and p.a.n == 11


def test_rehydrate_sans_obj_recree():
    p = _parent()
    json = dumps(p)
    q = loads(json, rehydrate=True, authorized_classes=CLASSES)
    assert q is not p and q.a is not p.a
    assert (q.a.n, q.liste[1].n, q.d["k"].n, q.ss.x) == (11, 44, 55, 30)
    # le mode est le défaut ; rehydrate=False rend la voie classique
    assert Decoder(authorized_classes=CLASSES).construct is not None
    assert Decoder(rehydrate=False, authorized_classes=CLASSES).construct is None


@pytest.mark.parametrize("rehydrate", [False, True])
def test_rehydrate_memoire_bornee(rehydrate):
    # le transitoire du chargement est la copie du document (tampon de
    # parse), pas un arbre de dicts : identique avec et sans le mode
    def transitoire(n):
        doc = dumps([Parent() for _ in range(n)]).encode()
        tracemalloc.start()
        resultat = loads(doc, rehydrate=rehydrate, authorized_classes=[Parent, Fils])
        courant, pic = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert len(resultat) == n  # le résultat compte dans `courant`, pas dans le transitoire
        return pic - courant - len(doc)

    assert transitoire(1000) < 2 * transitoire(100) + 4096
