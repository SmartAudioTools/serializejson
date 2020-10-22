
import numpy

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