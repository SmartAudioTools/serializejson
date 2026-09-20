import numpy

# QtGui et QtCore publies par le greffon Qt de serializejson (seul importateur
# de ce module) : son binding, quel qu'il soit, plutot qu'un second choisi ici.
from QtGui import QImage
from QtCore import QByteArray, QBuffer, QIODevice

grayTable = [(255 << 24) + (g << 16) + (g << 8) + g for g in range(256)]

QImage_format_bits = {
    QImage.Format_Invalid: 8,
    QImage.Format_Mono: 1,
    QImage.Format_MonoLSB: 1,
    QImage.Format_Indexed8: 8,
    QImage.Format_RGB32: 32,
    QImage.Format_ARGB32: 32,
    QImage.Format_ARGB32_Premultiplied: 32,
    QImage.Format_RGB16: 16,
    QImage.Format_ARGB8565_Premultiplied: 24,
    QImage.Format_RGB666: 24,
    QImage.Format_ARGB6666_Premultiplied: 24,
    QImage.Format_RGB555: 16,
    QImage.Format_ARGB8555_Premultiplied: 24,
    QImage.Format_RGB888: 24,
    QImage.Format_RGB444: 16,
    QImage.Format_ARGB4444_Premultiplied: 16,
    QImage.Format_RGBX8888: 32,
    QImage.Format_RGBA8888: 32,
    QImage.Format_RGBA8888_Premultiplied: 32,
    QImage.Format_BGR30: 32,
    QImage.Format_A2BGR30_Premultiplied: 32,
    QImage.Format_RGB30: 32,
    QImage.Format_A2RGB30_Premultiplied: 32,
    QImage.Format_Alpha8: 8,
    QImage.Format_Grayscale8: 8,
    # QImage.Format_Grayscale16 : 16,
    # QImage.Format_RGBX64: 64,
    # QImage.Format_RGBA64: 64,
    # QImage.Format_RGBA64_Premultiplied: 64,
    # QImage.Format_BGR888 : 24,
}



def _pas_aligne(width, format_):
    """Octets par ligne d'une QImage allouee par Qt : largeur utile arrondie au
    multiple de 4 octets. C'est aussi le pas que QImage(bytes, width, height,
    format) suppose a la relecture."""
    return ((width * QImage_format_bits[format_] + 31) // 32) * 4


def _octets_dimensionnes(ptr, taille):
    """constBits() rend un sip.voidptr a dimensionner (PyQt) ou un memoryview
    deja dimensionne sur toute l'image, padding de lignes compris (PySide)."""
    if hasattr(ptr, "setsize"):  # sip.voidptr
        ptr.setsize(taille)
        return ptr
    return ptr[:taille]


def _octets_image(qimage):
    """Octets d'une QImage dans la disposition attendue par
    QImage(bytes, width, height, format) : lignes alignees sur 32 bits.

    bytesPerLine() depasse la largeur utile des que celle-ci n'est pas alignee
    (Grayscale8 de 5 pixels : 8 octets par ligne), et une QImage batie sur un
    tampon etranger porte le pas qu'on lui a donne : ignorer ce pas decalait
    toutes les lignes sauf la premiere.
    """
    ptr = qimage.constBits()
    if ptr is None:
        return b""
    height = qimage.height()
    pas = qimage.bytesPerLine()
    octets = bytes(_octets_dimensionnes(ptr, pas * height))
    pas_attendu = _pas_aligne(qimage.width(), qimage.format())
    if pas == pas_attendu:
        return octets
    utile = min(pas, pas_attendu)
    return b"".join(octets[y * pas : y * pas + utile].ljust(pas_attendu, b"\0") for y in range(height))


# @profile
def QImage_to_bytes_width_height_format(qimage):
    """Converts a QImage into raw bytes,width,height,format tuple
    with format one of the enum QImage::Format

    To reconstruct the QImage :
    image = QImage(bytes,width,height,format)
    """
    return _octets_image(qimage), qimage.width(), qimage.height(), qimage.format()


def QImage_to_compressed_bytes(qimage, format):
    """
    Compress QImage or QPixmap into bytes corresponding to a image file format (BMP,PNG,JPG)

    To reconstruct the QImage or QPixamp :
    image = QImage.fromData(data)
    image = QImage() ; image.loadFromData(data)
    image = QPixmap(); image.loadFromData(data)


    The QImage.format will be preserved when loading only if in format in :
    Format_Mono
    Format_Indexed8
    Format_RGB32
    Format_ARGB32
    Format_Grayscale8

    """
    # https://stackoverflow.com/questions/24965646/convert-pyqt4-qtgui-qimage-object-to-base64-png-data
    # https://stackoverflow.com/questions/57404778/how-to-convert-a-qpixmaps-image-into-a-bytes

    qbytearray = QByteArray()
    qbuffer = QBuffer(qbytearray)
    qbuffer.open(QIODevice.WriteOnly)
    ok = qimage.save(qbuffer, format)
    assert ok
    return qbytearray.data()  # fait une copie ?
    # return qbytearray.toBase64()


class _ArrayQImage(numpy.ndarray):
    """Un ndarray nu n'a pas de __dict__ : porter l'attribut QImage demande une
    sous-classe (sinon AttributeError a l'affectation)."""


def QImage_to_numpy(qimage):
    """  Converts a QImage into an opencv MAT format  """
    qimage = qimage.convertToFormat(QImage.Format.Format_RGB32)
    width = qimage.width()
    height = qimage.height()
    ptr = _octets_dimensionnes(qimage.constBits(), width * height * 4)  # RGB32 : pas deja aligne
    array = numpy.frombuffer(ptr, numpy.uint8).reshape((height, width, 4)).view(_ArrayQImage)
    array.QImage = qimage  # garde une reference pour eviter de predre données si QImage est détruite ?
    return array


def numpy_to_QImage(array, QImage_format=None):
    """
    Transform numpy array into QImage.
    Data copy is avoided if possible.
    The QImage.data attribute contain the underlying numpy array
    to prevent python freeing that memory while the image is in use.
    (same or a copy of the given array, if copy was needed )
    """
    if numpy.ndim(array) == 2:
        h, w = array.shape
        if (QImage_format is None) or (
            QImage_format is QImage.Format_Indexed8
        ):  # lent pour affichage sur QWidget par contre rapide pour QGlWidget
            qimage = QImage(
                numpy.require(array, numpy.uint8, "C").data,
                w,
                h,
                QImage.Format_Indexed8,
            )
            qimage.setColorTable(grayTable)
            qimage.data = array
            return qimage
        elif QImage_format is QImage.Format_RGB32:
            # .astype avant la multiplication : numpy >= 2 refuse de promouvoir un uint8
            bgrx = numpy.require(array.astype(numpy.uint32) * 65793, numpy.uint32, "C")  # (65793 = (1<<16)+(1<<8)+1)
            qimage = QImage(bgrx.data, w, h, QImage.Format_RGB32)
            qimage.data = (
                bgrx  # permet de garder un reference de l'image et lui eviter un destruction qui fait planter PySide2
            )
            return qimage
        elif QImage_format is QImage.Format_ARGB32:
            bgra = numpy.empty((h, w, 4), numpy.uint8, "C")  # 0.01 mec
            bgra[..., 0] = array
            bgra[..., 1] = array  # 0.38 msec
            bgra[..., 2] = array
            bgra[..., 3] = 255
            qimage = QImage(bgra.data, w, h, QImage.Format_ARGB32)
            qimage.data = bgra
            return qimage
    elif numpy.ndim(array) == 3:
        h, w, channels = array.shape
        if channels == 3:
            bgrx = numpy.empty((h, w, 4), numpy.uint8, "C")
            bgrx[..., :3] = array
            qimage = QImage(bgrx.data, w, h, QImage.Format_RGB32)
            qimage.data = bgrx
            return qimage
        elif channels == 4:
            bgrx = numpy.require(array, numpy.uint8, "C")
            qimage = QImage(bgrx.data, w, h, QImage.Format_ARGB32)
            qimage.data = bgrx
            return qimage
        else:
            raise ValueError(
                "Color images can expects the last dimension to contain exactly three (R,G,B) or four (R,G,B,A) channels"
            )
    else:
        raise ValueError("can only convert 2D or 3D arrays")
