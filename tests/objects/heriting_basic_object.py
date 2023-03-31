import datetime
import collections
import array
import decimal

# class None_subclass(None):
#    pass

# class bool_subclass(bool):
#    pass


class int_subclass(int):
    pass


class float_subclass(float):
    pass


class complex_subclass(complex):
    pass


class str_subclass(str):
    pass


class bytes_subclass(bytes):
    pass


class bytesarray_subclass(bytearray):
    pass


class list_subclass(list):
    pass


class dict_subclass(dict):
    pass


# class range_subclass(range):
#    pass

# class slice_subclass(slice):
#    pass


class deque_subclass(collections.deque):
    pass


class Counter_subclass(collections.Counter):
    pass


class OrderedDict_subclass(collections.OrderedDict):
    pass


class defaultdict_subclass(collections.defaultdict):
    pass


class Decimal_subclass(decimal.Decimal):
    pass


class datetime_subclass(datetime.datetime):
    pass


class date_subclass(datetime.date):
    pass


class time_subclass(datetime.time):
    pass


class timedelta_subclass(datetime.timedelta):
    pass


# class struct_time_subclass(time.struct_time):
#    pass

# class array_subclass(array.array):
#    pass


class tuple_subclass(tuple):
    pass


class set_subclass(set):
    pass


class frozenset_subclass(frozenset):
    pass


import datetime
import decimal
import math
import collections

# import time
# import array
Point = collections.namedtuple("Point", ["x", "y"])

lists = {
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
}


objects = {
    "int_subclass": {
        "0": int_subclass(0),
        "1": int_subclass(1),
        "2": int_subclass(2),
        "-2": -int_subclass(2),
    },
    "float_subclass": {
        "0.0": float_subclass(0.0),
        "1.1": float_subclass(1.0),
        "2.0": float_subclass(2.0),
        "0.5": float_subclass(0.5),
        "-0.5": float_subclass(-0.5),
        "nan": float_subclass("nan"),
        "inf": float_subclass("inf"),
        "-inf": float_subclass("-inf"),
    },
    "complex_subclass": {"complex": complex_subclass(1 + 4j)},
    "str_subclass": {
        "ascii": str_subclass("bonjour"),
        "latin_1": str_subclass("héhé"),
        "latin_2": str_subclass("salut ! j'ai bien mangé"),
        "latin_3": str_subclass("aé"),
        "euro": str_subclass("€"),
        "unicode_1": str_subclass("鼅"),
        "unicode_2": str_subclass("Доброе утро"),
        # pour tester readline
        "multilines": str_subclass("hé!\nbonjour\nvous êtes prêts?\nmoi j'ai mangé"),
        # peut arriver si mélange utf-8 et cp1252, par exemple après avoir édité un fichier utf-8 apèrs l'avoir ouvert en cp1252
        "utf8_decoded_with_cp1252_mixed_with_latin_1": str_subclass(
            "hÃ©!\nbonjour\nvous Ãªtes prÃªts?\nmoi j'ai mangé"
        ),
        # peut arriver si mélange utf-8 et cp1252
        "utf8_decoded_with_cp1252_mixed_with_latin_2": str_subclass(
            "hÃ©!\nbonjour\nvous Ãªtes prÃªts pour partir dans les pr\Ã¨s ?\nnmoi j'ai mangé"
        ),
        # peut arriver si mélange utf-8 et cp1252
        "utf8_decoded_with_cp1252_mixed_with_latin_3": str_subclass(
            "hÃ©!\nbonjour\nvous Ãªtes prÃªts pour partir sur l'Ã®le de brÃ©hat ? moi j'ai mangé"
        ),
        "utf8_or_latin_ambiguity": str_subclass("é€€"),
        "utf8_or_latin_ambiguity_making_crash": str_subclass("é€€é££\né"),
    },
    "bytes_subclass": {
        "empty": bytes_subclass(b""),
        "ascii": bytes_subclass(b"bonjour"),
        "ascii_with_cotes": bytes_subclass(b'bonjour les "amis"'),
        "ascii_with_back_slash": bytes_subclass(b'bonjour les "amis"\\\n'),
        "range128": bytes_subclass(range(128)),
        "range256": bytes_subclass(range(256)),
    },
    "bytesarray_subclass": {
        "empty": bytesarray_subclass(),
        "ascii_printable": bytesarray_subclass(b"bonjour"),
        "range128": bytesarray_subclass(range(128)),
        "range256": bytesarray_subclass(range(256)),
        # "range256x1200":bytearray(range(256))*1200 : plante avec jsonpickle
    },
    "list_subclass": {
        "empty": list_subclass([]),
        "one_int": list_subclass([1]),
        "bools": list_subclass([False, True]),
        "ints_01": list_subclass([0, 1]),
        "ints_pos": list_subclass([2, 3]),
        "ints_neg": list_subclass([-2, -3]),
        "ints_nan": list_subclass([1, math.nan]),
        "floats_01": list_subclass([0.0, 1.0]),
        "floats_pos": list_subclass([2.0, 3.0]),
        "floats_neg": list_subclass([-2.0, -3.0]),
        "floats_nan": list_subclass([1.0, math.nan]),
        "floats_inf": list_subclass([-math.inf, math.inf]),
        "mixed_bools_ints": list_subclass([False, True, 0, 1]),
        "mixed_bools_floats": list_subclass([False, True, 0.0, 1.0]),
        "mixed_ints_floats": list_subclass([0, 1, 0.0, 1.0]),
    },
    "dict_subclass": {
        "dict": dict_subclass(
            {
                "var_False": False,
                "var_True": True,
                "va_int": 10,
                "_underscore": "_underscore",
            }
        ),
    },
    "collections_subclass": {
        "deque": deque_subclass([1, 2]),
        "Counter": Counter_subclass("bonjour les amis"),
        "OrderedDict": OrderedDict_subclass([("b", 1), ("a", 3)]),
        "defaultdict": defaultdict_subclass(list, {"a": 1, "b": 2}),
    },
    "Decimal_subclass": {"0.33": Decimal_subclass("0.33")},
    "datetime_subclass": {
        "datetime": datetime_subclass(2020, 3, 10, 17, 30),
        "date": date_subclass(2020, 3, 10),
        "time": time_subclass(17, 30),
        "timedelta": timedelta_subclass(30),
    },
    "binary_subclass": {
        # "array" :array_subclass("i",[1,2,3])
        # "buffer":buffer,
        # "struct" : struct,
        # "memoryview":memoryview
    },
}
objects["list_subclass"] = {key: list_subclass(value) for key, value in lists.items()}
objects["tuple_subclass"] = {key: tuple_subclass(value) for key, value in lists.items()}
objects["set_subclass"] = {key: set_subclass(value) for key, value in lists.items()}
objects["frozenset_subclass"] = {
    key: frozenset_subclass(value) for key, value in lists.items()
}
