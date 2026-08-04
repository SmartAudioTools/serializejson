# Les erreurs de parse portent la ligne et la colonne (base 1, colonne en
# caractères) quand l'entrée est en mémoire ; les flux gardent l'offset
# seul (le texte n'est pas retenu).
import io

import pytest

import serializejson


def test_ligne_et_colonne():
    with pytest.raises(ValueError) as excinfo:
        serializejson.loads('{\n\t"a": 1,\n\t"b": [1, 2,,]\n}')
    assert "(line 3, column 13)" in str(excinfo.value)


def test_colonne_en_caracteres_pas_en_octets():
    with pytest.raises(ValueError) as excinfo:
        serializejson.loads('{"clé_accentuée_très_longue": 1, "b": }')
    assert "(line 1, column 39)" in str(excinfo.value)


def test_flux_garde_l_offset_seul():
    with pytest.raises(ValueError) as excinfo:
        serializejson.load(io.BytesIO(b'{\n"a": ,}'))
    message = str(excinfo.value)
    assert "offset 7" in message and "line" not in message
