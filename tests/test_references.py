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


# --- grosses données : verrouille le chemin bytes -> blosc -> b64 --------------


def test_gros_bytes_compresses():
    data = bytes(range(256)) * 5000  # 1.28 Mo compressibles
    dumped, loaded = roundtrip(data)
    assert len(dumped) < len(data)  # la compression a bien eu lieu
    assert loaded == data


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
