from .log import log


class C_new:
    def __new__(cls, *args, **kwargs):
        log("__new__", args, kwargs)
        return object.__new__(cls)


class C_init:
    def __init__(self, *args):
        log("__init__", args)


class C_reduce:
    def __reduce__(self):
        log("__reduce__")
        return self.__class__, tuple(), None


class C_getnewargs:
    def __getnewargs__(self):
        log("__getnewargs__")
        return tuple()


class C_new_init:
    def __new__(cls, *args, **kwargs):
        log("__new__", args, kwargs)
        return object.__new__(cls)

    def __init__(self, *args):
        log("__init__", args)


class C_new_reduce:
    def __new__(cls, *args, **kwargs):
        log("__new__", args, kwargs)
        return object.__new__(cls)

    def __reduce__(self):
        log("__reduce__")
        return self.__class__, (3, 4), None


class C_new_getnewargs:
    def __new__(cls, *args, **kwargs):
        log("__new__", args, kwargs)
        return object.__new__(cls)

    def __getnewargs__(self):
        log("__getnewargs__")
        return (5, 6)


class C_init_reduce:
    def __init__(self, *args):
        log("__init__", args)

    def __reduce__(self):
        log("__reduce__")
        return self.__class__, (3, 4), None


class C_init_getnewargs:
    def __init__(self, *args):
        log("__init__", args)

    def __getnewargs__(self):
        log("__getnewargs__")
        return (5, 6)


class C_reduce_getnewargs:
    def __reduce__(self):
        log("__reduce__")
        return self.__class__, tuple(), None

    def __getnewargs__(self):
        log("__getnewargs__")
        return tuple()


class C_new_init_reduce:
    def __new__(cls, *args, **kwargs):
        log("__new__", args, kwargs)
        return object.__new__(cls)

    def __init__(self, *args):
        log("__init__", args)

    def __reduce__(self):
        log("__reduce__")
        return self.__class__, (3, 4), None


class C_new_init_getnewargs:
    def __new__(cls, *args, **kwargs):
        log("__new__", args, kwargs)
        return object.__new__(cls)

    def __init__(self, *args):
        log("__init__", args)

    def __getnewargs__(self):
        log("__getnewargs__")
        return (5, 6)


class C_new_reduce_getnewargs:
    def __new__(cls, *args, **kwargs):
        log("__new__", args, kwargs)
        return object.__new__(cls)

    def __reduce__(self):
        log("__reduce__")
        return self.__class__, (3, 4), None

    def __getnewargs__(self):
        log("__getnewargs__")
        return (5, 6)


class C_init_reduce_getnewargs:
    def __init__(self, *args):
        log("__init__", args)

    def __reduce__(self):
        log("__reduce__")
        return self.__class__, (3, 4), None

    def __getnewargs__(self):
        log("__getnewargs__")
        return (5, 6)


class C_new_init_reduce_getnewargs:
    def __new__(cls, *args, **kwargs):
        log("__new__", args, kwargs)
        return object.__new__(cls)

    def __init__(self, *args):
        log("__init__", args)

    def __reduce__(self):
        log("__reduce__")
        return self.__class__, (3, 4), None

    def __getnewargs__(self):
        log("__getnewargs__")
        return (5, 6)
