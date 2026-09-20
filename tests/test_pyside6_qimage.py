"""QImage : aller-retour par le greffon Qt, et conversions d'image_conversion.

Trois defauts trouves ici, tous anterieurs au passage a qtpy6 mais rendus
visibles par defaut sous PySide :

- constBits() rend un sip.voidptr a dimensionner sous PyQt, un memoryview deja
  dimensionne sous PySide (AttributeError: 'memoryview' object has no attribute
  'setsize') ;
- le pas des lignes (bytesPerLine) etait ignore : toute image dont la largeur
  utile n'est pas un multiple de 4 octets (Grayscale8 / RGB888 / RGB16 de 5
  pixels) se relisait DECALEE, en silence ;
- QImage_to_numpy affectait un attribut sur un ndarray nu, et numpy_to_QImage
  multipliait un uint8 par 65793 (refuse par numpy >= 2).
"""

import pytest

pytest.importorskip("PySide6")
numpy = pytest.importorskip("numpy")

import serializejson  # noqa: E402
from serializejson.plugins import serializejson_PyQt5_PySide2 as greffon  # noqa: E402

pytestmark = pytest.mark.skipif(greffon.API is None, reason="aucune API Qt")

QtGui = greffon.QtGui


def _image(width, height, format_):
    """Image remplie d'un degrade : toute erreur de pas decale les lignes."""
    image = QtGui.QImage(width, height, format_)
    image.fill(0)
    for y in range(height):
        for x in range(width):
            image.setPixelColor(x, y, QtGui.QColor(11 * x + 1, 7 * y + 3, 5 * x + 3 * y + 5))
    return image


def _octets(image):
    from serializejson._smartframework.image.image_conversion import _octets_image

    return _octets_image(image)


def _aller_retour(image):
    return serializejson.loads(
        serializejson.dumps(image), authorized_classes=["QtGui.QImage"]
    )


@pytest.mark.parametrize(
    "format_",
    [
        QtGui.QImage.Format_ARGB32,
        QtGui.QImage.Format_RGB32,
        QtGui.QImage.Format_RGB888,
        QtGui.QImage.Format_RGB16,
        QtGui.QImage.Format_Grayscale8,
    ],
)
@pytest.mark.parametrize("width", [4, 5])  # 5 : largeur utile non alignee sur 32 bits
def test_qimage_aller_retour(format_, width):
    image = _image(width, 3, format_)
    relue = _aller_retour(image)

    assert isinstance(relue, QtGui.QImage)
    assert (relue.width(), relue.height()) == (width, 3)
    assert relue.format() == image.format()
    assert relue == image  # compare le contenu, pas les adresses


def test_qimage_octets_suivent_le_pas_des_lignes():
    """Grayscale8 de 5 pixels : 8 octets par ligne, pas 5."""
    image = _image(5, 3, QtGui.QImage.Format_Grayscale8)
    assert image.bytesPerLine() == 8
    assert len(_octets(image)) == 8 * 3


def test_qimage_pas_etranger_redecoupe():
    """Une QImage batie sur un tampon au pas impose est remise au pas aligne,
    seul pas que QImage(bytes, width, height, format) suppose a la relecture."""
    pas = 16
    donnees = bytes((y * pas + x) % 256 for y in range(3) for x in range(pas))
    image = QtGui.QImage(donnees, 5, 3, pas, QtGui.QImage.Format_Grayscale8)
    assert image.bytesPerLine() == pas

    octets = _octets(image)
    assert len(octets) == 8 * 3
    assert octets == b"".join(donnees[y * pas : y * pas + 8] for y in range(3))
    assert _aller_retour(image) == image


def test_qimage_vide():
    vide = QtGui.QImage()
    assert _octets(vide) == b""
    relue = _aller_retour(vide)
    assert relue.isNull()


def test_qimage_indexed8_octets_conserves():
    """Le json ne porte que (octets, largeur, hauteur, format) : la table de
    couleurs d'une image indexee n'est PAS transportee, les octets si."""
    image = QtGui.QImage(5, 3, QtGui.QImage.Format_Indexed8)
    image.setColorTable([QtGui.qRgb(i, i, i) for i in range(256)])
    for y in range(3):
        for x in range(5):
            image.setPixel(x, y, (3 * x + 7 * y) % 256)

    relue = _aller_retour(image)
    assert relue.format() == image.format()
    assert _octets(relue) == _octets(image)
    assert relue.colorTable() != image.colorTable()  # limite connue


def test_qimage_to_compressed_bytes():
    from serializejson._smartframework.image.image_conversion import QImage_to_compressed_bytes

    image = _image(4, 3, QtGui.QImage.Format_ARGB32)
    donnees = QImage_to_compressed_bytes(image, "PNG")

    assert isinstance(donnees, bytes)
    assert donnees[:8] == b"\x89PNG\r\n\x1a\n"
    relue = QtGui.QImage.fromData(donnees)
    assert (relue.width(), relue.height()) == (4, 3)
    for y in range(3):
        for x in range(4):
            assert relue.pixelColor(x, y) == image.pixelColor(x, y)


def test_qimage_to_numpy():
    from serializejson._smartframework.image.image_conversion import QImage_to_numpy

    image = _image(4, 3, QtGui.QImage.Format_ARGB32)
    tableau = QImage_to_numpy(image)

    assert tableau.shape == (3, 4, 4)
    assert tableau.dtype == numpy.uint8
    assert tableau.QImage is not None  # reference gardee : le tampon lui appartient
    for y in range(3):
        for x in range(4):
            bleu, vert, rouge, _ = tableau[y, x]  # RGB32 : BGRX en memoire
            assert (rouge, vert, bleu) == image.pixelColor(x, y).getRgb()[:3]


@pytest.mark.parametrize(
    "forme, format_demande, format_attendu",
    [
        ((3, 4), None, QtGui.QImage.Format_Indexed8),
        ((3, 4), QtGui.QImage.Format_Indexed8, QtGui.QImage.Format_Indexed8),
        ((3, 4), QtGui.QImage.Format_RGB32, QtGui.QImage.Format_RGB32),
        ((3, 4), QtGui.QImage.Format_ARGB32, QtGui.QImage.Format_ARGB32),
        ((3, 4, 3), None, QtGui.QImage.Format_RGB32),
        ((3, 4, 4), None, QtGui.QImage.Format_ARGB32),
    ],
)
def test_numpy_to_qimage(forme, format_demande, format_attendu):
    from serializejson._smartframework.image.image_conversion import numpy_to_QImage

    tableau = numpy.arange(numpy.prod(forme), dtype=numpy.uint8).reshape(forme)
    image = numpy_to_QImage(tableau, format_demande)

    assert (image.width(), image.height()) == (forme[1], forme[0])
    assert image.format() == format_attendu
    if len(forme) == 2 and format_attendu is not QtGui.QImage.Format_Indexed8:
        gris = int(tableau[1, 2])
        assert image.pixelColor(2, 1).getRgb()[:3] == (gris, gris, gris)
    elif len(forme) == 3:
        rouge, vert, bleu = (int(v) for v in tableau[1, 2][:3])
        assert image.pixelColor(2, 1).getRgb()[:3] == (bleu, vert, rouge)  # BGR en memoire


@pytest.mark.parametrize("forme", [(3,), (3, 4, 5)])
def test_numpy_to_qimage_refuse_les_autres_formes(forme):
    from serializejson._smartframework.image.image_conversion import numpy_to_QImage

    tableau = numpy.zeros(forme, dtype=numpy.uint8)
    with pytest.raises(ValueError):
        numpy_to_QImage(tableau)
