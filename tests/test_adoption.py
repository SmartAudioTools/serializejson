"""Adoption d'un homologue vivant au rechargement (rehydrate, défaut).

La racine est reconstruite par son __init__, qui crée déjà ses enfants ; pour
chaque enfant lu dans le json, le décodeur doit ADOPTER l'enfant vivant (pas
de doublon, identité et connexions conservées) ou le RECONSTRUIRE (le vivant
ne peut pas prendre les valeurs du json). Critère visé, à trois étages :

1. arguments du json == arguments du vivant (lus par son réducteur) → adopter ;
2. arguments différents, mais chacun applicable par son nom au vivant
   (setter Qt `setNom`, ou attribut homonyme inscriptible) → adopter puis
   appliquer ;
3. sinon → reconstruire.

Deux familles de tests, sur les mêmes cas :
- VALEURS : le résultat porte les valeurs du json, quelle que soit la voie ;
- VOIE : adopté ou reconstruit, compté par les instances créées pendant le
  chargement (`Suivi.crees`) en recréation, par l'identité avec obj=.
"""

import pytest

from serializejson import loads, dumps
from serializejson.tools import class_str_from_class


class Suivi:
    # chaque __init__ s'inscrit : un enfant reconstruit en plus de celui du
    # __init__ de la racine se voit comme une seconde inscription
    crees = []

    def __init__(self):
        Suivi.crees.append(self)


class Config(Suivi):
    # sans argument, avec état
    def __init__(self):
        super().__init__()
        self.niveau = 0


class Enfant(Suivi):
    # parenté, sans état (le QLabel anonyme)
    def __init__(self, parent):
        super().__init__()
        self.parent = parent

    def __serializejson__(self):
        return class_str_from_class(Enfant), {"parent": self.parent}, None


class Nomme(Suivi):
    # parenté, avec état
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.texte = ""

    def __serializejson__(self):
        return class_str_from_class(Nomme), {"parent": self.parent}, {"texte": self.texte}


class Seg(Suivi):
    # arguments stockés sous des attributs homonymes, sans état
    def __init__(self, a, b):
        super().__init__()
        self.a, self.b = a, b

    def __serializejson__(self):
        return class_str_from_class(Seg), (self.a, self.b), None


class SegEtat(Suivi):
    # arguments homonymes ET état : le cas qui perdait ses arguments
    def __init__(self, a, b):
        super().__init__()
        self.a, self.b = a, b
        self.couleur = "noir"

    def __serializejson__(self):
        return class_str_from_class(SegEtat), (self.a, self.b), {"couleur": self.couleur}


class Echelle(Suivi):
    # argument TRANSFORMÉ : aucun attribut homonyme, rien à appliquer par nom
    def __init__(self, a):
        super().__init__()
        self._double = 2 * a

    def __serializejson__(self):
        return class_str_from_class(Echelle), (self._double // 2,), None


class Fige(Suivi):
    # attribut homonyme en LECTURE SEULE : non applicable par nom
    def __init__(self, x):
        super().__init__()
        self._x = x

    @property
    def x(self):
        return self._x

    def __serializejson__(self):
        return class_str_from_class(Fige), (self._x,), None


class AvecSetter(Suivi):
    # argument applicable par un setter à la Qt (valeur → setValeur)
    def __init__(self, valeur):
        super().__init__()
        self._v = valeur

    def valeur(self):
        return self._v

    def setValeur(self, v):
        self._v = v

    def __serializejson__(self):
        return class_str_from_class(AvecSetter), (self._v,), None


class Racine:
    def __init__(self):
        self.config = Config()
        self.enfant = Enfant(self)
        self.nomme = Nomme(self)
        self.seg_egal = Seg(0, 0)
        self.seg_modifie = Seg(0, 0)
        self.seg_etat = SegEtat(0, 0)
        self.echelle = Echelle(1)
        self.fige = Fige(0)
        self.avec_setter = AvecSetter(0)

    def __serializejson__(self):
        return class_str_from_class(Racine), (), dict(self.__dict__)


CLASSES = [Racine, Config, Enfant, Nomme, Seg, SegEtat, Echelle, Fige, AvecSetter]


def _modifie(r):
    """Ce que le programme d'origine a fait après le __init__ de la racine."""
    r.config.niveau = 3                    # modifié sur place
    r.nomme.texte = "bonjour"              # modifié sur place
    r.seg_modifie.a = 3                    # argument modifié sur place
    r.seg_etat = SegEtat(3, 4)             # remplacé
    r.seg_etat.couleur = "rouge"
    r.echelle = Echelle(5)                 # remplacé
    r.fige = Fige(5)                       # remplacé
    r.avec_setter = AvecSetter(7)          # remplacé
    return r


# attribut → (valeurs attendues, voie attendue)
CAS = {
    "config": (lambda o: o.niveau == 3, "adopte"),
    "enfant": (lambda o: type(o) is Enfant, "adopte"),
    "nomme": (lambda o: o.texte == "bonjour", "adopte"),
    "seg_egal": (lambda o: (o.a, o.b) == (0, 0), "adopte"),
    "seg_modifie": (lambda o: (o.a, o.b) == (3, 0), "adopte"),
    "seg_etat": (lambda o: (o.a, o.b, o.couleur) == (3, 4, "rouge"), "adopte"),
    "echelle": (lambda o: o._double == 10, "reconstruit"),
    "fige": (lambda o: o.x == 5, "reconstruit"),
    "avec_setter": (lambda o: o.valeur() == 7, "adopte"),
}


def _json():
    return dumps(_modifie(Racine()))


def _recree():
    json = _json()
    Suivi.crees = []
    r = loads(json, authorized_classes=CLASSES)
    return r, list(Suivi.crees)


def _rehydrate():
    json = _json()
    vivant = Racine()
    avant = dict(vivant.__dict__)
    assert loads(json, obj=vivant, authorized_classes=CLASSES) is vivant
    return vivant, avant


@pytest.mark.parametrize("attr", CAS)
def test_valeurs_recreation(attr):
    r, _ = _recree()
    assert CAS[attr][0](getattr(r, attr))


@pytest.mark.parametrize("attr", CAS)
def test_valeurs_rehydratation(attr):
    r, _ = _rehydrate()
    assert CAS[attr][0](getattr(r, attr))


@pytest.mark.parametrize("attr", CAS)
def test_voie_recreation(attr):
    r, crees = _recree()
    classe = type(getattr(r, attr))
    # le __init__ de la racine en crée un ; une reconstruction en ajoute un
    # second (la racine crée un seul objet de chaque classe, sauf Seg : deux)
    par_racine = 2 if classe is Seg else 1
    attendu = par_racine + (CAS[attr][1] == "reconstruit")
    assert sum(type(o) is classe for o in crees) == attendu
    # l'objet rangé sous l'attribut est bien un de ceux du __init__ si adopté
    rang = [o for o in crees if type(o) is classe].index(getattr(r, attr))
    assert (rang < par_racine) == (CAS[attr][1] == "adopte")


@pytest.mark.parametrize("attr", CAS)
def test_voie_rehydratation(attr):
    r, avant = _rehydrate()
    assert (getattr(r, attr) is avant[attr]) == (CAS[attr][1] == "adopte")


def test_enfant_ancre_sur_la_racine_reconstruite():
    # l'enfant adopté pointe sur la racine RENDUE, pas sur une autre
    r, _ = _recree()
    assert r.enfant.parent is r and r.nomme.parent is r
