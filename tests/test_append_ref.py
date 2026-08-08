# Doublons et cycles DANS un maillon appendé.
#
# Un maillon n'est pas un document : il est écrit à SA PLACE dans une liste.
# Ses chemins « $ref » doivent donc partir de la racine du FICHIER —
# « root[3]['a'] » et non « root['a'] » —, seule forme que la relecture du
# document sache suivre. L'écriture les composait depuis le maillon : tout
# fichier contenant un objet partagé ou un cycle dans un maillan de rang >= 1
# était illisible, en silence à l'écriture et par TypeError à la relecture.
# Corrigé le 08/08/2026, avec les deux relectures que le format promet :
# le document entier par `load`, et maillon par maillon par `Decoder`.
import pytest

import serializejson


@pytest.fixture
def chemin(tmp_path):
    return str(tmp_path / "appended.json")


def _relit(chemin, compare=True):
    """Les deux relectures que le format promet, à confronter l'une à l'autre.

    `compare` est faux pour un graphe cyclique : `==` s'y enfonce sans fin.
    """
    entier = serializejson.load(chemin)
    un_par_un = list(serializejson.Decoder(chemin))
    if compare:
        assert entier == un_par_un
    else:
        assert len(entier) == len(un_par_un)
    return entier, un_par_un


def test_partage_dans_un_maillon(chemin):
    partage = {"x": 1}
    encodeur = serializejson.Encoder(file=chemin, index=None, indent=None)
    for i in range(3):
        encodeur.append({"n": i})
    encodeur.append({"a": partage, "b": partage})
    encodeur.close()
    serializejson.wait_writes()

    with open(chemin, "rb") as fichier:
        assert fichier.read() == (
            b'[{"n":0},{"n":1},{"n":2},'
            b'{"a":{"x":1},"b":{"$ref": "root[3][\'a\']"}}]')
    entier, un_par_un = _relit(chemin)
    for relus in (entier, un_par_un):
        assert relus[3]["a"] is relus[3]["b"]


def test_cycle_dans_un_maillon(chemin):
    cycle = {"nom": "c"}
    cycle["moi"] = cycle
    encodeur = serializejson.Encoder(file=chemin, index=None, indent=None)
    encodeur.append({"n": 0})
    encodeur.append({"c": cycle})
    encodeur.close()
    serializejson.wait_writes()

    entier, un_par_un = _relit(chemin, compare=False)
    for relus in (entier, un_par_un):
        assert relus[1]["c"]["moi"] is relus[1]["c"]
        assert relus[1]["c"]["nom"] == "c"


def test_maillon_qui_se_designe_lui_meme(chemin):
    # le seul cas où le « $ref » désigne la RACINE du maillon : il vaut alors
    # « root[1] » tout court, et la relecture d'un maillon seul le ramène à
    # « root ». C'est aussi le seul chemin qui ne passe pas par un PathNode
    soi = {"nom": "moi"}
    soi["soi"] = soi
    encodeur = serializejson.Encoder(file=chemin, index=None, indent=None)
    encodeur.append({"n": 0})
    encodeur.append(soi)
    encodeur.close()
    serializejson.wait_writes()

    with open(chemin, "rb") as fichier:
        assert fichier.read() == (
            b'[{"n":0},{"nom":"moi","soi":{"$ref": "root[1]"}}]')
    entier, un_par_un = _relit(chemin, compare=False)
    for relus in (entier, un_par_un):
        assert relus[1]["soi"] is relus[1]


@pytest.mark.parametrize("indent", (None, "\t"))
def test_rang_rattrape_sur_fichier_deja_rempli(chemin, indent):
    # un encodeur NEUF par appel — ce que fait la fonction de module — ne sait
    # pas à quel rang tombe son maillon : il l'écrit, s'aperçoit qu'un « $ref »
    # a dû être composé sans lui, compte les maillons déjà là et recommence.
    # Le fichier doit être celui qu'un seul encodeur aurait écrit.
    partage = {"x": 1}
    for i in range(3):
        serializejson.append({"n": i}, chemin, index=None, indent=indent)
    serializejson.append({"a": partage, "b": partage}, chemin,
                         index=None, indent=indent)
    serializejson.wait_writes()

    temoin = str(chemin) + ".temoin"
    encodeur = serializejson.Encoder(file=temoin, index=None, indent=indent)
    for i in range(3):
        encodeur.append({"n": i})
    encodeur.append({"a": partage, "b": partage})
    encodeur.close()
    serializejson.wait_writes()
    with open(chemin, "rb") as un, open(temoin, "rb") as deux:
        assert un.read() == deux.read()

    entier, un_par_un = _relit(chemin)
    for relus in (entier, un_par_un):
        assert relus[3]["a"] is relus[3]["b"]


def test_rattrapage_puis_appends_suivants(chemin):
    # le rang rattrapé sert aussi aux maillons SUIVANTS du même encodeur :
    # le balayage ne se paie qu'une fois
    partage = {"x": 1}
    for i in range(2):
        serializejson.append({"n": i}, chemin, index=None, indent=None)
    encodeur = serializejson.Encoder(file=chemin, index=None, indent=None)
    encodeur.append({"a": partage, "b": partage})
    encodeur.append({"c": partage, "d": partage})
    encodeur.close()
    serializejson.wait_writes()

    with open(chemin, "rb") as fichier:
        contenu = fichier.read()
    assert b"root[2]['a']" in contenu
    assert b"root[3]['c']" in contenu
    entier, un_par_un = _relit(chemin)
    for relus in (entier, un_par_un):
        assert relus[2]["a"] is relus[2]["b"]
        assert relus[3]["c"] is relus[3]["d"]


def test_index_tenu_avec_un_partage(chemin):
    # l'index des maillons se tient toujours quand l'un d'eux porte un $ref
    partage = {"x": 1}
    encodeur = serializejson.Encoder(file=chemin, indent=None)
    encodeur.append({"n": 0})
    encodeur.append({"a": partage, "b": partage})
    encodeur.close()
    serializejson.wait_writes()

    relus = serializejson.load(chemin)
    assert relus[1]["a"] is relus[1]["b"]
    assert serializejson.load(chemin, path="root[1]['a']") == partage
