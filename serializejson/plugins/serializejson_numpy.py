try:
    import numpy
    from numpy import frombuffer, unpackbits, uint8, ndarray, int32, int64
    from numpy import dtype as numpy_dtype
except ModuleNotFoundError:
    pass
else:
    import blosc
    from pybase64 import b64encode_as_string, b64decode_as_bytearray
    import sys

    try:
        # from SmartFramework import numpyB64
        from SmartFramework.serialize.tools import serializejson_, constructors, blosc_compressions, authorized_classes
        from SmartFramework.serialize import serialize_parameters
    except:
        from serializejson import serialize_parameters
        from serializejson.tools import serializejson_, constructors, blosc_compressions, authorized_classes

    nb_bits = sys.maxsize.bit_length() + 1

    authorized_classes.update(
        {
            "numpy.bool_",
            "numpy.int8",
            "numpy.int16",
            "numpy.int32",
            "numpy.int64",
            "numpy.uint8",
            "numpy.uint16",
            "numpy.uint32",
            "numpy.uint64",
            "numpy.float16",
            "numpy.float32",
            "numpy.float64",
            "numpy.dtype",
            "numpy.ndarray",
            "numpy.array",
            "numpy.frombuffer",
            "numpyB64",
            "numpy.core.multiarray._reconstruct",
            "numpy.core.multiarray.scalar",
        }
    )

    def numpyB64(str64, dtype=None, shape_len_compression=None, compression=None):
        decoded_bytearray = b64decode_as_bytearray(str64, validate=True)
        if isinstance(shape_len_compression, str):
            compression = shape_len_compression
            shape_len = None
        else:
            shape_len = shape_len_compression
        if compression:
            if compression == "blosc":
                decoded_bytearray = blosc.decompress(decoded_bytearray, as_bytearray=True)
            else:
                raise Exception(f"unknow {compression} compression")
        if dtype in ("bool", bool):
            numpy_uint8_containing_8bits = frombuffer(decoded_bytearray, uint8)  # pas de copie -> read only
            numpy_uint8_containing_8bits = unpackbits(
                numpy_uint8_containing_8bits
            )  # copie dans un numpy array de uint8 mutable
            if shape_len is None:
                shape_len = len(numpy_uint8_containing_8bits)
            return ndarray(shape_len, dtype, numpy_uint8_containing_8bits)  # pas de recopie
        else:
            if isinstance(dtype, list):
                dtype = [(str(champName), champType) for champName, champType in dtype]
            if shape_len is None:
                array = frombuffer(decoded_bytearray, dtype)  # pas de recopie
            else:
                array = ndarray(shape_len, dtype, decoded_bytearray)  # pas de recopie
            if (
                nb_bits == 32 and serialize_parameters.numpyB64_convert_int64_to_int32_and_align_in_Python_32Bit
            ):  # pour pouvoir deserialiser les classifiers en python 32 bit ?
                if array.dtype in (int64, "int64"):
                    return array.astype(int32)
                elif isinstance(dtype, list):
                    newTypes = []
                    for champ in dtype:
                        champName, champType = champ
                        if champName:
                            champType = numpy_dtype(champType)
                            if champType in (int64, "int64"):
                                newTypes.append((champName, int32))
                            else:
                                newTypes.append((champName, champType))
                    newDtype = numpy_dtype(newTypes, align=True)
                    newN = ndarray(len(array), newDtype)
                    for champName, champType in newTypes:
                        if champName:
                            newN[champName][:] = array[champName]
                    return newN
            return array

    constructors["numpyB64"] = numpyB64

    def serializejson_ndarray(inst):

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

            # return ("numpy.array", (RawJSON(numpy.array2string(inst,separator =',')), dtype_str), None)  plus lent.

        if serialize_parameters.numpy_array_use_numpyB64:
            if dtype == bool:
                data = numpy.packbits(inst.astype(numpy.uint8))
                if inst.ndim == 1:
                    len_or_shape = len(inst)
                else:
                    len_or_shape = list(inst.shape)
            else:
                data = inst
                if inst.ndim == 1:
                    len_or_shape = None
                else:
                    len_or_shape = list(inst.shape)
            compression = serialize_parameters.bytes_compression
            if compression and data.nbytes >= serialize_parameters.bytes_size_compression_threshold:
                blosc_compression = blosc_compressions.get(compression, None)
                if blosc_compression:
                    compressed = blosc.compress(
                        numpy.ascontiguousarray(data),
                        data.itemsize,
                        cname=blosc_compression,
                        clevel=serialize_parameters.bytes_compression_level,
                    )
                    compression = "blosc"
                else:
                    raise Exception(f"{compression} compression unknow")
                if len(compressed) < data.nbytes:
                    if len_or_shape is None:
                        return (
                            "numpyB64",
                            (b64encode_as_string(compressed), dtype_str, compression),
                            None,
                        )
                    else:
                        return (
                            "numpyB64",
                            (b64encode_as_string(compressed), dtype_str, len_or_shape, compression),
                            None,
                        )
            if len_or_shape is None:
                return (
                    "numpyB64",
                    (b64encode_as_string(numpy.ascontiguousarray(data)), dtype_str),
                    None,
                )
            else:
                return (
                    "numpyB64",
                    (b64encode_as_string(numpy.ascontiguousarray(data)), dtype_str, len_or_shape),
                    None,
                )

        else:
            # if False :#inst.ndim == 1:
            #    return (numpy.frombuffer, (bytearray(inst), dtype_str), None)
            # else:
            return (
                "numpy.ndarray",
                (list(inst.shape), dtype_str, bytearray(inst)),
                None,
            )

    serializejson_[numpy.ndarray] = serializejson_ndarray

    def serializejson_dtype(inst):
        initArgs = (str(inst),)
        return (inst.__class__, initArgs, None)

    serializejson_[numpy.dtype] = serializejson_dtype

    def serializejson_bool_(inst):
        return (inst.__class__, (bool(inst),), None)

    serializejson_[numpy.bool_] = serializejson_bool_

    def serializejson_int(inst):
        return (inst.__class__, (int(inst),), None)

    serializejson_[numpy.int8] = serializejson_int
    serializejson_[numpy.int16] = serializejson_int
    serializejson_[numpy.int32] = serializejson_int
    serializejson_[numpy.int64] = serializejson_int
    serializejson_[numpy.uint8] = serializejson_int
    serializejson_[numpy.uint16] = serializejson_int
    serializejson_[numpy.uint32] = serializejson_int
    serializejson_[numpy.uint64] = serializejson_int

    def serializejson_float(inst):
        return (inst.__class__, (float(inst),), None)

    serializejson_[numpy.float16] = serializejson_float
    serializejson_[numpy.float32] = serializejson_float
    serializejson_[numpy.float64] = serializejson_float
