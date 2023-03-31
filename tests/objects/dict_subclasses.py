class C_MyDict(dict):
    def __getnewargs__(self):
        return ({"c": 1},)


myDict = C_MyDict({"a": 1})
myDict_with_attr = C_MyDict({"a": 1})
myDict_with_attr.new_att = 5
myDict_non_str_keys = C_MyDict({1: 1})
myDict_non_str_keys_with_attr = C_MyDict({1: 1})
myDict_non_str_keys_with_attr.new_att = 8


objects = {
    "dict_subclass": {
        "dict_subclass": myDict,
        "dict_subclass_with_attr": myDict_with_attr,
        "dict_subclass_non_str_key": myDict_non_str_keys,
        "dict_subclass_non_str_key_with_attr": myDict_non_str_keys_with_attr,
    }
}
