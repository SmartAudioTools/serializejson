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
SJ_DICT = E(DICT)
SJ_TUPLE = E(TUPLE)
SJ_GROUP = E(DICT_GROUP)
SJ_LIST = E(LIST)


def bench(fn, inner, repeat=800):
    best = 1e9
    total = 0.0
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        dt = time.perf_counter() - t0
        best = min(best, dt)
        total += dt
    return best * 1e6, total / repeat * 1e6   # µs par itération


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


rows = [
    ("pickle       (60 dumps)", pk_pickle, sj_pickle),
    ("unpickle     (60 loads)", pk_unpickle, sj_unpickle),
    ("pickle_list  (10 dumps)", pk_pickle_list, sj_pickle_list),
    ("unpickle_list(10 loads)", pk_unpickle_list, sj_unpickle_list),
    ("pickle_dict  ( 5 dumps)", pk_pickle_dict, sj_pickle_dict),
]


def mesures(repeat=800):
    # rend [(nom, pickle_min_µs, serializejson_min_µs)] — importable par le
    # rapport de benchmarks (tests/lance_benchmarks.py)
    resultats = []
    for name, pk, sj in rows:
        pk(); sj()  # échauffement
        pk_min, _ = bench(pk, name, repeat)
        sj_min, _ = bench(sj, name, repeat)
        resultats.append((name, pk_min, sj_min))
    return resultats


if __name__ == "__main__":
    print("python %d.%d.%d  (protocole pickle %d)"
          % (*sys.version_info[:3], PROTO))
    for name, pk_min, sj_min in mesures():
        print("  %-24s pickle %8.1f us   serializejson %8.1f us   ratio x%.2f"
              % (name, pk_min, sj_min, sj_min / pk_min))
