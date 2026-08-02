#ifndef SERIALIZEJSON_H
#define SERIALIZEJSON_H

#include <Python.h>
#include <structmember.h>


/////////////
// RawString //
/////////////


typedef struct {
    PyObject_HEAD
    PyObject* value;
} RawString;


static void
RawString_dealloc(RawString* self)
{
    Py_XDECREF(self->value);
    Py_TYPE(self)->tp_free((PyObject*) self);
}


static PyObject*
RawString_new(PyTypeObject* type, PyObject* args, PyObject* kwds)
{
    PyObject* self = type->tp_alloc(type, 0);
    static char const* kwlist[] = {
        "value",
        NULL
    };
    PyObject* value = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "U", (char**) kwlist, &value))
        return NULL;

    ((RawString*) self)->value = value;

    Py_INCREF(value);

    return self;
}

static PyMemberDef RawString_members[] = {
    {"value",
     T_OBJECT_EX, offsetof(RawString, value), READONLY,
     "string representing a serialized JSON object"},
    {NULL}  /* Sentinel */
};


PyDoc_STRVAR(RawString_doc,
             "Raw (preserialized) JSON object\n"
             "\n"
             "When rapidjson tries to serialize instances of this class, it will"
             " use their literal `value`. For instance:\n"
             ">>> rapidjson.dumps(RawString('{\"already\": \"serialized\"}'))\n"
             "'{\"already\": \"serialized\"}'");


static PyTypeObject RawString_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "rapidjson.RawString",            /* tp_name */
    sizeof(RawString),                /* tp_basicsize */
    0,                              /* tp_itemsize */
    (destructor) RawString_dealloc,   /* tp_dealloc */
    0,                              /* tp_print */
    0,                              /* tp_getattr */
    0,                              /* tp_setattr */
    0,                              /* tp_compare */
    0,                              /* tp_repr */
    0,                              /* tp_as_number */
    0,                              /* tp_as_sequence */
    0,                              /* tp_as_mapping */
    0,                              /* tp_hash */
    0,                              /* tp_call */
    0,                              /* tp_str */
    0,                              /* tp_getattro */
    0,                              /* tp_setattro */
    0,                              /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,             /* tp_flags */
    RawString_doc,                    /* tp_doc */
    0,                              /* tp_traverse */
    0,                              /* tp_clear */
    0,                              /* tp_richcompare */
    0,                              /* tp_weaklistoffset */
    0,                              /* tp_iter */
    0,                              /* tp_iternext */
    0,                              /* tp_methods */
    RawString_members,                /* tp_members */
    0,                              /* tp_getset */
    0,                              /* tp_base */
    0,                              /* tp_dict */
    0,                              /* tp_descr_get */
    0,                              /* tp_descr_set */
    0,                              /* tp_dictoffset */
    0,                              /* tp_init */
    0,                              /* tp_alloc */
    RawString_new,                    /* tp_new */
};



//////////////////
// RawBytes //
//////////////////


typedef struct {
    PyObject_HEAD
    PyObject* value;
} RawBytes;


static void
RawBytes_dealloc(RawBytes* self)
{
    Py_XDECREF(self->value);
    Py_TYPE(self)->tp_free((PyObject*) self);
}


static PyObject*
RawBytes_new(PyTypeObject* type, PyObject* args, PyObject* kwds)
{
    PyObject* self = type->tp_alloc(type, 0);
    static char const* kwlist[] = {
        "value",
        nullptr
    };
    PyObject* value = nullptr;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "S", (char**) kwlist, &value))
        return nullptr;

    ((RawBytes*) self)->value = value;

    Py_INCREF(value);

    return self;
}

static PyMemberDef RawBytes_members[] = {
    {"value",
     T_OBJECT_EX, offsetof(RawBytes, value), READONLY,
     "string representing a serialized JSON object"},
    {nullptr}  /* Sentinel */
};


PyDoc_STRVAR(RawBytes_doc,
             "Raw (preserialized) JSON object\n"
             "\n"
             "When rapidjson tries to serialize instances of this class, it will"
             " use their literal `value`. For instance:\n"
             ">>> rapidjson.dumps(RawBytes('{\"already\": \"serialized\"}'))\n"
             "'{\"already\": \"serialized\"}'");


static PyTypeObject RawBytes_Type = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "rapidjson.RawBytes",            /* tp_name */
    sizeof(RawBytes),                /* tp_basicsize */
    0,                              /* tp_itemsize */
    (destructor) RawBytes_dealloc,   /* tp_dealloc */
    0,                              /* tp_print */
    0,                              /* tp_getattr */
    0,                              /* tp_setattr */
    0,                              /* tp_compare */
    0,                              /* tp_repr */
    0,                              /* tp_as_number */
    0,                              /* tp_as_sequence */
    0,                              /* tp_as_mapping */
    0,                              /* tp_hash */
    0,                              /* tp_call */
    0,                              /* tp_str */
    0,                              /* tp_getattro */
    0,                              /* tp_setattro */
    0,                              /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,             /* tp_flags */
    RawBytes_doc,                    /* tp_doc */
    0,                              /* tp_traverse */
    0,                              /* tp_clear */
    0,                              /* tp_richcompare */
    0,                              /* tp_weaklistoffset */
    0,                              /* tp_iter */
    0,                              /* tp_iternext */
    0,                              /* tp_methods */
    RawBytes_members,                /* tp_members */
    0,                              /* tp_getset */
    0,                              /* tp_base */
    0,                              /* tp_dict */
    0,                              /* tp_descr_get */
    0,                              /* tp_descr_set */
    0,                              /* tp_dictoffset */
    0,                              /* tp_init */
    0,                              /* tp_alloc */
    RawBytes_new,                    /* tp_new */
};





//////////////////
// RawBytesToPutInQuotes //
//////////////////


typedef struct {
    PyObject_HEAD
    PyObject* value;
} RawBytesToPutInQuotes;


static void
RawBytesToPutInQuotes_dealloc(RawBytesToPutInQuotes* self)
{
    Py_XDECREF(self->value);
    Py_TYPE(self)->tp_free((PyObject*) self);
}


static PyObject*
RawBytesToPutInQuotes_new(PyTypeObject* type, PyObject* args, PyObject* kwds)
{
    PyObject* self = type->tp_alloc(type, 0);
    static char const* kwlist[] = {
        "value",
        nullptr
    };
    PyObject* value = nullptr;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "S", (char**) kwlist, &value))
        return nullptr;

    ((RawBytesToPutInQuotes*) self)->value = value;

    Py_INCREF(value);

    return self;
}

static PyMemberDef RawBytesToPutInQuotes_members[] = {
    {"value",
     T_OBJECT_EX, offsetof(RawBytesToPutInQuotes, value), READONLY,
     "bytes to put in quotes"},
    {nullptr}  /* Sentinel */
};


PyDoc_STRVAR(RawBytesToPutInQuotes_doc,
             "Raw (preserialized) string object\n"
             "\n"
             "When rapidjson tries to serialize instances of this class, it will"
             " use their literal `value` put in quotes. For instance:\n"
             ">>> rapidjson.dumps(RawBytesToPutInQuotes('{\"already\": \"serialized\"}'))\n"
             "'{\"already\": \"serialized\"}'");


static PyTypeObject RawBytesToPutInQuotes_Type = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "rapidjson.RawBytesToPutInQuotes",            /* tp_name */
    sizeof(RawBytesToPutInQuotes),                /* tp_basicsize */
    0,                              /* tp_itemsize */
    (destructor) RawBytesToPutInQuotes_dealloc,   /* tp_dealloc */
    0,                              /* tp_print */
    0,                              /* tp_getattr */
    0,                              /* tp_setattr */
    0,                              /* tp_compare */
    0,                              /* tp_repr */
    0,                              /* tp_as_number */
    0,                              /* tp_as_sequence */
    0,                              /* tp_as_mapping */
    0,                              /* tp_hash */
    0,                              /* tp_call */
    0,                              /* tp_str */
    0,                              /* tp_getattro */
    0,                              /* tp_setattro */
    0,                              /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,             /* tp_flags */
    RawBytesToPutInQuotes_doc,                    /* tp_doc */
    0,                              /* tp_traverse */
    0,                              /* tp_clear */
    0,                              /* tp_richcompare */
    0,                              /* tp_weaklistoffset */
    0,                              /* tp_iter */
    0,                              /* tp_iternext */
    0,                              /* tp_methods */
    RawBytesToPutInQuotes_members,                /* tp_members */
    0,                              /* tp_getset */
    0,                              /* tp_base */
    0,                              /* tp_dict */
    0,                              /* tp_descr_get */
    0,                              /* tp_descr_set */
    0,                              /* tp_dictoffset */
    0,                              /* tp_init */
    0,                              /* tp_alloc */
    RawBytesToPutInQuotes_new,                    /* tp_new */
};



//////////////////
// RawBytesToBase64 //
//////////////////

// Données binaires (tout objet à protocole buffer contigu : bytes, bytearray,
// numpy array...) écrites en base64, entre guillemets, DIRECTEMENT dans le
// buffer de sortie : ni chaîne base64 intermédiaire, ni scan d'échappement.

static const char serializejson_b64_table[65] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

// Encode src[0..n) vers dst et retourne le curseur avancé.
// Pour un encodage par morceaux, n doit être multiple de 3 pour tous les
// appels sauf le dernier (le padding "=" n'est produit qu'en fin de flux).
static inline char*
serializejson_b64_encode(const unsigned char* src, size_t n, char* dst)
{
    size_t i = 0;
    for (; i + 3 <= n; i += 3) {
        unsigned v = ((unsigned) src[i] << 16)
                   | ((unsigned) src[i + 1] << 8)
                   | (unsigned) src[i + 2];
        *dst++ = serializejson_b64_table[(v >> 18) & 63];
        *dst++ = serializejson_b64_table[(v >> 12) & 63];
        *dst++ = serializejson_b64_table[(v >> 6) & 63];
        *dst++ = serializejson_b64_table[v & 63];
    }
    if (i < n) {  // 1 ou 2 octets restants
        unsigned v = (unsigned) src[i] << 16;
        if (i + 1 < n)
            v |= (unsigned) src[i + 1] << 8;
        *dst++ = serializejson_b64_table[(v >> 18) & 63];
        *dst++ = serializejson_b64_table[(v >> 12) & 63];
        *dst++ = (i + 1 < n) ? serializejson_b64_table[(v >> 6) & 63] : '=';
        *dst++ = '=';
    }
    return dst;
}


typedef struct {
    PyObject_HEAD
    PyObject* value;
} RawBytesToBase64;


static void
RawBytesToBase64_dealloc(RawBytesToBase64* self)
{
    Py_XDECREF(self->value);
    Py_TYPE(self)->tp_free((PyObject*) self);
}


static PyObject*
RawBytesToBase64_new(PyTypeObject* type, PyObject* args, PyObject* kwds)
{
    static char const* kwlist[] = {
        "value",
        nullptr
    };
    PyObject* value = nullptr;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O", (char**) kwlist, &value))
        return nullptr;

    if (!PyObject_CheckBuffer(value)) {
        PyErr_SetString(PyExc_TypeError,
                        "RawBytesToBase64 expects a bytes-like object");
        return nullptr;
    }

    PyObject* self = type->tp_alloc(type, 0);
    if (self == nullptr)
        return nullptr;

    ((RawBytesToBase64*) self)->value = value;

    Py_INCREF(value);

    return self;
}

static PyMemberDef RawBytesToBase64_members[] = {
    {"value",
     T_OBJECT_EX, offsetof(RawBytesToBase64, value), READONLY,
     "bytes-like object to write as base64 in quotes"},
    {nullptr}  /* Sentinel */
};


PyDoc_STRVAR(RawBytesToBase64_doc,
             "Bytes-like object written as base64\n"
             "\n"
             "When rapidjson tries to serialize instances of this class, it"
             " base64-encodes their `value` straight into the output buffer,"
             " between quotes, without intermediate base64 string.");


static PyTypeObject RawBytesToBase64_Type = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "rapidjson.RawBytesToBase64",            /* tp_name */
    sizeof(RawBytesToBase64),                /* tp_basicsize */
    0,                              /* tp_itemsize */
    (destructor) RawBytesToBase64_dealloc,   /* tp_dealloc */
    0,                              /* tp_print */
    0,                              /* tp_getattr */
    0,                              /* tp_setattr */
    0,                              /* tp_compare */
    0,                              /* tp_repr */
    0,                              /* tp_as_number */
    0,                              /* tp_as_sequence */
    0,                              /* tp_as_mapping */
    0,                              /* tp_hash */
    0,                              /* tp_call */
    0,                              /* tp_str */
    0,                              /* tp_getattro */
    0,                              /* tp_setattro */
    0,                              /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,             /* tp_flags */
    RawBytesToBase64_doc,                    /* tp_doc */
    0,                              /* tp_traverse */
    0,                              /* tp_clear */
    0,                              /* tp_richcompare */
    0,                              /* tp_weaklistoffset */
    0,                              /* tp_iter */
    0,                              /* tp_iternext */
    0,                              /* tp_methods */
    RawBytesToBase64_members,                /* tp_members */
    0,                              /* tp_getset */
    0,                              /* tp_base */
    0,                              /* tp_dict */
    0,                              /* tp_descr_get */
    0,                              /* tp_descr_set */
    0,                              /* tp_dictoffset */
    0,                              /* tp_init */
    0,                              /* tp_alloc */
    RawBytesToBase64_new,                    /* tp_new */
};


//////////////////
// BloscToBase64 //
//////////////////

// Compression blosc faite en C, sans repasser par Python : la bibliothèque
// libblosc2 (celle de la roue python-blosc2, ou du système) est chargée à
// l'exécution par rapidjson.load_blosc_library(path) — aucune dépendance de
// compilation ni d'édition de liens. On passe par son API de compatibilité
// blosc1 : les trames produites gardent le format (et l'étiquette "b64_blosc")
// que python-blosc sait déjà relire.

typedef int  (*serializejson_blosc1_compress_t)(int clevel, int doshuffle,
                                                size_t typesize, size_t nbytes,
                                                const void* src, void* dest,
                                                size_t destsize);
typedef int  (*serializejson_blosc1_set_compressor_t)(const char* compname);
typedef int16_t (*serializejson_blosc2_set_nthreads_t)(int16_t nthreads);
typedef void (*serializejson_blosc2_init_t)(void);

static serializejson_blosc1_compress_t serializejson_blosc1_compress = nullptr;
static serializejson_blosc1_set_compressor_t serializejson_blosc1_set_compressor = nullptr;
static serializejson_blosc2_set_nthreads_t serializejson_blosc2_set_nthreads = nullptr;

#define SERIALIZEJSON_BLOSC1_MAX_OVERHEAD 32


typedef struct {
    PyObject_HEAD
    char* data;          // trame compressée, possédée par l'objet (free au dealloc)
    Py_ssize_t size;
} BloscToBase64;


static void
BloscToBase64_dealloc(BloscToBase64* self)
{
    if (self->data != nullptr)
        free(self->data);
    Py_TYPE(self)->tp_free((PyObject*) self);
}


static PyObject*
BloscToBase64_new(PyTypeObject* type, PyObject* args, PyObject* kwds)
{
    static char const* kwlist[] = {
        "value",
        "typesize",
        "clevel",
        "shuffle",
        "cname",
        nullptr
    };
    PyObject* value = nullptr;
    Py_ssize_t typesize = 1;
    int clevel = 5;
    int shuffle = 1;
    const char* cname = "blosclz";

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|niis", (char**) kwlist,
                                     &value, &typesize, &clevel, &shuffle,
                                     &cname))
        return nullptr;

    if (serializejson_blosc1_compress == nullptr) {
        PyErr_SetString(PyExc_RuntimeError,
                        "blosc library not loaded (call load_blosc_library first)");
        return nullptr;
    }

    Py_buffer view;
    if (PyObject_GetBuffer(value, &view, PyBUF_CONTIG_RO) != 0)
        return nullptr;

    if (serializejson_blosc1_set_compressor(cname) < 0) {
        PyBuffer_Release(&view);
        PyErr_Format(PyExc_ValueError, "unknown blosc compressor '%s'", cname);
        return nullptr;
    }

    size_t dest_size = (size_t) view.len + SERIALIZEJSON_BLOSC1_MAX_OVERHEAD;
    char* dest = (char*) malloc(dest_size);
    if (dest == nullptr) {
        PyBuffer_Release(&view);
        PyErr_NoMemory();
        return nullptr;
    }

    int compressed_size;
    Py_BEGIN_ALLOW_THREADS
    compressed_size = serializejson_blosc1_compress(
        clevel, shuffle, (size_t) typesize, (size_t) view.len,
        view.buf, dest, dest_size);
    Py_END_ALLOW_THREADS
    PyBuffer_Release(&view);

    if (compressed_size <= 0) {
        free(dest);
        PyErr_Format(PyExc_ValueError, "blosc compression failed (%d)",
                     compressed_size);
        return nullptr;
    }

    PyObject* self = type->tp_alloc(type, 0);
    if (self == nullptr) {
        free(dest);
        return nullptr;
    }
    ((BloscToBase64*) self)->data = dest;
    ((BloscToBase64*) self)->size = (Py_ssize_t) compressed_size;

    return self;
}

static PyMemberDef BloscToBase64_members[] = {
    {"compressed_size",
     T_PYSSIZET, offsetof(BloscToBase64, size), READONLY,
     "size of the compressed frame, to compare with the original size"},
    {nullptr}  /* Sentinel */
};


PyDoc_STRVAR(BloscToBase64_doc,
             "Buffer compressed with blosc in C at construction time, written"
             " as base64 straight into the output: no Python round trip, no"
             " intermediate bytes object.");


static PyTypeObject BloscToBase64_Type = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "rapidjson.BloscToBase64",            /* tp_name */
    sizeof(BloscToBase64),                /* tp_basicsize */
    0,                              /* tp_itemsize */
    (destructor) BloscToBase64_dealloc,   /* tp_dealloc */
    0,                              /* tp_print */
    0,                              /* tp_getattr */
    0,                              /* tp_setattr */
    0,                              /* tp_compare */
    0,                              /* tp_repr */
    0,                              /* tp_as_number */
    0,                              /* tp_as_sequence */
    0,                              /* tp_as_mapping */
    0,                              /* tp_hash */
    0,                              /* tp_call */
    0,                              /* tp_str */
    0,                              /* tp_getattro */
    0,                              /* tp_setattro */
    0,                              /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,             /* tp_flags */
    BloscToBase64_doc,                    /* tp_doc */
    0,                              /* tp_traverse */
    0,                              /* tp_clear */
    0,                              /* tp_richcompare */
    0,                              /* tp_weaklistoffset */
    0,                              /* tp_iter */
    0,                              /* tp_iternext */
    0,                              /* tp_methods */
    BloscToBase64_members,                /* tp_members */
    0,                              /* tp_getset */
    0,                              /* tp_base */
    0,                              /* tp_dict */
    0,                              /* tp_descr_get */
    0,                              /* tp_descr_set */
    0,                              /* tp_dictoffset */
    0,                              /* tp_init */
    0,                              /* tp_alloc */
    BloscToBase64_new,                    /* tp_new */
};


//////////////////
// ArrayRows //
//////////////////

// Tableau numérique 1D/2D (protocole buffer C-contigu : tableau numpy...)
// écrit DIRECTEMENT depuis son buffer par l'encodeur C++ : lignes compactes
// [v,v,...], extérieur indenté pour la 2D — sans tolist() ni aucun
// aller-retour Python par élément.

typedef struct {
    PyObject_HEAD
    PyObject* value;
} ArrayRows;


static void
ArrayRows_dealloc(ArrayRows* self)
{
    Py_XDECREF(self->value);
    Py_TYPE(self)->tp_free((PyObject*) self);
}


static PyObject*
ArrayRows_new(PyTypeObject* type, PyObject* args, PyObject* kwds)
{
    static char const* kwlist[] = {
        "value",
        nullptr
    };
    PyObject* value = nullptr;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O", (char**) kwlist, &value))
        return nullptr;

    if (!PyObject_CheckBuffer(value)) {
        PyErr_SetString(PyExc_TypeError, "ArrayRows expects a buffer object");
        return nullptr;
    }

    PyObject* self = type->tp_alloc(type, 0);
    if (self == nullptr)
        return nullptr;

    ((ArrayRows*) self)->value = value;

    Py_INCREF(value);

    return self;
}

static PyMemberDef ArrayRows_members[] = {
    {"value",
     T_OBJECT_EX, offsetof(ArrayRows, value), READONLY,
     "numeric 1D/2D buffer written as readable rows"},
    {nullptr}  /* Sentinel */
};


PyDoc_STRVAR(ArrayRows_doc,
             "Numeric 1D/2D buffer written as human readable rows straight"
             " from its memory: compact [v,v,...] rows, indented outer array"
             " for 2D — no tolist(), no per-element Python round trip.");


static PyTypeObject ArrayRows_Type = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "rapidjson.ArrayRows",            /* tp_name */
    sizeof(ArrayRows),                /* tp_basicsize */
    0,                              /* tp_itemsize */
    (destructor) ArrayRows_dealloc,   /* tp_dealloc */
    0,                              /* tp_print */
    0,                              /* tp_getattr */
    0,                              /* tp_setattr */
    0,                              /* tp_compare */
    0,                              /* tp_repr */
    0,                              /* tp_as_number */
    0,                              /* tp_as_sequence */
    0,                              /* tp_as_mapping */
    0,                              /* tp_hash */
    0,                              /* tp_call */
    0,                              /* tp_str */
    0,                              /* tp_getattro */
    0,                              /* tp_setattro */
    0,                              /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,             /* tp_flags */
    ArrayRows_doc,                    /* tp_doc */
    0,                              /* tp_traverse */
    0,                              /* tp_clear */
    0,                              /* tp_richcompare */
    0,                              /* tp_weaklistoffset */
    0,                              /* tp_iter */
    0,                              /* tp_iternext */
    0,                              /* tp_methods */
    ArrayRows_members,                /* tp_members */
    0,                              /* tp_getset */
    0,                              /* tp_base */
    0,                              /* tp_dict */
    0,                              /* tp_descr_get */
    0,                              /* tp_descr_set */
    0,                              /* tp_dictoffset */
    0,                              /* tp_init */
    0,                              /* tp_alloc */
    ArrayRows_new,                    /* tp_new */
};


//////////////////
// SingleLine //
//////////////////

// Valeur à écrire au format compact (sur une seule ligne) au milieu d'un
// document indenté, par le MÊME encodeur : le mémo des doublons, les hooks et
// le traqueur de chemin restent actifs dans le sous-arbre — contrairement à
// l'ancien contournement qui re-sérialisait la valeur avec un second encodeur
// compact, aveugle aux références déjà sérialisées. number_mode permet de
// surcharger le mode numérique pour le sous-arbre (ex : NM_NATIVE pour les
// lignes de tableaux numpy non flottants).

typedef struct {
    PyObject_HEAD
    PyObject* value;
    long numberMode;   // -1 : pas de surcharge
} SingleLine;


static void
SingleLine_dealloc(SingleLine* self)
{
    Py_XDECREF(self->value);
    Py_TYPE(self)->tp_free((PyObject*) self);
}


static PyObject*
SingleLine_new(PyTypeObject* type, PyObject* args, PyObject* kwds)
{
    static char const* kwlist[] = {
        "value",
        "number_mode",
        nullptr
    };
    PyObject* value = nullptr;
    PyObject* numberModeObj = nullptr;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|O", (char**) kwlist,
                                     &value, &numberModeObj))
        return nullptr;

    long numberMode = -1;
    if (numberModeObj != nullptr && numberModeObj != Py_None) {
        numberMode = PyLong_AsLong(numberModeObj);
        if (numberMode == -1 && PyErr_Occurred())
            return nullptr;
    }

    PyObject* self = type->tp_alloc(type, 0);
    if (self == nullptr)
        return nullptr;

    ((SingleLine*) self)->value = value;
    ((SingleLine*) self)->numberMode = numberMode;

    Py_INCREF(value);

    return self;
}

static PyMemberDef SingleLine_members[] = {
    {"value",
     T_OBJECT_EX, offsetof(SingleLine, value), READONLY,
     "value to write in compact form"},
    {"number_mode",
     T_LONG, offsetof(SingleLine, numberMode), READONLY,
     "number mode override for the subtree (-1: none)"},
    {nullptr}  /* Sentinel */
};


PyDoc_STRVAR(SingleLine_doc,
             "Value written in compact form (single line) inside an indented"
             " document, by the same encoder: duplicates memo, hooks and path"
             " tracking stay active inside the subtree.");


static PyTypeObject SingleLine_Type = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "rapidjson.SingleLine",            /* tp_name */
    sizeof(SingleLine),                /* tp_basicsize */
    0,                              /* tp_itemsize */
    (destructor) SingleLine_dealloc,   /* tp_dealloc */
    0,                              /* tp_print */
    0,                              /* tp_getattr */
    0,                              /* tp_setattr */
    0,                              /* tp_compare */
    0,                              /* tp_repr */
    0,                              /* tp_as_number */
    0,                              /* tp_as_sequence */
    0,                              /* tp_as_mapping */
    0,                              /* tp_hash */
    0,                              /* tp_call */
    0,                              /* tp_str */
    0,                              /* tp_getattro */
    0,                              /* tp_setattro */
    0,                              /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,             /* tp_flags */
    SingleLine_doc,                    /* tp_doc */
    0,                              /* tp_traverse */
    0,                              /* tp_clear */
    0,                              /* tp_richcompare */
    0,                              /* tp_weaklistoffset */
    0,                              /* tp_iter */
    0,                              /* tp_iternext */
    0,                              /* tp_methods */
    SingleLine_members,                /* tp_members */
    0,                              /* tp_getset */
    0,                              /* tp_base */
    0,                              /* tp_dict */
    0,                              /* tp_descr_get */
    0,                              /* tp_descr_set */
    0,                              /* tp_dictoffset */
    0,                              /* tp_init */
    0,                              /* tp_alloc */
    SingleLine_new,                    /* tp_new */
};


// ====================================================================

#endif // SERIALIZEJSON_H
