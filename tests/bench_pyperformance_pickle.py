# Réplique des benchmarks pickle de pyperformance (bm_pickle/run_benchmark.py)
# comparés à serializejson — mêmes charges, mêmes boucles (60/10/5 opérations
# par itération), protocole pickle le plus élevé, min et moyenne rapportés.
import datetime
import pickle
import random
import sys
import time

sys.path.insert(0, ".")
if "rapidjson" not in sys.modules:
    import rapidjson.rapidjson as rj

    sys.modules["rapidjson"] = rj
import serializejson

DICT = {
    'ads_flags': 0, 'age': 18, 'birthday': datetime.date(1980, 5, 7),
    'bulletin_count': 0, 'comment_count': 0, 'country': 'BR',
    'encrypted_id': 'G9urXXAJwjE', 'favorite_count': 9, 'first_name': '',
    'flags': 412317970704, 'friend_count': 0, 'gender': 'm',
    'gender_for_display': 'Male', 'id': 302935349,
    'is_custom_profile_icon': 0, 'last_name': '', 'locale_preference': 'pt_BR',
    'member': 0, 'tags': ['a', 'b', 'c', 'd', 'e', 'f', 'g'],
    'profile_foo_id': 827119638,
    'secure_encrypted_id': 'Z_xxx2dYx3t4YAdnmfgyKw', 'session_number': 2,
    'signup_id': '201-19225-223', 'status': 'A', 'theme': 1,
    'time_created': 1225237014, 'time_updated': 1233134493,
    'unread_message_count': 0, 'user_group': '0', 'username': 'collinwinter',
    'play_count': 9, 'view_count': 7, 'zip': ''}

TUPLE = (
    [265867233, 265868503, 265252341, 265243910, 265879514,
     266219766, 266021701, 265843726, 265592821, 265246784,
     265853180, 45526486, 265463699, 265848143, 265863062,
     265392591, 265877490, 265823665, 265828884, 265753032], 60)


def mutate_dict(orig_dict, random_source):
    new_dict = dict(orig_dict)
    for key, value in new_dict.items():
        rand_val = random_source.random() * sys.maxsize
        if isinstance(key, (int, bytes, str)):
            new_dict[key] = type(key)(rand_val)
    return new_dict


random_source = random.Random(5)
DICT_GROUP = [mutate_dict(DICT, random_source) for _ in range(3)]
LIST = [[list(range(10)), list(range(10))] for _ in range(10)]
MICRO_DICT = dict((key, dict.fromkeys(range(10))) for key in range(100))

PROTO = pickle.HIGHEST_PROTOCOL
E = serializejson.Encoder(return_bytes=True)
D = serializejson.Decoder()

# fidélité : aller-retour serializejson strictement égal
for obj in (DICT, TUPLE, DICT_GROUP, LIST, MICRO_DICT):
    back = D(E(obj))
    assert back == obj, type(obj)
assert isinstance(D(E(TUPLE)), tuple)
assert all(isinstance(k, int) for k in D(E(MICRO_DICT)))

PK_DICT = pickle.dumps(DICT, PROTO)
PK_TUPLE = pickle.dumps(TUPLE, PROTO)
PK_GROUP = pickle.dumps(DICT_GROUP, PROTO)
PK_LIST = pickle.dumps(LIST, PROTO)
PK_MICRO = pickle.dumps(MICRO_DICT, PROTO)
SJ_DICT = E(DICT)
SJ_TUPLE = E(TUPLE)
SJ_GROUP = E(DICT_GROUP)
SJ_LIST = E(LIST)
SJ_MICRO = E(MICRO_DICT)


def bench(fn, repeat=800):
    best = 1e9
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best * 1e6   # µs par itération


def pk_pickle():
    d, p = pickle.dumps, PROTO
    for _ in range(20):
        d(DICT, p); d(TUPLE, p); d(DICT_GROUP, p)


def sj_pickle():
    e = E
    for _ in range(20):
        e(DICT); e(TUPLE); e(DICT_GROUP)


def pk_unpickle():
    l = pickle.loads
    for _ in range(20):
        l(PK_DICT); l(PK_TUPLE); l(PK_GROUP)


def sj_unpickle():
    d = D
    for _ in range(20):
        d(SJ_DICT); d(SJ_TUPLE); d(SJ_GROUP)


def pk_pickle_list():
    d, p = pickle.dumps, PROTO
    for _ in range(10):
        d(LIST, p)


def sj_pickle_list():
    e = E
    for _ in range(10):
        e(LIST)


def pk_unpickle_list():
    l = pickle.loads
    for _ in range(10):
        l(PK_LIST)


def sj_unpickle_list():
    d = D
    for _ in range(10):
        d(SJ_LIST)


def pk_pickle_dict():
    d, p = pickle.dumps, PROTO
    for _ in range(5):
        d(MICRO_DICT, p)


def sj_pickle_dict():
    e = E
    for _ in range(5):
        e(MICRO_DICT)


def pk_unpickle_dict():
    l = pickle.loads
    for _ in range(5):
        l(PK_MICRO)


def sj_unpickle_dict():
    d = D
    for _ in range(5):
        d(SJ_MICRO)


# les charges par COUPLE écriture/lecture, pour se lire comme le reste du
# rapport (mêmes octets à l'aller et au retour). pyperformance ne fournit pas
# de `unpickle_dict` : sa lecture est ajoutée ici, sur la charge officielle de
# `pickle_dict`, pour que la troisième colonne ait ses deux sens comme les
# autres. Les octets TRANSPORTÉS par une itération ne pèsent rien tant que
# tout reste en mémoire, mais ce sont eux qui décident du temps total dès que
# la charge part sur un disque ou un réseau
GROUPES = [
    ("pickle / unpickle (60 dumps, 60 loads)",
     pk_pickle, sj_pickle, pk_unpickle, sj_unpickle,
     20 * (len(PK_DICT) + len(PK_TUPLE) + len(PK_GROUP)),
     20 * (len(SJ_DICT) + len(SJ_TUPLE) + len(SJ_GROUP))),
    ("pickle_list / unpickle_list (10, 10)",
     pk_pickle_list, sj_pickle_list, pk_unpickle_list, sj_unpickle_list,
     10 * len(PK_LIST), 10 * len(SJ_LIST)),
    ("pickle_dict / unpickle_dict (5, 5)",
     pk_pickle_dict, sj_pickle_dict, pk_unpickle_dict, sj_unpickle_dict,
     5 * len(PK_MICRO), 5 * len(SJ_MICRO)),
]


def mesures(repeat=800):
    # rend [(nom, écriture pickle µs, écriture serializejson µs, lecture
    # pickle µs, lecture serializejson µs, octets pickle, octets
    # serializejson)] — importable par le rapport de benchmarks
    # (tests/lance_benchmarks.py)
    resultats = []
    for nom, pk_e, sj_e, pk_l, sj_l, octets_pk, octets_sj in GROUPES:
        temps = []
        for fonction in (pk_e, sj_e, pk_l, sj_l):
            fonction()  # échauffement
            temps.append(bench(fonction, repeat))
        resultats.append((nom, *temps, octets_pk, octets_sj))
    return resultats


if __name__ == "__main__":
    print("python %d.%d.%d  (protocole pickle %d)"
          % (*sys.version_info[:3], PROTO))
    for nom, pk_e, sj_e, pk_l, sj_l, *_ in mesures():
        print("  %-38s écriture x%.2f   lecture x%.2f"
              % (nom, sj_e / pk_e, sj_l / pk_l))
