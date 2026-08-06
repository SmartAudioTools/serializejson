#ifndef SERIALIZEJSON_H
#define SERIALIZEJSON_H

#include <Python.h>
#include <structmember.h>
#include <thread>
#include <atomic>
#if defined(__SSSE3__)
#include <tmmintrin.h>
#endif
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
#if defined(__SSSE3__)
    // vectorisation pshufb (Mula/aklomp) : 12 octets -> 16 caracteres par
    // iteration. La charge lit 16 octets (4 au-dela des 12 consommes) : on
    // s'arrete des que moins de 16 octets restent, queue scalaire ensuite —
    // regle qui vaut aussi pour les segments paralleles (pas de sur-lecture
    // au-dela du tampon d'entree)
    if (n >= 16) {
        const __m128i shuf = _mm_set_epi8(10, 11, 9, 10, 7, 8, 6, 7,
                                          4, 5, 3, 4, 1, 2, 0, 1);
        const __m128i t0mask = _mm_set1_epi32(0x0fc0fc00);
        const __m128i t1mul  = _mm_set1_epi32(0x04000040);
        const __m128i t2mask = _mm_set1_epi32(0x003f03f0);
        const __m128i t3mul  = _mm_set1_epi32(0x01000010);
        const __m128i lut = _mm_setr_epi8(65, 71, -4, -4, -4, -4, -4, -4,
                                          -4, -4, -4, -4, -19, -16, 0, 0);
        const __m128i c25 = _mm_set1_epi8(25);
        const __m128i c51 = _mm_set1_epi8(51);
        while (i + 16 <= n) {
            __m128i x = _mm_loadu_si128((const __m128i*) (src + i));
            x = _mm_shuffle_epi8(x, shuf);
            __m128i t0 = _mm_and_si128(x, t0mask);
            __m128i t1 = _mm_mulhi_epu16(t0, t1mul);
            __m128i t2 = _mm_and_si128(x, t2mask);
            __m128i t3 = _mm_mullo_epi16(t2, t3mul);
            __m128i sextets = _mm_or_si128(t1, t3);
            __m128i indices = _mm_subs_epu8(sextets, c51);
            __m128i mask = _mm_cmpgt_epi8(sextets, c25);
            indices = _mm_sub_epi8(indices, mask);
            __m128i ascii = _mm_add_epi8(sextets, _mm_shuffle_epi8(lut, indices));
            _mm_storeu_si128((__m128i*) dst, ascii);
            dst += 16;
            i += 12;
        }
    }
#endif
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
static bool
sj_b64_decode_groups_scalar(const unsigned char* in, size_t groups,
                            unsigned char* dst, const unsigned char* table)
{
    for (size_t group = 0; group < groups; group++) {
        unsigned a = table[in[0]], b = table[in[1]],
                 c = table[in[2]], d = table[in[3]];
        if ((a | b | c | d) >= 64)
            return false;
        unsigned v = (a << 18) | (b << 12) | (c << 6) | d;
        *dst++ = (unsigned char) (v >> 16);
        *dst++ = (unsigned char) (v >> 8);
        *dst++ = (unsigned char) v;
        in += 4;
    }
    return true;
}

// validation seule des groupes complets (classification SIMD, pas d'écriture)
static inline bool
sj_b64_validate_groups(const unsigned char* in, size_t groups,
                       const unsigned char* table)
{
    size_t g = 0;
#if defined(__SSSE3__)
    if (groups >= 4) {
        const __m128i lut_lo = _mm_setr_epi8(
            0x15, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11,
            0x11, 0x11, 0x13, 0x1A, 0x1B, 0x1B, 0x1B, 0x1A);
        const __m128i lut_hi = _mm_setr_epi8(
            0x10, 0x10, 0x01, 0x02, 0x04, 0x08, 0x04, 0x08,
            0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10);
        const __m128i mask_0F = _mm_set1_epi8(0x0F);
        while (groups - g >= 4) {
            __m128i str = _mm_loadu_si128((const __m128i*) (in + g * 4));
            __m128i hi_nib = _mm_and_si128(_mm_srli_epi32(str, 4), mask_0F);
            __m128i lo_nib = _mm_and_si128(str, mask_0F);
            __m128i lo = _mm_shuffle_epi8(lut_lo, lo_nib);
            __m128i hi = _mm_shuffle_epi8(lut_hi, hi_nib);
            if (_mm_movemask_epi8(_mm_cmpgt_epi8(_mm_and_si128(lo, hi),
                                                 _mm_setzero_si128())) != 0)
                return false;
            g += 4;
        }
    }
#endif
    for (; g < groups; g++) {
        const unsigned char* q = in + g * 4;
        if ((table[q[0]] | table[q[1]] | table[q[2]] | table[q[3]]) >= 64)
            return false;
    }
    return true;
}

static bool
sj_b64_decode_groups(const unsigned char* in, size_t groups,
                     unsigned char* dst, const unsigned char* table)
{
    size_t g = 0;
#if defined(__SSSE3__)
    // vectorisation pshufb (Mula/aklomp) : 16 caracteres -> 12 octets par
    // iteration (4 groupes). Le store ecrit 16 octets (4 de rebut au-dela
    // des 12 utiles) : il faut 16 octets de place dans NOTRE segment de
    // sortie (jamais dans celui d'un autre thread), soit >= 6 groupes
    // restants ; queue scalaire ensuite. En cas de rejet SIMD, le scalaire
    // est l'arbitre (il revalide et decode le reste).
    if (groups >= 6) {
        const __m128i lut_lo = _mm_setr_epi8(
            0x15, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11,
            0x11, 0x11, 0x13, 0x1A, 0x1B, 0x1B, 0x1B, 0x1A);
        const __m128i lut_hi = _mm_setr_epi8(
            0x10, 0x10, 0x01, 0x02, 0x04, 0x08, 0x04, 0x08,
            0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10);
        const __m128i lut_roll = _mm_setr_epi8(
            0, 16, 19, 4, -65, -65, -71, -71, 0, 0, 0, 0, 0, 0, 0, 0);
        const __m128i mask_2F = _mm_set1_epi8(0x2F);
        const __m128i mask_0F = _mm_set1_epi8(0x0F);
        const __m128i pack1 = _mm_set1_epi32(0x01400140);
        const __m128i pack2 = _mm_set1_epi32(0x00011000);
        const __m128i final_shuf = _mm_setr_epi8(2, 1, 0, 6, 5, 4, 10, 9, 8,
                                                 14, 13, 12, -1, -1, -1, -1);
        while (groups - g >= 6) {
            __m128i str = _mm_loadu_si128((const __m128i*) (in + g * 4));
            __m128i hi_nib = _mm_and_si128(_mm_srli_epi32(str, 4), mask_0F);
            __m128i lo_nib = _mm_and_si128(str, mask_0F);
            __m128i lo = _mm_shuffle_epi8(lut_lo, lo_nib);
            __m128i hi = _mm_shuffle_epi8(lut_hi, hi_nib);
            if (_mm_movemask_epi8(_mm_cmpgt_epi8(_mm_and_si128(lo, hi),
                                                 _mm_setzero_si128())) != 0)
                break;  // caractere suspect : le scalaire tranchera
            __m128i eq_2F = _mm_cmpeq_epi8(str, mask_2F);
            __m128i roll = _mm_shuffle_epi8(lut_roll,
                                            _mm_add_epi8(eq_2F, hi_nib));
            __m128i values = _mm_add_epi8(str, roll);
            __m128i merged = _mm_maddubs_epi16(values, pack1);
            __m128i packed = _mm_madd_epi16(merged, pack2);
            packed = _mm_shuffle_epi8(packed, final_shuf);
            _mm_storeu_si128((__m128i*) (dst + g * 3), packed);
            g += 4;
        }
    }
#endif
    return sj_b64_decode_groups_scalar(in + g * 4, groups - g,
                                       dst + g * 3, table);
}


static inline bool
sj_b64_decode_maybe_parallel(const unsigned char* in, size_t groups,
                             unsigned char* dst, const unsigned char* table)
{
    // seuil : ~3 Mo d'entree (comme l'encodage)
    if (groups < (3u << 20) / 4)
        return sj_b64_decode_groups(in, groups, dst, table);
    size_t hw = std::thread::hardware_concurrency();
    size_t nthreads = hw ? (hw > 8 ? 8 : hw) : 1;
    if (nthreads < 2)
        return sj_b64_decode_groups(in, groups, dst, table);
    // segments fixes de 256k groupes (1 Mo d'entree, 768 Ko de sortie)
    const size_t seg = 1u << 18;
    size_t nsegs = (groups + seg - 1) / seg;
    std::atomic<size_t> next(0);
    std::atomic<bool> ok(true);
    auto work = [&]() {
        for (;;) {
            size_t s = next.fetch_add(1);
            if (s >= nsegs || !ok.load(std::memory_order_relaxed))
                return;
            size_t begin = s * seg;
            size_t n = groups - begin < seg ? groups - begin : seg;
            if (!sj_b64_decode_groups(in + begin * 4, n, dst + begin * 3, table))
                ok.store(false, std::memory_order_relaxed);
        }
    };
    std::vector<std::thread> pool;
    for (size_t t = 1; t < nthreads; t++)
        pool.emplace_back(work);
    work();
    for (std::thread& t : pool)
        t.join();
    return ok.load();
}

// disposition d'une charge base64 stricte : nombre de groupes complets,
// padding, taille décodée — et validation COMPLÈTE des caractères (le
// différé exige de trancher la validité au moment de la mise en file)
static inline bool
sj_b64_layout(const char* src, size_t length, size_t* full_groups,
              size_t* padding, size_t* out_length, const unsigned char* table)
{
    if (length == 0 || (length % 4) != 0)
        return false;
    size_t pad = 0;
    if (src[length - 1] == '=')
        pad = (src[length - 2] == '=') ? 2 : 1;
    size_t groups = length / 4 - (pad ? 1 : 0);
    const unsigned char* in = (const unsigned char*) src;
    if (!sj_b64_validate_groups(in, groups, table))
        return false;
    if (pad) {
        const unsigned char* q = in + groups * 4;
        if ((table[q[0]] | table[q[1]]) >= 64)
            return false;
        if (pad == 1) {
            if (table[q[2]] >= 64 || q[3] != '=')
                return false;
        } else if (q[2] != '=' || q[3] != '=') {
            return false;
        }
    }
    *full_groups = groups;
    *padding = pad;
    *out_length = length / 4 * 3 - pad;
    return true;
}

// décode une charge DÉJÀ validée par sj_b64_layout vers dst
static inline bool
sj_b64_decode_into(const char* src, size_t length, unsigned char* dst,
                   const unsigned char* table)
{
    size_t pad = 0;
    if (src[length - 1] == '=')
        pad = (src[length - 2] == '=') ? 2 : 1;
    size_t groups = length / 4 - (pad ? 1 : 0);
    const unsigned char* in = (const unsigned char*) src;
    if (!sj_b64_decode_groups(in, groups, dst, table))
        return false;
    dst += groups * 3;
    in += groups * 4;
    if (pad) {
        unsigned a = table[in[0]], b = table[in[1]];
        if (a >= 64 || b >= 64)
            return false;
        if (pad == 1) {
            unsigned c = table[in[2]];
            if (c >= 64)
                return false;
            unsigned v = (a << 18) | (b << 12) | (c << 6);
            *dst++ = (unsigned char) (v >> 16);
            *dst++ = (unsigned char) (v >> 8);
        } else {
            *dst++ = (unsigned char) ((a << 2) | (b >> 4));
        }
    }
    return true;
}

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
    // gros payloads : groupes de 4 caracteres decodes en parallele par
    // segments a frontieres fixes (sortie a 3/4 de l'offset d'entree,
    // deterministe) ; GIL relache par l'appelant impossible ici (objets
    // Python crees au-dessus), mais les workers n'en ont pas besoin
    if (!sj_b64_decode_maybe_parallel(in, full_groups, dst, table)) {
        Py_DECREF(result);
        return nullptr;
    }
    dst += full_groups * 3;
    in += full_groups * 4;
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


// encodage base64 PARALLÈLE et déterministe d'un gros buffer : l'entrée est
// découpée sur des multiples de 3 octets, chaque segment s'encode vers son
// offset de sortie exact (4/3 de l'offset d'entrée) — octets identiques au
// chemin séquentiel, quel que soit le nombre de threads
struct SjB64Job {
    const unsigned char* src;
    size_t length;      // multiple de 3, sauf pour le dernier segment
    char* dst;
};

static void
sj_b64_worker(std::vector<SjB64Job>* jobs, std::atomic<size_t>* next)
{
    while (true) {
        size_t index = next->fetch_add(1);
        if (index >= jobs->size())
            break;
        SjB64Job& job = (*jobs)[index];
        serializejson_b64_encode(job.src, job.length, job.dst);
    }
}

#define SERIALIZEJSON_B64_PARALLEL_THRESHOLD (3 << 20)  // 3 Mo

static void
sj_b64_encode_maybe_parallel(const unsigned char* src, size_t length, char* dst)
{
    if (length < SERIALIZEJSON_B64_PARALLEL_THRESHOLD) {
        serializejson_b64_encode(src, length, dst);
        return;
    }
    unsigned hardware = std::thread::hardware_concurrency();
    int nthreads = (int) (hardware ? hardware : 1);
    if (nthreads > 8)
        nthreads = 8;
    // segments de taille fixe multiple de 3 (déterminisme du découpage)
    const size_t segment = ((size_t) 1 << 20) / 3 * 3;  // ~1 Mo
    size_t count = (length + segment - 1) / segment;
    std::vector<SjB64Job> jobs(count);
    for (size_t i = 0; i < count; i++) {
        size_t offset = i * segment;
        size_t size = (offset + segment <= length) ? segment : (length - offset);
        jobs[i] = {src + offset, size, dst + offset / 3 * 4};
    }
    if (nthreads > (int) count)
        nthreads = (int) count;
    std::atomic<size_t> next(0);
    std::vector<std::thread> threads;
    for (int t = 1; t < nthreads; t++)
        threads.emplace_back(sj_b64_worker, &jobs, &next);
    sj_b64_worker(&jobs, &next);
    for (std::thread& worker : threads)
        worker.join();
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
// compilation ni d'édition de liens. Écriture par l'API contextes seulement ;
// la lecture relit aussi les trames blosc1 (v1) via la même bibliothèque.

typedef int16_t (*serializejson_blosc2_set_nthreads_t)(int16_t nthreads);
typedef void (*serializejson_blosc2_init_t)(void);

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

// cache d'UN contexte de compression : sa création (contexte zstd interne)
// domine le coût des petits tampons. Pris/rendu sous GIL — pas de verrou
// dédié ; jamais pour le chemin préfiltre (preparams pointe la pile d'appel).
struct SjCctxKey {
    uint8_t compcode; uint8_t clevel; int32_t typesize;
    int16_t nthreads; int32_t blocksize; uint8_t splitmode;
    uint8_t filters[BLOSC2_MAX_FILTERS];
    uint8_t filters_meta[BLOSC2_MAX_FILTERS];
};
static blosc2_context* sj_cctx_cache = nullptr;
static SjCctxKey sj_cctx_cache_key;

// --- somme de préfixe (défaire une dérivée) ---------------------------------
// scalaire par défaut ; en SSE, préfixe EN REGISTRE par décalages-additions
// puis propagation du report — le scalaire bute sur la chaîne de dépendance
// (~1,5 ns/élément), le vectorisé tourne à la bande passante mémoire
#ifdef RAPIDJSON_SSE42
static void
sj_prefix_u16(uint16_t* d, const uint16_t* s, Py_ssize_t n)
{
    Py_ssize_t i = 0;
    __m128i carry = _mm_setzero_si128();
    for (; i + 8 <= n; i += 8) {
        __m128i v = _mm_loadu_si128((const __m128i*) (s + i));
        v = _mm_add_epi16(v, _mm_slli_si128(v, 2));
        v = _mm_add_epi16(v, _mm_slli_si128(v, 4));
        v = _mm_add_epi16(v, _mm_slli_si128(v, 8));
        v = _mm_add_epi16(v, carry);
        _mm_storeu_si128((__m128i*) (d + i), v);
        carry = _mm_shufflehi_epi16(v, _MM_SHUFFLE(3, 3, 3, 3));
        carry = _mm_unpackhi_epi64(carry, carry);
    }
    uint16_t last = i ? d[i - 1] : 0;
    for (; i < n; i++) {
        last = (uint16_t) (last + s[i]);
        d[i] = last;
    }
}

static void
sj_prefix_u32(uint32_t* d, const uint32_t* s, Py_ssize_t n)
{
    Py_ssize_t i = 0;
    __m128i carry = _mm_setzero_si128();
    for (; i + 4 <= n; i += 4) {
        __m128i v = _mm_loadu_si128((const __m128i*) (s + i));
        v = _mm_add_epi32(v, _mm_slli_si128(v, 4));
        v = _mm_add_epi32(v, _mm_slli_si128(v, 8));
        v = _mm_add_epi32(v, carry);
        _mm_storeu_si128((__m128i*) (d + i), v);
        carry = _mm_shuffle_epi32(v, _MM_SHUFFLE(3, 3, 3, 3));
    }
    uint32_t last = i ? d[i - 1] : 0;
    for (; i < n; i++) {
        last += s[i];
        d[i] = last;
    }
}

// préfixes À ENJAMBÉE 2 (stéréo entrelacée) : même cascade décalages-additions
// en sautant la première passe — les lanes paires ne reçoivent que des lanes
// paires, les canaux ne se mélangent jamais ; le report est le dernier COUPLE
static void
sj_prefix_u16_s2(uint16_t* d, const uint16_t* s, Py_ssize_t n)
{
    Py_ssize_t i = 0;
    __m128i carry = _mm_setzero_si128();
    for (; i + 8 <= n; i += 8) {
        __m128i v = _mm_loadu_si128((const __m128i*) (s + i));
        v = _mm_add_epi16(v, _mm_slli_si128(v, 4));
        v = _mm_add_epi16(v, _mm_slli_si128(v, 8));
        v = _mm_add_epi16(v, carry);
        _mm_storeu_si128((__m128i*) (d + i), v);
        // dernier couple (lanes 6-7) diffusé sur les quatre couples
        carry = _mm_shuffle_epi32(v, _MM_SHUFFLE(3, 3, 3, 3));
    }
    uint16_t lastA = (i >= 2) ? d[i - 2] : 0;
    uint16_t lastB = (i >= 1) ? d[i - 1] : 0;
    for (; i < n; i++) {
        if ((i & 1) == 0) {
            lastA = (uint16_t) (lastA + s[i]);
            d[i] = lastA;
        } else {
            lastB = (uint16_t) (lastB + s[i]);
            d[i] = lastB;
        }
    }
}

static void
sj_prefix_u32_s2(uint32_t* d, const uint32_t* s, Py_ssize_t n)
{
    Py_ssize_t i = 0;
    __m128i carry = _mm_setzero_si128();
    for (; i + 4 <= n; i += 4) {
        __m128i v = _mm_loadu_si128((const __m128i*) (s + i));
        v = _mm_add_epi32(v, _mm_slli_si128(v, 8));
        v = _mm_add_epi32(v, carry);
        _mm_storeu_si128((__m128i*) (d + i), v);
        carry = _mm_unpackhi_epi64(v, v);  // dernier couple (lanes 2-3)
    }
    uint32_t lastA = (i >= 2) ? d[i - 2] : 0;
    uint32_t lastB = (i >= 1) ? d[i - 1] : 0;
    for (; i < n; i++) {
        if ((i & 1) == 0) {
            lastA += s[i];
            d[i] = lastA;
        } else {
            lastB += s[i];
            d[i] = lastB;
        }
    }
}

static void
sj_prefix_u8(uint8_t* d, const uint8_t* s, Py_ssize_t n)
{
    Py_ssize_t i = 0;
    __m128i carry = _mm_setzero_si128();
    for (; i + 16 <= n; i += 16) {
        __m128i v = _mm_loadu_si128((const __m128i*) (s + i));
        v = _mm_add_epi8(v, _mm_slli_si128(v, 1));
        v = _mm_add_epi8(v, _mm_slli_si128(v, 2));
        v = _mm_add_epi8(v, _mm_slli_si128(v, 4));
        v = _mm_add_epi8(v, _mm_slli_si128(v, 8));
        v = _mm_add_epi8(v, carry);
        _mm_storeu_si128((__m128i*) (d + i), v);
        carry = _mm_set1_epi8((char) _mm_extract_epi8(v, 15));
    }
    uint8_t last = i ? d[i - 1] : 0;
    for (; i < n; i++) {
        last = (uint8_t) (last + s[i]);
        d[i] = last;
    }
}
#endif

// somme cumulée EN PLACE le long de l'axe 0 (défaire la dérivée _diff au
// chargement) : ~10x numpy.cumsum sur les petits entiers. Arithmétique en
// NON-SIGNÉ (l'enroulement 2-complément est identique à celle de numpy à
// même dtype, et l'addition signée déborderait en comportement indéfini).
template <typename T>
static void
sj_cumsum_rows(T* dst, const T* src, Py_ssize_t rows, Py_ssize_t cols)
{
    if (dst != src)
        for (Py_ssize_t j = 0; j < cols; j++)
            dst[j] = src[j];
    for (Py_ssize_t i = 1; i < rows; i++) {
        const T* s = src + i * cols;
        T* prev = dst + (i - 1) * cols;
        T* cur = dst + i * cols;
        for (Py_ssize_t j = 0; j < cols; j++)
            cur[j] = (T) (s[j] + prev[j]);
    }
}

static void
sj_cumsum_slice(void* dst, const void* src, Py_ssize_t itemsize,
                Py_ssize_t rows, Py_ssize_t row_elems)
{
    switch (itemsize) {
    case 1:
#ifdef RAPIDJSON_SSE42
        if (row_elems == 1)
            sj_prefix_u8((uint8_t*) dst, (const uint8_t*) src, rows);
        else
#endif
        sj_cumsum_rows((uint8_t*) dst, (const uint8_t*) src, rows, row_elems);
        break;
    case 2:
#ifdef RAPIDJSON_SSE42
        if (row_elems == 1)
            sj_prefix_u16((uint16_t*) dst, (const uint16_t*) src, rows);
        else if (row_elems == 2)  // stéréo : préfixe à enjambée 2
            sj_prefix_u16_s2((uint16_t*) dst, (const uint16_t*) src, rows * 2);
        else
#endif
        sj_cumsum_rows((uint16_t*) dst, (const uint16_t*) src, rows, row_elems);
        break;
    case 4:
#ifdef RAPIDJSON_SSE42
        if (row_elems == 1)
            sj_prefix_u32((uint32_t*) dst, (const uint32_t*) src, rows);
        else if (row_elems == 2)  // stéréo : préfixe à enjambée 2
            sj_prefix_u32_s2((uint32_t*) dst, (const uint32_t*) src, rows * 2);
        else
#endif
        sj_cumsum_rows((uint32_t*) dst, (const uint32_t*) src, rows, row_elems);
        break;
    default:
        sj_cumsum_rows((uint64_t*) dst, (const uint64_t*) src, rows, row_elems);
        break;
    }
}

// FUSION CACHE à l'écriture : PRÉFILTRE blosc2 exécuté par bloc — la dérivée
// d'axe 0 est calculée par la lib au moment où elle constitue chaque bloc,
// au lieu d'une pré-passe séparée avec tampon intermédiaire (mesuré : la
// passe + la remise du tampon coûtaient ~40 % de l'écriture). Chaque bloc
// blosc2 étant un bloc de dérivée (blocksize calé), le bloc est
// auto-suffisant : sa première ligne reste brute, comme dans _diff_axis0.
struct SjPreDiff {
    Py_ssize_t itemsize;
    Py_ssize_t row_elems;
};

template <typename T>
static void
sj_diff_block_copy(T* dst, const T* src, Py_ssize_t n, Py_ssize_t cols)
{
    Py_ssize_t head = (cols < n) ? cols : n;
    for (Py_ssize_t i = 0; i < head; i++)
        dst[i] = src[i];
    for (Py_ssize_t i = head; i < n; i++)
        dst[i] = (T) (src[i] - src[i - cols]);
}

static int
sj_diff_prefilter(blosc2_prefilter_params* p)
{
    const SjPreDiff* u = (const SjPreDiff*) p->user_data;
    Py_ssize_t n = (Py_ssize_t) p->output_size / u->itemsize;
    switch (u->itemsize) {
    case 1:
        sj_diff_block_copy((uint8_t*) p->output, (const uint8_t*) p->input,
                           n, u->row_elems);
        break;
    case 2:
        sj_diff_block_copy((uint16_t*) (void*) p->output,
                           (const uint16_t*) (const void*) p->input, n,
                           u->row_elems);
        break;
    case 4:
        sj_diff_block_copy((uint32_t*) (void*) p->output,
                           (const uint32_t*) (const void*) p->input, n,
                           u->row_elems);
        break;
    default:
        sj_diff_block_copy((uint64_t*) (void*) p->output,
                           (const uint64_t*) (const void*) p->input, n,
                           u->row_elems);
        break;
    }
    return 0;
}

// FUSION CACHE à la lecture : postfiltre blosc2 exécuté par BLOC, dans les
// threads de la lib, juste après la décompression du bloc — la somme cumulée
// se fait pendant que le bloc est chaud en cache, au lieu d'une seconde
// passe RAM.
// Exige des blocs alignés aux lignes et une dérivée redémarrée par bloc
// (l'écriture cale blocksize = block_rows * octets_par_ligne).
struct SjPostCumsum {
    Py_ssize_t itemsize;
    Py_ssize_t row_elems;
};

static int
sj_cumsum_postfilter(blosc2_postfilter_params* p)
{
    const SjPostCumsum* u = (const SjPostCumsum*) p->user_data;
    // pas de memcpy : la somme cumulée LIT le tampon de bloc et ÉCRIT la
    // sortie en une seule passe — c'est elle, la copie
    Py_ssize_t rb = u->itemsize * u->row_elems;
    sj_cumsum_slice(p->output, p->input, u->itemsize,
                    (Py_ssize_t) p->size / rb, u->row_elems);
    return 0;
}

// --- filtre blosc2 « delta d'octets par bloc » ------------------------------
// Filtre UTILISATEUR enregistré (id 242), pensé pour passer APRÈS le
// shuffle : chaque flux d'octets shufflé (poids faibles, poids forts) est
// lisse pour des données numériques régulières, et le delta d'octets les
// linéarise tous — mesuré 28,5 % contre 36,2 % pour la dérivée globale
// pré-shuffle sur un signal int16. Aucun typesize nécessaire (octets),
// réversible exactement, exécuté par bloc dans les threads de blosc2 des
// deux côtés ; la trame se décrit elle-même.
#define SJ_BLOSC2_FILTER_DELTA 242

static int
sj_delta_filter_forward(const uint8_t* src, uint8_t* dest, int32_t size,
                        uint8_t meta, blosc2_cparams* cparams, uint8_t id)
{
    (void) meta;
    (void) cparams;
    (void) id;
    if (size <= 0)
        return 0;
    dest[0] = src[0];
    for (int32_t i = 1; i < size; i++)
        dest[i] = (uint8_t) (src[i] - src[i - 1]);
    return 0;
}

static int
sj_delta_filter_backward(const uint8_t* src, uint8_t* dest, int32_t size,
                         uint8_t meta, blosc2_dparams* dparams, uint8_t id)
{
    (void) meta;
    (void) dparams;
    (void) id;
    if (size <= 0)
        return 0;
#ifdef RAPIDJSON_SSE42
    sj_prefix_u8(dest, src, size);  // la somme de préfixe EST la copie
#else
    dest[0] = src[0];
    for (int32_t i = 1; i < size; i++)
        dest[i] = (uint8_t) (src[i] + dest[i - 1]);
#endif
    return 0;
}

// Filtre UTILISATEUR zigzag (id 244), pensé pour passer AVANT le bitshuffle
// natif : replie les négatifs entre les positifs (0, -1, +1, -2 -> 0, 1, 2,
// 3) pour que ±ε partagent leurs bits — sans lui, chaque bascule de signe
// d'une dérivée traverse TOUS les plans de bits et le bitshuffle perd
// (mesuré 87 % contre 73 % avec, sur la stéréo réelle). Largeur d'élément
// passée par filters_meta (persistée dans la trame), bijectif pour toute
// largeur, tail d'octets copiée telle quelle.
#define SJ_BLOSC2_FILTER_ZIGZAG 244

template <typename T, typename U>
static inline void
sj_zigzag_fwd_typed(const uint8_t* src, uint8_t* dest, int32_t n)
{
    const T* in = (const T*) (const void*) src;
    U* out = (U*) (void*) dest;
    const int nb = (int) sizeof(T) * 8 - 1;
    for (int32_t i = 0; i < n; i++) {
        T d = in[i];
        out[i] = ((U) d << 1) ^ (U) (d >> nb);
    }
}

template <typename T, typename U>
static inline void
sj_zigzag_bwd_typed(const uint8_t* src, uint8_t* dest, int32_t n)
{
    const U* in = (const U*) (const void*) src;
    T* out = (T*) (void*) dest;
    for (int32_t i = 0; i < n; i++) {
        U u = in[i];
        out[i] = (T) ((u >> 1) ^ (U) (0 - (u & 1)));
    }
}

// dézigzag + somme cumulée d'enjambée c en UNE passe (la dérivée par blocs
// redémarre à chaque bloc, et le filtre traite exactement un bloc) : le
// postfiltre et son saut de tampon disparaissent pour les petites lignes
template <typename T, typename U>
static inline void
sj_zigzag_cumsum_bwd_typed(const uint8_t* src, uint8_t* dest, int32_t n,
                           int32_t c)
{
    const U* in = (const U*) (const void*) src;
    T* out = (T*) (void*) dest;
    int32_t head = (c < n) ? c : n;
    for (int32_t i = 0; i < head; i++) {
        U u = in[i];
        out[i] = (T) ((u >> 1) ^ (U) (0 - (u & 1)));
    }
    for (int32_t i = head; i < n; i++) {
        U u = in[i];
        out[i] = (T) (((u >> 1) ^ (U) (0 - (u & 1))) + (U) out[i - c]);
    }
}

static int
sj_zigzag_filter_forward(const uint8_t* src, uint8_t* dest, int32_t size,
                         uint8_t meta, blosc2_cparams* cparams, uint8_t id)
{
    (void) id;
    int ts = (meta & 0xF) ? (int) (meta & 0xF)
                          : (cparams ? (int) cparams->typesize : 1);
    int32_t n = size / ts;
    switch (ts) {
        case 1: sj_zigzag_fwd_typed<int8_t, uint8_t>(src, dest, n); break;
        case 2: sj_zigzag_fwd_typed<int16_t, uint16_t>(src, dest, n); break;
        case 4: sj_zigzag_fwd_typed<int32_t, uint32_t>(src, dest, n); break;
        case 8: sj_zigzag_fwd_typed<int64_t, uint64_t>(src, dest, n); break;
        default: memcpy(dest, src, (size_t) size); return 0;
    }
    if (n * ts < size)  // queue d'octets incomplète : copiée telle quelle
        memcpy(dest + n * ts, src + n * ts, (size_t) (size - n * ts));
    return 0;
}


#ifdef RAPIDJSON_SSE42
// dézigzag + somme de préfixe en UNE passe vectorielle (le dézigzag se
// vectorise lane par lane, la cascade de Hillis-Steele fait le reste) —
// c'est ce qui permet au filtre 244 arrière de défaire zigzag ET dérivée
// sans perdre le débit du préfixe SSE du postfiltre qu'il remplace
static inline __m128i
sj_unzig_epi16(__m128i v)
{
    __m128i one = _mm_set1_epi16(1);
    __m128i sign = _mm_sub_epi16(_mm_setzero_si128(), _mm_and_si128(v, one));
    return _mm_xor_si128(_mm_srli_epi16(v, 1), sign);
}

static inline __m128i
sj_unzig_epi32(__m128i v)
{
    __m128i one = _mm_set1_epi32(1);
    __m128i sign = _mm_sub_epi32(_mm_setzero_si128(), _mm_and_si128(v, one));
    return _mm_xor_si128(_mm_srli_epi32(v, 1), sign);
}

static void
sj_unzig_prefix_u16(uint16_t* d, const uint16_t* s, Py_ssize_t n,
                    Py_ssize_t stride)
{
    Py_ssize_t i = 0;
    __m128i carry = _mm_setzero_si128();
    if (stride == 1) {
        for (; i + 8 <= n; i += 8) {
            __m128i v = sj_unzig_epi16(
                _mm_loadu_si128((const __m128i*) (s + i)));
            v = _mm_add_epi16(v, _mm_slli_si128(v, 2));
            v = _mm_add_epi16(v, _mm_slli_si128(v, 4));
            v = _mm_add_epi16(v, _mm_slli_si128(v, 8));
            v = _mm_add_epi16(v, carry);
            _mm_storeu_si128((__m128i*) (d + i), v);
            carry = _mm_shufflehi_epi16(v, _MM_SHUFFLE(3, 3, 3, 3));
            carry = _mm_unpackhi_epi64(carry, carry);
        }
    } else {  // stride == 2 (stéréo)
        for (; i + 8 <= n; i += 8) {
            __m128i v = sj_unzig_epi16(
                _mm_loadu_si128((const __m128i*) (s + i)));
            v = _mm_add_epi16(v, _mm_slli_si128(v, 4));
            v = _mm_add_epi16(v, _mm_slli_si128(v, 8));
            v = _mm_add_epi16(v, carry);
            _mm_storeu_si128((__m128i*) (d + i), v);
            carry = _mm_shuffle_epi32(v, _MM_SHUFFLE(3, 3, 3, 3));
        }
    }
    for (; i < n; i++) {
        uint16_t u = s[i];
        uint16_t x = (uint16_t) ((u >> 1) ^ (0 - (u & 1)));
        d[i] = (uint16_t) (x + ((i >= stride) ? d[i - stride] : 0));
    }
}

static void
sj_unzig_prefix_u32(uint32_t* d, const uint32_t* s, Py_ssize_t n,
                    Py_ssize_t stride)
{
    Py_ssize_t i = 0;
    __m128i carry = _mm_setzero_si128();
    if (stride == 1) {
        for (; i + 4 <= n; i += 4) {
            __m128i v = sj_unzig_epi32(
                _mm_loadu_si128((const __m128i*) (s + i)));
            v = _mm_add_epi32(v, _mm_slli_si128(v, 4));
            v = _mm_add_epi32(v, _mm_slli_si128(v, 8));
            v = _mm_add_epi32(v, carry);
            _mm_storeu_si128((__m128i*) (d + i), v);
            carry = _mm_shuffle_epi32(v, _MM_SHUFFLE(3, 3, 3, 3));
        }
    } else {  // stride == 2
        for (; i + 4 <= n; i += 4) {
            __m128i v = sj_unzig_epi32(
                _mm_loadu_si128((const __m128i*) (s + i)));
            v = _mm_add_epi32(v, _mm_slli_si128(v, 8));
            v = _mm_add_epi32(v, carry);
            _mm_storeu_si128((__m128i*) (d + i), v);
            carry = _mm_unpackhi_epi64(v, v);
        }
    }
    for (; i < n; i++) {
        uint32_t u = s[i];
        uint32_t x = (u >> 1) ^ (0 - (u & 1));
        d[i] = x + ((i >= stride) ? d[i - stride] : 0);
    }
}
#endif

static int
sj_zigzag_filter_backward(const uint8_t* src, uint8_t* dest, int32_t size,
                          uint8_t meta, blosc2_dparams* dparams, uint8_t id)
{
    (void) id;
    (void) dparams;
    int ts = (meta & 0xF) ? (int) (meta & 0xF) : 1;
    int code = meta >> 4;  // 0 : dézigzag seul ; 1..4 : + cumsum, c = 1<<(code-1)
    int32_t n = size / ts;
    if (code) {
        int32_t c = (int32_t) 1 << (code - 1);
#ifdef RAPIDJSON_SSE42
        if (ts == 2 && (c == 1 || c == 2)) {
            sj_unzig_prefix_u16((uint16_t*) (void*) dest,
                                (const uint16_t*) (const void*) src, n, c);
            if (n * ts < size)
                memcpy(dest + n * ts, src + n * ts,
                       (size_t) (size - n * ts));
            return 0;
        }
        if (ts == 4 && (c == 1 || c == 2)) {
            sj_unzig_prefix_u32((uint32_t*) (void*) dest,
                                (const uint32_t*) (const void*) src, n, c);
            if (n * ts < size)
                memcpy(dest + n * ts, src + n * ts,
                       (size_t) (size - n * ts));
            return 0;
        }
#endif
        switch (ts) {
        case 1: sj_zigzag_cumsum_bwd_typed<int8_t, uint8_t>(src, dest, n, c); break;
        case 2: sj_zigzag_cumsum_bwd_typed<int16_t, uint16_t>(src, dest, n, c); break;
        case 4: sj_zigzag_cumsum_bwd_typed<int32_t, uint32_t>(src, dest, n, c); break;
        default: sj_zigzag_cumsum_bwd_typed<int64_t, uint64_t>(src, dest, n, c); break;
        }
        if (n * ts < size)
            memcpy(dest + n * ts, src + n * ts, (size_t) (size - n * ts));
        return 0;
    }
    switch (ts) {
        case 1: sj_zigzag_bwd_typed<int8_t, uint8_t>(src, dest, n); break;
        case 2: sj_zigzag_bwd_typed<int16_t, uint16_t>(src, dest, n); break;
        case 4: sj_zigzag_bwd_typed<int32_t, uint32_t>(src, dest, n); break;
        case 8: sj_zigzag_bwd_typed<int64_t, uint64_t>(src, dest, n); break;
        default: memcpy(dest, src, (size_t) size); return 0;
    }
    if (n * ts < size)
        memcpy(dest + n * ts, src + n * ts, (size_t) (size - n * ts));
    return 0;
}

typedef int (*sj_blosc2_register_filter_t)(blosc2_filter*);
static bool serializejson_blosc2_delta_ok = false;
static bool serializejson_blosc2_zigzag_ok = false;
static int serializejson_blosc2_nthreads_global = 1;


struct SjDecompressJob {
    const char* src;
    int32_t srcsize;
    char* dest;
    int32_t destsize;
    int result;
};

static void
sj_decompress_worker(std::vector<SjDecompressJob>* jobs, std::atomic<size_t>* next,
                     int inner_threads, const SjPostCumsum* post)
{
    // inner_threads > 1 quand il y a moins de trames que de coeurs (cas
    // courant : UNE grosse trame compressée par le MT interne du fork) —
    // la décompression est déterministe par nature, aucune contrainte d'ordre
    blosc2_dparams dparams = BLOSC2_DPARAMS_DEFAULTS;
    dparams.nthreads = (int16_t) inner_threads;
    blosc2_postfilter_params pparams;
    if (post != nullptr) {
        // fusion cache : la somme cumulée se fait bloc par bloc dans les
        // threads de blosc2, pendant que le bloc décompressé est chaud
        memset(&pparams, 0, sizeof(pparams));
        pparams.user_data = (void*) post;
        dparams.postfilter = sj_cumsum_postfilter;
        dparams.postparams = &pparams;
    }
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
        "blocksize",
        "diff_cols",
        nullptr
    };
    PyObject* value = nullptr;
    Py_ssize_t typesize = 1;
    int clevel = 5;
    int shuffle = 1;
    const char* cname = "blosclz";
    int nthreads = 1;
    int blocksize = 0;  // blocs blosc2 = blocs de dérivée (fusion cache)
    Py_ssize_t diff_cols = 0;  // > 0 : dérivée d'axe 0 par PRÉFILTRE

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|niisiin", (char**) kwlist,
                                     &value, &typesize, &clevel, &shuffle,
                                     &cname, &nthreads, &blocksize,
                                     &diff_cols))
        return nullptr;
    // nthreads accepté pour compatibilité d'appel : le multi-thread INTERNE
    // (déterministe avec le fork) suit le réglage global, pas ce paramètre
    (void) nthreads;
    if (diff_cols > 0 && blocksize <= 0) {
        PyErr_SetString(PyExc_ValueError,
                        "diff_cols requires an explicit blocksize (aligned"
                        " derivative blocks)");
        return nullptr;
    }
    if (!serializejson_blosc2_ctx_ok) {
        PyErr_SetString(PyExc_RuntimeError,
                        "blosc library not loaded (call load_blosc_library first)");
        return nullptr;
    }
    if (shuffle == 3 && !serializejson_blosc2_zigzag_ok) {
        // pas de repli silencieux : shuffle=3 exige le filtre enregistré
        PyErr_SetString(PyExc_ValueError,
                        "zigzag+bitshuffle requires a loadable libblosc2");
        return nullptr;
    }

    Py_buffer view;
    if (PyObject_GetBuffer(value, &view, PyBUF_CONTIG_RO) != 0)
        return nullptr;

    // trame UNIQUE par l'API contextes — la seule voie d'écriture : filtres
    // enregistrés (zigzag, delta) et blocs calés l'exigent, et le fork rend
    // le multi-thread interne déterministe (octets stables quel que soit le
    // nombre de threads). L'écriture par morceaux concaténés (blosc2p) et le
    // repli blosc1 ont été retirés le 05/08/2026 — leur LECTURE demeure.
    if ((size_t) view.len >= (size_t) INT32_MAX - BLOSC2_MAX_OVERHEAD) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_ValueError,
                        "buffer too large for a single blosc2 frame (2 GiB)");
        return nullptr;
    }
    {
        int compcode = sj_blosc2_compname_to_compcode(cname);
        if (compcode < 0) {
            PyBuffer_Release(&view);
            PyErr_Format(PyExc_ValueError, "unknown blosc compressor '%s'",
                         cname);
            return nullptr;
        }
        blosc2_cparams cparams = BLOSC2_CPARAMS_DEFAULTS;
        cparams.compcode = (uint8_t) compcode;
        cparams.clevel = (uint8_t) clevel;
        cparams.typesize = (int32_t) typesize;
        cparams.nthreads = (int16_t) serializejson_blosc2_nthreads_global;
        for (int f = 0; f < BLOSC2_MAX_FILTERS; f++) {
            cparams.filters[f] = BLOSC_NOFILTER;
            cparams.filters_meta[f] = 0;
        }
        if (shuffle == 3) {
            // pipeline zigzag -> bitshuffle, blocs larges (le bitshuffle
            // transpose PAR BLOC, des plans de bits courts perdent 2-4 pts).
            // Colonnes 1/2/4/8 avec dérivée par préfiltre : le cumsum de
            // lecture est fusionné dans l'ARRIÈRE du filtre (quartet haut du
            // meta) — plus de postfiltre ni de saut de tampon à la lecture
            uint8_t zz_meta = (uint8_t) typesize;
            if (diff_cols == 1 || diff_cols == 2 || diff_cols == 4
                || diff_cols == 8) {
                int code = (diff_cols == 1) ? 1 : (diff_cols == 2) ? 2
                           : (diff_cols == 4) ? 3 : 4;
                zz_meta |= (uint8_t) (code << 4);
            }
            cparams.filters[BLOSC2_MAX_FILTERS - 2] = SJ_BLOSC2_FILTER_ZIGZAG;
            cparams.filters_meta[BLOSC2_MAX_FILTERS - 2] = zz_meta;
            cparams.filters[BLOSC2_MAX_FILTERS - 1] = BLOSC_BITSHUFFLE;
            cparams.splitmode = BLOSC_NEVER_SPLIT;
            cparams.blocksize = 1 << 19;  // 512 Ko : L2-résident, mesuré sans
                                          // perte de poids (sauf +0,9 pt 24/96)
        } else if (shuffle == 2 && serializejson_blosc2_delta_ok) {
            // pipeline shuffle -> delta d'octets (ordre MESURÉ gagnant)
            cparams.filters[BLOSC2_MAX_FILTERS - 2] = BLOSC_SHUFFLE;
            cparams.filters[BLOSC2_MAX_FILTERS - 1] = SJ_BLOSC2_FILTER_DELTA;
        } else {
            // shuffle simple (ou aucun)
            cparams.filters[BLOSC2_MAX_FILTERS - 1] =
                shuffle ? BLOSC_SHUFFLE : BLOSC_NOFILTER;
        }
        if (blocksize > 0)
            cparams.blocksize = blocksize;  // blocs = blocs de dérivée
        SjPreDiff pre_cfg = {typesize, diff_cols};
        blosc2_prefilter_params preparams;
        if (diff_cols > 0) {
            // fusion écriture : la dérivée par blocs est calculée par la lib
            // au moment où elle constitue chaque bloc (octets identiques à la
            // pré-passe _diff_axis0 bloquée, sans tampon intermédiaire)
            memset(&preparams, 0, sizeof(preparams));
            preparams.user_data = (void*) &pre_cfg;
            cparams.prefilter = sj_diff_prefilter;
            cparams.preparams = &preparams;
        }
        size_t delta_dest_size = (size_t) view.len + BLOSC2_MAX_OVERHEAD;
        char* delta_dest = (char*) malloc(delta_dest_size);
        if (delta_dest == nullptr) {
            PyBuffer_Release(&view);
            PyErr_NoMemory();
            return nullptr;
        }
        int delta_csize = -1;
        SjCctxKey key;
        memset(&key, 0, sizeof(key));
        key.compcode = cparams.compcode; key.clevel = cparams.clevel;
        key.typesize = cparams.typesize; key.nthreads = cparams.nthreads;
        key.blocksize = cparams.blocksize; key.splitmode = cparams.splitmode;
        memcpy(key.filters, cparams.filters, sizeof(key.filters));
        memcpy(key.filters_meta, cparams.filters_meta,
               sizeof(key.filters_meta));
        bool cacheable = (diff_cols <= 0);
        blosc2_context* delta_ctx = nullptr;
        if (cacheable && sj_cctx_cache != nullptr
            && memcmp(&key, &sj_cctx_cache_key, sizeof(key)) == 0) {
            delta_ctx = sj_cctx_cache;   // pris sous GIL
            sj_cctx_cache = nullptr;
        }
        Py_BEGIN_ALLOW_THREADS
        if (delta_ctx == nullptr)
            delta_ctx = sj_blosc2_create_cctx(cparams);
        if (delta_ctx != nullptr) {
            delta_csize = sj_blosc2_compress_ctx(
                delta_ctx, view.buf, (int32_t) view.len, delta_dest,
                (int32_t) delta_dest_size);
        }
        Py_END_ALLOW_THREADS
        if (delta_ctx != nullptr) {
            if (cacheable && sj_cctx_cache == nullptr) {
                sj_cctx_cache = delta_ctx;   // rendu sous GIL (UN ctx vit
                sj_cctx_cache_key = key;     // jusqu'à la fin du processus)
            } else {
                sj_blosc2_free_ctx(delta_ctx);
            }
        }
        PyBuffer_Release(&view);
        if (delta_csize <= 0) {
            free(delta_dest);
            PyErr_Format(PyExc_ValueError,
                         "blosc delta compression failed (%d)", delta_csize);
            return nullptr;
        }
        PyObject* self = type->tp_alloc(type, 0);
        if (self == nullptr) {
            free(delta_dest);
            return nullptr;
        }
        ((BloscToBase64*) self)->data = delta_dest;
        ((BloscToBase64*) self)->size = (Py_ssize_t) delta_csize;
        return self;
    }
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
