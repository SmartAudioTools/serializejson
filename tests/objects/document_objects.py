"""Un DOCUMENT applicatif synthétique : arbre profond, hétérogène, à références denses.

Les autres catégories du banc sont des lots d'objets frères, tous du même type : aucune ne
ressemble à un document réel, où l'on descend sur plusieurs niveaux de classes différentes et où
les `$ref` sont la règle. Celui-ci reproduit la forme d'un sujet SmartTeacher (le document du
02/10/2026 : ~450 objets) sans en dépendre :

    Paquet ── 50 Question ── 8 Choix chacune      (≈ 450 objets, 3 niveaux)

- un `Bareme` PARTAGÉ par le paquet et toutes ses questions (un objet, puis des `$ref`) ;
- une référence ARRIÈRE de chaque choix vers sa question, qui est encore en construction quand le
  choix est relu (le cas `$ref` vers un ancêtre ouvert) ;
- les classes de SmartTeacher : paramètres de constructeur avec défaut, écriture par
  `__serializejson__` + `serializejson.etat_sans_defauts`, relecture par
  `__setstate__ = __init__(**etat)`, noms de classes RACCOURCIS inscrits dans
  `serializejson.constructors`.

Importé seulement par `lance_benchmarks.py` (catégorie `document`).
"""
import serializejson


class _Objet:
    DEFAUTS = {}

    def __init__(self, **attributs):
        self.__dict__.update(self.DEFAUTS)
        self.__dict__.update(attributs)

    def __setstate__(self, etat):
        self.__init__(**etat)

    def __serializejson__(self):
        return (type(self).__name__, None, serializejson.etat_sans_defauts(self, self.DEFAUTS, ()))

    def __init_subclass__(cls):
        serializejson.constructors[cls.__name__] = cls


class Bareme(_Objet):
    DEFAUTS = {"juste": 1.0, "faux": 0.0, "neutre": 0.0, "arrondi": 0.25}


class Choix(_Objet):
    DEFAUTS = {"texte": "", "correct": False, "question": None, "retour": "", "poids": 1.0}


class Question(_Objet):
    DEFAUTS = {"nom": "", "enonce": "", "points": 1.0, "bareme": None, "choix": (),
               "melange": True, "commentaire": "", "duree": 0}


class Paquet(_Objet):
    DEFAUTS = {"titre": "", "auteur": "", "bareme": None, "questions": (), "version": 1}


QUESTIONS, CHOIX = 50, 8
NOMBRE_OBJETS = 1 + 1 + QUESTIONS * (1 + CHOIX)   # paquet + barème + questions et leurs choix


def document():
    bareme = Bareme(faux=-0.5)
    questions = []
    for q in range(QUESTIONS):
        question = Question(nom="q%d" % q, enonce="Énoncé de la question %d ?" % q,
                            points=float(1 + q % 3), bareme=bareme,
                            commentaire="à revoir" if q % 7 == 0 else "")
        question.choix = [Choix(texte="réponse %d.%d" % (q, c), correct=c == q % CHOIX,
                                question=question,
                                retour="presque" if c == (q + 1) % CHOIX else "")
                          for c in range(CHOIX)]
        questions.append(question)
    return Paquet(titre="Sujet synthétique", auteur="banc", bareme=bareme, questions=questions)


objects = {"document": {"paquet": document()}}
nombre_objets = {"document": NOMBRE_OBJETS}
