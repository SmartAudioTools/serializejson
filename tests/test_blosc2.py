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


# les bytes et bytearray NUS ne sont plus compressés par défaut (blocs opaques,
# le plus souvent déjà compressés) : les tests qui portent sur leur trame
# compressée redemandent donc le seuil explicitement
SEUIL_BYTES = {"bytes_size_compression_threshold": 512}


def test_bytes_blosc2():
    data = bytes(range(256)) * 5000
    dumped, loaded = roundtrip(data, bytes_compression=("blosc2_zstd", 5),
                               **SEUIL_BYTES)
    assert '"b64_blosc2"' in dumped
    assert len(dumped) < len(data)
    assert loaded == data


def test_bytearray_blosc2():
    data = bytearray(range(256)) * 5000
    dumped, loaded = roundtrip(data, bytes_compression=("blosc2", 9),  # blosclz
                               **SEUIL_BYTES)
    assert '"b64_blosc2"' in dumped
    assert type(loaded) is bytearray
    assert loaded == data


def test_bytes_pas_compresses_par_defaut():
    # le DÉFAUT depuis le 06/08/2026 : un bloc d'octets nu part en base64 sans
    # passer par la compression, même très compressible et très au-dessus des
    # 512 octets — c'est le seuil des tableaux numpy, pas celui des bytes
    data = bytes(range(256)) * 5000
    dumped, loaded = roundtrip(data)
    assert '"b64"' in dumped and "blosc2" not in dumped
    assert loaded == data


def test_niveau_0_aucune_compression():
    # niveau 0 = aucune compression, sur TOUTES les charges : mêmes octets
    # qu'avec bytes_compression=None, en-tête blosc2 compris
    data = bytes(range(256)) * 5000
    sans, _ = roundtrip(data, bytes_compression=None, **SEUIL_BYTES)
    niveau_0, loaded = roundtrip(data, bytes_compression=("blosc2_zstd", 0),
                                 **SEUIL_BYTES)
    assert niveau_0 == sans
    assert loaded == data
    if use_numpy:
        array = numpy.arange(200_000, dtype=numpy.float64)
        assert (serializejson.dumps(array, indent=None,
                                    bytes_compression=("blosc2_zstd", 0))
                == serializejson.dumps(array, indent=None,
                                       bytes_compression=None))


def test_bytes_blosc2_incompressibles():
    import random

    data = bytes(random.Random(0).getrandbits(8) for _ in range(100_000))
    dumped, loaded = roundtrip(data, bytes_compression=("blosc2_zstd", 5),
                               **SEUIL_BYTES)
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
    # depuis la bascule des défauts : blosc2 dès que la roue est disponible —
    # sur un bloc d'octets NU il faut redemander le seuil, les tableaux numpy
    # sont eux compressés par défaut
    data = bytes(range(256)) * 5000
    dumped = serializejson.dumps(data, indent=None, **SEUIL_BYTES)
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
        **SEUIL_BYTES,
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


# --- barème « smart » : le niveau choisit codec ET chaîne (06/08/2026) --------


def test_bareme_smart_barreau_6_est_l_ancien_defaut():
    # le barreau 6 est exactement l'ancien défaut (blosc2_zstd 1, chaîne
    # smart) : les octets qu'il produit ne doivent PAS avoir bougé
    data = bytes(range(256)) * 5000
    ancien, _ = roundtrip(data, bytes_compression=("blosc2_zstd", 1),
                          **SEUIL_BYTES)
    assert roundtrip(data, bytes_compression=("smart", 6),
                     **SEUIL_BYTES)[0] == ancien


def test_bareme_smart_defaut_est_le_barreau_1():
    # « smart » sans niveau, et le défaut nu, valent le barreau 1
    data = bytes(range(256)) * 5000
    barreau_1, _ = roundtrip(data, bytes_compression=("smart", 1),
                             **SEUIL_BYTES)
    assert roundtrip(data, bytes_compression="smart",
                     **SEUIL_BYTES)[0] == barreau_1
    assert roundtrip(data, **SEUIL_BYTES)[0] == barreau_1  # défaut nu


@pytest.mark.parametrize("niveau", range(7))
def test_bareme_smart_tous_les_barreaux(niveau):
    data = bytes(range(256)) * 5000
    dumped, loaded = roundtrip(data, bytes_compression=("smart", niveau),
                               **SEUIL_BYTES)
    assert loaded == data
    if use_numpy:
        array = numpy.arange(200_000, dtype=numpy.int32).reshape(500, 400)
        relu = serializejson.loads(serializejson.dumps(
            array, indent=None, bytes_compression=("smart", niveau)))
        assert numpy.array_equal(relu, array)


def test_bareme_smart_niveau_0_est_le_base64_seul():
    data = bytes(range(256)) * 5000
    sans, _ = roundtrip(data, bytes_compression=None, **SEUIL_BYTES)
    assert roundtrip(data, bytes_compression=("smart", 0),
                     **SEUIL_BYTES)[0] == sans


def test_bareme_smart_niveau_inconnu():
    with pytest.raises(Exception, match="smart levels go from 0"):
        serializejson.dumps(b"x", bytes_compression=("smart", 12))


@pytest.mark.parametrize("niveau", (7, 8, 9))
def test_bareme_smart_niveaux_reserves(niveau):
    # 7, 8 et 9 sont LIBRES, gardés pour des méthodes qui passeront sous
    # x0,7 : ils doivent être REFUSÉS, avec un message qui le dit, plutôt
    # que rabattus en silence sur le barreau 6
    with pytest.raises(Exception, match="reserved for future methods"):
        serializejson.dumps(b"x", bytes_compression=("smart", niveau))


@pytest.mark.skipif(not use_numpy, reason="numpy absent")
def test_bareme_smart_chaine_explicite_prioritaire():
    # une chaîne demandée explicitement l'emporte sur celle du barreau :
    # le niveau 1 impose « zigzag », mais pas si l'appelant a choisi
    array = numpy.arange(200_000, dtype=numpy.int32).reshape(500, 400)
    barreau = serializejson.dumps(array, indent=None,
                                  bytes_compression=("smart", 1))
    force = serializejson.dumps(array, indent=None,
                                bytes_compression=("smart", 1),
                                bytes_compression_diff_dtypes=None)
    assert barreau != force
    assert numpy.array_equal(serializejson.loads(force), array)


@pytest.mark.skipif(not use_numpy, reason="numpy absent")
def test_chaine_zigzag_est_smart_sans_la_derivee():
    # « zigzag » = la chaîne smart privée de sa dérivée : octets distincts
    # de smart comme du shuffle nu, et relus sans étiquette (la trame
    # blosc2 est auto-descriptive, aucun suffixe _diffb n'est écrit)
    array = numpy.arange(200_000, dtype=numpy.int32).reshape(500, 400)
    dumps = {
        chaine: serializejson.dumps(
            array, indent=None, bytes_compression=("blosc2_lz4", 1),
            bytes_compression_diff_dtypes=chaine)
        for chaine in ("zigzag", "smart", None)}
    assert len(set(dumps.values())) == 3
    assert "_diffb" not in dumps["zigzag"]
    assert numpy.array_equal(serializejson.loads(dumps["zigzag"]), array)


@pytest.mark.skipif(not use_numpy, reason="numpy absent")
def test_chaine_delta_pour_tous_les_dtypes():
    # « delta » = le filtre delta d'octets sans nommer de dtype : mêmes
    # octets que l'ancienne forme opt-in qui les nommait tous
    array = numpy.arange(200_000, dtype=numpy.int32).reshape(500, 400)
    par_nom = serializejson.dumps(array, indent=None,
                                  bytes_compression=("blosc2_lz4", 5),
                                  bytes_compression_diff_dtypes=(array.dtype,))
    par_mot = serializejson.dumps(array, indent=None,
                                  bytes_compression=("blosc2_lz4", 5),
                                  bytes_compression_diff_dtypes="delta")
    assert par_nom == par_mot
    assert numpy.array_equal(serializejson.loads(par_mot), array)
