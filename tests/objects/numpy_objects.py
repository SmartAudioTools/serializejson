import numpy
objects = {
    "numpy" :   {
        # recarray
        # multidimentional
        # masqued array ( pour avoir equivalent de nan mais pour tableau d'entier ?)
        "empty": numpy.array([]),
        "bools": numpy.array([False, True]),
        "ints_01": numpy.array([0, 1]),
        "ints_pos": numpy.array([2, 3]),
        "ints_neg": numpy.array([-2, -3]),
        "ints_nan": numpy.array([1, numpy.nan]),
        "floats_01": numpy.array([0.0, 1.0]),
        "floats_pos": numpy.array([2.0, 3.0]),
        "floats_neg": numpy.array([-2.0, -3.0]),
        "floats_nan": numpy.array([1.0, numpy.nan]),
        "floats_inf": numpy.array([-numpy.inf, numpy.inf]),
        "mixed_bools_ints": numpy.array([False, True, 0, 1]),
        "mixed_bools_floats": numpy.array([False, True, 0.0, 1.0]),
        "mixed_ints_floats": numpy.array([0, 1, 0.0, 1.0]),
        "in_tuple_array": (9, numpy.array([2]), 1),
        "2D_array": numpy.array([[1, 2], [3, 4]]),
        "int16_inf_10": numpy.arange(10, dtype=numpy.int16),
        "int16_sup_9": numpy.arange(10, 20, dtype=numpy.int16),
        "int16_inf_9999": numpy.arange(9990, 10000, dtype=numpy.int32),
        "int16_sup_9999": numpy.arange(10000, 10010, dtype=numpy.int32),
    }
}