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

// --- somme de préfixe (défaire une dérivée) ---------------------------------
// scalaire par défaut ; en SSE, préfixe EN REGISTRE par décalages-additions
// puis propagation du report — le scalaire bute sur la chaîne de dépendance
// (~1,5 ns/élément), le vectorisé tourne à la bande passante mémoire
#ifdef RAPIDJSON_SSE42
static void
sj_prefix_u16(uint16_t* d, Py_ssize_t n)
{
    Py_ssize_t i = 0;
    __m128i carry = _mm_setzero_si128();
    for (; i + 8 <= n; i += 8) {
        __m128i v = _mm_loadu_si128((__m128i*) (d + i));
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
        last = (uint16_t) (last + d[i]);
        d[i] = last;
    }
}

static void
sj_prefix_u32(uint32_t* d, Py_ssize_t n)
{
    Py_ssize_t i = 0;
    __m128i carry = _mm_setzero_si128();
    for (; i + 4 <= n; i += 4) {
        __m128i v = _mm_loadu_si128((__m128i*) (d + i));
        v = _mm_add_epi32(v, _mm_slli_si128(v, 4));
        v = _mm_add_epi32(v, _mm_slli_si128(v, 8));
        v = _mm_add_epi32(v, carry);
        _mm_storeu_si128((__m128i*) (d + i), v);
        carry = _mm_shuffle_epi32(v, _MM_SHUFFLE(3, 3, 3, 3));
    }
    uint32_t last = i ? d[i - 1] : 0;
    for (; i < n; i++) {
        last += d[i];
        d[i] = last;
    }
}

static void
sj_prefix_u8(uint8_t* d, Py_ssize_t n)
{
    Py_ssize_t i = 0;
    __m128i carry = _mm_setzero_si128();
    for (; i + 16 <= n; i += 16) {
        __m128i v = _mm_loadu_si128((__m128i*) (d + i));
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
        last = (uint8_t) (last + d[i]);
        d[i] = last;
    }
}
#endif

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
    memcpy(dest, src, (size_t) size);
#ifdef RAPIDJSON_SSE42
    sj_prefix_u8(dest, size);
#else
    for (int32_t i = 1; i < size; i++)
        dest[i] = (uint8_t) (dest[i] + dest[i - 1]);
#endif
    return 0;
}

typedef int (*sj_blosc2_register_filter_t)(blosc2_filter*);
static bool serializejson_blosc2_delta_ok = false;
static int serializejson_blosc2_nthreads_global = 1;

// --- codec blosc2 « Rice à prédicteurs fixes » (id 243) ---------------------
// Codec UTILISATEUR enregistré : par trame de 1024 échantillons, le meilleur
// prédicteur polynomial FIXE d'ordre 0..3 (les mêmes que le mode « fixed » de
// FLAC — nos dérivées itérées), puis résidus zigzag codés en Rice avec un
// calibre k réajusté par partition de 256 échantillons (6 bits d'en-tête,
// k=63 = partition verbatim). C'est l'adaptation LOCALE qui permet de
// descendre sous l'entropie globale des résidus, là où zstd plafonne —
// mesuré 57 437 octets contre 68 625 (zstd sur delta) et 50 200 (FLAC) sur
// la voix de référence. Entiers 2 et 4 octets ; pur, donc déterministe ;
// exécuté par bloc dans les threads de blosc2. Ignore clevel.
#define SJ_BLOSC2_CODEC_RICE 243
#define SJ_RICE_FRAME 1024
#define SJ_RICE_PART 256
#define SJ_RICE_ESCAPE 63
#define SJ_RICE_ZERO 62  // partition entièrement nulle : 6 bits, pas de charge
                         // (l'équivalent du sous-frame constant de FLAC —
                         // sans lui, le silence coûterait 1 bit/échantillon
                         // là où le RLE de zstd le rend presque gratuit)

struct SjBitWriter {
    uint8_t* out;
    int32_t cap;
    int32_t pos;
    uint64_t acc;
    int nbits;
    bool overflow;
};

static inline void
sj_bw_flush(SjBitWriter* w)
{
    while (w->nbits >= 8) {
        if (w->pos >= w->cap) {
            w->overflow = true;
            w->nbits = 0;
            return;
        }
        w->out[w->pos++] = (uint8_t) w->acc;
        w->acc >>= 8;
        w->nbits -= 8;
    }
}

static inline void
sj_bw_put(SjBitWriter* w, uint64_t v, int n)  // n <= 56, poids faible d'abord
{
    w->acc |= v << w->nbits;
    w->nbits += n;
    sj_bw_flush(w);
}

static inline void
sj_bw_unary(SjBitWriter* w, uint64_t q)  // q zéros puis un 1
{
    while (q >= 48 && !w->overflow) {
        sj_bw_put(w, 0, 48);
        q -= 48;
    }
    sj_bw_put(w, (uint64_t) 1 << q, (int) q + 1);
}

struct SjBitReader {
    const uint8_t* in;
    int32_t len;
    int32_t pos;
    uint64_t acc;
    int nbits;
    bool fail;
};

static inline void
sj_br_fill(SjBitReader* r)
{
    while (r->nbits <= 56 && r->pos < r->len) {
        r->acc |= (uint64_t) r->in[r->pos++] << r->nbits;
        r->nbits += 8;
    }
}

static inline uint64_t
sj_br_get(SjBitReader* r, int n)
{
    sj_br_fill(r);
    if (r->nbits < n) {
        r->fail = true;
        return 0;
    }
    uint64_t v = r->acc & (((uint64_t) 1 << n) - 1);
    r->acc >>= n;
    r->nbits -= n;
    return v;
}

static inline uint64_t
sj_br_unary(SjBitReader* r)
{
    uint64_t q = 0;
    while (true) {
        sj_br_fill(r);
        if (r->nbits == 0) {
            r->fail = true;
            return 0;
        }
        if (r->acc == 0) {  // que des zéros dans le tampon : tout consommer
            q += (uint64_t) r->nbits;
            r->nbits = 0;
            continue;
        }
#if defined(_MSC_VER)
        unsigned long t32;
        _BitScanForward64(&t32, r->acc);
        int t = (int) t32;
#else
        int t = __builtin_ctzll(r->acc);
#endif
        q += (uint64_t) t;
        // t + 1 peut valoir 64 (q unaire finissant pile en haut du tampon) :
        // un décalage de 64 est INDÉFINI en C (pris modulo 64 sur x86, acc
        // resterait INCHANGÉ et un bit fantôme ressortirait plus loin)
        r->acc = (t + 1 < 64) ? (r->acc >> (t + 1)) : 0;
        r->nbits -= t + 1;
        return q;
    }
}

// prédiction polynomiale fixe d'ordre eff sur l'historique h (h = x + i),
// à PAS c : pour de l'audio entrelacé à c canaux, l'échantillon précédent du
// MÊME canal est c positions en arrière — sans ce pas, la prédiction
// enjambe les canaux (gauche prédit depuis droite) et Rice perd en stéréo
template <typename T>
static inline int64_t
sj_rice_predict(const T* h, int eff, int32_t c)
{
    switch (eff) {
        case 1: return (int64_t) h[-c];
        case 2: return 2 * (int64_t) h[-c] - (int64_t) h[-2 * c];
        case 3: return 3 * ((int64_t) h[-c] - (int64_t) h[-2 * c])
                       + (int64_t) h[-3 * c];
        default: return 0;
    }
}

// mid/side (c == 2 seulement) : valeur transformée à la position g, calculée
// à la volée depuis la paire d'échantillons — mid = (L+R)>>1 aux positions
// paires, side = L-R aux impaires. Le décodeur ayant toujours reconstruit x
// pour les paires passées, l'historique se recalcule des deux côtés sans
// tampon ni état. Un échantillon final non appairé vaut sa propre valeur.
template <typename T>
static inline int64_t
sj_rice_ms_value(const T* x, int32_t g, int32_t n)
{
    int32_t b = g & ~1;
    if (b + 1 >= n)
        return (int64_t) x[b];
    if (g & 1)
        return (int64_t) x[b] - (int64_t) x[b + 1];
    return ((int64_t) x[b] + (int64_t) x[b + 1]) >> 1;
}

template <typename T>
static int32_t
sj_rice_encode_typed(const T* x, int32_t n, uint8_t* out, int32_t cap,
                     int32_t c)
{
    SjBitWriter w = {out, cap, 0, 0, 0, false};
    static const int esc_bits = (int) sizeof(T) * 8 + 4;
    int64_t r[4][SJ_RICE_FRAME];
    uint64_t u[SJ_RICE_PART];
    for (int32_t start = 0; start < n; start += SJ_RICE_FRAME) {
        int32_t m = n - start;
        if (m > SJ_RICE_FRAME)
            m = SJ_RICE_FRAME;
        // stéréo : gauche/droite ou mid/side, un bit par trame — les valeurs
        // transformées sont matérialisées UNE fois (trame + 6 d'historique,
        // les appels à la volée par échantillon et par ordre coûtaient 2× en
        // vitesse), puis décision par une passe bon marché sur les résidus
        // d'ordre 1 ; la recherche complète ne tourne que sur le domaine élu
        bool ms = false;
        int64_t tw[SJ_RICE_FRAME + 6];
        int64_t* t6 = tw + 6;
        if (c == 2) {
            for (int32_t i = -6; i < m; i++) {
                int32_t g = start + i;
                t6[i] = (g >= 0) ? sj_rice_ms_value(x, g, n) : 0;
            }
            uint64_t clr = 0, cms = 0;
            for (int32_t i = 0; i < m; i++) {
                int32_t g = start + i;
                int64_t dlr = (g >= 2) ? (int64_t) x[g] - (int64_t) x[g - 2]
                                       : (int64_t) x[g];
                int64_t dms = (g >= 2) ? t6[i] - t6[i - 2] : t6[i];
                clr += (uint64_t) (dlr < 0 ? -dlr : dlr);
                cms += (uint64_t) (dms < 0 ? -dms : dms);
            }
            ms = cms < clr;  // égalité -> gauche/droite (déterministe)
            sj_bw_put(&w, ms ? 1 : 0, 1);
        }
        // le side occupe un bit de plus que la source : escape élargi d'autant
        int eb = ms ? esc_bits + 1 : esc_bits;
        // résidus des quatre ordres (la prédiction traverse les trames :
        // l'historique est le signal déjà vu, le décodeur fait pareil)
        uint64_t cost[4] = {0, 0, 0, 0};
        for (int o = 0; o < 4; o++) {
            for (int32_t i = 0; i < m; i++) {
                int32_t g = start + i;
                int eff = (g < o * c) ? (int) (g / c) : o;
                int64_t d = ms ? t6[i] - sj_rice_predict(t6 + i, eff, 2)
                               : (int64_t) x[g]
                                     - sj_rice_predict(x + g, eff, c);
                r[o][i] = d;
                cost[o] += (uint64_t) (d < 0 ? -d : d);
            }
        }
        int order = 0;
        for (int o = 1; o < 4; o++)
            if (cost[o] < cost[order])
                order = o;
        sj_bw_put(&w, (uint64_t) order, 2);
        // mid/side : mids d'abord, sides ensuite — sans ce réordonnancement,
        // chaque partition mélange les deux flux et le calibre k d'un side
        // quasi nul est imposé par les mids actifs (le gain disparaissait)
        int64_t ro[SJ_RICE_FRAME];
        const int64_t* rr = r[order];
        if (ms) {
            int32_t j = 0;
            for (int32_t i = 0; i < m; i += 2)
                ro[j++] = r[order][i];
            for (int32_t i = 1; i < m; i += 2)
                ro[j++] = r[order][i];
            rr = ro;
        }
        for (int32_t ps = 0; ps < m; ps += SJ_RICE_PART) {
            int32_t pm = m - ps;
            if (pm > SJ_RICE_PART)
                pm = SJ_RICE_PART;
            uint64_t sum = 0;
            for (int32_t i = 0; i < pm; i++) {
                int64_t d = rr[ps + i];
                u[i] = ((uint64_t) d << 1) ^ (uint64_t) (d >> 63);  // zigzag
                sum += u[i];
            }
            if (sum == 0) {  // silence : partition constante nulle
                sj_bw_put(&w, SJ_RICE_ZERO, 6);
                if (w.overflow)
                    return 0;
                continue;
            }
            // calibre : ~log2(moyenne), affiné sur les voisins, comparé au
            // verbatim (partitions incompressibles : bruit fort, transitoires)
            uint64_t mean = sum / (uint64_t) pm;
            int k0 = 0;
            while ((mean >> k0) > 1)
                k0++;
            uint64_t best_cost = (uint64_t) pm * (uint64_t) eb;
            int best_k = SJ_RICE_ESCAPE;
            int k_lo = (k0 > 1) ? k0 - 1 : 0;
            for (int k = k_lo; k <= k0 + 2 && k < eb; k++) {
                uint64_t c = (uint64_t) pm * (uint64_t) (k + 1);
                for (int32_t i = 0; i < pm; i++)
                    c += u[i] >> k;
                if (c < best_cost) {
                    best_cost = c;
                    best_k = k;
                }
            }
            sj_bw_put(&w, (uint64_t) best_k, 6);
            if (best_k == SJ_RICE_ESCAPE) {
                for (int32_t i = 0; i < pm; i++)
                    sj_bw_put(&w, u[i], eb);
            } else {
                uint64_t mask = ((uint64_t) 1 << best_k) - 1;
                for (int32_t i = 0; i < pm; i++) {
                    sj_bw_unary(&w, u[i] >> best_k);
                    if (best_k)
                        sj_bw_put(&w, u[i] & mask, best_k);
                }
            }
            if (w.overflow)
                return 0;
        }
    }
    if (w.nbits & 7)
        sj_bw_put(&w, 0, 8 - (w.nbits & 7));
    sj_bw_flush(&w);
    return w.overflow ? 0 : w.pos;
}

template <typename T>
static int32_t
sj_rice_decode_typed(const uint8_t* in, int32_t len, T* x, int32_t n,
                     int32_t c)
{
    SjBitReader rd = {in, len, 0, 0, 0, false};
    static const int esc_bits = (int) sizeof(T) * 8 + 4;
    for (int32_t start = 0; start < n; start += SJ_RICE_FRAME) {
        int32_t m = n - start;
        if (m > SJ_RICE_FRAME)
            m = SJ_RICE_FRAME;
        bool ms = (c == 2) && sj_br_get(&rd, 1) != 0;
        int eb = ms ? esc_bits + 1 : esc_bits;
        int order = (int) sj_br_get(&rd, 2);
        // mid/side : les mids arrivent d'abord, puis les sides (partitions
        // homogènes, voir l'encodeur). tv[] garde les valeurs t de la trame :
        // pendant le décodage réordonné, x n'est pas encore reconstruit, donc
        // l'historique intra-trame se lit ici et l'inter-trame dans x
        int64_t tv[SJ_RICE_FRAME];
        int32_t nmid = (m + 1) / 2;
        for (int32_t ps = 0; ps < m; ps += SJ_RICE_PART) {
            int32_t pm = m - ps;
            if (pm > SJ_RICE_PART)
                pm = SJ_RICE_PART;
            int k = (int) sj_br_get(&rd, 6);
            uint64_t v;
            for (int32_t i = 0; i < pm; i++) {
                if (k == SJ_RICE_ZERO)
                    v = 0;
                else if (k == SJ_RICE_ESCAPE)
                    v = sj_br_get(&rd, eb);
                else {
                    uint64_t q = sj_br_unary(&rd);
                    v = (q << k) | (k ? sj_br_get(&rd, k) : 0);
                }
                int64_t d = (int64_t) (v >> 1) ^ -(int64_t) (v & 1);
                int32_t j = ps + i;
                if (ms) {
                    int32_t fi = (j < nmid) ? 2 * j : 2 * (j - nmid) + 1;
                    int32_t g = start + fi;
                    int eff = (g < order * 2) ? (int) (g / 2) : order;
                    int64_t p = 0;
                    for (int o = 1; o <= eff; o++) {
                        static const int64_t coef[4][3] = {
                            {0, 0, 0}, {1, 0, 0}, {2, -1, 0}, {3, -3, 1}};
                        int32_t gg = g - 2 * o;
                        int64_t h = (gg >= start)
                                        ? tv[gg - start]
                                        : sj_rice_ms_value(x, gg, n);
                        p += coef[eff][o - 1] * h;
                    }
                    tv[fi] = d + p;
                } else {
                    int32_t g = start + j;
                    int eff = (g < order * c) ? (int) (g / c) : order;
                    x[g] = (T) (d + sj_rice_predict(x + g, eff, c));
                }
            }
            if (rd.fail)
                return -1;
        }
        if (ms) {  // reconstruction des paires depuis mid/side
            for (int32_t i = 0; i + 1 < m; i += 2) {
                int64_t s = tv[i + 1];
                int64_t L = tv[i] + ((s + (s & 1)) >> 1);
                x[start + i] = (T) L;
                x[start + i + 1] = (T) (L - s);
            }
            if (m & 1)  // échantillon final non appairé : mid = valeur
                x[start + m - 1] = (T) tv[m - 1];
        }
    }
    return n * (int32_t) sizeof(T);
}

static int
sj_rice_encoder(const uint8_t* input, int32_t input_len, uint8_t* output,
                int32_t output_len, uint8_t meta, blosc2_cparams* cparams,
                const void* chunk)
{
    (void) chunk;
    // meta : largeur d'échantillon dans le quartet bas, nombre de canaux
    // dans le quartet haut (0 = mono, compatible avec les trames déjà
    // écrites sans canaux)
    int typesize = meta ? (int) (meta & 0xF)
                        : (cparams ? (int) cparams->typesize : 0);
    int32_t c = (meta >> 4) ? (int32_t) (meta >> 4) : 1;
    int32_t cap = output_len;
    if (cap > input_len - 1)
        cap = input_len - 1;  // n'accepter que strictement plus petit
    if (cap <= 0)
        return 0;
    if (typesize == 2 && input_len % 2 == 0)
        return sj_rice_encode_typed<int16_t>(
            (const int16_t*) (const void*) input, input_len / 2, output, cap,
            c);
    if (typesize == 4 && input_len % 4 == 0)
        return sj_rice_encode_typed<int32_t>(
            (const int32_t*) (const void*) input, input_len / 4, output, cap,
            c);
    return 0;  // largeur non gérée : blosc stocke le bloc brut
}

static int
sj_rice_decoder(const uint8_t* input, int32_t input_len, uint8_t* output,
                int32_t output_len, uint8_t meta, blosc2_dparams* dparams,
                const void* chunk)
{
    (void) dparams;
    (void) chunk;
    int typesize = (int) (meta & 0xF);
    int32_t c = (meta >> 4) ? (int32_t) (meta >> 4) : 1;
    if (typesize == 2 && output_len % 2 == 0)
        return sj_rice_decode_typed<int16_t>(
            input, input_len, (int16_t*) (void*) output, output_len / 2, c);
    if (typesize == 4 && output_len % 4 == 0)
        return sj_rice_decode_typed<int32_t>(
            input, input_len, (int32_t*) (void*) output, output_len / 4, c);
    return -1;
}

typedef int (*sj_blosc2_register_codec_t)(blosc2_codec*);
static bool serializejson_blosc2_rice_ok = false;

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
                   int shuffle, const char* cname, int nthreads, int channels,
                   size_t* out_size, long* out_frames)
{
    bool rice = (strcmp(cname, "rice") == 0);
    int compcode;
    if (rice) {
        if (!serializejson_blosc2_rice_ok)
            return nullptr;
        compcode = SJ_BLOSC2_CODEC_RICE;
    } else {
        compcode = sj_blosc2_compname_to_compcode(cname);
        if (compcode < 0)
            return nullptr;
    }
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
    for (int f = 0; f < BLOSC2_MAX_FILTERS; f++) {
        cparams.filters[f] = BLOSC_NOFILTER;
        cparams.filters_meta[f] = 0;
    }
    if (rice) {
        // le codec fait sa propre prédiction : aucun filtre devant ; largeur
        // d'échantillon (quartet bas) et canaux (quartet haut) passés par le
        // meta, persisté dans la trame ; pas de découpage en flux
        cparams.compcode_meta = (uint8_t) (typesize | (channels << 4));
        cparams.splitmode = BLOSC_NEVER_SPLIT;
    } else if (shuffle == 2 && serializejson_blosc2_delta_ok) {
        // pipeline shuffle -> delta d'octets (ordre MESURÉ gagnant : après
        // shuffle, chaque flux d'octets est lisse et le delta les linéarise)
        cparams.filters[BLOSC2_MAX_FILTERS - 2] = BLOSC_SHUFFLE;
        cparams.filters[BLOSC2_MAX_FILTERS - 1] = SJ_BLOSC2_FILTER_DELTA;
    } else
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
sj_decompress_worker(std::vector<SjDecompressJob>* jobs, std::atomic<size_t>* next,
                     int inner_threads)
{
    // inner_threads > 1 quand il y a moins de trames que de coeurs (cas
    // courant : UNE grosse trame compressée par le MT interne du fork) —
    // la décompression est déterministe par nature, aucune contrainte d'ordre
    blosc2_dparams dparams = BLOSC2_DPARAMS_DEFAULTS;
    dparams.nthreads = (int16_t) inner_threads;
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
        "channels",
        nullptr
    };
    PyObject* value = nullptr;
    Py_ssize_t typesize = 1;
    int clevel = 5;
    int shuffle = 1;
    const char* cname = "blosclz";
    int nthreads = 1;
    int channels = 1;  // canaux entrelacés (codec rice seulement)

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|niisii", (char**) kwlist,
                                     &value, &typesize, &clevel, &shuffle,
                                     &cname, &nthreads, &channels))
        return nullptr;
    if (channels < 1 || channels > 15)
        channels = 1;  // le quartet du meta est la limite du format

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
                                     nthreads, channels, &chunked_size,
                                     &frames);
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

    // trame unique par l'API contextes : NÉCESSAIRE pour le filtre delta et
    // le codec Rice — la voie blosc1 ne connaît ni les pipelines de filtres
    // ni les codecs enregistrés, et son paramètre shuffle=2 signifierait
    // bitshuffle. Le nombre de threads du contexte reprend le réglage global
    // (déterministe avec le fork, octets stables quel que soit leur nombre).
    bool rice = (strcmp(cname, "rice") == 0);
    if (((shuffle == 2 && serializejson_blosc2_delta_ok)
         || (rice && serializejson_blosc2_rice_ok))
        && serializejson_blosc2_ctx_ok
        && (size_t) view.len < (size_t) INT32_MAX - BLOSC2_MAX_OVERHEAD) {
        int compcode;
        if (rice)
            compcode = SJ_BLOSC2_CODEC_RICE;
        else {
            compcode = sj_blosc2_compname_to_compcode(cname);
            if (compcode < 0) {
                PyBuffer_Release(&view);
                PyErr_Format(PyExc_ValueError, "unknown blosc compressor '%s'",
                             cname);
                return nullptr;
            }
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
        if (rice) {
            cparams.compcode_meta = (uint8_t) (typesize | (channels << 4));
            cparams.splitmode = BLOSC_NEVER_SPLIT;
        } else {
            // pipeline shuffle -> delta d'octets (ordre MESURÉ gagnant)
            cparams.filters[BLOSC2_MAX_FILTERS - 2] = BLOSC_SHUFFLE;
            cparams.filters[BLOSC2_MAX_FILTERS - 1] = SJ_BLOSC2_FILTER_DELTA;
        }
        size_t delta_dest_size = (size_t) view.len + BLOSC2_MAX_OVERHEAD;
        char* delta_dest = (char*) malloc(delta_dest_size);
        if (delta_dest == nullptr) {
            PyBuffer_Release(&view);
            PyErr_NoMemory();
            return nullptr;
        }
        int delta_csize = -1;
        Py_BEGIN_ALLOW_THREADS
        blosc2_context* delta_ctx = sj_blosc2_create_cctx(cparams);
        if (delta_ctx != nullptr) {
            delta_csize = sj_blosc2_compress_ctx(
                delta_ctx, view.buf, (int32_t) view.len, delta_dest,
                (int32_t) delta_dest_size);
            sj_blosc2_free_ctx(delta_ctx);
        }
        Py_END_ALLOW_THREADS
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
        ((BloscToBase64*) self)->frames = 1;
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
