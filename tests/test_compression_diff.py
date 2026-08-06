# bytes_compression_diff_dtypes (opt-in par dtype), réactivé et fiabilisé
# le 04/08/2026. Voie blosc2 : FILTRE enregistré « shuffle puis delta
# d'octets » porté par la trame (aucune étiquette, bit-exact pour tout
# dtype, multithreadé par blosc2 des deux côtés). Voie python-blosc v1 :
# dérivée globale C + étiquette _diff, entiers seulement.
import numpy
import pytest

import serializejson
from serializejson.tools import sans_prefixe_longueur

# codec FIGÉ des tests qui comparent des CHAÎNES entre elles : le barreau
# par défaut du barème peut changer, ce qu'ils mesurent ne doit pas
ZSTD = ("blosc2_zstd", 1)


def _trame(blosc_to_base64):
    # dumps d'un BloscToBase64 : « "<n>:<base64>" » — retire les guillemets
    # et le préfixe de longueur, rend la trame binaire
    from base64 import b64decode

    import rapidjson

    return b64decode(sans_prefixe_longueur(rapidjson.dumps(blosc_to_base64)[1:-1]))


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
    # référence SANS delta (le défaut est désormais « smart ») :
    sans = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=None)(rampe)
    # la rampe se comprime bien mieux (0,55 : les deux dumps portent le
    # préfixe de longueur « <n>: » devant le base64, surcoût constant)
    assert len(dump) < len(sans) * 0.55
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
    # et le pipeline shuffle->delta bat la dérivée globale d'hier.
    # Codec FIGÉ des deux côtés : ce qu'on compare est le filtre, pas le
    # codec du barreau par défaut
    rng = numpy.random.default_rng(5)
    signal = (10000 * numpy.sin(numpy.linspace(0, 60, 200_000))
              + rng.integers(-5, 5, 200_000)).astype(numpy.int16)
    sans = serializejson.Encoder(
        return_bytes=True, bytes_compression=ZSTD,
        bytes_compression_diff_dtypes=None)(signal)
    avec = serializejson.Encoder(
        return_bytes=True, bytes_compression=ZSTD,
        bytes_compression_diff_dtypes=(numpy.int16,))(signal)
    assert b"_diff" not in avec
    assert len(avec) < len(sans) * 0.75
    assert numpy.array_equal(serializejson.Decoder()(avec), signal)


# littéraux FIGÉS, produits par python-blosc/l'ancien écrivain avant le
# retrait de l'écriture v1 (05/08/2026) : la LECTURE de ces formats doit
# survivre sans python-blosc (le fork libblosc2 relit les trames v1)
_DOC_V1_NUMPY_DIFF = '{"__class__":"numpyB64","__init__":["AgGRBCADAAAgAwAAfQAAABQAAABlAAAAKLUv/WAgAt0CACKICoMhIigYbSEkW1AiELxXquNSeiBIzMgs4IbA4HymKOEbSdH4CZr8j+GiXxIoEBpjtB4Q0O7//38HVAAsCh7LViDiw1IZTNChrBhKZMDu8RV+bsOYc7+64gQ=","int32","blosc_diff"]}'
_DOC_B2_NUMPY_DIFF = '{"__class__":"numpyB64","__init__":["BQGFBCADAAAgAwAAkAAAAAAAAAAAAQUAAAAAAAAAAAAkAAAAXAAAACi1L/0gyJ0CAFLICoMhEiM0RKYQ3jT6AENjlSTC7hQYn0XZADFhZLiWEnTQxHdy9JBcVE+wEy0QKBAc4/UQ2AdgJN9FhA9LPVigj7IYisiA3fEJv21D5tCv/joBAAAAAAAAAAAAAAAA","int32","blosc2_diff"]}'


def test_ancienne_etiquette_diff_toujours_lue():
    # les fichiers étiquetés _diff (dérivée GLOBALE : voie v1 python-blosc,
    # et trames blosc2 écrites un temps le 05/08 matin) se rechargent
    # toujours, alors que plus rien ne les écrit : étiquette reconnue,
    # somme cumulée appliquée — trames figées, sans python-blosc
    attendu = numpy.cumsum(
        numpy.random.default_rng(42).integers(0, 5, 200)).astype(numpy.int32)
    for document in (_DOC_V1_NUMPY_DIFF, _DOC_B2_NUMPY_DIFF):
        recharge = serializejson.loads(document)
        assert recharge.dtype == numpy.int32
        assert numpy.array_equal(recharge, attendu)


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


def test_smart_1d_lisse():
    # chaîne « smart » (sans sonde) : entiers -> dérivée par blocs (étiquette
    # _diff/_diffb) + zigzag + bitshuffle, nettement plus petit que sans delta
    rng = numpy.random.default_rng(10)
    signal = (10000 * numpy.sin(numpy.linspace(0, 60, 200_000))
              + rng.integers(-5, 5, 200_000)).astype(numpy.int16)
    sans = serializejson.Encoder(
        return_bytes=True, bytes_compression=ZSTD,
        bytes_compression_diff_dtypes=None)(signal)
    smart = serializejson.Encoder(
        return_bytes=True, bytes_compression=ZSTD,
        bytes_compression_diff_dtypes="smart")(signal)
    assert b"_diff" in smart
    assert len(smart) < len(sans) * 0.75
    assert numpy.array_equal(serializejson.Decoder()(smart), signal)


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


def test_ecriture_v1_refusee_avec_message():
    # l'écriture v1 python-blosc a été retirée : un nom v1 doit produire un
    # message qui l'explique (et pas un « compression unknown » générique)
    with pytest.raises(Exception, match="v1 python-blosc write support"):
        serializejson.Encoder(bytes_compression="blosc_zstd")


def test_smart_1d_entiers_larges():
    # timestamps int64 triés : la chaîne smart (dérivée arithmétique avec
    # retenues + zigzag + bitshuffle) doit rester dans la course du filtre
    # d'octets et écraser la version sans delta
    rng = numpy.random.default_rng(15)
    stamps = (numpy.cumsum(rng.integers(100, 200, 500_000))
              + 1_700_000_000_000_000).astype(numpy.int64)
    smart = serializejson.Encoder(
        return_bytes=True, bytes_compression=ZSTD,
        bytes_compression_diff_dtypes="smart")(stamps)
    filtre_seul = serializejson.Encoder(
        return_bytes=True, bytes_compression=ZSTD,
        bytes_compression_diff_dtypes=(numpy.int64,))(stamps)
    sans = serializejson.Encoder(
        return_bytes=True, bytes_compression=ZSTD,
        bytes_compression_diff_dtypes=None)(stamps)
    assert b"_diff" in smart         # la dérivée est appliquée
    assert len(smart) < len(filtre_seul) * 1.10
    assert len(smart) < len(sans) * 0.80
    assert numpy.array_equal(serializejson.Decoder()(smart), stamps)


def _signal_type_voix(n, dtype=numpy.int16):
    # alternance silence / salves toniques bruitées : profil de type voix,
    # exigeant pour les tailles de bord et l'adaptation locale
    rng = numpy.random.default_rng(20)
    out = numpy.zeros(n, dtype=numpy.int64)
    for debut in range(n // 8, n, n // 4):
        fin = min(debut + n // 8, n)
        t = numpy.arange(fin - debut)
        out[debut:fin] = (8000 * numpy.sin(t * 0.11)
                          + rng.integers(-40, 41, fin - debut))
    return out.astype(dtype)


@pytest.mark.parametrize("n", [3, 255, 256, 1023, 1024, 1025, 70_001])
def test_smart_bords_de_trame(n):
    # la chaîne smart doit rester exacte sur toutes les tailles : blocs
    # partiels, tableaux plus petits qu'un bloc, restes SIMD
    donnees = _signal_type_voix(max(n, 8))[:n]
    dump = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
    recharge = serializejson.Decoder()(dump)
    assert recharge.dtype == donnees.dtype
    assert numpy.array_equal(recharge, donnees)


def test_profil_voix_gagne_sans_presumer_du_candidat():
    # sur ce profil, la chaîne smart par défaut doit rester au niveau du
    # shuffle aveugle : on vérifie le gain et l'exactitude, pas le nom
    donnees = _signal_type_voix(200_000)
    auto = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
    sans = serializejson.Encoder(return_bytes=True)(donnees)
    # jamais pire qu'à l'aveugle (à l'erreur d'échantillonnage près)
    assert len(auto) <= len(sans) * 1.02
    assert numpy.array_equal(serializejson.Decoder()(auto), donnees)


def test_smart_int32_et_bruit_mele():
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


def test_smart_deterministe_et_tuple_inchange():
    donnees = _signal_type_voix(100_000)
    enc = lambda: serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
    assert enc() == enc()
    # le tuple explicite garde le comportement historique : filtre d'octets
    tup = serializejson.Encoder(
        return_bytes=True,
        bytes_compression_diff_dtypes=(numpy.int16,))(donnees)
    assert numpy.array_equal(serializejson.Decoder()(tup), donnees)


def test_smart_stereo():
    # (N, 2) : la dérivée par blocs enjambe les colonnes correctement
    # (colonnes portées par le quartet haut du meta du filtre 244)
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


def test_smart_canaux_disparates():
    # canal pair lisse + canal impair de grand bruit : profil extrême qui
    # avait débusqué un décalage C indéfini dans l'ex-codec rice — gardé
    # comme aller-retour exigeant pour la chaîne smart (1D et stéréo)
    rng = numpy.random.default_rng(24)
    a = rng.integers(-30000, 30000, 200_000).astype(numpy.int16)
    a[::2] = rng.integers(-5, 5, 100_000)
    for donnees in (a, a.reshape(-1, 2)):
        dump = serializejson.Encoder(
            return_bytes=True, bytes_compression_diff_dtypes=True)(donnees)
        assert numpy.array_equal(serializejson.Decoder()(dump), donnees)


def test_diff_par_blocs_exactitude():
    # dérivée par blocs indépendants (chaque bloc redémarre, première ligne
    # brute) : identité dérivée -> somme cumulée pour toutes les formes et
    # toutes les tailles de bloc, y compris dégénérées (1 ligne, plus grand
    # que le tableau)
    import rapidjson
    from serializejson.plugins.serializejson_numpy import _diff_axis0

    rng = numpy.random.default_rng(30)
    for shape, cols in [((100_003,), 1), ((50_000, 2), 2), ((300, 500), 500)]:
        a = numpy.ascontiguousarray(numpy.cumsum(
            rng.integers(-3, 4, int(numpy.prod(shape)))).astype(
                numpy.int16).reshape(shape))
        for block_rows in (0, 1, 7, 4096, 10**9):
            d = bytearray(_diff_axis0(a.data, a.itemsize, cols, block_rows))
            rapidjson._cumsum_axis0(d, a.itemsize, cols, block_rows)
            assert bytes(d) == a.tobytes(), (shape, block_rows)


def test_diff_par_blocs_etiquette():
    # l'étiquette est TOUJOURS _diffb<lignes> (l'étiquette _diff globale
    # n'est plus écrite depuis le 05/08/2026 — un tableau plus petit qu'un
    # bloc est UN bloc) ; la lecture se parallélise par bloc
    rng = numpy.random.default_rng(31)
    gros = numpy.cumsum(rng.integers(-3, 4, 2_000_000)).astype(numpy.int64)
    dump = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(gros)
    assert b"_diffb" in dump
    assert numpy.array_equal(serializejson.Decoder()(dump), gros)
    petit = numpy.cumsum(rng.integers(-3, 4, 20_000)).astype(numpy.int64)
    dump2 = serializejson.Encoder(
        return_bytes=True, bytes_compression_diff_dtypes=True)(petit)
    assert b"_diffb20000" in dump2   # un seul bloc : toutes les lignes
    assert numpy.array_equal(serializejson.Decoder()(dump2), petit)


def test_prefiltre_derivee_source_intacte():
    # fusion écriture : la dérivée par blocs calculée par le PRÉFILTRE blosc2
    # doit produire les mêmes octets que la pré-passe _diff_axis0, sans
    # toucher au tableau source — régression du bug de rotation de tampons du
    # fork (avec préfiltre + deux filtres, le pipeline écrivait DANS le
    # tampon source de l'appelant)
    import rapidjson
    from serializejson.plugins.serializejson_numpy import _diff_axis0

    rng = numpy.random.default_rng(32)
    for dt in (numpy.int16, numpy.int32):
        a = numpy.ascontiguousarray(
            numpy.cumsum(rng.integers(-3, 4, 3_000_000)).astype(dt))
        copie = a.copy()
        br = (1 << 20) // a.itemsize
        bs = br * a.itemsize
        f = _trame(rapidjson.BloscToBase64(
            a.data, a.itemsize, 1, 3, "zstd", 1, bs, 1))
        assert numpy.array_equal(a, copie)  # source jamais modifiée
        fp = _trame(rapidjson.BloscToBase64(
            _diff_axis0(a.data, a.itemsize, 1, br), a.itemsize, 1, 3,
            "zstd", 1, bs))
        # seule différence légitime : l'octet meta 28 du filtre 244 (la voie
        # préfiltre y code le cumsum interne, la pré-passe non)
        assert len(f) == len(fp)
        assert f[:28] == fp[:28] and f[29:] == fp[29:]
        raw = rapidjson.blosc_decompress_chunks(f, 1, 0, a.itemsize, 1, br)
        assert bytes(raw) == a.tobytes()


def test_zigzag_bitshuffle_toutes_largeurs():
    # filtre 244 (zigzag) chaîné au bitshuffle natif (shuffle=3) : replie
    # ±epsilon pour que les plans de bits restent propres — aller-retour
    # exact pour toutes les largeurs d'entiers, tailles impaires comprises
    import rapidjson

    rng = numpy.random.default_rng(28)
    for dt in (numpy.int8, numpy.int16, numpy.int32, numpy.int64,
               numpy.uint8, numpy.uint64):
        a = numpy.ascontiguousarray(
            numpy.cumsum(rng.integers(-3, 4, 50_003)).astype(dt))
        frame = _trame(rapidjson.BloscToBase64(
            a.data, a.itemsize, 1, 3, "zstd"))
        assert bytes(rapidjson.blosc_decompress_chunks(frame, 1)) == a.tobytes()


def test_zigzag_bitshuffle_multithread_deterministe():
    # mêmes octets quel que soit le nombre de threads (fork déterministe :
    # le paramètre nthreads est accepté et ignoré, le multithread interne
    # suit le réglage global), et rechargement exact
    import rapidjson

    rng = numpy.random.default_rng(29)
    a = numpy.ascontiguousarray(
        numpy.cumsum(rng.integers(-3, 4, 3_000_000)).astype(numpy.int32))
    frames = []
    for nthreads in (8, 2):
        frames.append(_trame(rapidjson.BloscToBase64(
            a.data, a.itemsize, 1, 3, "zstd", nthreads)))
    assert frames[0] == frames[1]
    assert bytes(rapidjson.blosc_decompress_chunks(frames[0], 1)) == a.tobytes()


