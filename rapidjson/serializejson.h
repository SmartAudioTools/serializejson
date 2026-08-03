#ifndef SERIALIZEJSON_H
#define SERIALIZEJSON_H

#include <Python.h>
#include <structmember.h>
#include <thread>
#include <atomic>
#include <vector>

// En-têtes blosc2 vendorés (roue python-blosc2) : uniquement pour les TYPES
// (blosc2_cparams...) — aucune édition de liens, tous les appels passent par
// les pointeurs résolus par dlsym dans load_blosc_library().
#include "blosc2_headers/blosc2.h"

// l'en-tête vendoré embarque un print_error statique qui référence
// blosc2_error_string : on fournit un bouchon local (jamais appelé,
// tous les vrais appels passent par dlsym)
extern "C" const char*
blosc2_error_string(int Py_UNUSED(error_code))
{
    return "blosc2 library not linked (serializejson stub)";
}


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


// table de décodage base64 (255 = invalide, 254 = '=')
static inline const unsigned char*
serializejson_b64_decode_table()
{
    static unsigned char table[256];
    static bool ready = false;
    if (!ready) {
        memset(table, 255, 256);
        for (int i = 0; i < 64; i++)
            table[(unsigned char) serializejson_b64_table[i]] = (unsigned char) i;
        table[(unsigned char) '='] = 254;
        ready = true;
    }
    return table;
}

// Décode du base64 strict (sans blancs, padding final) directement en
// PyBytes (as_bytearray=0) ou PyByteArray (1). nullptr SANS exception Python
// si la chaîne n'est pas du base64 propre : l'appelant reprend alors le
// chemin normal.
static PyObject*
serializejson_b64_decode_to_pyobject(const char* src, size_t length,
                                     int as_bytearray)
{
    if (length == 0 || (length % 4) != 0)
        return nullptr;
    const unsigned char* table = serializejson_b64_decode_table();
    size_t padding = 0;
    if (src[length - 1] == '=') {
        padding = (src[length - 2] == '=') ? 2 : 1;
    }
    size_t out_length = length / 4 * 3 - padding;
    PyObject* result = as_bytearray
        ? PyByteArray_FromStringAndSize(nullptr, (Py_ssize_t) out_length)
        : PyBytes_FromStringAndSize(nullptr, (Py_ssize_t) out_length);
    if (result == nullptr)
        return nullptr;
    unsigned char* dst = as_bytearray
        ? (unsigned char*) PyByteArray_AS_STRING(result)
        : (unsigned char*) PyBytes_AS_STRING(result);
    size_t full_groups = (length / 4) - (padding ? 1 : 0);
    const unsigned char* in = (const unsigned char*) src;
    for (size_t group = 0; group < full_groups; group++) {
        unsigned a = table[in[0]], b = table[in[1]],
                 c = table[in[2]], d = table[in[3]];
        if ((a | b | c | d) >= 64) {
            Py_DECREF(result);
            return nullptr;
        }
        unsigned v = (a << 18) | (b << 12) | (c << 6) | d;
        *dst++ = (unsigned char) (v >> 16);
        *dst++ = (unsigned char) (v >> 8);
        *dst++ = (unsigned char) v;
        in += 4;
    }
    if (padding) {
        unsigned a = table[in[0]], b = table[in[1]];
        if (a >= 64 || b >= 64) {
            Py_DECREF(result);
            return nullptr;
        }
        if (padding == 1) {
            unsigned c = table[in[2]];
            if (c >= 64 || in[3] != '=') {
                Py_DECREF(result);
                return nullptr;
            }
            unsigned v = (a << 18) | (b << 12) | (c << 6);
            *dst++ = (unsigned char) (v >> 16);
            *dst++ = (unsigned char) (v >> 8);
        } else {
            if (in[2] != '=' || in[3] != '=') {
                Py_DECREF(result);
                return nullptr;
            }
            *dst++ = (unsigned char) ((a << 2) | (b >> 4));
        }
    }
    return result;
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

// API par contextes de c-blosc2 : chaque contexte est mono-thread, donc
// PUREMENT DÉTERMINISTE — le parallélisme se fait au-dessus, par morceaux
// d'entrée de taille FIXE compressés indépendamment par nos threads et
// concaténés dans l'ordre. Résolue par dlsym ; désactivée si la version
// majeure de la bibliothèque ne correspond pas aux en-têtes vendorés
// (structures passées par valeur).
typedef blosc2_context* (*sj_blosc2_create_cctx_t)(blosc2_cparams);
typedef blosc2_context* (*sj_blosc2_create_dctx_t)(blosc2_dparams);
typedef int  (*sj_blosc2_compress_ctx_t)(blosc2_context*, const void*, int32_t,
                                         void*, int32_t);
typedef int  (*sj_blosc2_decompress_ctx_t)(blosc2_context*, const void*, int32_t,
                                           void*, int32_t);
typedef void (*sj_blosc2_free_ctx_t)(blosc2_context*);
typedef int  (*sj_blosc2_compname_to_compcode_t)(const char*);
typedef void (*sj_blosc1_cbuffer_sizes_t)(const void*, size_t*, size_t*, size_t*);
typedef const char* (*sj_blosc2_get_version_string_t)(void);

static sj_blosc2_create_cctx_t sj_blosc2_create_cctx = nullptr;
static sj_blosc2_create_dctx_t sj_blosc2_create_dctx = nullptr;
static sj_blosc2_compress_ctx_t sj_blosc2_compress_ctx = nullptr;
static sj_blosc2_decompress_ctx_t sj_blosc2_decompress_ctx = nullptr;
static sj_blosc2_free_ctx_t sj_blosc2_free_ctx = nullptr;
static sj_blosc2_compname_to_compcode_t sj_blosc2_compname_to_compcode = nullptr;
static sj_blosc1_cbuffer_sizes_t sj_blosc1_cbuffer_sizes = nullptr;
static bool serializejson_blosc2_ctx_ok = false;

// taille de morceau FIXE : c'est elle qui garantit le déterminisme, quel que
// soit le nombre de threads (ne jamais la faire dépendre de la machine)
#define SERIALIZEJSON_BLOSC_CHUNK (1 << 20)

#define SERIALIZEJSON_BLOSC1_MAX_OVERHEAD 32


// --- compression/décompression parallèles DÉTERMINISTES par morceaux -------
// Morceaux d'entrée de taille fixe, compressés indépendamment par des
// contextes mono-thread (purs), trames concaténées dans l'ordre : les octets
// produits ne dépendent ni du nombre de threads ni de l'ordonnancement.

struct SjCompressJob {
    const char* src;
    int32_t srcsize;
    char* dest;
    int32_t destcap;
    int result;
};

static void
sj_compress_worker(std::vector<SjCompressJob>* jobs, std::atomic<size_t>* next,
                   blosc2_cparams cparams)
{
    blosc2_context* ctx = sj_blosc2_create_cctx(cparams);
    while (true) {
        size_t index = next->fetch_add(1);
        if (index >= jobs->size())
            break;
        SjCompressJob& job = (*jobs)[index];
        job.result = (ctx == nullptr)
            ? -1000
            : sj_blosc2_compress_ctx(ctx, job.src, job.srcsize,
                                     job.dest, job.destcap);
    }
    if (ctx != nullptr)
        sj_blosc2_free_ctx(ctx);
}

// Retourne un buffer malloc (à libérer par l'appelant), sa taille et le
// nombre de trames ; nullptr en cas d'échec, sans exception Python.
static char*
sj_compress_chunks(const char* src, size_t length, size_t typesize, int clevel,
                   int shuffle, const char* cname, int nthreads,
                   size_t* out_size, long* out_frames)
{
    int compcode = sj_blosc2_compname_to_compcode(cname);
    if (compcode < 0)
        return nullptr;
    const size_t chunk = SERIALIZEJSON_BLOSC_CHUNK;
    size_t count = (length + chunk - 1) / chunk;
    size_t stride = chunk + BLOSC2_MAX_OVERHEAD;
    char* scratch = (char*) malloc(count * stride);
    if (scratch == nullptr)
        return nullptr;
    std::vector<SjCompressJob> jobs(count);
    for (size_t i = 0; i < count; i++) {
        size_t offset = i * chunk;
        size_t size = (offset + chunk <= length) ? chunk : (length - offset);
        jobs[i] = {src + offset, (int32_t) size, scratch + i * stride,
                   (int32_t) stride, 0};
    }
    blosc2_cparams cparams = BLOSC2_CPARAMS_DEFAULTS;
    cparams.compcode = (uint8_t) compcode;
    cparams.clevel = (uint8_t) clevel;
    cparams.typesize = (int32_t) typesize;
    cparams.nthreads = 1;  // c'est LUI qui garantit le déterminisme
    for (int f = 0; f < BLOSC2_MAX_FILTERS; f++)
        cparams.filters[f] = BLOSC_NOFILTER;
    cparams.filters[BLOSC2_MAX_FILTERS - 1] =
        shuffle ? BLOSC_SHUFFLE : BLOSC_NOFILTER;
    if (nthreads > (int) count)
        nthreads = (int) count;
    std::atomic<size_t> next(0);
    std::vector<std::thread> threads;
    for (int t = 1; t < nthreads; t++)
        threads.emplace_back(sj_compress_worker, &jobs, &next, cparams);
    sj_compress_worker(&jobs, &next, cparams);
    for (std::thread& worker : threads)
        worker.join();
    size_t total = 0;
    for (SjCompressJob& job : jobs) {
        if (job.result <= 0) {
            free(scratch);
            return nullptr;
        }
        total += (size_t) job.result;
    }
    char* out = (char*) malloc(total);
    if (out == nullptr) {
        free(scratch);
        return nullptr;
    }
    char* cursor = out;
    for (SjCompressJob& job : jobs) {
        memcpy(cursor, job.dest, (size_t) job.result);
        cursor += job.result;
    }
    free(scratch);
    *out_size = total;
    *out_frames = (long) count;
    return out;
}


struct SjDecompressJob {
    const char* src;
    int32_t srcsize;
    char* dest;
    int32_t destsize;
    int result;
};

static void
sj_decompress_worker(std::vector<SjDecompressJob>* jobs, std::atomic<size_t>* next)
{
    blosc2_dparams dparams = BLOSC2_DPARAMS_DEFAULTS;
    dparams.nthreads = 1;
    blosc2_context* ctx = sj_blosc2_create_dctx(dparams);
    while (true) {
        size_t index = next->fetch_add(1);
        if (index >= jobs->size())
            break;
        SjDecompressJob& job = (*jobs)[index];
        job.result = (ctx == nullptr)
            ? -1000
            : sj_blosc2_decompress_ctx(ctx, job.src, job.srcsize,
                                       job.dest, job.destsize);
    }
    if (ctx != nullptr)
        sj_blosc2_free_ctx(ctx);
}


typedef struct {
    PyObject_HEAD
    char* data;          // trame compressée, possédée par l'objet (free au dealloc)
    Py_ssize_t size;
    long frames;         // 1 : trame unique ; > 1 : morceaux concaténés
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
        "nthreads",
        nullptr
    };
    PyObject* value = nullptr;
    Py_ssize_t typesize = 1;
    int clevel = 5;
    int shuffle = 1;
    const char* cname = "blosclz";
    int nthreads = 1;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|niisi", (char**) kwlist,
                                     &value, &typesize, &clevel, &shuffle,
                                     &cname, &nthreads))
        return nullptr;

    if (serializejson_blosc1_compress == nullptr) {
        PyErr_SetString(PyExc_RuntimeError,
                        "blosc library not loaded (call load_blosc_library first)");
        return nullptr;
    }

    Py_buffer view;
    if (PyObject_GetBuffer(value, &view, PyBUF_CONTIG_RO) != 0)
        return nullptr;

    // compression parallèle DÉTERMINISTE par morceaux : que si plusieurs
    // morceaux pleins et l'API par contextes disponible ; sinon trame unique
    if (nthreads > 1 && serializejson_blosc2_ctx_ok
        && (size_t) view.len > SERIALIZEJSON_BLOSC_CHUNK) {
        size_t chunked_size = 0;
        long frames = 0;
        char* chunked;
        Py_BEGIN_ALLOW_THREADS
        chunked = sj_compress_chunks((const char*) view.buf, (size_t) view.len,
                                     (size_t) typesize, clevel, shuffle, cname,
                                     nthreads, &chunked_size, &frames);
        Py_END_ALLOW_THREADS
        PyBuffer_Release(&view);
        if (chunked == nullptr) {
            PyErr_Format(PyExc_ValueError,
                         "blosc chunked compression failed (%s)", cname);
            return nullptr;
        }
        PyObject* self = type->tp_alloc(type, 0);
        if (self == nullptr) {
            free(chunked);
            return nullptr;
        }
        ((BloscToBase64*) self)->data = chunked;
        ((BloscToBase64*) self)->size = (Py_ssize_t) chunked_size;
        ((BloscToBase64*) self)->frames = frames;
        return self;
    }

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
    ((BloscToBase64*) self)->frames = 1;

    return self;
}

static PyMemberDef BloscToBase64_members[] = {
    {"compressed_size",
     T_PYSSIZET, offsetof(BloscToBase64, size), READONLY,
     "size of the compressed frame, to compare with the original size"},
    {"frames",
     T_LONG, offsetof(BloscToBase64, frames), READONLY,
     "1: single frame; > 1: ordered chunked frames (deterministic parallel)"},
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
