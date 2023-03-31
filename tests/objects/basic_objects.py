import datetime
import decimal
import math
import collections
import time
import array


dict_no_str_keys = {
    # math.nan : "value",
    "": "value",
    "string_key": "value",
    "string'key": "value",
    'string"key': "value",
    b"bytes_key": "value",
    b"bytes'key": "value",
    b'bytes"key': "value",
    bytes(range(0, 32)): "value",
    True: "value",
    2: "value",
    3.4: "value",
    (5, 6): "value",
    (5, (6, 8)): "value",
    frozenset([7, 8]): "value",
    "string_key": "value",
    "string'key": "value",
    'string"key': "value",
    "b'bytes_key'": "value",
    "b64'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8='": "value",
    "true": "value",
    "2": "value",
    "3.4": "value",
    "[5,6]": "value",
    '{"__class__":"frozenset","__init__":[8,7]}': "value",
    "'false'": "value",
    "'7'": "value",
    "'8.9'": "value",
}
objects = {
    "None": {"None": None},
    "bool": {"true": True, "false": False},
    "int": {"0": 0, "1": 1, "2": 2, "-2": -2},
    "float": {
        "0.0": 0.0,
        "1.1": 1.0,
        "2.0": 2.0,
        "0.5": 0.5,
        "-0.5": -0.5,
        "nan": float("nan"),
        "inf": float("inf"),
        "-inf": float("-inf"),
    },
    "complex": {"complex": (1 + 4j)},
    "str": {
        "ascii": "bonjour",
        "latin_1": "héhé",
        "latin_2": "salut ! j'ai bien mangé",
        "latin_3": "aé",
        "euro": "€",
        "unicode_1": "鼅",
        "unicode_2": "Доброе утро",
        "multilines": "hé!\nbonjour\nvous êtes prêts?\nmoi j'ai mangé",  # pour tester readline
        "utf8_decoded_with_cp1252_mixed_with_latin_1": "hÃ©!\nbonjour\nvous Ãªtes prÃªts?\nmoi j'ai mangé",  # peut arriver si mélange utf-8 et cp1252, par exemple après avoir édité un fichier utf-8 apèrs l'avoir ouvert en cp1252
        "utf8_decoded_with_cp1252_mixed_with_latin_2": "hÃ©!\nbonjour\nvous Ãªtes prÃªts pour partir dans les pr\Ã¨s ?\nnmoi j'ai mangé",  # peut arriver si mélange utf-8 et cp1252
        "utf8_decoded_with_cp1252_mixed_with_latin_3": "hÃ©!\nbonjour\nvous Ãªtes prÃªts pour partir sur l'Ã®le de brÃ©hat ? moi j'ai mangé",  # peut arriver si mélange utf-8 et cp1252
        "utf8_or_latin_ambiguity": "é€€",
        "utf8_or_latin_ambiguity_making_crash": "é€€é££\né",
    },
    "bytes": {
        "empty": b"",
        "ascii": b"bonjour",
        "ascii_with_cotes": b'bonjour les "amis"',
        "ascii_with_back_slash": b'bonjour les "amis"\\\n',
        "range128": bytes(range(128)),
        "range256": bytes(range(256)),
        "range256*2": bytes(range(256)) * 2,
        # "range256x1200": bytes(range(256)) * 1200,
    },
    "bytesarray": {
        "empty": bytearray(),
        "ascii_printable": bytearray(b"bonjour"),
        "range128": bytearray(range(128)),
        "range256": bytearray(range(256)),
        "range256x2": bytearray(range(256)) * 2,
        # "range256x1200":bytearray(range(256))* 2#*1200 #: plante avec jsonpickle
    },
    "list": {
        "empty": [],
        "one_int": [1],
        "bools": [False, True],
        "ints_01": [0, 1],
        "ints_pos": [2, 3],
        "ints_neg": [-2, -3],
        "ints_nan": [1, math.nan],
        "floats_01": [0.0, 1.0],
        "floats_pos": [2.0, 3.0],
        "floats_neg": [-2.0, -3.0],
        "floats_nan": [1.0, math.nan],
        "floats_inf": [-math.inf, math.inf],
        "mixed_bools_ints": [False, True, 0, 1],
        "mixed_bools_floats": [False, True, 0.0, 1.0],
        "mixed_ints_floats": [0, 1, 0.0, 1.0],
    },
    "composeds": {
        "list_of_list": [[1, 2], [3, 4]],
    },
    "dict": {
        "dict": {
            "var_False": False,
            "var_True": True,
            "va_int": 10,
            "_underscore": "_underscore",
        },
        "dict-non_string_keys": dict_no_str_keys,
    },
    "range": {
        "range_0_10": range(10),
    },
    "slice": {"slice_1_10_2": slice(1, 10, 2)},
    "iterators": {
        # "list_iterator": [i*10 for i in range(10)],
        # "tuple_iterator": (i+10 for i in range(10)),
        # "dic_iterator": {key : value*10 for key , value in {"key1": 1, "key2":2}.items()}
    },
    "collections": {
        "deque": collections.deque([1, 2]),
        "Counter": collections.Counter("bonjour les amis"),
        "OrderedDict": collections.OrderedDict([("b", 1), ("a", 3)]),
        "defaultdict": collections.defaultdict(list, {"a": 1, "b": 2}),
        "Counter_no_string_keys": collections.Counter(dict_no_str_keys),
        "OrderedDict_no_string_keys": collections.OrderedDict(dict_no_str_keys),
        "defaultdict_no_string_keys": collections.defaultdict(list, dict_no_str_keys),
    },
    "queue": {
        # 'Queue' : queue.Queue(),
        # 'LifoQueue' : queue.LifoQueue(),
        # 'PriorityQueue': queue.PriorityQueue(),
        # 'SimpleQueue' : queue.SimpleQueue()
    },
    "decimales": {"0.33": decimal.Decimal("0.33")},
    "datetime": {
        "datetime": datetime.datetime(2020, 3, 10, 17, 30),
        "date": datetime.date(2020, 3, 10),
        "time": datetime.time(17, 30),
        "timedelta": datetime.timedelta(30),
        "struct_time": time.struct_time([2020, 5, 7, 16, 8, 55, 3, 128, 1]),
    },
    "binary": {
        "array_signed_char": array.array("b", [1, 2, 3]),
        "array_unsigned_char": array.array("B", [1, 2, 3]),
        "array_unicode": array.array("u", "coucou"),
        "array_signed_short": array.array("h", [1, 2, 3]),
        "array_unsigned_short": array.array("H", [1, 2, 3]),
        "array_signed_int": array.array("i", [1, 2, 3]),
        "array_unsigned_int": array.array("I", [1, 2, 3]),
        "array_signed_long": array.array("l", [1, 2, 3]),
        "array_unsigned_long": array.array("L", [1, 2, 3]),
        "array_signed_long_long": array.array("q", [1, 2, 3]),
        "array_unsigned_long_long": array.array("Q", [1, 2, 3]),
        "array_float": array.array("f", [1.0, 2.0, 3.0]),
        "array_double": array.array("d", [1.0, 2.0, 3.0]),
        # "buffer":buffer,
        # "struct" : struct,
        # "memoryview":memoryview
    },
    "types": {
        "type": type,
        "NoneType": type(None),
        "bool": bool,
        "int": int,
        "float": float,
        "complex": complex,
        "str": str,
        "bytes": bytes,
        "bytesarray": bytearray,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "set": set,
        "frozenset": frozenset,
        "range": range,
        "slice": slice,
        "deque": collections.deque,
        "Counter": collections.Counter,
        "OrderedDict": collections.OrderedDict,
        "defaultdict": collections.defaultdict,
        "decimal": decimal.Decimal,
        "datetime": datetime.datetime,
        "date": datetime.date,
        "time": datetime.time,
        "timedelta": datetime.timedelta,
        "struct_time": time.struct_time,
        # "class": Empty
    },
}
objects["tuple"] = {key: tuple(value) for key, value in objects["list"].items()}
objects["set"] = {key: set(value) for key, value in objects["list"].items()}
objects["frozenset"] = {key: frozenset(value) for key, value in objects["list"].items()}
