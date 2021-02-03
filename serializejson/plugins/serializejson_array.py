try:
    from SmartFramework.serialize.tools import serializejson_, authorized_classes
    from SmartFramework.serialize import serialize_parameters
except:
    from serializejson import serialize_parameters
    from serializejson.tools import serializejson_, authorized_classes
import array


def serializejson_array(inst):
    typecode = inst.typecode
    max_size = serialize_parameters.array_readable_max_size
    if typecode == "u":
        return inst.__class__, (typecode, inst.tounicode()), None
    if isinstance(max_size, dict):
        if typecode in max_size:
            max_size = max_size[typecode]
        else:
            max_size = 0
    if max_size is None or len(inst) <= max_size:
        return inst.__class__, (typecode, inst.tolist()), None
    else:
        return inst.__class__, (typecode, inst.tobytes()), None


serializejson_[array.array] = serializejson_array
authorized_classes.update({"array.array", "array._array_reconstructor"})
