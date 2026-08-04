# bytes_compression_diff_dtypes : la dérivée avant compression (opt-in par
# dtype), réactivée et fiabilisée le 04/08/2026 — l'encode était désactivé
# en dur, le decode oubliait le cumsum, et le repli non-compressé aurait
# écrit la dérivée sans étiquette.
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
    assert b"_diff" in dump
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


def test_floats_ignores():
    # les différences flottantes ne se retournent pas au bit près : ignorées
    rng = numpy.random.default_rng(2)
    donnees = rng.random(20_000)
    dump = serializejson.Encoder(
        return_bytes=True,
        bytes_compression_diff_dtypes=(numpy.float64,))(donnees)
    assert b"_diff" not in dump
    assert numpy.array_equal(serializejson.Decoder()(dump), donnees)


def test_dtype_non_liste_inchange():
    donnees = numpy.arange(30_000, dtype=numpy.int16)
    dump_sans = serializejson.Encoder(return_bytes=True)(donnees)
    dump_autre = serializejson.Encoder(
        return_bytes=True,
        bytes_compression_diff_dtypes=(numpy.int64,))(donnees)
    assert dump_sans == dump_autre        # dtype non listé : octets inchangés


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


def test_int8_sans_promotion():
    # numpy.diff(prepend=uint8) promouvait int8 en int16 (corruption
    # latente) : la dérivée C reste au dtype
    rng = numpy.random.default_rng(4)
    donnees = (numpy.cumsum(rng.integers(-1, 2, 50_000)) % 100).astype(numpy.int8)
    dump = serializejson.Encoder(
        return_bytes=True,
        bytes_compression_diff_dtypes=(numpy.int8,))(donnees)
    assert b"_diff" in dump
    recharge = serializejson.Decoder()(dump)
    assert recharge.dtype == numpy.int8
    assert numpy.array_equal(recharge, donnees)
