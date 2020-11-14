try:
    import numpy
except ModuleNotFoundError:
    pass
try:
    from SmartFramework import numpyB64
    from SmartFramework.serialize.tools import encodedB64
    from SmartFramework.serialize import serialize_parameters
except:
    from serializejson import numpyB64
    from serializejson.tools import encodedB64
    from serializejson import serialize_parameters
# from rapidjson import RawJSON
import blosc

blosc_compressions = set(blosc.cnames)


def tuple_from_ndarray(inst):

    # inst = numpy.ascontiguousarray(inst)
    dtype = inst.dtype
    # compression = serialize_parameters.bytes_compression
    if dtype.fields is None:
        dtype_str = str(dtype)
        max_size = serialize_parameters.numpy_array_readable_max_size
        if isinstance(max_size, dict):
            if dtype_str in max_size:
                max_size = max_size[dtype_str]
            else:
                max_size = 0
        if max_size is None or inst.size <= max_size:
            return (
                "numpy.array",
                (inst.tolist(), dtype_str),
                None,
            )  #  A REVOIR : pass genial car va tester ultérieurement si tous les elements sont du même type....
    else:
        dtype_str = dtype.descr

        # return (numpy.array, (RawJSON(numpy.array2string(inst,separator =',')), dtype_str), None)  plus lent.

    if serialize_parameters.numpy_array_use_numpyB64:
        if dtype == bool:
            data = numpy.packbits(inst.astype(numpy.uint8))
            if inst.ndim == 1:
                len_or_shape = len(inst)
            else:
                len_or_shape = inst.shape
        else:
            data = inst
            if inst.ndim == 1:
                len_or_shape = None
            else:
                len_or_shape = inst.shape
        compression = serialize_parameters.bytes_compression
        if compression and data.nbytes >= serialize_parameters.bytes_size_compression_threshold:
            if compression in blosc_compressions:
                compressed = blosc.compress(
                    numpy.ascontiguousarray(data),
                    data.itemsize,
                    cname=compression,
                    clevel=serialize_parameters.bytes_compression_level,
                )
            else:
                raise Exception(f"{compression} compression unknow")
            if len(compressed) < data.nbytes:
                if len_or_shape is None:
                    return (
                        numpyB64,
                        (encodedB64(compressed), dtype_str, compression),
                        None,
                    )
                else:
                    return (
                        numpyB64,
                        (encodedB64(compressed), dtype_str, len_or_shape, compression),
                        None,
                    )
        if len_or_shape is None:
            return (
                numpyB64,
                (encodedB64(numpy.ascontiguousarray(data)), dtype_str),
                None,
            )
        else:
            return (
                numpyB64,
                (encodedB64(numpy.ascontiguousarray(data)), dtype_str, len_or_shape),
                None,
            )

    else:
        if inst.ndim == 1:
            return ("numpy.frombuffer", (bytearray(inst), dtype_str), None)
        else:
            return (
                numpy.ndarray,
                (inst.shape, dtype_str, bytearray(inst)),
                None,
            )


def tuple_from_dtype(inst):
    initArgs = (str(inst),)
    return (inst.__class__, initArgs, None)


def tuple_from_bool_(inst):
    return (inst.__class__, (bool(inst),), None)


def tuple_from_int(inst):
    return (inst.__class__, (int(inst),), None)


def tuple_from_float(inst):
    return (inst.__class__, (float(inst),), None)


tuple_from_int8 = tuple_from_int
tuple_from_int16 = tuple_from_int
tuple_from_int32 = tuple_from_int
tuple_from_int64 = tuple_from_int
tuple_from_uint8 = tuple_from_int
tuple_from_uint16 = tuple_from_int
tuple_from_uint32 = tuple_from_int
tuple_from_uint64 = tuple_from_int
tuple_from_float16 = tuple_from_float
tuple_from_float32 = tuple_from_float
tuple_from_float64 = tuple_from_float
