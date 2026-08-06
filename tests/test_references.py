"""Filet de sécurité pour la migration C++ : références circulaires, duplicatas, grosses données.

Les cycles et duplicatas de dicts/listes sont couverts depuis les hooks
default_dict/default_list de l'Encoder (rapidjson du dépôt + serializejson).
"""

import pytest
import serializejson

try:
    import numpy

    use_numpy = True
except ModuleNotFoundError:
    use_numpy = False


class Node:
    def __init__(self):
        self.child = None


def roundtrip(obj):
    dumped = serializejson.dumps(obj, indent=None)
    return dumped, serializejson.loads(dumped, authorized_classes=[Node])


# --- objets : déjà supportés, ne doit jamais régresser -------------------------


def test_object_duplique_partage():
    shared = Node()
    a = Node()
    b = Node()
    a.child = shared
    b.child = shared
    dumped, loaded = roundtrip([a, b])
    assert dumped.count('"$ref"') == 1
    assert loaded[0].child is loaded[1].child


def test_objets_circulaires():
    a = Node()
    b = Node()
    a.child = b
    b.child = a
    dumped, loaded = roundtrip([a, b])
    assert loaded[0].child is loaded[1]
    assert loaded[1].child is loaded[0]


def test_objet_reference_son_parent():
    parent = Node()
    child = Node()
    parent.child = child
    child.child = parent
    dumped, loaded = roundtrip(parent)
    assert loaded.child.child is loaded


# --- dict/list : couverts par les hooks default_dict/default_list --------------


def test_dict_circulaire():
    A = {"name": "A"}
    B = {"name": "B"}
    A["link"] = B
    B["link"] = A
    dumped, loaded = roundtrip(A)
    assert loaded["link"]["link"] is loaded


def test_liste_circulaire():
    L = [1]
    L.append(L)
    dumped, loaded = roundtrip(L)
    assert loaded[1] is loaded


def test_dict_duplique_partage():
    d = {"x": 1}
    dumped, loaded = roundtrip([d, d])
    assert loaded[0] is loaded[1]


def test_liste_dupliquee_partage():
    L = [1, 2]
    dumped, loaded = roundtrip([L, L])
    assert loaded[0] is loaded[1]


class AvecInitArgs:
    def __init__(self, a, b=None):
        self.a = a
        self.b = b

    def __reduce__(self):
        return (self.__class__, (self.a, self.b))


def test_doublon_dans_init_compact():
    # un doublon à l'intérieur des args __init__ (sous-arbre compact SingleLine)
    # doit être détecté par le mémo : un seul encodeur pour tout le document
    partage = [1, 2]
    obj = AvecInitArgs(partage, partage)
    dumped = serializejson.dumps(obj, indent="\t")
    assert dumped.count('"$ref"') == 1
    loaded = serializejson.loads(dumped, authorized_classes=[AvecInitArgs])
    assert loaded.a is loaded.b


class NodeSlots:
    __slots__ = ("child",)

    def __init__(self):
        self.child = None


def test_ref_differee_dans_slot():
    # racine liste -> les $ref ne peuvent être résolus qu'après le parse,
    # et la cible doit être réinstallée dans un slot
    shared = {"x": 1}
    a = NodeSlots()
    b = NodeSlots()
    a.child = shared
    b.child = shared
    dumped = serializejson.dumps([a, b], indent=None)
    loaded = serializejson.loads(dumped, authorized_classes=[NodeSlots])
    assert loaded[0].child is loaded[1].child


# --- rigueur des __dict__ partagés : au-delà de pickle, qui perd ces partages --


def test_dict_reel_reference_apres_objet():
    # l'objet est aplati d'abord, puis son vrai __dict__ apparait comme valeur
    a = Node()
    a.child = 1
    dumped = serializejson.dumps([a, a.__dict__], indent=None)
    assert '"$ref"' in dumped
    loaded = serializejson.loads(dumped, authorized_classes=[Node])
    assert loaded[1] is loaded[0].__dict__


def test_dict_reel_reference_avant_objet():
    # le dict apparait d'abord comme simple valeur, l'objet qui l'utilise
    # comme __dict__ est sérialisé ensuite
    a = Node()
    a.child = 1
    dumped = serializejson.dumps([a.__dict__, a], indent=None)
    assert '"__dict__"' in dumped
    loaded = serializejson.loads(dumped, authorized_classes=[Node])
    assert loaded[1].__dict__ is loaded[0]


def test_deux_objets_partageant_le_meme_dict():
    b = Node()
    c = Node()
    c.__dict__ = b.__dict__
    b.child = 5
    dumped = serializejson.dumps([b, c], indent=None)
    loaded_b, loaded_c = serializejson.loads(dumped, authorized_classes=[Node])
    assert loaded_b.__dict__ is loaded_c.__dict__
    loaded_b.autre = 1
    assert loaded_c.autre == 1


# --- grosses données : verrouille le chemin bytes -> blosc -> b64 --------------


def test_gros_bytes_compresses():
    # les bytes nus ne sont plus compressés par défaut : le chemin bytes ->
    # blosc -> b64 se demande par le seuil (06/08/2026)
    data = bytes(range(256)) * 5000  # 1.28 Mo compressibles
    dumped = serializejson.dumps(data, indent=None,
                                 bytes_size_compression_threshold=512)
    assert len(dumped) < len(data)  # la compression a bien eu lieu
    assert serializejson.loads(dumped) == data


def test_gros_bytes_incompressibles():
    import random

    rng = random.Random(0)
    data = bytes(rng.getrandbits(8) for _ in range(100_000))
    dumped, loaded = roundtrip(data)
    assert loaded == data


@pytest.mark.skipif(not use_numpy, reason="numpy absent")
def test_gros_tableau_numpy_1d():
    array = numpy.arange(200_000, dtype=numpy.float64)
    dumped = serializejson.dumps(array, indent=None)
    loaded = serializejson.loads(dumped)
    assert loaded.dtype == array.dtype
    assert numpy.array_equal(loaded, array)


@pytest.mark.skipif(not use_numpy, reason="numpy absent")
def test_gros_tableau_numpy_2d():
    array = numpy.arange(100_000, dtype=numpy.int32).reshape(500, 200)
    dumped = serializejson.dumps(array, indent=None)
    loaded = serializejson.loads(dumped)
    assert loaded.dtype == array.dtype
    assert loaded.shape == array.shape
    assert numpy.array_equal(loaded, array)


@pytest.mark.skipif(not use_numpy, reason="numpy absent")
def test_tableau_numpy_bool():
    array = numpy.array([True, False, True] * 1000)
    dumped = serializejson.dumps(array, indent=None)
    loaded = serializejson.loads(dumped)
    assert loaded.dtype == array.dtype
    assert numpy.array_equal(loaded, array)


# --- références VERS l'intérieur d'une enveloppe de dict à clés non-str -------
# (cassées depuis toujours : le chemin porte le texte ENCODÉ de la clé — '2',
# b'k', [5,6] — alors que le dict reconstruit porte la clé DÉCODÉE ; corrigé
# le 05/08/2026 des deux côtés : résolveur C et from_name décodent la clé)


@pytest.mark.parametrize(
    "cle",
    [2, True, b"k", b"x'y", "true", "2", (5, 6), frozenset([7])],
    ids=["int", "bool", "bytes", "bytes_quote", "str_true", "str_2",
         "tuple", "frozenset"],
)
def test_ref_vers_valeur_de_dict_cle_non_str(cle):
    shared = [9, 8]
    dumped, loaded = roundtrip([{cle: shared}, shared])
    assert dumped.count('"$ref"') == 1
    assert loaded[0][cle] is loaded[1]


def test_ref_vers_valeur_de_dict_cle_non_str_racine_dict():
    shared = [9, 8]
    data = {"a": {2: shared}, "b": shared}
    dumped, loaded = roundtrip(data)
    assert loaded["a"][2] is loaded["b"]


def test_ref_style_historique_point_sur_enveloppe_dict():
    # documents écrits par l'ancienne voie python : segment « .2 » (attribut)
    # au lieu de « ['2'] » — doit rester lisible
    legacy = ('[{"__class__": "dict", "2": [9,8],'
              ' "p": {"$ref": "root[0].2"}}, {"$ref": "root[0].2"}]')
    loaded = serializejson.loads(legacy)
    assert loaded[0][2] is loaded[1] and loaded[0]["p"] is loaded[1]


def test_ref_chemin_echappe_guillemet_dans_cle():
    # une clé contenant un guillemet rendait le document INVALIDE (guillemet
    # brut dans la chaîne $ref) — l'échappement JSON du chemin le corrige
    shared = [9, 8]
    for cle in ['a"b', b'x"y', 'x\ty', 'a\\b']:
        dumped, loaded = roundtrip([{cle: shared}, shared])
        assert loaded[0][cle] is loaded[1]


def test_ref_vers_interieur_de_collections():
    # les chemins .__items__ / .__init__ d'une enveloppe de collection
    # se résolvent sur l'objet RECONSTRUIT (les éléments sont l'objet
    # lui-même ; __init__ est la fabrique d'un defaultdict, jamais la
    # méthode) — cassé depuis toujours, corrigé le 06/08/2026
    import collections

    shared = [9, 8]
    cas = [
        collections.deque([shared]),
        collections.OrderedDict({"x": shared}),
        collections.Counter(),  # __init__ vide : juste le roundtrip
        collections.defaultdict(None, {"y": shared}),
    ]
    for objet in cas:
        dumped, loaded = roundtrip([objet, shared])
        obj = loaded[0]
        assert type(obj) is type(objet)
        if isinstance(obj, collections.deque):
            assert obj[0] is loaded[1]
        elif len(obj):
            assert next(iter(obj.values())) is loaded[1]


def test_deque_maxlen_reste_voie_python():
    import collections

    d = collections.deque([1, 2], maxlen=5)
    dumped, loaded = roundtrip(d)
    assert type(loaded) is collections.deque
    assert loaded.maxlen == 5 and list(loaded) == [1, 2]


def test_types_de_cles_non_str_preserves():
    # le décodage AU VOL des clés (état 7) doit rendre les MÊMES TYPES que
    # dict_non_str_keys — un int relu en float passerait l'égalité de dict
    # (2 == 2.0) mais pas ce test (attrapé le 06/08 : PyLong_FromString
    # lisait au-delà de la clé dans le tampon de parse non terminé)
    d = {2: "a", 3.5: "b", True: "c", None: "d", b"k": "e", "2": "f",
         10**30: "g", (5, 6): "h", "s": "i"}
    dumped, loaded = roundtrip(d)
    assert loaded == d
    assert sorted(type(k).__name__ for k in loaded) == sorted(
        type(k).__name__ for k in d)


@pytest.mark.parametrize("partage", [(6, 8), frozenset([1, 2])])
@pytest.mark.parametrize("cle_dabord", [True, False])
def test_conteneur_partage_entre_une_cle_et_une_valeur(partage, cle_dabord):
    # une clé tuple/frozenset est écrite par le même dumps_internal que le
    # reste : sans suspension du mémo, l'occurrence hors clé sortait en
    # {"$ref": ...} vers un chemin INTERNE à la clé, illisible (KeyError à
    # la relecture). Vérifié en retirant la suspension : ce test échoue,
    # et lui seul de toute la batterie
    entrees = [((5, partage), 0), ("v", partage)]
    d = dict(entrees if cle_dabord else reversed(entrees))
    dumped, loaded = roundtrip(d)
    assert "$ref" not in dumped
    assert loaded == d
