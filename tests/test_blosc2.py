"""Compressions blosc2 (opt-in) : faites en C par le rapidjson du dépôt.

Trames au format blosc2 (étiquette "b64_blosc2" / "blosc2"), relisibles par le
décodage de serializejson via python-blosc2 mais pas par python-blosc v1 —
les défauts restent sur blosc v1, l'activation est explicite :
bytes_compression=("blosc2_zstd", 9) etc.
"""

import pytest
import serializejson
from serializejson.tools import use_blosc2_cpp

try:
    import numpy

    use_numpy = True
except ModuleNotFoundError:
    use_numpy = False

pytestmark = pytest.mark.skipif(
    not use_blosc2_cpp, reason="roue python-blosc2 absente (Python 3.10 ?)"
)


def roundtrip(obj, **encoder_args):
    dumped = serializejson.dumps(obj, indent=None, **encoder_args)
    return dumped, serializejson.loads(dumped)


def test_bytes_blosc2():
    data = bytes(range(256)) * 5000
    dumped, loaded = roundtrip(data, bytes_compression=("blosc2_zstd", 5))
    assert '"b64_blosc2"' in dumped
    assert len(dumped) < len(data)
    assert loaded == data


def test_bytearray_blosc2():
    data = bytearray(range(256)) * 5000
    dumped, loaded = roundtrip(data, bytes_compression=("blosc2", 9))  # blosclz
    assert '"b64_blosc2"' in dumped
    assert type(loaded) is bytearray
    assert loaded == data


def test_bytes_blosc2_incompressibles():
    import random

    data = bytes(random.Random(0).getrandbits(8) for _ in range(100_000))
    dumped, loaded = roundtrip(data, bytes_compression=("blosc2_zstd", 5))
    # trop peu compressible : retombe sur le base64 brut, et se recharge
    assert loaded == data


@pytest.mark.skipif(not use_numpy, reason="numpy absent")
def test_numpy_blosc2():
    array = numpy.arange(200_000, dtype=numpy.float64)
    dumped, loaded = roundtrip(array, bytes_compression=("blosc2_zstd", 5))
    assert '"blosc2"' in dumped
    assert loaded.dtype == array.dtype
    assert numpy.array_equal(loaded, array)


def test_defaut_blosc2_quand_disponible():
    # depuis la bascule des défauts : blosc2 dès que la roue est disponible
    data = bytes(range(256)) * 5000
    dumped = serializejson.dumps(data, indent=None)
    assert '"b64_blosc2"' in dumped
    assert serializejson.loads(dumped) == data


def test_fork_deterministe_multithread_interne():
    # avec le fork libblosc2_serializejson (patch « commit des blocs dans
    # l'ordre »), le multi-thread INTERNE de la bibliothèque produit des
    # octets identiques au mono-thread : trame unique standard, pas besoin
    # du format par morceaux
    from serializejson.tools import use_blosc2_fork

    if not use_blosc2_fork:
        pytest.skip("fork libblosc2_serializejson absent")
    import numpy

    array = numpy.arange(2_000_000, dtype=numpy.float64)
    sorties = set()
    for nthreads in (1, 4, 8):
        sorties.add(
            serializejson.dumps(
                array,
                indent=None,
                bytes_compression=("blosc2_zstd", 5),
                bytes_compression_threads=nthreads,
            )
        )
    assert len(sorties) == 1  # mêmes octets à 1, 4 et 8 threads internes
    dumped = sorties.pop()
    assert '"blosc2"' in dumped and '"blosc2p"' not in dumped  # trame unique
    assert numpy.array_equal(serializejson.loads(dumped), array)


def test_blosc2_parallele_deterministe():
    # les octets produits ne dépendent pas du nombre de threads (fork
    # déterministe : nthreads accepté et ignoré, multithread interne stable)
    import rapidjson

    data = bytes(range(256)) * 40000  # 10 Mo
    sorties = {
        rapidjson.dumps(rapidjson.BloscToBase64(data, 1, 5, 0, "zstd", nthreads))
        for nthreads in (2, 4, 8)
    }
    assert len(sorties) == 1
    dumped = serializejson.dumps(
        data,
        indent=None,
        bytes_compression=("blosc2_zstd", 5),
        bytes_compression_threads=4,
    )
    # trame unique : le format par morceaux b64_blosc2p n'est plus écrit
    assert '"b64_blosc2"' in dumped
    assert serializejson.loads(dumped) == data


def test_anciens_fichiers_blosc_v1_toujours_lisibles():
    # un fichier écrit avec la compression v1 (python-blosc) doit rester
    # lisible alors que plus rien ne l'écrit : trame FIGÉE, produite par
    # python-blosc avant le retrait (05/08/2026), relue par le fork libblosc2
    document = (
        '{"__class__":"bytes","__init__":["AgGRAQAIAAAACAAALAEAABQAAAAUAQAAKLUv'
        "/WAAB1UIAAQQAAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKi"
        "ssLS4vMDEyMzQ1Njc4OTo7PD0+P0BBQkNERUZHSElKS0xNTk9QUVJTVFVWV1hZWltcXV5f"
        "YGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6e3x9fn+AgYKDhIWGh4iJiouMjY6PkJGSk5"
        "SVlpeYmZqbnJ2en6ChoqOkpaanqKmqq6ytrq+wsbKztLW2t7i5uru8vb6/wMHCw8TFxsfI"
        "ycrLzM3Oz9DR0tPU1dbX2Nna29zd3t/g4eLj5OXm5+jp6uvs7e7v8PHy8/T19vf4+fr7/P"
        '3+/wEAAP0O/GsK","b64_blosc"]}'
    )
    assert serializejson.loads(document) == bytes(range(256)) * 8
