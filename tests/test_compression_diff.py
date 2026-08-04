# bytes_compression_diff_dtypes (opt-in par dtype), réactivé et fiabilisé
# le 04/08/2026. Voie blosc2 : FILTRE enregistré « shuffle puis delta
# d'octets » porté par la trame (aucune étiquette, bit-exact pour tout
# dtype, multithreadé par blosc2 des deux côtés). Voie python-blosc v1 :
# dérivée globale C + étiquette _diff, entiers seulement.
import numpy
import pytest

import serializejson


@pytest.mark.parametrize("dtype", [numpy.int16, numpy.int32, numpy.int64,
                                   numpy.uint8])
def test_aller_retour_exact(dtype):
    rng = numpy.random.default_rng(1)
    donnees = numpy.cumsum(rng.integers(0, 5, 30_000)).astype(dtype)
    encoder = serializejson.Encoder(return_bytes=True,
                                    bytes_compression_diff_dtypes=(dtype,))
    dump = encoder(donnees)
    # voie blosc2 : le filtre est porté par la trame, plus d'étiquette
    assert b"_diff" not in dump
    recharge = serializejson.Decoder()(dump)
    assert recharge.dtype == donnees.dtype
    assert numpy.array_equal(recharge, donnees)


def test_2d_axe_0():
    rampe = (numpy.arange(200)[:, None] * 100
             + numpy.arange(100)[None, :]).astype(numpy.int32)
    encoder = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=(numpy.int32,))
    dump = encoder(rampe)
    sans = serializejson.Encoder(return_bytes=True)(rampe)
    assert len(dump) < len(sans) / 2      # la rampe se comprime bien mieux
    recharge = serializejson.Decoder()(dump)
    assert recharge.shape == rampe.shape
    assert numpy.array_equal(recharge, rampe)


def test_floats_bit_exacts_via_filtre():
    # sur la voie blosc2, la dérivée est un FILTRE d'octets (après shuffle) :
    # réversible au bit près pour TOUT contenu, flottants compris — et sans
    # étiquette, la trame se décrit elle-même
    rng = numpy.random.default_rng(2)
    donnees = numpy.sin(numpy.linspace(0, 60, 20_000)) + rng.random(20_000) * 1e-3
    dump = serializejson.Encoder(
        return_bytes=True,
        bytes_compression_diff_dtypes=(numpy.float64,))(donnees)
    assert b"_diff" not in dump
    recharge = serializejson.Decoder()(dump)
    assert numpy.array_equal(recharge.view(numpy.uint8),
                             donnees.view(numpy.uint8))


def test_filtre_sans_etiquette_et_plus_compact():
    # la voie blosc2 n'étiquette plus : le filtre est porté par la trame,
    # et le pipeline shuffle->delta bat la dérivée globale d'hier
    rng = numpy.random.default_rng(5)
    signal = (10000 * numpy.sin(numpy.linspace(0, 60, 200_000))
              + rng.integers(-5, 5, 200_000)).astype(numpy.int16)
    sans = serializejson.Encoder(return_bytes=True)(signal)
    avec = serializejson.Encoder(
        return_bytes=True,
        bytes_compression_diff_dtypes=(numpy.int16,))(signal)
    assert b"_diff" not in avec
    assert len(avec) < len(sans) * 0.75
    assert numpy.array_equal(serializejson.Decoder()(avec), signal)


def test_ancienne_etiquette_diff_toujours_lue():
    # les fichiers étiquetés _diff (dérivée globale de la voie v1, et ceux
    # écrits ce matin par la voie blosc2 d'alors) se rechargent toujours :
    # étiquette retirée, somme cumulée appliquée
    donnees = numpy.cumsum(
        numpy.random.default_rng(6).integers(0, 5, 30_000)).astype(numpy.int32)
    dump = serializejson.Encoder(
        return_bytes=True,
        bytes_compression="blosc_zstd",
        bytes_compression_diff_dtypes=(numpy.int32,))(donnees)
    assert b"_diff" in dump
    recharge = serializejson.Decoder()(dump)
    assert recharge.dtype == numpy.int32
    assert numpy.array_equal(recharge, donnees)


def test_diff_cumsum_c_identiques_a_numpy():
    # les portages C (diff une-allocation, cumsum SIMD) rendent exactement
    # les octets de numpy à même dtype, restes SIMD et enroulements compris
    import rapidjson as rj
    rng = numpy.random.default_rng(9)
    for dtype in (numpy.int8, numpy.uint16, numpy.int32, numpy.uint64):
        itemsize = numpy.dtype(dtype).itemsize
        for forme in [(1,), (17,), (1000,), (50, 40), (13, 7, 5)]:
            n = int(numpy.prod(forme))
            a = numpy.frombuffer(rng.bytes(n * itemsize),
                                 dtype=dtype).reshape(forme).copy()
            cols = a.size // a.shape[0] if a.ndim > 1 else 1
            c = a.copy()
            rj._cumsum_axis0(c.data, itemsize, cols)
            assert numpy.array_equal(
                c, numpy.cumsum(a, axis=0, dtype=dtype))
            d = numpy.frombuffer(rj._diff_axis0(a.data, itemsize, cols),
                                 dtype=dtype).reshape(forme).copy()
            rj._cumsum_axis0(d.data, itemsize, cols)
            assert numpy.array_equal(d, a)


def test_int8_voie_v1_sans_promotion():
    # numpy.diff(prepend=uint8) promouvait int8 en int16 (corruption
    # latente) : la dérivée C de la voie v1 reste au dtype
    rng = numpy.random.default_rng(4)
    donnees = (numpy.cumsum(rng.integers(-1, 2, 50_000)) % 100).astype(numpy.int8)
    dump = serializejson.Encoder(
        return_bytes=True,
        bytes_compression="blosc_zstd",
        bytes_compression_diff_dtypes=(numpy.int8,))(donnees)
    assert b"_diff" in dump
    recharge = serializejson.Decoder()(dump)
    assert recharge.dtype == numpy.int8
    assert numpy.array_equal(recharge, donnees)
