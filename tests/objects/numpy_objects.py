import numpy
objects = {
    "numpy_array" :   {
        # recarray
        # multidimentional
        # masqued array ( pour avoir equivalent de nan mais pour tableau d'entier ?)
        "numpy_array_empty": numpy.array([]),
        "numpy_array_bools": numpy.array([False, True]),
        "numpy_array_ints_01": numpy.array([0, 1]),
        "numpy_array_ints_pos": numpy.array([2, 3]),
        "numpy_array_ints_neg": numpy.array([-2, -3]),
        "numpy_array_ints_nan": numpy.array([1, numpy.nan]),
        "numpy_array_floats_01": numpy.array([0.0, 1.0]),
        "numpy_array_floats_pos": numpy.array([2.0, 3.0]),
        "numpy_array_floats_neg": numpy.array([-2.0, -3.0]),
        "numpy_array_floats_nan": numpy.array([1.0, numpy.nan]),
        "numpy_array_floats_inf": numpy.array([-numpy.inf, numpy.inf]),
        "numpy_array_mixed_bools_ints": numpy.array([False, True, 0, 1]),
        "numpy_array_mixed_bools_floats": numpy.array([False, True, 0.0, 1.0]),
        "numpy_array_mixed_ints_floats": numpy.array([0, 1, 0.0, 1.0]),
        "tuple_with_array": (9, numpy.array([2]), 1),
        "numpy_array_2D": numpy.array([[1, 2], [3, 4]]),
        "numpy_array_int16_inf_10": numpy.arange(10, dtype=numpy.int16),
        "numpy_array_int16_sup_9": numpy.arange(10, 20, dtype=numpy.int16),
        "numpy_array_int16_inf_9999": numpy.arange(9990, 10000, dtype=numpy.int32),
        "numpy_array_int16_sup_9999": numpy.arange(10000, 10010, dtype=numpy.int32),
    },
    "numpy_dtype" : {
        "numpy_dtype_bool_": numpy.bool_,
        "numpy_dtype_int8": numpy.int8,
        "numpy_dtype_int16": numpy.int16,
        "numpy_dtype_int32": numpy.int32,
        "numpy_dtype_int64": numpy.int64,
        "numpy_dtype_uint8": numpy.uint8,
        "numpy_dtype_uint16": numpy.uint16,
        "numpy_dtype_uint32": numpy.uint32,
        "numpy_dtype_uint64": numpy.uint64,
        "numpy_dtype_float16": numpy.float16,
        "numpy_dtype_float32": numpy.float32,
        "numpy_dtype_float64": numpy.float64        
    },
    "numpy_value" : {
        "numpy_value_bool_": numpy.bool_(),
        "numpy_value_int8": numpy.int8(),
        "numpy_value_int16": numpy.int16(),
        "numpy_value_int32": numpy.int32(),
        "numpy_value_int64": numpy.int64(),
        "numpy_value_uint8": numpy.uint8(),
        "numpy_value_uint16": numpy.uint16(),
        "numpy_value_uint32": numpy.uint32(),
        "numpy_value_uint64": numpy.uint64(),
        "numpy_value_float16": numpy.float16(),
        "numpy_value_float32": numpy.float32(),
        #"numpy_value_float64": numpy.float64()        
    }
}