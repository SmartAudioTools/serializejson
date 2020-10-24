#from __future__ import absolute_import
import sys
import collections
import pickle
import io
import time
from time import perf_counter
from SmartFramework.files import joinPath, directory, removeExistingPathAndCreateFolder
from SmartFramework.tools.objects import deepCompare

try:
    import numpy
    from numpy import median
    use_numpy = True
except ModuleNotFoundError:
    from statistics import median
    use_numpy = False

try:    
    from qtpy import QtWidgets
    from SmartFramework.serialize import serializeJson as serializejson
    from SmartFramework.serialize import serializePython
    from SmartFramework.serialize import serializeRepr
    from SmartFramework.plot.PlotUI import Curve, Pen
    from SmartFramework.plot.PlotWithCurveSelectorUI import PlotWithCurveSelectorUI
    from SmartFramework.plot.ColorEnumerator import ColorEnumerator
    full_smartFramework = True
except ImportError:
    full_smartFramework = False
    import serializejson


# Import des objets


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


# --- DATAS -------------------------------------------------------------------

if __package__:
    from .objects import (
        log,
        basic_objects,
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
else:
    from objects import (
        log,
        basic_objects,
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
objects = basic_objects.objects
if full_smartFramework:
    app = QtWidgets.QApplication(sys.argv)
    if __package__:
        from .objects import pyqt_objects
    else:
        from objects import pyqt_objects
    objects.update(pyqt_objects.objects)
if use_numpy:
    if __package__:
        from .objects import numpy_objects
    else:
        from objects import numpy_objects
    objects.update(numpy_objects.objects)

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
    for class_name, class_ in module.__dict__.items():
        if class_name.startswith("C_"):
            categorie_dict[class_name] = class_()
            autorized_classes.append(class_)


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
            0.0 : 0,
            1.0 : 1,
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


def test_serialize_vs_pickle():

    # --- SERIALIZERS -------------------------------------------------------------
    bytesIO = io.BytesIO()

    serializers = {
        "pickle": {"encoder": pickle.dumps, "decoder": pickle.loads},
        "serializejson": {
            "encoder": serializejson.Encoder(attributs_filter=None,numpy_types_to_python_types = False),
            "decoder": serializejson.Decoder(set_attributs=True),
        },
        "serializejson_in_file": {
            "encoder": serializejson.Encoder(fp=bytesIO, attributs_filter=None,numpy_types_to_python_types = False),
            "decoder": serializejson.Decoder(fp=bytesIO, set_attributs=True),
        },
    }

    if full_smartFramework:
        serializers.update(
            {
                "serializeRepr": {
                    "encoder": lambda obj: serializeRepr.dumps(
                        obj, 
                        modules=modules,
                        attributs_filter=None,
                        set_attributs=True,
                        numpy_types_to_python_types = False
                    ),
                    "decoder": lambda obj: serializeRepr.loads(obj, modules=modules),
                },
                "serializePython": {
                    "encoder": lambda obj: serializePython.dumps(
                        obj,
                        attributs_filter=None,
                        set_attributs=True,
                        numpy_types_to_python_types = False
                    ),
                    "decoder": serializePython.loads,
                }
                # "jsonpickle": {
                #    "encoder": jsonpickle.dumps,
                #    "decoder": jsonpickle.loads
                # },
            }
        )

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
        serializerDumpsPath = joinPath(
            directory(__file__) + "/serialized", serializerName, "txt"
        )
        all_ok = True
        removeExistingPathAndCreateFolder(serializerDumpsPath)
        for categoryName, categoryDict in objects.items():
            #category_ok = False
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
                    median_time = median(times)
                    dumps_times_by_type[serializerName][categoryName + " " + key] = round(
                        median_time * 1000000, 1
                    )
                    total_dumps_time_by_serializer[serializerName] += median_time * 100000
                except TypeError:
                    message = "  unable to dumps ", repr(value)
                    print(message)
                    all_ok = False
                    if serializerName != "pickle":
                        raise Exception(message)
                    break
                if serializerName != "serializejson_in_file":
                    addInFile(serializerDumpsPath, dumped)
                if serializerName in ("serializejson", "serializejson_in_file"):
                    serializer["decoder"].set_autorized_classes(
                        serializer["encoder"].get_dumped_classes()
                    )
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
                    median_time = median(times)
                    loads_times_by_type[serializerName][categoryName + " " + key] = round(
                        median_time * 1000000, 1
                    )
                    total_loads_time_by_serializer[serializerName] += median_time * 100000
                except:
                    message = " unable to loads %s -> %s -> ERROR" % (repr(value), repr(dumped))
                    print(message)
                    all_ok = False
                    raise 

                else:
                    if categoryName.startswith("object"):

                        if serializerName != "pickle":
                            log.logs = []
                            pickled = pickle.dumps(value)
                            pickle_dump_logs = log.logs
                            log.logs = []
                            unpickle_value = pickle.loads(pickled)
                            pickle_load_logs = log.logs
                            (
                                same_as_pickle,
                                pickle_diff_loaded,
                                loaded_diff_pickle,
                            ) = deepCompare(unpickle_value, loaded, return_reason=True)
                            if not same_as_pickle:
                                all_ok = False
                                print(
                                    "  unpickled %s (%s)\n   -> %s\n  -> %s (%s)"
                                    % (
                                        value.__class__.__name__,
                                        str(pickle_diff_loaded),
                                        dumped,
                                        loaded.__class__.__name__,
                                        str(loaded_diff_pickle),
                                    )
                                )

                            if pickle_dump_logs != dump_logs:
                                print(
                                    value.__class__.__name__,
                                    ":\n   ",
                                    pickle_dump_logs,
                                    "\n ->",
                                    dump_logs,
                                )
                            if pickle_load_logs != load_logs:
                                print(
                                    value.__class__.__name__,
                                    ":\n   ",
                                    pickle_load_logs,
                                    "\n ->",
                                    load_logs,
                                )
                    else:
                        (
                            same_as_original,
                            original_diff_loaded,
                            loaded_diff_orginal,
                        ) = deepCompare(value, loaded, return_reason=True)
                        if not same_as_original:
                            all_ok = False
                            repr_value = repr(value)
                            repr_loaded = repr(loaded)
                            if repr_value != repr_loaded:
                                message = "  %s -> %s -> %s" % (repr_value, repr(dumped), repr_loaded)
                            else:
                                message = "  %s (%s)-> %s -> %s (%s)" % (
                                    repr_value,
                                    str(original_diff_loaded),
                                    repr(dumped),
                                    repr_loaded,
                                    str(loaded_diff_orginal),
                                )
                            print(message)
                            raise_exception = True
                            type_value  =type(value)
                            if serializerName == "serializePython" :
                                if categoryName == "QtWidgets" :
                                    raise_exception = False
                            elif serializerName in ("serializejson","serializejson_in_file"):
                                # exception pour serializejson 
                                if type_value is tuple:
                                    (
                                        same_as_original,
                                        original_diff_loaded,
                                        loaded_diff_orginal,
                                    ) = deepCompare(list(value), loaded, return_reason=True)
                                    if same_as_original:
                                        raise_exception = False
                                elif type_value in (collections.Counter, collections.OrderedDict, collections.defaultdict) and dict(value) == loaded:
                                    raise_exception = False
                                elif type_value is time.struct_time and list(value) == loaded:
                                    raise_exception = False
                                elif use_numpy and type_value is numpy.float64 and value == loaded :
                                    raise_exception = False
                            if raise_exception:
                                raise Exception(message)
        if all_ok:
            print("  all is ok !")

    serializejson.dump(
        dumps_times_by_type,
        directory(__file__) + "/serialized/dumps_times.json",
        sort_keys=False,
    )
    serializejson.dump(
        loads_times_by_type,
        directory(__file__) + "/serialized/loads_times.json",
        sort_keys=False,
    )

    print(
        "Dumps -------------\n"
        + "\n".join(
            (
                f"{key} : {value:.2f}"
                for key, value in total_dumps_time_by_serializer.items()
            )
        )
    )
    print(
        "Loads -------------\n"
        + "\n".join(
            (
                f"{key} : {value:.2f}"
                for key, value in total_loads_time_by_serializer.items()
            )
        )
    )

    # --- PLOT BENCHMARK -----------------------------------------------------------------

    if full_smartFramework:
        plotUI = PlotWithCurveSelectorUI(
            antialising=True, rotation=90
        )  # ,backgroundColor = QtCore.Qt.black
        colorEnumerator = ColorEnumerator()
        for serializerName in reversed(list(loads_times_by_type.keys())):
            color = colorEnumerator.getNewColor()
            varnames, loads_times = zip(*loads_times_by_type[serializerName].items())
            curve = Curve(
                list(varnames), list(loads_times), ["loads", serializerName], Pen(color)
            )
            plotUI.addCurve(curve)
            varnames, dumps_times = zip(*dumps_times_by_type[serializerName].items())
            curve = Curve(
                list(varnames), list(dumps_times), ["dumps", serializerName], Pen(color)
            )
            plotUI.addCurve(curve)
        plotUI.show()
        app.exec_()  # pas besoin si on n'utilise pas de signaux


if __name__ == "__main__":
    test_serialize_vs_pickle()
