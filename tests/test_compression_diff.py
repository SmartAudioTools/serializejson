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
