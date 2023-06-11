import sys
import pickle
import io
import inspect
import codecs
from time import perf_counter
from SmartFramework.files import joinPath, directory, removeExistingPathAndCreateFolder
from SmartFramework.tools.objects import deepCompare


from statistics import median

use_numpy = False
use_qtpy = False

nb_iter = 1
full_smartFramework = False
import serializejson


# Import des objets


def addInFile(path, element, encoding="utf_8_sig", newline="\n"):
    if isinstance(element, bytes):
        with open(path, "ab") as f:
            if f.tell() == 0:
                f.write(codecs.BOM_UTF8)
            elif newline:
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
        heriting_basic_object,
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
        new_getnewargs,
        getstate_no_string_keys,
        dict_subclasses,
        tuple_subclasses,
        properties,
        # -------------------------------------
        init_args_explicite_getstate,
        init_args_filtered_state_explicite_getstate,
        init_args_ghost_getinitargs,
        init_default_explicite_getstate,
        init_default_filtered_state_explicite_getstate,
        init_default_ghots_getstate,
        init_default_ghost_getinitargs,
        init_kwargs_explicite_getstate,
        init_kwargs_filtered_state_explicite_getstate,
        init_and_new,
    )
else:
    from objects import (
        log,
        basic_objects,
        heriting_basic_object,
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
        new_getnewargs,
        getstate_no_string_keys,
        dict_subclasses,
        tuple_subclasses,
        properties,
        # --------------------------------------------
        init_args_explicite_getstate,
        init_args_filtered_state_explicite_getstate,
        init_args_ghost_getinitargs,
        init_default_explicite_getstate,
        init_default_filtered_state_explicite_getstate,
        init_default_ghots_getstate,
        init_default_ghost_getinitargs,
        init_kwargs_explicite_getstate,
        init_kwargs_filtered_state_explicite_getstate,
        init_and_new,
        single_line,
    )

modules = [
    new_getnewargs,
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
    init_default_ghost_getinitargs,
    new_getnewargs,
    getstate_no_string_keys,
    dict_subclasses,
    tuple_subclasses,
    properties,
    init_and_new,
    single_line,
]
objects = basic_objects.objects
# objects.update(heriting_basic_object.objects)
if use_qtpy:
    app = QtWidgets.QApplication(sys.argv)
    if __package__:
        from .objects import pyqt_objects
    else:
        from objects import pyqt_objects
    modules.append(pyqt_objects)
    objects.update(pyqt_objects.objects)
if use_numpy:
    if __package__:
        from .objects import numpy_objects
    else:
        from objects import numpy_objects
    objects.update(numpy_objects.objects)

authorized_classes = []
for module in modules:
    if hasattr(module, "authorized_classes"):
        authorized_classes.extend(module.__dict__["authorized_classes"])
    if hasattr(module, "objects"):
        module_objects = module.__dict__["objects"]
        objects.update(module_objects)
        for categorie, categorie_classes in module_objects.items():
            for class_name, obj in categorie_classes.items():
                if inspect.isclass(obj):
                    authorized_classes.append(obj)
                else:
                    authorized_classes.append(type(obj))
    else:
        objects["object_" + module.__name__] = categorie_dict = dict()
        for class_name, class_ in module.__dict__.items():
            if class_name.startswith("C_"):
                categorie_dict[class_name] = class_()
                authorized_classes.append(class_)

# print(categorie_dict)
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
        "pickle_protocol_4": {
            "encoder": lambda obj: pickle.dumps(obj, protocol=4),
            "decoder": pickle.loads,
        },
        "serializejson_strict_pickle_protocol_3": {
            "encoder": serializejson.Encoder(strict_pickle=True, protocol=3, indent=None),
            "decoder": serializejson.Decoder(setters=False),
        },
        "serializejson_strict_pickle_protocol_4": {
            "encoder": serializejson.Encoder(strict_pickle=True, protocol=4, indent=None),
            "decoder": serializejson.Decoder(setters=False),
        },
        # "pickle_python_version": {"encoder": pickle._dumps, "decoder": pickle.loads},
        # "serializePickle": {
        #    "encoder": serializePickle._dumps,
        #    "decoder": serializePickle._loads,
        # },
        "serializejson": {
            "encoder": serializejson.Encoder(
                attributes_filter=False,
                numpy_types_to_python_types=False,
                indent=None,
                numpy_array_readable_max_size=4,
            ),
            "decoder": serializejson.Decoder(),
        },
        "serializejson_properties_getter_setters": {
            "encoder": serializejson.Encoder(
                attributes_filter=False,
                numpy_types_to_python_types=False,
                indent=None,
                numpy_array_readable_max_size=4,
                properties=True,
                getters=True,
            ),
            "decoder": serializejson.Decoder(properties=True, setters=True),
        },
        "serializejson_string": {
            "encoder": serializejson.Encoder(
                attributes_filter=False,
                numpy_types_to_python_types=False,
                indent=None,
                return_bytes=False,
            ),
            "decoder": serializejson.Decoder(),
        },
        "serializejson_blosclz_level9": {
            "encoder": serializejson.Encoder(
                attributes_filter=False,
                numpy_types_to_python_types=False,
                indent=None,
                bytes_compression=("blosc_zstd", 9),
            ),
            "decoder": serializejson.Decoder(),
        },
        "serializejson_in_file": {
            "encoder": serializejson.Encoder(file=bytesIO, attributes_filter=False, numpy_types_to_python_types=False),
            "decoder": serializejson.Decoder(file=bytesIO, setters=True),
        },
        "serializejson_with_tab_indent": {
            "encoder": serializejson.Encoder(attributes_filter=False, numpy_types_to_python_types=False, indent="\t"),
            "decoder": serializejson.Decoder(),
        },
        "serializejson_no_compression": {
            "encoder": serializejson.Encoder(
                attributes_filter=False,
                numpy_types_to_python_types=False,
                indent=None,
                bytes_compression=None,
            ),
            "decoder": serializejson.Decoder(),
        },
        "serializejson_readeable_numpy_int32": {
            "encoder": serializejson.Encoder(
                attributes_filter=False,
                numpy_types_to_python_types=False,
                indent=None,
                numpy_array_readable_max_size={"int32": None},
            ),
            "decoder": serializejson.Decoder(),
        },
    }
    if use_numpy:
        serializers.update(
            {
                "serializejson_numpy_array_to_list": {
                    "encoder": serializejson.Encoder(
                        attributes_filter=False,
                        numpy_array_to_list=True,
                        numpy_types_to_python_types=False,
                        indent=None,
                    ),
                    "decoder": serializejson.Decoder(setters=True, numpy_array_from_list=True),
                },
                "serializejson_numpy_array_to_list_with_tab_indent": {
                    "encoder": serializejson.Encoder(
                        attributes_filter=False,
                        numpy_array_to_list=True,
                        numpy_types_to_python_types=False,
                        indent="\t",
                    ),
                    "decoder": serializejson.Decoder(setters=True, numpy_array_from_list=True),
                },
            }
        )
    if False:  # full_smartFramework:
        serializers.update(
            {
                "serializeRepr": {
                    "encoder": lambda obj: serializeRepr.dumps(
                        obj,
                        modules=modules,
                        attributes_filter=False,
                        properties=True,
                        getters=True,
                        setters=True,
                        numpy_types_to_python_types=False,
                        numpy_array_readable_max_size=4,
                    ),
                    "decoder": lambda obj: serializeRepr.loads(obj, modules=modules, setters=True),
                },
                "serializePython": {
                    "encoder": lambda obj: serializePython.dumps(
                        obj,
                        attributes_filter=False,
                        properties=True,
                        getters=True,
                        setters=True,
                        numpy_types_to_python_types=False,
                    ),
                    "decoder": lambda obj: serializePython.loads(obj, setters=True),
                },
                # "serpent": {"encoder": lambda obj: serpent.dumps(obj, module_in_classname = True) ,
                #            "decoder": serpent.loads},
            }
        )

    """
                "jsonpickle": {
                    "encoder": jsonpickle.encode,
                    "decoder": jsonpickle.decode,
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
            dumps_times_by_type[serializerName] = dict()
            loads_times_by_type[serializerName] = dict()
        print("\n" + serializerName.upper() + ":\n")
        serializerDumpsPath = joinPath(directory(__file__) + "/serialized", serializerName, "txt")
        all_ok = True
        removeExistingPathAndCreateFolder(serializerDumpsPath)
        for categoryName, categoryDict in objects.items():
            # category_ok = False
            for key, value in categoryDict.items():
                modules = set()
                try:
                    times = []
                    for i in range(nb_iter):
                        bytesIO.seek(0)
                        bytesIO.truncate(0)
                        log.logs = []
                        t1 = perf_counter()
                        dumped = serializer["encoder"](value)
                        t2 = perf_counter()
                        dump_logs = log.logs
                        times.append(t2 - t1)
                    median_time = median(times)
                    categorNameKey = categoryName + " " + key
                    # if categorNameKey not in dumps_times_by_type[serializerName]:
                    #   dumps_times_by_type[serializerName] = dict()
                    dumps_times_by_type[serializerName][categorNameKey] = round(median_time * 1000000, 1)
                    if (serializerName == "pickle") or categorNameKey in dumps_times_by_type["pickle"]:
                        total_dumps_time_by_serializer[serializerName] += median_time * 1000000
                except (TypeError, ValueError, pickle.PicklingError) as exception:
                    message = "unable to dumps " + repr(value) + " : " + str(exception)
                    print(message)
                    all_ok = False
                    if serializerName not in (
                        "pickle",
                        "pickle_python_version",
                        "jsonpickle",
                        "serializePickle",
                        "serpent",
                    ):
                        print(key)
                        print(message)
                        raise  # Exception(message)
                    continue
                    # break
                if serializerName != "serializejson_in_file":
                    addInFile(serializerDumpsPath, dumped)
                if serializerName.startswith("serializejson"):
                    serializer["decoder"].set_authorized_classes(authorized_classes)
                try:
                    times = []
                    for i in range(nb_iter):
                        bytesIO.seek(0)
                        log.logs = []
                        t1 = perf_counter()
                        loaded = serializer["decoder"](dumped)
                        t2 = perf_counter()
                        load_logs = log.logs
                        # times.append(t2 - t1)
                        times.append(t2 - t1)
                    median_time = median(times)
                    categorNameKey = categoryName + " " + key
                    # if categorNameKey not in loads_times_by_type[serializerName]:
                    #    loads_times_by_type[serializerName] = dict()
                    loads_times_by_type[serializerName][categorNameKey] = round(median_time * 1000000, 1)
                    if (serializerName == "pickle") or categorNameKey in loads_times_by_type["pickle"]:
                        total_loads_time_by_serializer[serializerName] += median_time * 1000000
                except (TypeError, ValueError, Exception) as exception:
                    message = "unable to loads %s -> %s -> ERROR" % (repr(value), repr(dumped)) + "\n" + str(exception)
                    print(message)
                    all_ok = False
                    if not (
                        serializerName.startswith("pickle")
                        or serializerName in ("jsonpickle", "serpent")
                        or key == "C_New_SaveDict_SetState_slots_and_dict"
                    ):
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
                                    "unpickled %s (%s)\n  -> %s\n  -> %s (%s)"
                                    % (
                                        value.__class__.__name__,
                                        str(pickle_diff_loaded),
                                        repr(dumped),
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
                                message = "   %s \n->%s \n-> %s\n" % (
                                    repr_value,
                                    repr(dumped[:200]),
                                    repr_loaded,
                                )
                            else:
                                message = "   %s (%s)\n->%s \n-> %s (%s)\n" % (
                                    repr_value,
                                    str(original_diff_loaded),
                                    repr(dumped[:200]),
                                    repr_loaded,
                                    str(loaded_diff_orginal),
                                )
                            print(message)
                            raise_exception = True
                            type_value = type(value)
                            # if serializerName == "serializePython" :
                            #    if categoryName == "QtWidgets" :
                            #        raise_exception = False
                            if serializerName.startswith("serializejson_numpy_array_to_list") and (
                                isinstance(value, (tuple, list)) or isinstance(value, numpy.ndarray)
                            ):
                                raise_exception = False
                            elif serializerName.startswith("serializejson"):
                                # exception pour serializejson
                                if use_numpy and type_value is numpy.float64 and value == loaded:
                                    raise_exception = False
                                if type_value in (
                                    heriting_basic_object.int_subclass,
                                    heriting_basic_object.float_subclass,
                                    heriting_basic_object.str_subclass,
                                    heriting_basic_object.list_subclass,
                                ):
                                    raise_exception = False
                            elif serializerName in ("jsonpickle", "serpent"):
                                # and (value is type(None)):
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
        + "\n".join((f"{key} : {value:.2f}" for key, value in total_dumps_time_by_serializer.items()))
    )
    print(
        "Loads -------------\n"
        + "\n".join((f"{key} : {value:.2f}" for key, value in total_loads_time_by_serializer.items()))
    )

    # --- PLOT BENCHMARK -----------------------------------------------------------------

    if full_smartFramework:
        plotUI = PlotWithCurveSelectorUI(antialising=True, rotation=90)
        colorEnumerator = ColorEnumerator()
        for serializerName in reversed(list(loads_times_by_type.keys())):
            color = colorEnumerator.getNewColor()
            varnames, loads_times = zip(*loads_times_by_type[serializerName].items())
            curve = Curve(list(varnames), list(loads_times), ["loads", serializerName], Pen(color))
            plotUI.addCurve(curve)
            varnames, dumps_times = zip(*dumps_times_by_type[serializerName].items())
            curve = Curve(list(varnames), list(dumps_times), ["dumps", serializerName], Pen(color))
            plotUI.addCurve(curve)
        plotUI.show()
        app.exec_()  # pas besoin si on n'utilise pas de signaux


if __name__ == "__main__":
    test_serialize_vs_pickle()
