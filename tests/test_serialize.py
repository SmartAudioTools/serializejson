import sys
import math
import collections
import datetime
import decimal
import pickle
import time
import io
import statistics
from time import perf_counter
from serializejson.SmartFramework.files import joinPath, directory, removeExistingPathAndCreateFolder
from serializejson.SmartFramework.tools.objects import deepCompare
from serializejson.SmartFramework.serialize.objects import (
    init_arg,
    init_args,
    init_args_filtered_state,
    init_default,
    init_default_filtered_state,
    init_kwarg,
    init_kwargs,
    init_kwargs_filtered_state,
    no_init,
    no_init_filtered_state,
    no_init_slots,
    no_init_slots_and_dict,
    no_init_slots_subclass,
    no_init_setters,
)
from serializejson.SmartFramework.serialize.objects import (
    init_args_explicite_getstate,
    init_args_filtered_state_explicite_getstate,
    init_args_ghost_getinitargs,
    init_default_explicite_getstate,
    init_default_filtered_state_explicite_getstate,
    init_default_ghots_getstate,
    init_kwargs_explicite_getstate,
    init_kwargs_filtered_state_explicite_getstate,
    init_default_ghost_getinitargs,
)
from serializejson.SmartFramework.serialize.objects import log

try:
    import numpy

    use_numpy = True
except:
    use_numpy = False
if __file__.endswith("serialize/test_serialize.py"):
    full_smartFramework = True
    from SmartFramework.serialize import serializeJson as serializejson
    from SmartFramework.serialize import serializePython
    from SmartFramework.serialize import serializeRepr
    from SmartFramework.plot.PlotUI import Curve, Pen
    from SmartFramework.plot.PlotWithCurveSelectorUI import PlotWithCurveSelectorUI
    from SmartFramework.plot.ColorEnumerator import ColorEnumerator
    from qtpy import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication(sys.argv)
else:
    full_smartFramework = False
    import serializejson


def addInFile(path, element, encoding="utf_8_sig", newline="\n"):
    if isinstance(element, bytes):
        with open(path, "ab") as f:
            if f.tell() != 0 and newline:
                f.write(newline.encode("ascii"))
            f.write(element)
    elif isinstance(element, str):
        with open(path, "a", encoding=encoding, newline=newline) as f:
            if f.tell() != 0 and newline:
                f.write(newline)
            f.write(element)
    else:
        raise Exception()


# --- SERIALIZERS -------------------------------------------------------------
bytesIO = io.BytesIO()


serializers = {
    "pickle": {"encoder": pickle.dumps, "decoder": pickle.loads},
    "serializejson": {
        "encoder": serializejson.Encoder(attributs_filter=None),
        "decoder": serializejson.Decoder(set_attributs=False),
    },
    "serializejson_in_file": {
        "encoder": serializejson.Encoder(fp=bytesIO, attributs_filter=None),
        "decoder": serializejson.Decoder(fp=bytesIO, set_attributs=False),
    },
}

if full_smartFramework:
    serializers.update(
        {
            "serializeRepr": {
                "encoder": lambda obj: serializeRepr.dumps(
                    obj, modules=modules, attributs_filter=None, set_attributs=False
                ),
                "decoder": lambda obj: serializeRepr.loads(obj, modules=modules),
            },
            "serializePython": {
                "encoder": lambda obj: serializePython.dumps(obj, attributs_filter=None, set_attributs=False),
                "decoder": serializePython.loads,
            }
            # "jsonpickle": {
            #    "encoder": jsonpickle.dumps,
            #    "decoder": jsonpickle.loads
            # },
        }
    )


# --- DATAS -------------------------------------------------------------------

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
        "-inf": -float("-inf"),
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
    },
    "bytesarray": {
        "empty": bytearray(),
        "ascii_printable": bytearray(b"bonjour"),
        "range128": bytearray(range(128)),
        "range256": bytearray(range(256)),
    },
    "list": {
        "empty": [],
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
        "dict": {"var_False": False, "var_True": True, "va_int": 10, "_underscore": "_underscore"},
    },
}


objects["tuple"] = {key: tuple(value) for key, value in objects["list"].items()}
objects["set"] = {key: set(value) for key, value in objects["list"].items()}
objects["frozenset"] = {key: frozenset(value) for key, value in objects["list"].items()}
if use_numpy:
    objects["numpy"] = {key: numpy.array(value) for key, value in objects["list"].items()}
    objects["numpy"].update(
        {
            # recarray
            # multidimentional
            # masqued array ( pour avoir equivalent de nan mais pour tableau d'entier ?)
            "in_tuple_array": (9, numpy.array([2]), 1),
            "2D_array": numpy.array([[1, 2], [3, 4]]),
            "int16_inf_10": numpy.arange(10, dtype=numpy.int16),
            "int16_sup_9": numpy.arange(10, 20, dtype=numpy.int16),
            "int16_inf_9999": numpy.arange(9990, 10000, dtype=numpy.int32),
            "int16_sup_9999": numpy.arange(10000, 10010, dtype=numpy.int32),
        }
    )


objects.update(
    {
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
            # "namedtuple" : collections.namedtuple(),
            "deque": collections.deque([1, 2]),
            "Counter": collections.Counter("bonjour les amis"),
            "OrderedDict": collections.OrderedDict([("b", 1), ("a", 3)]),
            "defaultdict": collections.defaultdict(list),
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
            "struct_time": time.struct_time([2020, 5, 7, 16, 8, 55, 3, 128, 1]),  # time.localtime()
        },
        "binary": {
            # "array" :array.array("i",[1,2,3])
            # "buffer":buffer,
            # "struct" : struct,
            # "memoryview":memoryview
        },
        "types": {
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
)
if full_smartFramework:
    objects["QtWidgets"] = {
        "QWidget": QtWidgets.QWidget(),
        #'QCheckBox': QtWidgets.QCheckBox(),
        #'QDoubleSpinBox': QtWidgets.QDoubleSpinBox(),
        #'QLineEdit': QtWidgets.QLineEdit(),
        #'QPlainTextEdit': QtWidgets.QPlainTextEdit(),
        # "QSpinBox": QtWidgets.QSpinBox(),
        "QPushButton": QtWidgets.QPushButton(),
    }
    objects["PyQt_pickable"] = {
        "QByteArray": QtCore.QByteArray(),
        "QColor": QtGui.QColor(),
        ## "QChar": tuple_from_reducableQt,
        "QDate": QtCore.QDate(),
        "QDateTime": QtCore.QDateTime(),
        "QKeySequence": QtGui.QKeySequence(),
        ## "QLatin1Char": tuple_from_reducableQt,
        ## "QLatin1String": tuple_from_reducableQt,
        "QLine": QtCore.QLine(),
        "QLineF": QtCore.QLineF(),
        ##'QPen': tuple_from_QPen,
        ##'QBrush': tuple_from_QBrush,
        "QPoint": QtCore.QPoint(),
        "QPointF": QtCore.QPointF(),
        "QPolygon": QtGui.QPolygon(),
        # "QPolygonF": QtGui.QPolygonF(),
        "QRect": QtCore.QRect(),
        "QRectF": QtCore.QRectF(),
        "QSize": QtCore.QSize(),
        "QSizeF": QtCore.QSizeF(),
        ## "QMatrix": tuple_from_reducableQt,
        ## "QString": tuple_from_reducableQt,
        "QTime": QtCore.QTime(),
        "QTransform": QtGui.QTransform(),  # pas reducable dans documentation ?
        "QVector3D": QtGui.QVector3D(),  # pas reducable dans documentation ?
    }
autorized_classes = []
for module in [
    init_arg,
    init_args_explicite_getstate,
    init_args_filtered_state_explicite_getstate,
    init_args_filtered_state,
    init_args_ghost_getinitargs,
    init_args,
    init_default_explicite_getstate,
    init_default_filtered_state_explicite_getstate,
    init_default_filtered_state,
    init_default_ghost_getinitargs,
    init_default_ghots_getstate,
    init_default,
    init_kwarg,
    init_kwargs_explicite_getstate,
    init_kwargs_filtered_state_explicite_getstate,
    init_kwargs_filtered_state,
    init_kwargs,
    no_init,
    no_init_filtered_state,
    no_init_slots,
    no_init_slots_and_dict,
    no_init_slots_subclass,
    no_init_setters,
]:
    objects["object_" + module.__name__] = categorie_dict = dict()
    for key, value in module.__dict__.items():
        if key.startswith("C_"):
            categorie_dict[key] = value()
            autorized_classes.append(value)

# serializejson.setAutorizedClasses(autorized_classes)
# serializejson.setAutorizedClasses('all')

""""
    #datetime.datetime, datetime.date, datetime.time, enum.Enum, and uuid.UUID)


         "dict_with_bool_keys": {
            False: False,
            True : True
        },
        "dict_with_int_keys": {
            0 : 0,
            1 : 1,
        },
        "dict_with_float_keys": {
            0 : 0,
            1 : 1,
        },
        "dict_with_None_keys": {
            None : None
        },
        "dict_with_bytes_keys": {
            b'bytes' : "coucou",
        },
        "dict_with_bytes_string_keys": {
            b'bytes' : "coucou",
            "string" : "string"
        },


MyNamedTuple = namedtuple('MyNamedTuple',("var_False","var_True","va_int"))
myNamedTuple = MyNamedTuple(**{
            "var_False": False,
            "var_True": True,
            "va_int" : 10,
            })

    "namedtuple": {
        "namedtuple":myNamedTuple
    },
"""

# --- BENCHMARK ----------------------------------------------------------------


dumps_times_by_type = dict()
loads_times_by_type = dict()
total_dumps_time_by_serializer = dict()
total_loads_time_by_serializer = dict()
for serializerName, serializer in serializers.items():
    total_dumps_time_by_serializer[serializerName] = 0
    total_loads_time_by_serializer[serializerName] = 0
    if serializerName not in dumps_times_by_type:
        dumps_times_by_type[serializerName] = collections.defaultdict(dict)
        loads_times_by_type[serializerName] = collections.defaultdict(dict)
    print("\n" + serializerName.upper() + ":\n")
    serializerDumpsPath = joinPath(directory(__file__) + "/serialized", serializerName, "txt")
    all_ok = True
    removeExistingPathAndCreateFolder(serializerDumpsPath)
    for categoryName, categoryDict in objects.items():
        category_ok = False
        for key, value in categoryDict.items():
            modules = []
            try:
                times = []
                for i in range(100):
                    bytesIO.seek(0)
                    bytesIO.truncate(0)
                    log.logs = []
                    t1 = perf_counter()
                    dumped = serializer["encoder"](value)
                    t2 = perf_counter()
                    dump_logs = log.logs
                    times.append(t2 - t1)
                time = statistics.median(times)
                dumps_times_by_type[serializerName][categoryName + " " + key] = round(time * 1000000, 1)
                total_dumps_time_by_serializer[serializerName] += time * 100000
            except TypeError:
                print("  unable to dumps ", repr(value))
                all_ok = False
                if serializerName != "pickle":
                    raise
                break
            if serializerName != "serializejson_in_file":
                addInFile(serializerDumpsPath, dumped)
            if serializerName in ("serializejson", "serializejson_in_file"):
                serializer["decoder"].set_autorized_classes(serializer["encoder"].get_dumped_classes())
            try:
                times = []
                for i in range(100):
                    bytesIO.seek(0)
                    log.logs = []
                    t1 = perf_counter()
                    loaded = serializer["decoder"](dumped)
                    t2 = perf_counter()
                    load_logs = log.logs
                    # times.append(t2 - t1)
                    times.append(t2 - t1)
                time = statistics.median(times)
                loads_times_by_type[serializerName][categoryName + " " + key] = round(time * 1000000, 1)
                total_loads_time_by_serializer[serializerName] += time * 100000
            except:
                raise
                print(" unable to loads %s -> %s -> ERROR" % (repr(value), repr(dumped)))
                all_ok = False
                # raise

            else:
                if categoryName.startswith("object"):

                    if serializerName != "pickle":
                        log.logs = []
                        pickled = pickle.dumps(value)
                        pickle_dump_logs = log.logs
                        log.logs = []
                        unpickle_value = pickle.loads(pickled)
                        pickle_load_logs = log.logs
                        same_as_pickle, pickle_diff_loaded, loaded_diff_pickle = deepCompare(
                            unpickle_value, loaded, return_reason=True
                        )
                        if not same_as_pickle:
                            all_ok = False
                            print(
                                "  unpickled %s (%s)-> %s -> %s (%s)"
                                % (
                                    value.__class__.__name__,
                                    str(pickle_diff_loaded),
                                    repr(dumped),
                                    loaded.__class__.__name__,
                                    str(loaded_diff_pickle),
                                )
                            )
                        if pickle_dump_logs != dump_logs:
                            print(value.__class__.__name__, ":\n   ", pickle_dump_logs, "\n ->", dump_logs)
                        if pickle_load_logs != load_logs:
                            print(value.__class__.__name__, ":\n   ", pickle_load_logs, "\n ->", load_logs)
                else:
                    same_as_original, original_diff_loaded, loaded_diff_orginal = deepCompare(
                        value, loaded, return_reason=True
                    )
                    if not same_as_original:
                        all_ok = False
                        repr_value = repr(value)
                        repr_loaded = repr(loaded)
                        if repr_value != repr_loaded:
                            print("  %s -> %s -> %s" % (repr_value, repr(dumped), repr_loaded))
                        else:
                            print(
                                "  %s (%s)-> %s -> %s (%s)"
                                % (
                                    repr_value,
                                    str(original_diff_loaded),
                                    repr(dumped),
                                    repr_loaded,
                                    str(loaded_diff_orginal),
                                )
                            )
    if all_ok:
        print("  all is ok !")

serializejson.dump(
    dumps_times_by_type, directory(__file__) + "/serialized/dumps_times.json", sort_keys=False
)
serializejson.dump(
    loads_times_by_type, directory(__file__) + "/serialized/loads_times.json", sort_keys=False
)

print(
    "Dumps -------------\n"
    + "\n".join((f"{key} : {value:.2f}" for key, value in total_dumps_time_by_serializer.items()))
)
print(
    "Loads -------------\n"
    + "\n".join((f"{key} : {value:.2f}" for key, value in total_loads_time_by_serializer.items()))
)

# --- PLOT BENCHMARK -----------------------------------------------------------------

if full_smartFramework:
    plotUI = PlotWithCurveSelectorUI(antialising=True, rotation=90)  # ,backgroundColor = QtCore.Qt.black
    colorEnumerator = ColorEnumerator()
    for serializerName in loads_times_by_type.keys():
        color = colorEnumerator.getNewColor()
        varnames, loads_times = zip(*loads_times_by_type[serializerName].items())
        curve = Curve(list(varnames), list(loads_times), ["loads", serializerName], Pen(color))
        plotUI.addCurve(curve)
        varnames, dumps_times = zip(*dumps_times_by_type[serializerName].items())
        curve = Curve(list(varnames), list(dumps_times), ["dumps", serializerName], Pen(color))
        plotUI.addCurve(curve)
    plotUI.show()
    app.exec_()  # pas besoin si on n'utilise pas de signaux
