import collections

Point = collections.namedtuple("Point", ["x", "y"])


objects = {"tuple_subclasses": {"namedtuple": Point(11, y=22)}}
