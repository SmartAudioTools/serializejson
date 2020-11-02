try:
    import numpy
except ModuleNotFoundError: 
    pass
try:
    from SmartFramework import  numpyB64
    from SmartFramework.serialize.tools import encodedB64,classStrFromClass
    from SmartFramework.serialize import serializeParameters
except :
    from serializejson import numpyB64
    from serializejson.tools import encodedB64,classStrFromClass
    from serializejson import serializeParameters
#from rapidjson import RawJSON
    
    
_numpy_float_types = set(
        (
            numpy.float16,
            numpy.float32,
            numpy.float64,
        )
    )
    
def tuple_from_ndarray(inst):

    instCont = numpy.ascontiguousarray(inst)
    dtype = instCont.dtype
    if dtype.fields is None:
        instContdtype = str(dtype)
        if instContdtype in serializeParameters.numpy_array_readable_max_size : 
            max_size = serializeParameters.numpy_array_readable_max_size[instContdtype]
            if max_size == -1 or instCont.size <= max_size:
                return ("numpy.array", (instCont.tolist(), instContdtype), None)
    else:
        instContdtype = dtype.descr

        #return (numpy.array, (RawJSON(numpy.array2string(instCont,separator =',')), instContdtype), None)  plus lent.
    if instCont.ndim == 1:
        if serializeParameters.numpy_array_use_numpyB64:
            if dtype == bool:
                return (
                    numpyB64,
                    (
                        encodedB64(numpy.packbits(instCont.astype(numpy.uint8))),
                        "bool",
                        len(instCont),
                    ),
                    None,
                )
            else:
                return (numpyB64, (encodedB64(instCont), instContdtype), None)
        else:
            return ("numpy.frombuffer", (bytearray(instCont), instContdtype), None)
    else:

        if serializeParameters.numpy_array_use_numpyB64:
            if dtype == bool:
                return (
                    numpyB64,
                    (
                        encodedB64(numpy.packbits(instCont.astype(numpy.uint8))),
                        "bool",
                        instCont.shape,
                    ),
                    None,
                )
            else:
                return (
                    numpyB64,
                    (encodedB64(instCont), instContdtype, instCont.shape),
                    None,
                )
        else:
            return (
                numpy.ndarray,
                (instCont.shape, instContdtype, bytearray(instCont)),
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
 