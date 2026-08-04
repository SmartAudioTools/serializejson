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

def test_auto_1d_lisse_choisit_le_filtre():
    # bytes_compression_diff_dtypes=True : décision par échantillon.
    # Signal 1D lisse -> le filtre delta doit gagner (trame, pas d'étiquette)
    rng = numpy.random.default_rng(10)
    signal = (10000 * numpy.sin(numpy.linspace(0, 60, 200_000))
              + rng.integers(-5, 5, 200_000)).astype(numpy.int16)
    sans = serializejson.Encoder(return_bytes=True)(signal)
    auto = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(signal)
    assert b"_diff" not in auto
    assert len(auto) < len(sans) * 0.75
    assert numpy.array_equal(serializejson.Decoder()(auto), signal)


def test_auto_2d_choisit_l_axe_0():
    # données lisses le long de l'AXE 0 seulement (chaque colonne est une
    # rampe, les lignes sont du bruit) : la dérivée d'axe 0 doit gagner
    # contre le filtre (qui suit l'ordre mémoire, donc l'axe 1)
    rng = numpy.random.default_rng(11)
    base = rng.integers(0, 32000, (1, 64)).astype(numpy.int32)
    donnees = base + numpy.arange(20_000, dtype=numpy.int32)[:, None]
    auto = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
    filtre_seul = serializejson.Encoder(
        return_bytes=True,
        bytes_compression_diff_dtypes=(numpy.int32,))(donnees)
    assert b"_diff" in auto            # l'axe 0 a été retenu
    assert len(auto) < len(filtre_seul) / 2
    recharge = serializejson.Decoder()(auto)
    assert recharge.shape == donnees.shape
    assert numpy.array_equal(recharge, donnees)


def test_auto_floats_et_bruit():
    # flottants : le filtre reste candidat (bit-exact), la dérivée d'axe 0
    # arithmétique non ; et sur du bruit pur, aucun delta ne doit être retenu
    rng = numpy.random.default_rng(12)
    lisse = numpy.sin(numpy.linspace(0, 60, 100_000))
    dump = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(lisse)
    assert b"_diff" not in dump
    recharge = serializejson.Decoder()(dump)
    assert numpy.array_equal(recharge.view(numpy.uint8), lisse.view(numpy.uint8))
    bruit = numpy.frombuffer(rng.bytes(200_000), dtype=numpy.int16).copy()
    dump_bruit = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(bruit)
    assert b"_diff" not in dump_bruit
    assert numpy.array_equal(serializejson.Decoder()(dump_bruit), bruit)


def test_auto_deterministe():
    rng = numpy.random.default_rng(13)
    donnees = numpy.cumsum(rng.integers(-3, 4, (5000, 16)),
                           axis=0).astype(numpy.int16)
    encode = lambda: serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
    assert encode() == encode()


def test_auto_voie_v1():
    # voie python-blosc (pas de filtre) : l'essai porte sur la seule dérivée
    # d'axe 0 — retenue sur du lisse, écartée sur du bruit
    rng = numpy.random.default_rng(14)
    lisse = numpy.cumsum(rng.integers(0, 5, 50_000)).astype(numpy.int32)
    dump = serializejson.Encoder(
        return_bytes=True, bytes_compression="blosc_zstd",
        bytes_compression_diff_dtypes=True)(lisse)
    assert b"_diff" in dump
    assert numpy.array_equal(serializejson.Decoder()(dump), lisse)
    bruit = numpy.frombuffer(rng.bytes(100_000), dtype=numpy.int32).copy()
    dump_bruit = serializejson.Encoder(
        return_bytes=True, bytes_compression="blosc_zstd",
        bytes_compression_diff_dtypes=True)(bruit)
    assert b"_diff" not in dump_bruit
    assert numpy.array_equal(serializejson.Decoder()(dump_bruit), bruit)


def test_auto_1d_entiers_larges_choisit_l_arithmetique():
    # en 1D la dérivée arithmétique (retenues, avant shuffle) est candidate
    # aussi : sur des entiers larges elle bat le filtre d'octets — mesuré
    # -16 % sur des timestamps int64 triés
    rng = numpy.random.default_rng(15)
    stamps = (numpy.cumsum(rng.integers(100, 200, 500_000))
              + 1_700_000_000_000_000).astype(numpy.int64)
    auto = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(stamps)
    filtre_seul = serializejson.Encoder(
        return_bytes=True,
        bytes_compression_diff_dtypes=(numpy.int64,))(stamps)
    assert b"_diff" in auto          # l'arithmétique a été retenue
    assert len(auto) < len(filtre_seul)
    assert numpy.array_equal(serializejson.Decoder()(auto), stamps)


def _signal_type_voix(n, dtype=numpy.int16):
    # alternance silence / salves toniques bruitées : le profil qui a piégé
    # l'échantillon central (silence) et motivé stratification + partition
    # nulle du codec Rice
    rng = numpy.random.default_rng(20)
    out = numpy.zeros(n, dtype=numpy.int64)
    for debut in range(n // 8, n, n // 4):
        fin = min(debut + n // 8, n)
        t = numpy.arange(fin - debut)
        out[debut:fin] = (8000 * numpy.sin(t * 0.11)
                          + rng.integers(-40, 41, fin - debut))
    return out.astype(dtype)


@pytest.mark.parametrize("n", [3, 255, 256, 1023, 1024, 1025, 70_001])
def test_rice_bords_de_trame(n):
    # le codec Rice (blosc2 enregistré, id 243) doit rester exact sur toutes
    # les tailles : partitions et trames partielles comprises
    donnees = _signal_type_voix(max(n, 8))[:n]
    dump = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
    recharge = serializejson.Decoder()(dump)
    assert recharge.dtype == donnees.dtype
    assert numpy.array_equal(recharge, donnees)


def test_profil_voix_gagne_sans_presumer_du_candidat():
    # sur ce profil, l'essai choisit le meilleur pipeline (dérivée+filtre ou
    # rice selon les données) : on vérifie le gain et l'exactitude, pas le nom
    donnees = _signal_type_voix(200_000)
    auto = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
    sans = serializejson.Encoder(return_bytes=True)(donnees)
    # jamais pire qu'à l'aveugle (à l'erreur d'échantillonnage près)
    assert len(auto) <= len(sans) * 1.02
    assert numpy.array_equal(serializejson.Decoder()(auto), donnees)


def test_rice_choisi_sur_amplitude_modulee():
    # bruit dont l'amplitude change toutes les ~700 valeurs : le cas d'école
    # de l'adaptation LOCALE du calibre Rice, hors de portée de zstd et des
    # deltas — rice est porté par la trame, donc aucune étiquette
    rng = numpy.random.default_rng(22)
    sections = [rng.normal(0, s, 700) for s in ([2, 300, 8, 3000, 30, 1000] * 40)]
    donnees = numpy.concatenate(sections).astype(numpy.int16)
    auto = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
    sans = serializejson.Encoder(return_bytes=True)(donnees)
    assert b"_diff" not in auto
    assert len(auto) < len(sans) * 0.95
    assert numpy.array_equal(serializejson.Decoder()(auto), donnees)


def test_rice_int32_et_bruit_mele():
    # int32 24 bits : silence, signal lisse et bruit fort (échappement)
    rng = numpy.random.default_rng(21)
    morceaux = [numpy.zeros(3000, numpy.int32),
                (2**20 * numpy.sin(numpy.linspace(0, 30, 50_000))).astype(numpy.int32),
                rng.integers(-2**22, 2**22, 4000).astype(numpy.int32)]
    donnees = numpy.concatenate(morceaux)
    dump = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
    recharge = serializejson.Decoder()(dump)
    assert recharge.dtype == numpy.int32
    assert numpy.array_equal(recharge, donnees)


def test_rice_deterministe_et_tuple_inchange():
    donnees = _signal_type_voix(100_000)
    enc = lambda: serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
    assert enc() == enc()
    # le tuple explicite ne passe jamais par rice : filtre comme avant
    tup = serializejson.Encoder(
        return_bytes=True,
        bytes_compression_diff_dtypes=(numpy.int16,))(donnees)
    assert numpy.array_equal(serializejson.Decoder()(tup), donnees)


def test_rice_stereo_par_canal():
    # (N, 2) : rice prédit chaque canal depuis lui-même (pas de c en mémoire,
    # canaux portés par le quartet haut du meta) — sans cela la prédiction
    # enjambait les canaux et rice perdait en stéréo
    rng = numpy.random.default_rng(23)
    t = numpy.linspace(0, 40, 60_000)
    stereo = numpy.stack([
        (9000 * numpy.sin(t) + rng.integers(-30, 31, len(t))),
        (7000 * numpy.cos(t * 1.3) + rng.integers(-30, 31, len(t)))],
        1).astype(numpy.int16)
    dump = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(stereo)
    recharge = serializejson.Decoder()(dump)
    assert recharge.shape == stereo.shape
    assert numpy.array_equal(recharge, stereo)


def test_rice_unaire_64_bits():
    # régression : un q unaire finissant PILE en haut du tampon de 64 bits
    # déclenchait un décalage C indéfini (acc >>= 64 : acc inchangé sur x86,
    # bit fantôme relu plus loin) — canal pair lisse + canal impair fou
    # fabrique ces q extrêmes en rafale
    rng = numpy.random.default_rng(24)
    a = rng.integers(-30000, 30000, 200_000).astype(numpy.int16)
    a[::2] = rng.integers(-5, 5, 100_000)
    for donnees in (a, a.reshape(-1, 2)):
        dump = serializejson.Encoder(
            return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
        assert numpy.array_equal(serializejson.Decoder()(dump), donnees)
