import os

import serializejson


def test_iterator():
    path = "my_list.json"
    if os.path.exists(path):
        os.remove(path)
    encoder = serializejson.Encoder(path, indent=None)
    elements = [False, True, 1, 2, "coucou", [1, 2]]
    for element in elements:
        encoder.append(element)
    # le fichier n'est un json complet qu'ici : le tampon de l'encodeur garde
    # le dernier maillon et le crochet fermant jusqu'à la fermeture. Avant, la
    # relecture anticipée voyait un document TRONQUÉ et zip() sautait
    # silencieusement le dernier élément — les six sont maintenant comparés
    encoder.close()
    print(open("my_list.json").read())
    for element, loaded_element in zip(elements, serializejson.Decoder(path)):
        assert element == loaded_element
        print(loaded_element)


if __name__ == "__main__":
    test_iterator()
