import numpy

# import PIL
# import os
objects = {
    "numpy_array": {
        # recarray
        # multidimentional
        # masqued array ( pour avoir equivalent de nan mais pour tableau d'entier ?)
        "numpy_array_empty_bool": numpy.array([], dtype=numpy.bool_),
        "numpy_array_empty_int8": numpy.array([], dtype=numpy.int8),
        "numpy_array_empty_int16": numpy.array([], dtype=numpy.int16),
        "numpy_array_empty_int32": numpy.array([], dtype=numpy.int32),
        "numpy_array_empty_int64": numpy.array([], dtype=numpy.int64),
        "numpy_array_empty_uint8": numpy.array([], dtype=numpy.uint8),
        "numpy_array_empty_uint16": numpy.array([], dtype=numpy.uint16),
        "numpy_array_empty_uint32": numpy.array([], dtype=numpy.uint32),
        "numpy_array_empty_uint64": numpy.array([], dtype=numpy.uint64),
        "numpy_array_empty_float16": numpy.array([], dtype=numpy.float16),
        "numpy_array_empty_float32": numpy.array([], dtype=numpy.float32),
        "numpy_array_empty_float64": numpy.array([], dtype=numpy.float64),
        "numpy_array_one_bool": numpy.array([True], dtype=numpy.bool_),
        "numpy_array_one_int8": numpy.array([1], dtype=numpy.int8),
        "numpy_array_one_int16": numpy.array([1], dtype=numpy.int16),
        "numpy_array_one_int32": numpy.array([1], dtype=numpy.int32),
        "numpy_array_one_int64": numpy.array([1], dtype=numpy.int64),
        "numpy_array_one_uint8": numpy.array([1], dtype=numpy.uint8),
        "numpy_array_one_uint16": numpy.array([1], dtype=numpy.uint16),
        "numpy_array_one_uint32": numpy.array([1], dtype=numpy.uint32),
        "numpy_array_one_uint64": numpy.array([1], dtype=numpy.uint64),
        "numpy_array_one_float16": numpy.array([1], dtype=numpy.float16),
        "numpy_array_one_float32": numpy.array([1], dtype=numpy.float32),
        "numpy_array_one_float64": numpy.array([1], dtype=numpy.float64),
        "numpy_array_bool": numpy.array([False, True], dtype=numpy.bool_),
        "numpy_array_int8": numpy.array([0, 1], dtype=numpy.int8),
        "numpy_array_int16": numpy.array([0, 1], dtype=numpy.int16),
        "numpy_array_int32": numpy.array([0, 1], dtype=numpy.int32),
        "numpy_array_int64": numpy.array([0, 1], dtype=numpy.int64),
        "numpy_array_uint8": numpy.array([0, 1], dtype=numpy.uint8),
        "numpy_array_uint16": numpy.array([0, 1], dtype=numpy.uint16),
        "numpy_array_uint32": numpy.array([0, 1], dtype=numpy.uint32),
        "numpy_array_uint64": numpy.array([0, 1], dtype=numpy.uint64),
        "numpy_array_float16": numpy.array([0, 1], dtype=numpy.float16),
        "numpy_array_float32": numpy.array([0, 1], dtype=numpy.float32),
        "numpy_array_float64": numpy.array([0, 1], dtype=numpy.float64),
        # "numpy_array_uint8_640x480": numpy.zeros((640, 480), dtype=numpy.uint8),
        # "numpy_array_bool_big": numpy.ones(2**15,dtype=numpy.bool_),
        # "numpy_array_uint8_big": numpy.arange(2**15,dtype=numpy.uint8),
        # "numpy_array_int8_big": numpy.ones(2**15,dtype=numpy.int8),
        # "numpy_array_uint16_big": numpy.arange(2**15,dtype=numpy.uint16),
        # "numpy_array_int16_big": numpy.arange(2**15,dtype=numpy.int16),
        # "numpy_array_float16_big": numpy.arange(2**15,dtype=numpy.float16),
        # "numpy_array_int32_big": numpy.arange(2**15,dtype=numpy.int32),
        # "numpy_array_float32_big": numpy.arange(2**15,dtype=numpy.float32),
        # "numpy_array_uint64_big": numpy.arange(2**15,dtype=numpy.uint64),
        # "numpy_array_int64_big": numpy.arange(2**15,dtype=numpy.int64),
        # "numpy_array_float64_big": numpy.arange(2**15,dtype=numpy.float64),
        # "numpy_array_uint32_big": numpy.arange(2**15,dtype=numpy.uint32),
        "numpy_array_vertical_bool": numpy.array([[False, True]], dtype=numpy.bool_),
        "numpy_array_vertical_int8": numpy.array([[0, 1]], dtype=numpy.int8),
        "numpy_array_vertical_int16": numpy.array([[0, 1]], dtype=numpy.int16),
        "numpy_array_vertical_int32": numpy.array([[0, 1]], dtype=numpy.int32),
        "numpy_array_vertical_int64": numpy.array([[0, 1]], dtype=numpy.int64),
        "numpy_array_vertical_uint8": numpy.array([[0, 1]], dtype=numpy.uint8),
        "numpy_array_vertical_uint16": numpy.array([[0, 1]], dtype=numpy.uint16),
        "numpy_array_vertical_uint32": numpy.array([[0, 1]], dtype=numpy.uint32),
        "numpy_array_vertical_uint64": numpy.array([[0, 1]], dtype=numpy.uint64),
        "numpy_array_vertical_float16": numpy.array([[0, 1]], dtype=numpy.float16),
        "numpy_array_vertical_float32": numpy.array([[0, 1]], dtype=numpy.float32),
        "numpy_array_vertical_float64": numpy.array([[0, 1]], dtype=numpy.float64),
        "numpy_array_float64_nan": numpy.array([1.0, numpy.nan]),
        "numpy_array_float64_inf": numpy.array([-numpy.inf, numpy.inf]),
        "numpy_array_2D_bool": numpy.array(
            [[False, True], [False, False]], dtype=numpy.bool_
        ),
        "numpy_array_2D_int8": numpy.array([[0, 1], [2, 3]], dtype=numpy.int8),
        "numpy_array_2D_int16": numpy.array([[0, 1], [2, 3]], dtype=numpy.int16),
        "numpy_array_2D_int32": numpy.array([[0, 1], [2, 3]], dtype=numpy.int32),
        "numpy_array_2D_int64": numpy.array([[0, 1], [2, 3]], dtype=numpy.int64),
        "numpy_array_2D_uint8": numpy.array([[0, 1], [2, 3]], dtype=numpy.uint8),
        "numpy_array_2D_uint8_16x32": numpy.zeros((16, 32), dtype=numpy.uint8),
        "numpy_array_2D_uint16": numpy.array([[0, 1], [2, 3]], dtype=numpy.uint16),
        "numpy_array_2D_uint32": numpy.array([[0, 1], [2, 3]], dtype=numpy.uint32),
        "numpy_array_2D_uint64": numpy.array([[0, 1], [2, 3]], dtype=numpy.uint64),
        "numpy_array_2D_float16": numpy.array([[0, 1], [2, 3]], dtype=numpy.float16),
        "numpy_array_2D_float32": numpy.array([[0, 1], [2, 3]], dtype=numpy.float32),
        "numpy_array_2D_float64": numpy.array([[0, 1], [2, 3]], dtype=numpy.float64),
        "numpy_array_3D_bool": numpy.array(
            [[[False, True], [False, False]], [[True, True], [True, False]]],
            dtype=numpy.bool_,
        ),
        "numpy_array_3D_int8": numpy.array(
            [[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=numpy.int8
        ),
        "numpy_array_3D_int16": numpy.array(
            [[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=numpy.int16
        ),
        "numpy_array_3D_int32": numpy.array(
            [[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=numpy.int32
        ),
        "numpy_array_3D_int64": numpy.array(
            [[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=numpy.int64
        ),
        "numpy_array_3D_uint8": numpy.array(
            [[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=numpy.uint8
        ),
        "numpy_array_3D_uint16": numpy.array(
            [[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=numpy.uint16
        ),
        "numpy_array_3D_uint32": numpy.array(
            [[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=numpy.uint32
        ),
        "numpy_array_3D_uint64": numpy.array(
            [[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=numpy.uint64
        ),
        "numpy_array_3D_float16": numpy.array(
            [[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=numpy.float16
        ),
        "numpy_array_3D_float32": numpy.array(
            [[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=numpy.float32
        ),
        "numpy_array_3D_float64": numpy.array(
            [[[0, 1], [2, 3]], [[4, 5], [6, 7]]], dtype=numpy.float64
        ),
        # "numpy_array_3D_uint8_640x480x3": numpy.asarray(PIL.Image.open(os.path.dirname(__file__)+"/test_image_640x480_color.jpg")),
        # "numpy_array_mixed_bools_ints": numpy.array([False, True, 0, 1]),
        # "numpy_array_mixed_bools_floats": numpy.array([False, True, 0.0, 1.0]),
        # "numpy_array_mixed_ints_floats": numpy.array([0, 1, 0.0, 1.0]),
        # "numpy_array_2D": numpy.array([[1, 2], [3, 4]]),
        # "numpy_array_int16_inf_10": numpy.arange(10, dtype=numpy.int16),
        # "numpy_array_int16_sup_9": numpy.arange(10, 20, dtype=numpy.int16),
        # "numpy_array_int32_inf_9999": numpy.arange(9990, 10000, dtype=numpy.int32),
        # "numpy_array_int32_sup_9999": numpy.arange(10000, 10010, dtype=numpy.int32),
        "tuple_with_array": (9, numpy.array([2]), 1),
    },
    "numpy_dtype": {
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
        "numpy_dtype_float64": numpy.float64,
    },
    "numpy_value": {
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
        "numpy_value_float64": numpy.float64(),
    },
}
