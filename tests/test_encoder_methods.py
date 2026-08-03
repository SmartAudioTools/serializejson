import os

import serializejson


def test_dumps_dumpb_per_call_return_bytes():
    # le return_bytes par appel prime sur celui du constructeur
    # (régression de la migration : il était ignoré, dumps rendait des bytes)
    obj = {"a": 1, "b": [1.5, "x"]}
    for constructor_return_bytes in (False, True):
        encoder = serializejson.Encoder(return_bytes=constructor_return_bytes)
        assert type(encoder.dumps(obj)) is str
        assert type(encoder.dumpb(obj)) is bytes
        assert encoder.dumps(obj).encode() == encoder.dumpb(obj)
        # sans argument, celui du constructeur s'applique
        assert type(encoder(obj)) is (bytes if constructor_return_bytes else str)


def test_dump_to_file(tmp_path):
    # régression de la migration : dump() passait chunk_size au __call__
    # Python qui ne l'acceptait pas (TypeError)
    path = str(tmp_path / "dumped.json")
    obj = {"a": 1, "liste": [1, 2, 3]}
    encoder = serializejson.Encoder()
    encoder.dump(obj, path)
    assert serializejson.load(path) == obj


def test_call_protocol_state():
    # les attributs volatils posés par le protocole C du __call__ :
    # dumped_classes accessible après le dump, mémo des doublons remis à
    # zéro entre deux appels
    class Something:
        pass

    encoder = serializejson.Encoder(return_bytes=True)
    encoder(Something())
    assert any("Something" in c for c in encoder.get_dumped_classes())
    shared = [1, 2]
    first = encoder({"m": shared, "n": shared})
    assert first.count(b"$ref") == 1
    # même objet re-dumpé : le mémo ne doit pas se souvenir de l'appel
    assert encoder({"m": shared, "n": shared}) == first


if __name__ == "__main__":
    test_dumps_dumpb_per_call_return_bytes()
    test_dump_to_file(__import__("pathlib").Path(os.environ.get("TMPDIR", "/tmp")))
    test_call_protocol_state()
    print("OK")
