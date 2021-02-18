import numpy
from qtpy.QtGui import QImage
from qtpy.QtCore import QByteArray, QBuffer, QIODevice

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


# @profile
def QImage_to_bytes_width_height_format(qimage):
    """Converts a QImage into raw bytes,width,height,format tuple
    with format one of the enum QImage::Format

    To reconstruct the QImage :
    image = QImage(bytes,width,height,format)
    """
    width = qimage.width()
    height = qimage.height()
    format_ = qimage.format()
    ptr = qimage.constBits()
    if ptr is None:
        return b"", width, height, format_
    ptr.setsize(width * height * int(QImage_format_bits[format_] / 8))
    return bytes(ptr), width, height, format_


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


def QImage_to_numpy(qimage):
    """  Converts a QImage into an opencv MAT format  """
    qimage = qimage.convertToFormat(QImage.Format.Format_RGB32)
    width = qimage.width()
    height = qimage.height()
    format_ = qimage.format()
    ptr = qimage.constBits()
    ptr.setsize(width * height * int(QImage_format_bits[format_] / 8))
    array = numpy.frombuffer(ptr, numpy.uint8).reshape((height, width, 4))
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
            bgrx = numpy.require(array * 65793, numpy.uint32, "C")  # 0.7 a 0.9 msec (65793    = (1<<16)+(1<<8)+1)
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
