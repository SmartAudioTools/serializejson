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


// ====================================================================

#endif // SERIALIZEJSON_H
