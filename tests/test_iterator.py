import os

try:
    import SmartFramework.serialize.serializejson as serializejson
except ImportError:
    import serializejson


def test_iterator():
    path = "my_list.json"
    if os.path.exists(path):
        os.remove(path)
    encoder = serializejson.Encoder(path, indent=None)
    elements = [False, True, 1, 2, "coucou", [1, 2]]
    for element in elements:
        encoder.append(element)
    print(open("my_list.json").read())
    for element, loaded_element in zip(elements, serializejson.Decoder(path)):
        assert element == loaded_element
        print(loaded_element)


if __name__ == "__main__":
    test_iterator()
