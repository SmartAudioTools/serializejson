"""Objets APPLICATIFS : le même état écrit, par les six voies qu'une application peut prendre.

Le banc du dépôt mesure des TYPES python (`basic_objects`) : aucune de ses catégories n'exerce
les crochets que l'APPELANT tend à serializejson (`__serializejson__`, `__getstate__`,
`__reduce__`). Ce code-là reste pourtant en python alors que tout le reste est passé en C, il est
appelé une fois par objet, et il finit donc par dominer sans que rien dans le dépôt ne le montre.
Trouvé le 02/10/2026 : 3 806 appels d'un `__serializejson__` de six lignes pesaient 60 ms des
1,7 s d'ouverture d'un sujet SmartTeacher — invisibles pour toutes les campagnes précédentes.

La comparaison est CONTRÔLÉE : les six classes écrivent exactement les mêmes six clés (donc le
même json à l'ordre des clés et au nom de classe près), seule la VOIE change. L'écart entre les
barres est donc le prix de la voie, pas celui du document :

- `crochet_python`   : le filtrage des valeurs par défaut écrit en python (l'état d'avant) ;
- `crochet_C`        : le même filtrage par `serializejson.etat_sans_defauts` (fonction C) ;
- `crochet_C_nom_court` : le même, sous un nom de classe RACCOURCI inscrit dans
  `serializejson.constructors` — la forme exacte de SmartTeacher. Jusqu'au commit 5abea26 ce
  registre privait la classe du plan de décodage C (×5 en lecture) : la barre attendue est
  désormais celle de `crochet_C` ;
- `crochet_getstate` : même état, rendu par `__getstate__` ;
- `crochet_reduce`   : même état, rendu par `__reduce__` (le crochet le plus répandu) ;
- `sans_crochet`     : TÉMOIN, aucun crochet — serializejson lit le `__dict__` en C. Il n'a pas
  de valeurs par défaut à écarter : c'est justement le travail que les quatre autres font. Son
  `__dict__` ne porte donc que les six attributs écrits, là où les autres en portent onze.

Module VOLONTAIREMENT inerte pour le reste du dépôt (rien n'énumère `tests/objects/`) : il n'est
importé que par `lance_benchmarks.py` et par `rapidjson/pgo_workload.py`.
"""
import serializejson

_MODULE = __name__

# la forme de l'`Objet` de SmartTeacher : des paramètres de constructeur avec leur défaut, dont
# certains sont lus par une property (la saisie d'une question, qui vit dans ses widgets)
DEFAUTS = {"nom": "", "enonce": "", "points": 1.0, "difficulte": 0, "duree": 0,
           "melange": True, "choix": (), "reponse": None, "commentaire": "", "saisie": ""}
PROPRIETES = ["saisie"]

# cinq valeurs posées hors défaut (dont deux cas limites du filtrage : `reponse` à 0 contre un
# défaut None est GARDÉE ; une liste contre un défaut tuple ne l'est que si elle en diffère). Les
# cinq autres paramètres restent à leur valeur par défaut : c'est le travail du crochet de les
# écarter, et c'est ce travail que le banc doit voir
POSES = {"nom": "q12", "enonce": "Quelle est la capitale du Pérou ?", "points": 2.0,
         "choix": ["Lima", "Quito", "La Paz"], "reponse": 0, "_saisie": "Lima"}
ECRITS = {"nom": "q12", "enonce": "Quelle est la capitale du Pérou ?", "points": 2.0,
          "choix": ["Lima", "Quito", "La Paz"], "reponse": 0, "saisie": "Lima"}

# les défauts tels qu'un `__init__` les pose dans le `__dict__` : les properties n'y sont pas
_DEFAUTS_VARS = {nom: valeur for nom, valeur in DEFAUTS.items() if nom not in PROPRIETES}
_DEFAUTS_VARS["_saisie"] = DEFAUTS["saisie"]


def _defaut(valeur, defaut):
    """La règle de SmartTeacher, recopiée telle quelle : un défaut None vaut tout vide sauf 0, et
    un défaut tuple vaut la liste de mêmes éléments (une liste par défaut serait partagée)."""
    return (valeur == defaut
            or (defaut is None and not valeur and valeur != 0)
            or (isinstance(defaut, tuple) and valeur == list(defaut)))


def etat_python(obj):
    """Les attributs hors défaut, puis les properties hors défaut : l'ordre des clés fait foi."""
    etat = {nom: valeur for nom, valeur in vars(obj).items()
            if nom in DEFAUTS and not _defaut(valeur, DEFAUTS[nom])}
    for nom in PROPRIETES:
        if nom not in etat:
            valeur = getattr(obj, nom)
            if not _defaut(valeur, DEFAUTS[nom]):
                etat[nom] = valeur
    return etat


class _Base:
    def __init__(self, **attributs):
        self.__dict__.update(_DEFAUTS_VARS)      # un objet applicatif porte TOUS ses paramètres
        self.__dict__.update(attributs)

    def __setstate__(self, etat):
        """Repose les défauts avant l'état lu : sans lui, un objet reconstruit (par le banc, qui
        réplique ses lots au pickle, ou par une relecture) n'aurait plus que ses six attributs
        hors défaut — le crochet n'aurait plus rien à écarter et le banc mesurerait à vide."""
        self.__dict__.update(_DEFAUTS_VARS)
        for nom, valeur in etat.items():
            setattr(self, nom, valeur)

    @property
    def saisie(self):
        return self.__dict__.get("_saisie", "")

    @saisie.setter                      # sinon la relecture échoue sur une property en lecture seule
    def saisie(self, valeur):
        self.__dict__["_saisie"] = valeur


class CrochetPython(_Base):
    def __serializejson__(self):
        return (_MODULE + ".CrochetPython", None, etat_python(self))


class CrochetC(_Base):
    def __serializejson__(self):
        return (_MODULE + ".CrochetC", None,
                serializejson.etat_sans_defauts(self, DEFAUTS, PROPRIETES))


class CrochetCourt(_Base):
    def __serializejson__(self):
        return ("CrochetCourt", None, serializejson.etat_sans_defauts(self, DEFAUTS, PROPRIETES))


# ce que fait SmartTeacher dans `__init_subclass__` : le nom court résout vers la classe
serializejson.constructors["CrochetCourt"] = CrochetCourt


class CrochetGetstate(_Base):
    def __getstate__(self):
        return etat_python(self)


class CrochetReduce(_Base):
    def __reduce__(self):
        return (type(self), (), etat_python(self))


class SansCrochet:
    """Témoin : les six clés écrites sont déjà, et seules, dans son `__dict__`."""

    def __init__(self, **attributs):
        self.__dict__.update(attributs)


# huit objets par catégorie : assez pour que la voie domine les frais fixes d'un appel à dumps
_COMBIEN = 8


def _lot(classe, attributs):
    # chaque objet reçoit des valeurs DISTINCTES : une liste partagée par les huit s'écrirait une
    # fois puis sept `$ref`, et le banc mesurerait la référence au lieu de la voie
    return {"objet %d" % rang:
            classe(**{nom: (list(valeur) if type(valeur) is list else valeur)
                      for nom, valeur in dict(attributs, nom="q%d" % rang).items()})
            for rang in range(_COMBIEN)}


objects = {
    "crochet_python": _lot(CrochetPython, POSES),
    "crochet_C": _lot(CrochetC, POSES),
    "crochet_C_nom_court": _lot(CrochetCourt, POSES),
    "crochet_getstate": _lot(CrochetGetstate, POSES),
    "crochet_reduce": _lot(CrochetReduce, POSES),
    "sans_crochet": _lot(SansCrochet, ECRITS),
}
# objets par catégorie, pour la colonne « µs par objet » du rapport
nombre_objets = {categorie: _COMBIEN for categorie in objects}
