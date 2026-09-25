// -*- coding: utf-8 -*-
// :Project:   python-rapidjson -- Python extension module
// :Author:    Ken Robbins <ken@kenrobbins.com>
// :License:   MIT License
// :Copyright: © 2015 Ken Robbins
// :Copyright: © 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022 Lele Gaifax
//

// chemins SIMD de rapidjson (saut d'espaces et scan des chaînes sans
// échappement) — la machine cible compile déjà en -march=native. Pas en
// WebAssembly (lecteur web sous Pyodide), qui n'a pas SSE4.2.
#ifndef __EMSCRIPTEN__
#define RAPIDJSON_SSE42
#endif

// exigée par les formats « # » de PyArg_ParseTuple/Py_BuildValue, qui sans
// elle lèvent SystemError avant Python 3.13 (où Python.h la pose d'office)
#define PY_SSIZE_T_CLEAN

#include <locale.h>
#include <Python.h>
#include <datetime.h>
#include <structmember.h>
#include <algorithm>
#include <cmath>
#include <memory>
#include <string>
#include <vector>
#include <unordered_map>
#include <dlfcn.h>

// copie brute vers str quand tout le buffer est resté ascii (drapeau
// maybe_non_ascii) : évite la passe de validation du décodeur utf-8
static inline PyObject* sj_unicode_from_ascii(const char* s, Py_ssize_t size) {
    PyObject* u = PyUnicode_New(size, 127);
    if (u != nullptr)
        memcpy(PyUnicode_1BYTE_DATA(u), s, (size_t) size);
    return u;
}

// « un octet >= 0xC4 dans le mot ? » — c'est-à-dire : cette tranche sort-elle
// du régime latin-1, où tout point de code tient sur un octet ? Écrit comme
// un « un octet < 60 » sur le complément (0xC4 <=> 255 - 60), l'idiome SWAR
// de la maison, valable pour un seuil <= 128.
//
// L'emprunt d'un octet sur le suivant, qui rend cet idiome inexact en
// général, est ici sans effet : il ne se produit QUE sur un octet déjà
// détecté, donc jamais sur un mot qui devait rendre zéro.
static inline uint64_t sj_has_above_c3(uint64_t w) {
    const uint64_t x = ~w;
    return (x - UINT64_C(0x3C3C3C3C3C3C3C3C)) & ~x
           & UINT64_C(0x8080808080808080);
}

// décodage utf-8 -> latin-1, dans un tampon d'octets fourni : rend le nombre
// de caractères écrits, ou (size_t) -1 si la chaîne est mal formée — cas
// rendu à CPython, seul à savoir lever le UnicodeDecodeError attendu, avec
// sa position. L'appelant a déjà écarté les octets >= 0xC4 : il ne reste
// que 0xC2/0xC3 suivis d'une continuation, séquences ni surlongues ni
// substituts, donc validées par la seule forme de la continuation.
static inline size_t sj_latin1_core(const char* s, size_t len,
                                    unsigned char* d) {
    const unsigned char* d0 = d;
    size_t i = 0;
    while (i < len) {
        const unsigned char c = (unsigned char) s[i];
        if (c < 0x80) {
            *d++ = c;
            i++;
            continue;
        }
        if (i + 1 >= len || ((unsigned char) s[i + 1] & 0xC0) != 0x80)
            return (size_t) -1;
        *d++ = (unsigned char) (((c & 0x03) << 6)
                                | ((unsigned char) s[i + 1] & 0x3F));
        i += 2;
    }
    return (size_t) (d - d0);
}

// Un str latin-1 est plus COURT que ses octets : sa taille n'est connue
// qu'une fois décodé. Deux façons de s'en tirer, chacune la meilleure sur
// son régime (mesuré contre PyUnicode_FromStringAndSize sur les mêmes
// octets) : décoder dans un tampon de pile puis allouer juste, ce qui vaut
// -41 % à 61 octets et -44 % à 8 ; ou allouer à la borne haute puis recopier
// à la taille vraie, ce qui vaut -52 % sur un mégaoctet, là où la pile ne
// suffit plus. Le seuil sépare les deux.
static const size_t SJ_LATIN1_PILE = 1024;

static PyObject* sj_unicode_from_latin1(const char* s, size_t len) {
    if (len <= SJ_LATIN1_PILE) {
        unsigned char pile[SJ_LATIN1_PILE];
        const size_t n = sj_latin1_core(s, len, pile);
        if (n == (size_t) -1)
            return nullptr;
        PyObject* u = PyUnicode_New((Py_ssize_t) n, 255);
        if (u != nullptr)
            memcpy(PyUnicode_1BYTE_DATA(u), pile, n);
        return u;
    }
    PyObject* large = PyUnicode_New((Py_ssize_t) len, 255);   // borne haute
    if (large == nullptr)
        return nullptr;
    const size_t n = sj_latin1_core(s, len, PyUnicode_1BYTE_DATA(large));
    if (n == (size_t) -1) {
        Py_DECREF(large);
        return nullptr;
    }
    PyObject* u = PyUnicode_New((Py_ssize_t) n, 255);
    if (u != nullptr)
        memcpy(PyUnicode_1BYTE_DATA(u), PyUnicode_1BYTE_DATA(large), n);
    Py_DECREF(large);
    return u;
}

// « la chaîne sort-elle du régime latin-1 ? », par mots de 8 octets
static inline bool sj_hors_latin1(const char* s, size_t len) {
    uint64_t hors = 0;
    size_t i = 0;
    for (; i + 8 <= len; i += 8) {
        uint64_t w;
        memcpy(&w, s + i, 8);
        hors |= sj_has_above_c3(w);
    }
    for (; i < len; i++)
        hors |= ((unsigned char) s[i] >= 0xC4);
    return hors != 0;
}

// création d'un str depuis de l'utf-8 : le balayage ascii choisit entre
// trois fabrications, de la moins chère à la plus chère — copie brute,
// décodage latin-1 maison, décodeur de CPython. La deuxième est ce que ce
// balayage rapportait de neuf : il ne servait jusqu'ici qu'à séparer l'ascii
// du reste, et tout le reste — donc tout texte accentué — repartait au
// décodeur générique.
//
// Le régime est cherché en SECOND balayage, et non fondu dans le premier :
// fondu, il faisait payer 5,5 % aux chaînes ascii échappées, qui passent
// aussi par ici sans rien avoir à y gagner. Séparé, il n'est parcouru que
// par les chaînes non ascii, où il ouvre un gain de moitié.
static inline PyObject* sj_unicode_from_utf8(const char* s, size_t len) {
    // 0 et 1 octet : le chemin standard renvoie les singletons du cache
    // (chaine vide, caracteres latin1) sans allocation
    if (len < 2)
        return PyUnicode_FromStringAndSize(s, (Py_ssize_t) len);
    uint64_t acc = 0;
    size_t i = 0;
    for (; i + 8 <= len; i += 8) {
        uint64_t w;
        memcpy(&w, s + i, 8);
        acc |= w;
    }
    for (; i < len; i++)
        acc |= (unsigned char) s[i];
    if (!(acc & UINT64_C(0x8080808080808080)))
        return sj_unicode_from_ascii(s, (Py_ssize_t) len);
    if (!sj_hors_latin1(s, len)) {
        PyObject* u = sj_unicode_from_latin1(s, len);
        if (u != nullptr)
            return u;
        PyErr_Clear();          // mal formée : au décodeur, pour l'erreur
    }
    return PyUnicode_FromStringAndSize(s, (Py_ssize_t) len);
}

// variante guidée par l'indice du scan SSE du reader : 1 = prouvé pur
// ascii sans échappement -> copie brute directe, sans re-scan du contenu
static inline PyObject* sj_unicode_from_utf8_hint(const char* s, size_t len,
                                                  int asciiHint) {
    if (asciiHint == 1 && len >= 2)
        return sj_unicode_from_ascii(s, (Py_ssize_t) len);
    return sj_unicode_from_utf8(s, len);
}

#include "serializejson.h"
#include "dtoa_repr.h"
#include "reader.h"
#include "schema.h"
#include "stringbuffer.h"
#include "writer.h"
#include "prettywriter.h"
#include "error/en.h"
#include "pywritestreamwrapper.h"
#include "pybytesbuffer.h"
#include "fdwritestream.h"
#include "indexscan.h"
#include "sjcrypto.h"


using namespace rapidjson;


/* On some MacOS combo, using Py_IS_XXX() macros does not work (see
   https://github.com/python-rapidjson/python-rapidjson/issues/78).
   OTOH, MSVC < 2015 does not have std::isxxx() (see
   https://stackoverflow.com/questions/38441740/where-is-isnan-in-msvc-2010).
   Oh well... */

#if defined (_MSC_VER) && (_MSC_VER < 1900)
#define IS_NAN(x) Py_IS_NAN(x)
#define IS_INF(x) Py_IS_INFINITY(x)
#else
#define IS_NAN(x) std::isnan(x)
#define IS_INF(x) std::isinf(x)
#endif

#define WORTH_BUFFER_BYPASS 256 // size (to ajust) from which it is worth the cost to build a PyMemoryView and call file.write(). to tuen

static PyObject* decimal_type = nullptr;
static PyObject* timezone_type = nullptr;
static PyObject* timezone_utc = nullptr;
static PyObject* uuid_type = nullptr;
static PyObject* struct_time_type = nullptr;
static PyObject* validation_error = nullptr;
static PyObject* decode_error = nullptr;


/* These are the names of oftenly used methods or literal values, interned in the module
   initialization function, to avoid repeated creation/destruction of PyUnicode values
   from plain C strings.

   We cannot use _Py_IDENTIFIER() because that upsets the GNU C++ compiler in -pedantic
   mode. */

static PyObject* astimezone_name = nullptr;
static PyObject* hex_name = nullptr;
static PyObject* timestamp_name = nullptr;
static PyObject* total_seconds_name = nullptr;
static PyObject* utcoffset_name = nullptr;
static PyObject* is_infinite_name = nullptr;
static PyObject* is_nan_name = nullptr;
static PyObject* start_object_name = nullptr;
static PyObject* end_object_name = nullptr;
static PyObject* default_name = nullptr;
static PyObject* default_dict_name = nullptr;
static PyObject* default_list_name = nullptr;
static PyObject* class_plan_name = nullptr;
static PyObject* dict_dunder_name = nullptr;
static PyObject* decode_class_plan_name = nullptr;
static PyObject* fast_start_object_name = nullptr;
static PyObject* fast_plain_end_object_name = nullptr;
static PyObject* root_attr_name = nullptr;
static PyObject* class_key_name = nullptr;
static PyObject* ref_key_name = nullptr;
// marqueur one-shot « la prochaine valeur est le résultat de default() »
// pour les dumps sans pathTracker (toujours manipulé sous GIL)
static bool sj_next_dict_is_attrs_noplan = false;
// cache ÉCRITURE des valeurs de type : classe -> nom émis ("type" inversé
// du cache de lecture) — rempli au premier passage par la recette python,
// servi ensuite par la branche native (réfs fortes, durée de vie module)
static PyObject* sj_type_names_cache = nullptr;

// enrichit l'AttributeError d'une restauration d'attribut au chargement :
// la classe et la clé fautive, avec l'erreur d'origine en cause — le
// message brut de setattr ne disait pas OÙ chercher (slot manquant,
// property sans setter, attribut renommé...)
static void
sj_enrich_setattr_error(PyObject* inst, PyObject* attr_key)
{
    if (!PyErr_ExceptionMatches(PyExc_AttributeError))
        return;
    PyObject* etype;
    PyObject* evalue;
    PyObject* etraceback;
    PyErr_Fetch(&etype, &evalue, &etraceback);
    PyErr_NormalizeException(&etype, &evalue, &etraceback);
    // format ASCII pur : PyUnicode_FromFormat refuse un format non-ascii
    PyObject* message = PyUnicode_FromFormat(
        "serializejson : impossible de poser l'attribut %R en rechargeant "
        "un objet %s (cle du JSON sans slot ni setter correspondant ? "
        "attribut renomme ?) : %S",
        attr_key, Py_TYPE(inst)->tp_name,
        evalue ? evalue : Py_None);
    if (message == nullptr) {
        PyErr_Restore(etype, evalue, etraceback);
        return;
    }
    PyObject* enriched = PyObject_CallFunctionObjArgs(
        PyExc_AttributeError, message, nullptr);
    Py_DECREF(message);
    if (enriched == nullptr) {
        PyErr_Restore(etype, evalue, etraceback);
        return;
    }
    if (evalue != nullptr) {
        Py_INCREF(evalue);
        PyException_SetCause(enriched, evalue);  // vole la référence
    }
    Py_XDECREF(etype);
    Py_XDECREF(evalue);
    Py_XDECREF(etraceback);
    PyErr_SetObject(PyExc_AttributeError, enriched);
    Py_DECREF(enriched);
}
static PyObject* init_key_name = nullptr;
static PyObject* new_key_name = nullptr;
static PyObject* state_key_name = nullptr;
static PyObject* items_key_name = nullptr;
static PyObject* empty_args_tuple = nullptr;
static PyObject* b64_payload_classes_name = nullptr;
static PyObject* type_values_cache_name = nullptr;
static PyObject* end_array_name = nullptr;
static PyObject* string_name = nullptr;
static PyObject* read_name = nullptr;
static PyObject* write_name = nullptr;
static PyObject* encoding_name = nullptr;

// protocole serializejson : types enregistrés par register_serializejson()
// et module serialize_parameters (paramètres globaux, poussée amortie)
static PyObject* sj_encoder_type = nullptr;
static PyObject* sj_decoder_type = nullptr;
static PyObject* sj_params_module = nullptr;
static PyObject* owner_name = nullptr;
static PyObject* decoder_owner_name = nullptr;
static PyObject* update_parameters_name = nullptr;
static PyObject* push_decode_parameters_name = nullptr;
static PyObject* call_update_name = nullptr;
static PyObject* resolve_duplicates_name = nullptr;
static PyObject* dumped_classes_name = nullptr;
static PyObject* bytes_natif_seuil_name = nullptr;
static PyObject* cle_json_name = nullptr;             // "_cle_json"
static PyObject* default_one_line_name = nullptr;     // "_default_one_line"
static PyObject* bytes_class_name_str = nullptr;      // "bytes"
static PyObject* bytearray_class_name_str = nullptr;  // "bytearray"
static PyObject* collections_prefix_str = nullptr;    // "collections."
static PyObject* decode_cle_name = nullptr;
static PyObject* construct_name = nullptr;            // "construct"
static PyObject* live_root_name = nullptr;            // "_live_root"
static PyObject* reconcile_name = nullptr;            // "_reconcile"
static PyObject* updatables_name = nullptr;           // "updatableClassStrs"
static PyObject* already_serialized_name = nullptr;
static PyObject* keep_alive_name = nullptr;
static PyObject* root_underscore_name = nullptr;
static PyObject* chunk_size_name = nullptr;
static PyObject* converted_numpy_name = nullptr;
static PyObject* not_authorized_name = nullptr;
static PyObject* updating_name = nullptr;
static PyObject* startswith_curly_name = nullptr;
static PyObject* duplicates_name = nullptr;
static PyObject* dotdict_name = nullptr;
static PyObject* class_from_attributes_name = nullptr;
static PyObject* strict_pickle_name = nullptr;
static PyObject* setters_name = nullptr;
static PyObject* properties_name = nullptr;

static PyObject* minus_inf_string_value = nullptr;
static PyObject* nan_string_value = nullptr;
static PyObject* plus_inf_string_value = nullptr;


// Au-delà de ce nombre d'éléments, la tranche en attente est versée et la
// liste reprend sa croissance ordinaire : le différé économise les
// allocations successives, mais ajoute une recopie du tampon, qui cesse
// d'être gratuite dès qu'elle sort du cache. 4 096 pointeurs tiennent en
// 32 ko. Sans plafond, un tableau plat perd 9,5 % à 200 000 entiers et
// 17,7 % à 2 millions ; avec, il est au niveau de l'ancien code (+0,7 %),
// et les gains sur les listes courantes sont intacts. Les valeurs voisines
// (256, 1 024, 65 536) ne s'en séparent pas sous la charge de la mesure.
static const size_t SJ_ATTENTE_MAX = 4096;

struct HandlerContext {
    PyObject* object;
    const char* key;
    SizeType keyLength;
    bool isObject;
    bool keyValuePairs;
    bool copiedKey;
    // vrai si une clé "__class__" ou "$ref" a été vue dans ce dict : les
    // dicts SANS clé spéciale peuvent sauter le end_object Python quand le
    // décodeur l'a certifié (_fast_plain_end_object)
    bool specialKey;
    // reconnaissance des ENVELOPPES au parse : {"__class__": nom,
    // "__new__"/"__init__": args} capturé au vol SANS remplir le dict — la
    // fin d'objet instancie directement (EnvelopeConstruct) ; au moindre
    // écart de forme, EnvFlush verse la capture dans le dict et la voie
    // classique reprend, octets et sémantique inchangés.
    //   0 : dict normal ; 1 : "__class__" vu, valeur attendue ;
    //   2 : classe capturée ; 3 : "__new__"/"__init__" vu, args attendus ;
    //   4 : args capturés
    //   5 : "__items__" vu, items attendus ; 6 : items capturés
    uint8_t envState;
    uint8_t envSlot;          // 1 : __new__ ; 2 : __init__
    //   7 : enveloppe de dict à clés non-str — les clés sont DÉCODÉES au
    //   vol et les paires insérées directement dans object (qui devient le
    //   dict FINAL, sans étiquette) ; envDictKey est la clé décodée en
    //   attente de sa valeur (nulle : valeur à jeter, __class__ dupliqué)
    PyObject* envClass;       // référence possédée (ou nullptr)
    PyObject* envArgs;        // référence possédée (ou nullptr)
    PyObject* envItems;       // référence possédée (ou nullptr)
    PyObject* envDictKey;     // référence possédée (ou nullptr)
    // $ref résolu AU VOL, à l'événement String de sa valeur : le dict reste
    // vide et sera jeté à sa fermeture. Le chemin brut (pointeur dans le
    // tampon insitu, stable jusqu'à la fin du parse) permet de réinsérer la
    // paire si une clé supplémentaire dément la forme {"$ref": chemin} seule
    PyObject* refResolu;      // référence possédée (ou nullptr)
    const char* refCheminBrut;
    SizeType refCheminBrutLg;
    // Remplissage DIFFÉRÉ des listes json : les éléments s'empilent dans
    // `attente` et la liste n'est remplie qu'à sa fermeture, d'un bloc, à la
    // taille EXACTE. La faire grandir par appends demande une allocation à 4,
    // 8, 16, 25… éléments : sur des documents entiers, A/B interlacé, le load
    // gagne 14 % (dicts et petites listes), 27 % (tableau de tableaux de 50)
    // et 14 à 17 % (listes de 20), sans rien perdre ailleurs. Le compte vient
    // de rapidjson (EndArray) : l'index de positions, lui, ne retient que
    // les conteneurs d'au moins 1 ko, où il n'y a justement plus rien à
    // gagner (mesuré 1,7 %).
    size_t attenteBase;       // premier élément de CE niveau dans `attente`
    bool differe;             // faux dès que les éléments sont dans la liste
    // réhydratation : l'instance rangée dans __class__ à ce niveau sort de
    // tp_new (object.__new__) sans arguments — son __dict__ est vide, aucun
    // homologue vivant ne peut exister sous elle, et son état s'assigne
    // d'un bloc (dict entier) au lieu d'être fusionné clé par clé
    bool envFresh;
    // réhydratation : la construction de ce niveau a été tentée (faite ou
    // déclinée) — les clés d'état suivantes ne la rejouent pas
    bool envConstruit;
};


// détient des références fortes relâchées à la sortie de portée (les
// valeurs de slots viennent de PyObject_GetAttr, contrairement aux valeurs
// de __dict__ qui sont empruntées)
struct SjOwnedRefs {
    std::vector<PyObject*> refs;
    ~SjOwnedRefs() {
        for (PyObject* ref : refs)
            Py_DECREF(ref);
    }
};


// vrai si l'instance est d'un type serializejson enregistré (ou dérivé)
static inline bool
sj_is_registered(PyObject* self, PyObject* registered)
{
    if (registered == nullptr)
        return false;
    if ((PyObject*) Py_TYPE(self) == registered)
        return true;
    return PyType_IsSubtype(Py_TYPE(self), (PyTypeObject*) registered);
}


// pose un attribut volatil fraîchement créé (référence volée), en
// contournant l'éventuel __setattr__ du sous-type : les attributs volatils
// ne doivent pas invalider la poussée amortie des paramètres globaux
static int
sj_set_new_volatile(PyObject* self, PyObject* name, PyObject* value)
{
    if (value == nullptr)
        return -1;
    int r = PyObject_GenericSetAttr(self, name, value);
    Py_DECREF(value);
    return r;
}


enum DatetimeMode {
    DM_NONE = 0,
    // Formats
    DM_ISO8601 = 1<<0,      // Bidirectional ISO8601 for datetimes, dates and times
    DM_UNIX_TIME = 1<<1,    // Serialization only, "Unix epoch"-based number of seconds
    // Options
    DM_ONLY_SECONDS = 1<<4, // Truncate values to the whole second, ignoring micro seconds
    DM_IGNORE_TZ = 1<<5,    // Ignore timezones
    DM_NAIVE_IS_UTC = 1<<6, // Assume naive datetime are in UTC timezone
    DM_SHIFT_TO_UTC = 1<<7, // Shift to/from UTC
    DM_MAX = 1<<8
};


#define DATETIME_MODE_FORMATS_MASK 0x0f // 0b00001111 in C++14


static inline int
datetime_mode_format(unsigned mode) {
    return mode & DATETIME_MODE_FORMATS_MASK;
}


static inline bool
valid_datetime_mode(int mode) {
    int format = datetime_mode_format(mode);
    return (mode >= 0 && mode < DM_MAX
            && (format <= DM_UNIX_TIME)
            && (mode == 0 || format > 0));
}


static int
days_per_month(int year, int month) {
    assert(month >= 1);
    assert(month <= 12);
    if (month == 1 || month == 3 || month == 5 || month == 7
        || month == 8 || month == 10 || month == 12) {
        return 31;
    } else if (month == 4 || month == 6 || month == 9 || month == 11) {
        return 30;
    } else if (year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)) {
        return 29;
    } else {
        return 28;
    }
}


enum UuidMode {
    UM_NONE = 0,
    UM_CANONICAL = 1<<0, // 4-dashed 32 hex chars: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    UM_HEX = 1<<1,       // canonical OR 32 hex chars in a row
    UM_MAX = 1<<2
};


enum NumberMode {
    NM_NONE = 0,
    NM_NAN = 1<<0,     // allow "not-a-number" values
    NM_DECIMAL = 1<<1, // serialize Decimal instances, deserialize floats as Decimal
    NM_NATIVE = 1<<2,  // use faster native C library number handling
    NM_MAX = 1<<3
};


enum BytesMode {
    BM_NONE = 0,
    BM_UTF8 = 1<<0,             // try to convert to UTF-8
    BM_MAX = 1<<1
};


enum ParseMode {
    PM_NONE = 0,
    PM_COMMENTS = 1<<0,         // Allow one-line // ... and multi-line /* ... */ comments
    PM_TRAILING_COMMAS = 1<<1,  // allow trailing commas at the end of objects and arrays
    PM_MAX = 1<<2
};


enum WriteMode {
    WM_COMPACT = 0,
    WM_PRETTY = 1<<0,            // Use PrettyWriter
    WM_SINGLE_LINE_ARRAY = 1<<1, // Format arrays on a single line
    WM_MAX = 1<<2
};


enum IterableMode {
    IM_ANY_ITERABLE = 0,        // Default, any iterable is dumped as JSON array
    IM_ONLY_LISTS = 1<<0,       // Only list instances are dumped as JSON arrays
    IM_MAX = 1<<1
};


enum MappingMode {
    MM_ANY_MAPPING = 0,                // Default, any mapping is dumped as JSON object
    MM_ONLY_DICTS = 1<<0,              // Only dict instances are dumped as JSON objects
    MM_COERCE_KEYS_TO_STRINGS = 1<<1,  // Convert keys to strings
    MM_SKIP_NON_STRING_KEYS = 1<<2,    // Ignore non-string keys
    MM_SORT_KEYS = 1<<3,               // Sort keys
    MM_MAX = 1<<4
};


//////////////////////////
// Forward declarations //
//////////////////////////


static PyObject* do_decode(PyObject* decoder,
                           const char* jsonStr, Py_ssize_t jsonStrlen,
                           PyObject* jsonStream, size_t chunkSize,
                           PyObject* objectHook,
                           unsigned numberMode, unsigned datetimeMode,
                           unsigned uuidMode, unsigned parseMode);
extern PyTypeObject Decoder_Type;
static void decoder_dealloc(PyObject* self);
static PyObject* decoder_call(PyObject* self, PyObject* args, PyObject* kwargs);
static PyObject* decoder_decode_fn(PyObject* self, PyObject* args, PyObject* kwargs);
static PyObject* decoder_new(PyTypeObject* type, PyObject* args, PyObject* kwargs);


// Suivi du chemin JSON courant pendant l'encodage ("root[0].attr['clef']"),
// pour que les hooks default/default_dict/default_list puissent mémoriser où
// chaque objet a été écrit et émettre des {"$ref": chemin} sans avoir à
// remonter le graphe avec gc.get_referrers côté Python.
// (défini dans indexscan.h : l'index construit à l'écriture vit dans
// l'écrivain, qui n'inclut pas ce fichier, et compose les mêmes chemins)
using PathSegment = SjSegment;
// noeud matérialisé d'un chemin : arbre à partage structurel, un noeud par
// position réellement demandée via json_path_id() (la clé y est COPIÉE car
// les pointeurs empruntés des segments peuvent mourir avant la fin du dump)
struct PathNode {
    int parent;   // index dans nodes, -1 pour un enfant direct de root
    PathSegment::Kind kind;
    std::string key;
    Py_ssize_t index;
    // {"$ref": "..."} rendu et échappé, composé à la PREMIÈRE référence vers
    // ce noeud puis resservi tel quel : les documents à répliques (types,
    // singletons...) émettent des centaines de fois le même $ref (~0,4 µs
    // la composition, mesuré sur le lot types)
    std::string refJson;
};
// table de hachage a adressage ouvert specialisee pointeur -> long :
// remplace unordered_map pour le memo des conteneurs (~13% du temps
// d'encodage des graphes de conteneurs mesure au profil)
struct PtrMemo {
    struct Slot { PyObject* first; long second; };
    struct It {
        Slot* p;
        Slot* operator->() const { return p; }
        bool operator!=(const It& o) const { return p != o.p; }
        bool operator==(const It& o) const { return p == o.p; }
    };
    std::vector<Slot> slots;
    size_t mask = 0;
    size_t count = 0;

    static inline size_t hash(PyObject* k) {
        // en 64 bits même quand les pointeurs n'en font que 32 (WebAssembly) :
        // un décalage de 33 sur un uintptr_t de 32 bits est indéfini, et clang
        // en fait un piège (unreachable)
        uint64_t h = (uint64_t) (uintptr_t) k;
        h ^= h >> 33; h *= 0xff51afd7ed558ccdULL; h ^= h >> 29;
        return (size_t) h;
    }
    void rehash(size_t newSize) {
        std::vector<Slot> old_slots;
        old_slots.swap(slots);
        slots.assign(newSize, Slot{nullptr, 0});
        mask = newSize - 1;
        for (Slot& s : old_slots)
            if (s.first) {
                size_t i = hash(s.first) & mask;
                while (slots[i].first) i = (i + 1) & mask;
                slots[i] = s;
            }
    }
    void reserve(size_t n) {
        size_t needed = 16;
        while (needed * 7 < (n + 1) * 10) needed <<= 1;
        if (needed > slots.size()) rehash(needed);
    }
    It end() { return It{nullptr}; }
    It find(PyObject* k) {
        if (!count) return end();
        size_t i = hash(k) & mask;
        while (slots[i].first) {
            if (slots[i].first == k) return It{&slots[i]};
            i = (i + 1) & mask;
        }
        return end();
    }
    // sonde unique : renvoie l'emplacement du couple si présent (found=vrai),
    // sinon réserve le slot (clé posée, valeur à remplir par l'appelant)
    Slot* find_or_reserve(PyObject* k, bool* found) {
        if ((count + 1) * 10 >= slots.size() * 7)
            rehash(slots.empty() ? 16 : slots.size() * 2);
        size_t i = hash(k) & mask;
        while (slots[i].first) {
            if (slots[i].first == k) { *found = true; return &slots[i]; }
            i = (i + 1) & mask;
        }
        slots[i].first = k;
        count++;
        *found = false;
        return &slots[i];
    }
    void emplace(PyObject* k, long v) {
        if ((count + 1) * 10 >= slots.size() * 7)
            rehash(slots.empty() ? 16 : slots.size() * 2);
        size_t i = hash(k) & mask;
        while (slots[i].first) {
            if (slots[i].first == k) return;  // deja present, comme emplace
            i = (i + 1) & mask;
        }
        slots[i] = Slot{k, v};
        count++;
    }
    size_t size() const { return count; }
    void decref_keys() {
        for (Slot& s : slots)
            if (s.first)
                Py_DECREF(s.first);
    }
};

// --- conversion parallèle des listes homogènes de nombres ---------------
// Les valeurs sont extraites sous GIL en tableau C, converties en texte par
// tranches d'index fixes sur plusieurs threads (GIL relâché), puis recollées
// dans l'ordre : octets strictement identiques au chemin séquentiel.

#define SJ_NUM_MT_MIN 32768
#define SJ_NUM_MT_CHUNK 16384

struct sj_numchunk {
    std::vector<char> text;
};

// brouillons réutilisés d'un dump à l'autre (possédés par l'Encoder) : les
// vecteurs gardent leur capacité, donc leurs pages déjà touchées — un malloc
// de 8 Mo par dump repasserait par mmap et re-paierait les défauts de page
struct SjMtScratch {
    std::vector<long long> ivals;
    std::vector<double> dvals;
    std::vector<sj_numchunk> chunks;
};

static void
sj_render_int_chunk(const long long* vals, size_t n, sj_numchunk& out)
{
    out.text.resize(n * 21);
    char* cursor = out.text.data();
    for (size_t i = 0; i < n; i++) {
        if (i)
            *cursor++ = ',';
        cursor = rapidjson::internal::i64toa(vals[i], cursor);
    }
    out.text.resize((size_t) (cursor - out.text.data()));
}

static void
sj_render_double_chunk(const double* vals, size_t n, sj_numchunk& out)
{
    out.text.resize(n * 28);
    char* base = out.text.data();
    char* cursor = base;
    for (size_t i = 0; i < n; i++) {
        if (i)
            *cursor++ = ',';
        double v = vals[i];
        if (IS_NAN(v)) {
            memcpy(cursor, "NaN", 3); cursor += 3;
        } else if (IS_INF(v)) {
            if (v < 0) { memcpy(cursor, "-Infinity", 9); cursor += 9; }
            else       { memcpy(cursor, "Infinity", 8);  cursor += 8; }
        } else {
            cursor += sjdtoa::ReprDouble(v, cursor);
        }
    }
    out.text.resize((size_t) (cursor - base));
}

// lance nthreads sur les tranches (atomic d'index), GIL relâché par l'appelant
template <typename T, void (*RENDER)(const T*, size_t, sj_numchunk&)>
static void
sj_render_chunks_parallel(const T* vals, size_t total,
                          std::vector<sj_numchunk>& chunks, size_t nthreads)
{
    size_t nchunks = chunks.size();
    std::atomic<size_t> next(0);
    auto work = [&]() {
        for (;;) {
            size_t c = next.fetch_add(1);
            if (c >= nchunks)
                return;
            size_t begin = c * SJ_NUM_MT_CHUNK;
            size_t n = std::min((size_t) SJ_NUM_MT_CHUNK, total - begin);
            RENDER(vals + begin, n, chunks[c]);
        }
    };
    std::vector<std::thread> pool;
    for (size_t t = 1; t < nthreads; t++)
        pool.emplace_back(work);
    work();
    for (std::thread& t : pool)
        t.join();
}

// recolle les tranches dans le flux ; l'appelant a déjà écrit StartArray
// et fera AnnounceArrayValues+EndArray
template <typename WriterT>
static bool
sj_splice_chunks(WriterT* writer, std::vector<sj_numchunk>& chunks)
{
    auto& os = writer->Os();
    bool first_chunk = true;
    for (sj_numchunk& chunk : chunks) {
        if (!first_chunk)
            os.Put(',');
        first_chunk = false;
        os.RawValue(chunk.text.data(), chunk.text.size());
    }
    return true;
}

// plan de forme d'un dict : la séquence exacte de ses clés (références
// fortes) et leurs graphies pré-échappées. Les listes d'enregistrements
// homogènes re-rencontrent la même séquence de pointeurs de clés : les clés
// s'écrivent alors en RawValue, sans re-scan ni re-échappement par clé.
#define SJ_SHAPE_MAX_KEYS 64
struct DictShape {
    std::vector<PyObject*> keys;                          // réfs fortes
    std::vector<std::string> fragments;                   // "clef" prêt à écrire
    std::vector<std::pair<const char*, size_t>> key_strs; // utf-8 emprunté (vivant via keys)
    void clear_refs() {
        for (PyObject* k : keys)
            Py_DECREF(k);
        keys.clear();
        fragments.clear();
        key_strs.clear();
    }
};

struct PathTracker {
    std::vector<PathSegment> segments;
    // pile parallèle à segments : index du PathNode déjà matérialisé pour ce
    // niveau, ou -1 si pas encore demandé. Invariant : préfixe rempli puis
    // suffixe de -1 (les push ajoutent -1 en queue, les pop retirent en
    // queue, materialize remplit tout) — firstUnregistered borne le préfixe
    std::vector<int> registered;
    size_t firstUnregistered = 0;
    std::vector<PathNode> nodes;
    // mémo C++ des dicts/listes déjà écrits (encoder memo_refs=True) :
    // conteneur -> index de PathNode ; garde une référence forte sur chaque
    // clé (relâchée par le destructeur, à la fin de l'encodage) pour qu'un id
    // de conteneur temporaire réutilisé ne passe pas pour un doublon
    PtrMemo memo;
    bool memoContainers = false;
    // Racine des chemins $ref, VIDE pour « root ». Un maillon d'`append` n'est
    // pas un document : il est écrit à sa place dans une liste, et un doublon
    // interne doit donc se désigner « root[3]['x'] » et non « root['x'] » —
    // c'est le chemin ABSOLU dans le fichier que la relecture sait suivre, et
    // que `rebase_refs` ramène sur la tranche quand on charge le maillon seul.
    std::string racine;
    std::string racineRefJson;    // composé au premier $ref vers la racine
    // Place du maillon INCONNUE : la liste n'a pas été remplie depuis le début,
    // donc aucun chemin absolu n'est composable. Écrire quand même écrirait un
    // fichier illisible, sans un mot — le doublon est relevé ici et l'encodage
    // échoue (voir encoder_call).
    bool racineInconnue = false;
    bool refImpossible = false;
    // chemin rapide par classe : class_plan(classe) est appelé UNE fois par
    // classe et par dump ; il retourne None (chemin Python complet) ou un
    // tuple (nom_de_classe, filtrer_underscores) autorisant l'écriture de
    // l'objet entièrement en C++ (attributs du __dict__, triés)
    PyObject* classPlanFn = nullptr;   // référence empruntée (encoder_call)
    // dumped_classes de l'Encoder (référence FORTE, posée par encoder_call
    // après le reset, libérée en fin d'appel) : les recettes
    // __serializejson__ y ajoutent le nom de classe émis
    PyObject* dumpedClasses = nullptr;
    // anneau des derniers noms AJOUTÉS à dumpedClasses (pointeurs empruntés,
    // valides le temps du dump) : les documents homogènes re-payaient un
    // PySet_Add par objet pour les mêmes noms. Une éviction ne coûte qu'un
    // PySet_Add redondant (idempotent), jamais un nom manquant
    PyObject* classesAjoutees[8] = {};
    unsigned classesAjouteesPos = 0;
    std::unordered_map<PyTypeObject*, PyObject*> classPlans;  // réfs possédées
    // écrit sur une seule ligne les listes homogènes de nombres, où qu'elles
    // soient (valeurs de dicts purs et sous-listes comprises)
    bool singleLineNumbers = false;
    bool singleLineInit = true;
    bool singleLineNew = true;
    bool strictPickle = false;
    // écriture native C des petits bytes/bytearray : longueur STRICTEMENT
    // inférieure à ce seuil -> enveloppe écrite ici sans rappel python
    // (0 : désactivé — pas d'Encoder serializejson, ou greffons bytes
    // remplacés par l'utilisateur ; posé par _bytes_natif_seuil)
    Py_ssize_t bytesNatifSeuil = 0;
    // écriture native C des dicts à clés non-str : rappel python _cle_json
    // de l'Encoder pour les seules clés exotiques (réf FORTE, None jamais
    // stocké — nullptr = chemin python complet). Le cache mémorise le texte
    // des clés exotiques par ÉGALITÉ (les répliques d'un même document
    // partagent leurs clés), créé au premier besoin, relâché en fin de dump
    PyObject* cleJsonFn = nullptr;
    PyObject* cleJsonCache = nullptr;
    // recette _default_one_line de l'Encoder (réf FORTE) : celle que
    // _cle_json passait à rapidjson.dumps. Sert de defaultFn au
    // sous-document des clés tuple/frozenset écrites nativement
    PyObject* defaultOneLineFn = nullptr;
    // vrai si le prochain dict rencontré est l'état d'un objet retourné par
    // default() : ses clés sont alors des attributs (".attr" et non "['clef']")
    bool next_dict_is_attrs = false;

    // 4 plans de forme, indexés par profondeur : des dicts imbriqués de
    // formes différentes ne s'écrasent pas mutuellement le cache
    DictShape shapes[4];
    // brouillons du multithread numérique, possédés par l'Encoder (survivent
    // au dump), nullptr pour les chemins sans Encoder
    SjMtScratch* mtScratch = nullptr;

    ~PathTracker() {
        for (DictShape& s : shapes)
            s.clear_refs();
        memo.decref_keys();
        for (auto& entry : classPlans)
            Py_DECREF(entry.second);
        Py_XDECREF(cleJsonFn);
        Py_XDECREF(cleJsonCache);
        Py_XDECREF(defaultOneLineFn);
    }
};

// matérialise (une seule fois par position) la chaîne des noeuds du chemin
// courant et retourne l'index du dernier (-1 = racine)
static long
path_tracker_materialize(PathTracker* tracker)
{
    // repart du premier niveau non enregistré (préfixe déjà matérialisé)
    size_t start = tracker->firstUnregistered;
    int parent = start ? tracker->registered[start - 1] : -1;
    for (size_t level = start; level < tracker->segments.size(); level++) {
        const PathSegment& segment = tracker->segments[level];
        PathNode node;
        node.parent = parent;
        node.kind = segment.kind;
        node.index = segment.index;
        if (segment.str != nullptr)
            node.key.assign(segment.str, segment.len);
        tracker->nodes.push_back(std::move(node));
        parent = (int) tracker->nodes.size() - 1;
        tracker->registered[level] = parent;
    }
    tracker->firstUnregistered = tracker->segments.size();
    return parent;
}

// ajoute path à ref_ en l'échappant pour une chaîne JSON : une clé de dict
// peut contenir guillemets, antislashs ou contrôles — insérée brute, elle
// rendait le document invalide (constaté sur {'a"b': ...} partagé)
static void
sj_ref_append_escape(std::string& ref_, const std::string& path)
{
    for (char c : path) {
        unsigned char u = (unsigned char) c;
        switch (c) {
        case '"':  ref_ += "\\\""; break;
        case '\\': ref_ += "\\\\"; break;
        case '\t': ref_ += "\\t"; break;
        case '\n': ref_ += "\\n"; break;
        case '\r': ref_ += "\\r"; break;
        default:
            if (u < 0x20) {
                char buffer[8];
                snprintf(buffer, sizeof(buffer), "\\u%04x", u);
                ref_ += buffer;
            } else {
                ref_ += c;
            }
        }
    }
}


static std::string
path_tracker_string(PathTracker* tracker, long node_index);

// {"$ref": "..."} du noeud node_index, composé et échappé à la PREMIÈRE
// demande puis mémoïsé sur le noeud (-1 = racine, forme constante)
static const std::string&
sj_ref_json(PathTracker* tracker, long node_index)
{
    static const std::string root_ref = "{\"$ref\": \"root\"}";
    if (tracker->racineInconnue)
        tracker->refImpossible = true;
    if (node_index < 0) {
        if (tracker->racine.empty())
            return root_ref;
        if (tracker->racineRefJson.empty())
            tracker->racineRefJson = "{\"$ref\": \"" + tracker->racine + "\"}";
        return tracker->racineRefJson;
    }
    PathNode& node = tracker->nodes[(size_t) node_index];
    if (node.refJson.empty()) {
        std::string ref_ = "{\"$ref\": \"";
        sj_ref_append_escape(ref_, path_tracker_string(tracker, node_index));
        ref_ += "\"}";
        node.refJson = std::move(ref_);
    }
    return node.refJson;
}

// graphie repr() d'un flottant FINI, mémoïsée par motif de bits (cache
// direct 256 entrées, sous GIL) : les documents répètent massivement les
// mêmes valeurs — ~45 ns la composition Ryu, ~6 ns le hit
static inline const char*
sj_float_repr(double d, size_t* out_length)
{
    struct SjFloatRepr { uint64_t bits; uint8_t len; char text[24]; };
    static SjFloatRepr repr_cache[256];
    uint64_t bits;
    memcpy(&bits, &d, 8);
    SjFloatRepr& slot = repr_cache[(bits ^ (bits >> 17) ^ (bits >> 32)) & 255];
    if (slot.len != 0 && slot.bits == bits) {
        *out_length = slot.len;
        return slot.text;
    }
    static char repr_buf[40];
    size_t repr_len = (size_t) sjdtoa::ReprDouble(d, repr_buf);
    if (repr_len <= sizeof(slot.text)) {
        slot.bits = bits;
        slot.len = (uint8_t) repr_len;
        memcpy(slot.text, repr_buf, repr_len);
        *out_length = repr_len;
        return slot.text;
    }
    *out_length = repr_len;
    return repr_buf;
}


// écrit ICI les scalaires sûrs (None, bool, int64 exact, float fini exact —
// graphies identiques à leurs branches générales, quel que soit le mode
// nombre) sans garde de récursion ni dispatch ; faux = voie générale
// (int hors 64 bits, float non fini, tout le reste)
template<typename WriterT>
static inline bool
sj_write_scalar_inline(WriterT* writer, PyObject* item)
{
    if (item == Py_None) {
        writer->Null();
        return true;
    }
    if (item == Py_True || item == Py_False) {
        writer->Bool(item == Py_True);
        return true;
    }
    if (PyLong_CheckExact(item)) {
        int overflow;
        long long iv = PyLong_AsLongLongAndOverflow(item, &overflow);
        if (overflow == 0 && !(iv == -1 && PyErr_Occurred())) {
            writer->Int64(iv);
            return true;
        }
        PyErr_Clear();
        return false;
    }
    if (PyFloat_CheckExact(item)) {
        double dv = PyFloat_AS_DOUBLE(item);
        if (dv == dv && dv != (1.0 / 0.0) && dv != (-1.0 / 0.0)) {
            size_t repr_len;
            const char* repr_str = sj_float_repr(dv, &repr_len);
            writer->RawValue(repr_str, repr_len);
            return true;
        }
    }
    return false;
}


// PySet_Add dans dumped_classes, dédoublonné par POINTEUR via l'anneau du
// tracker : les documents homogènes ajoutent les mêmes noms à chaque objet
static inline void
sj_ajoute_classe_dumpee(PathTracker* pt, PyObject* nom)
{
    for (PyObject* deja : pt->classesAjoutees)
        if (deja == nom)
            return;
    if (PySet_Add(pt->dumpedClasses, nom) < 0) {
        PyErr_Clear();
        return;
    }
    pt->classesAjoutees[pt->classesAjouteesPos & 7] = nom;
    pt->classesAjouteesPos++;
}


// chaîne "root[0].attr['clef']" du noeud node_index (-1 = "root")
static std::string
path_tracker_string(PathTracker* tracker, long node_index)
{
    std::vector<int> chain;
    while (node_index != -1) {
        chain.push_back((int) node_index);
        node_index = tracker->nodes[(size_t) node_index].parent;
    }
    std::string out(tracker->racine.empty() ? "root" : tracker->racine);
    char index_buffer[32];
    for (size_t i = chain.size(); i-- > 0;) {
        const PathNode& node = tracker->nodes[(size_t) chain[i]];
        switch (node.kind) {
        case PathSegment::INDEX:
            snprintf(index_buffer, sizeof(index_buffer), "[%zd]",
                     (ssize_t) node.index);
            out += index_buffer;
            break;
        case PathSegment::KEY:
            out += "['";
            out += node.key;
            out += "']";
            break;
        case PathSegment::ATTR:
            out += '.';
            out += node.key;
            break;
        }
    }
    return out;
}

static PyObject* do_encode(PyObject* value, PyObject* defaultFn,
                           PyObject* defaultDictFn, PyObject* defaultListFn,
                           PathTracker* pathTracker,
                           bool ensureAscii,
                           unsigned writeMode, char indentChar, unsigned indentCount,
                           unsigned numberMode, unsigned datetimeMode,
                           unsigned uuidMode, unsigned bytesMode,
                           unsigned iterableMode, unsigned mappingMode, bool returnBytes,
                           size_t* outputHighWater);
static PyObject* do_stream_encode(PyObject* value, PyObject* stream, size_t chunkSize,
                                  PyObject* defaultFn,
                                  PyObject* defaultDictFn, PyObject* defaultListFn,
                                  PathTracker* pathTracker,
                                  bool ensureAscii,
                                  unsigned writeMode, char indentChar,
                                  unsigned indentCount, unsigned numberMode,
                                  unsigned datetimeMode, unsigned uuidMode,
                                  unsigned bytesMode, unsigned iterableMode,
                                  unsigned mappingMode);
static PyObject* encoder_call(PyObject* self, PyObject* args, PyObject* kwargs);
static PyObject* encoder_new(PyTypeObject* type, PyObject* args, PyObject* kwargs);


static PyObject* validator_call(PyObject* self, PyObject* args, PyObject* kwargs);
static void validator_dealloc(PyObject* self);
static PyObject* validator_new(PyTypeObject* type, PyObject* args, PyObject* kwargs);


///////////////////////////////////////////////////
// Stream wrapper around Python file-like object //
///////////////////////////////////////////////////


class PyReadStreamWrapper {
public:
    typedef char Ch;

    PyReadStreamWrapper(PyObject* stream, size_t size)
        : stream(stream) {
        Py_INCREF(stream);
        chunkSize = PyLong_FromUnsignedLong(size);
        buffer = nullptr;
        chunk = nullptr;
        chunkLen = 0;
        pos = 0;
        offset = 0;
        eof = false;
    }

    ~PyReadStreamWrapper() {
        Py_CLEAR(stream);
        Py_CLEAR(chunkSize);
        Py_CLEAR(chunk);
    }

    Ch Peek() {
        if (!eof && pos == chunkLen) {
            Read();
        }
        return eof ? '\0' : buffer[pos];
    }

    Ch Take() {
        if (!eof && pos == chunkLen) {
            Read();
        }
        return eof ? '\0' : buffer[pos++];
    }

    size_t Tell() const {
        return offset + pos;
    }

    void Flush() {
        assert(false);
    }

    void Put(Ch c) {
        assert(false);
    }

    Ch* PutBegin() {
        assert(false);
        return 0;
    }

    size_t PutEnd(Ch* begin) {
        assert(false);
        return 0;
    }

private:
    void Read() {
        Py_CLEAR(chunk);

        chunk = PyObject_CallMethodObjArgs(stream, read_name, chunkSize, nullptr);

        if (chunk == nullptr) {
            eof = true;
        } else {
            Py_ssize_t len;

            if (PyBytes_Check(chunk)) {
                len = PyBytes_GET_SIZE(chunk);
                buffer = PyBytes_AS_STRING(chunk);
            } else {
                buffer = PyUnicode_AsUTF8AndSize(chunk, &len);
                if (buffer == nullptr) {
                    len = 0;
                }
            }

            if (len == 0) {
                eof = true;
            } else {
                offset += chunkLen;
                chunkLen = len;
                pos = 0;
            }
        }
    }

    PyObject* stream;
    PyObject* chunkSize;
    PyObject* chunk;
    const Ch* buffer;
    size_t chunkLen;
    size_t pos;
    size_t offset;
    bool eof;
};





// ====================================================================



static bool
accept_indent_arg(PyObject* arg, unsigned &write_mode, unsigned &indent_count,
                   char &indent_char)
{
    if (arg != nullptr && arg != Py_None) {
        write_mode = WM_PRETTY;

        if (PyLong_Check(arg) && PyLong_AsLong(arg) >= 0) {
            indent_count = PyLong_AsUnsignedLong(arg);
        } else if (PyUnicode_Check(arg)) {
            Py_ssize_t len;
            const char* indentStr = PyUnicode_AsUTF8AndSize(arg, &len);

            indent_count = len;
            if (indent_count) {
                indent_char = '\0';
                while (len--) {
                    char ch = indentStr[len];

                    if (ch == '\n' || ch == ' ' || ch == '\t' || ch == '\r') {
                        if (indent_char == '\0') {
                            indent_char = ch;
                        } else if (indent_char != ch) {
                            PyErr_SetString(
                                PyExc_TypeError,
                                "indent string cannot contains different chars");
                            return false;
                        }
                    } else {
                        PyErr_SetString(PyExc_TypeError,
                                        "non-whitespace char in indent string");
                        return false;
                    }
                }
            }
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "indent must be a non-negative int or a string");
            return false;
        }
    }
    return true;
}

static bool
accept_write_mode_arg(PyObject* arg, unsigned &write_mode)
{
    if (arg != nullptr && arg != Py_None) {
        if (PyLong_Check(arg)) {
            long mode = PyLong_AsLong(arg);
            if (mode < 0 || mode >= WM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid write_mode");
                return false;
            }
            if (mode == WM_COMPACT) {
                write_mode = WM_COMPACT;
            } else if (mode & WM_SINGLE_LINE_ARRAY) {
                write_mode = (unsigned) (write_mode | WM_SINGLE_LINE_ARRAY);
            }
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "write_mode must be a non-negative int");
            return false;
        }
    }
    return true;
}

static bool
accept_number_mode_arg(PyObject* arg, int allow_nan, unsigned &number_mode)
{
    if (arg != nullptr) {
        if (arg == Py_None)
            number_mode = NM_NONE;
        else if (PyLong_Check(arg)) {
            long mode = PyLong_AsLong(arg);
            if (mode < 0 || mode >= NM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid number_mode, out of range");
                return false;
            }
            number_mode = (unsigned) mode;
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "number_mode must be a non-negative int");
            return false;
        }
    }
    if (allow_nan != -1) {
        if (allow_nan)
            number_mode |= NM_NAN;
        else
            number_mode &= ~NM_NAN;
    }
    return true;
}

static bool
accept_datetime_mode_arg(PyObject* arg, unsigned &datetime_mode)
{
    if (arg != nullptr && arg != Py_None) {
        if (PyLong_Check(arg)) {
            long mode = PyLong_AsLong(arg);
            if (!valid_datetime_mode(mode)) {
                PyErr_SetString(PyExc_ValueError, "Invalid datetime_mode, out of range");
                return false;
            }
            datetime_mode = (unsigned) mode;
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "datetime_mode must be a non-negative int");
            return false;
        }
    }
    return true;
}

static bool
accept_uuid_mode_arg(PyObject* arg, unsigned &uuid_mode)
{
    if (arg != nullptr && arg != Py_None) {
        if (PyLong_Check(arg)) {
            long mode = PyLong_AsLong(arg);
            if (mode < 0 || mode >= UM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid uuid_mode, out of range");
                return false;
            }
            uuid_mode = (unsigned) mode;
        } else {
            PyErr_SetString(PyExc_TypeError, "uuid_mode must be a non-negative int");
            return false;
        }
    }
    return true;
}

static bool
accept_bytes_mode_arg(PyObject* arg, unsigned &bytes_mode)
{
    if (arg != nullptr && arg != Py_None) {
        if (PyLong_Check(arg)) {
            long mode = PyLong_AsLong(arg);
            if (mode < 0 || mode >= BM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid bytes_mode, out of range");
                return false;
            }
            bytes_mode = (unsigned) mode;
        } else {
            PyErr_SetString(PyExc_TypeError, "bytes_mode must be a non-negative int");
            return false;
        }
    }
    return true;
}

static bool
accept_iterable_mode_arg(PyObject* arg, unsigned &iterable_mode)
{
    if (arg != nullptr && arg != Py_None) {
        if (PyLong_Check(arg)) {
            long mode = PyLong_AsLong(arg);
            if (mode < 0 || mode >= IM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid iterable_mode, out of range");
                return false;
            }
            iterable_mode = (unsigned) mode;
        } else {
            PyErr_SetString(PyExc_TypeError, "iterable_mode must be a non-negative int");
            return false;
        }
    }
    return true;
}

static bool
accept_mapping_mode_arg(PyObject* arg, unsigned &mapping_mode)
{
    if (arg != nullptr && arg != Py_None) {
        if (PyLong_Check(arg)) {
            long mode = PyLong_AsLong(arg);
            if (mode < 0 || mode >= MM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid mapping_mode, out of range");
                return false;
            }
            mapping_mode = (unsigned) mode;
        } else {
            PyErr_SetString(PyExc_TypeError, "mapping_mode must be a non-negative int");
            return false;
        }
    }
    return true;
}

static bool
accept_chunk_size_arg(PyObject* arg, size_t &chunk_size)
{
    if (arg != nullptr && arg != Py_None) {
        if (PyLong_Check(arg)) {
            Py_ssize_t size = PyNumber_AsSsize_t(arg, PyExc_ValueError);
            if (PyErr_Occurred() || size < 4 || size > UINT_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid chunk_size, out of range");
                return false;
            }
            chunk_size = (size_t) size;
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "chunk_size must be a non-negative int");
            return false;
        }
    }
    return true;
}

static bool
accept_parse_mode_arg(PyObject* arg, unsigned &parse_mode)
{
    if (arg != nullptr && arg != Py_None) {
        if (PyLong_Check(arg)) {
            long mode = PyLong_AsLong(arg);
            if (mode < 0 || mode >= PM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid parse_mode, out of range");
                return false;
            }
            parse_mode = (unsigned) mode;
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "parse_mode must be a non-negative int");
            return false;
        }
    }
    return true;
}


/////////////
// Decoder //
/////////////


/* Adapted from CPython's Objects/floatobject.c::float_from_string_inner() */

static PyObject*
float_from_string(const char* s, Py_ssize_t len)
{
    double x;
    const char* end;

    /* We don't care about overflow or underflow.  If the platform
     * supports them, infinities and signed zeroes (on underflow) are
     * fine. */
    x = PyOS_string_to_double(s, (char **) &end, nullptr);
    if (end != s + len) {
        return nullptr;
    } else if (x == -1.0 && PyErr_Occurred()) {
        return nullptr;
    } else {
        return PyFloat_FromDouble(x);
    }
}


typedef struct {
    PyObject_HEAD
    unsigned datetimeMode;
    unsigned uuidMode;
    unsigned numberMode;
    unsigned parseMode;
    // cache PERSISTANT des valeurs chaînes courtes (alloué au premier
    // besoin, libéré au dealloc) : les mêmes documents relus par le même
    // Decoder partagent leurs objets str d'un appel à l'autre
    void* sjValCache;          // KeyCacheSlot[kValCacheSize]
    unsigned sjValCacheCount;
    int sjValCacheBudget;      // crédit adaptatif, persistant lui aussi
} DecoderObject;


// décode une clé d'ENVELOPPE de dict à clés non-str rencontrée dans un
// chemin $ref, formes SIMPLES seulement ('quotée' -> str, b'...' -> bytes,
// b64'...' -> bytes, true/false/null, entier, flottant) : le chemin porte le
// texte encodé de la clé, le dict reconstruit porte la clé décodée. Rend une
// NOUVELLE référence, ou nullptr SANS erreur si la forme n'est pas simple
// (clé ordinaire, tuple « [...] », enveloppe « {...} » : repli appelant)
static PyObject*
sj_decode_cle_ref(const char* u8, Py_ssize_t lg)
{
    if (lg <= 0)
        return nullptr;
    char premier = u8[0];
    if (premier == '\'') {
        if (lg >= 2 && u8[lg - 1] == '\'')
            return PyUnicode_FromStringAndSize(u8 + 1, lg - 2);
    } else if (premier == 'b') {
        if (lg >= 3 && u8[lg - 1] == '\'' && u8[1] == '\'') {
            return PyBytes_FromStringAndSize(u8 + 2, lg - 3);
        } else if (lg >= 5 && u8[lg - 1] == '\''
                   && memcmp(u8, "b64'", 4) == 0) {
            size_t groups, pad, out_length;
            if (sj_b64_layout(u8 + 4, (size_t) (lg - 5), &groups, &pad,
                              &out_length, serializejson_b64_decode_table())) {
                PyObject* octets = PyBytes_FromStringAndSize(
                    nullptr, (Py_ssize_t) out_length);
                if (octets == nullptr) {
                    PyErr_Clear();
                    return nullptr;
                }
                if (sj_b64_decode_into(
                        u8 + 4, (size_t) (lg - 5),
                        (unsigned char*) PyBytes_AS_STRING(octets),
                        serializejson_b64_decode_table()))
                    return octets;
                Py_DECREF(octets);
            }
        }
    } else if (lg == 4 && memcmp(u8, "true", 4) == 0) {
        Py_RETURN_TRUE;
    } else if (lg == 5 && memcmp(u8, "false", 5) == 0) {
        Py_RETURN_FALSE;
    } else if (lg == 4 && memcmp(u8, "null", 4) == 0) {
        Py_RETURN_NONE;
    } else if ((premier >= '0' && premier <= '9') || premier == '-'
               || premier == 'N' || premier == 'I') {
        char* fin = nullptr;
        PyObject* entier = PyLong_FromString(u8, &fin, 10);
        if (entier != nullptr && fin == u8 + lg)
            return entier;
        Py_XDECREF(entier);
        PyErr_Clear();
        PyObject* texte = PyUnicode_FromStringAndSize(u8, lg);
        if (texte == nullptr) {
            PyErr_Clear();
            return nullptr;
        }
        PyObject* flottant = PyFloat_FromString(texte);
        Py_DECREF(texte);
        if (flottant != nullptr)
            return flottant;
        PyErr_Clear();
    }
    return nullptr;
}


// résolution C des chemins $ref ÉMIS PAR L'ENCODEUR : root, .attr, [int],
// ['clé'] — même sémantique que from_name(accept_dict_as_object=True).
// Rend une référence FORTE, ou nullptr SANS erreur posée (chemin hors
// grammaire, navigation en échec) : l'appelant retombe sur la voie python,
// qui porte les messages d'erreur et les cas exotiques
static PyObject*
sj_resolve_ref_path(const char* path, Py_ssize_t length, PyObject* root)
{
    const char* p = path;
    const char* end = path + length;
    if (length < 4 || memcmp(p, "root", 4) != 0)
        return nullptr;
    p += 4;
    PyObject* current = root;
    Py_INCREF(current);
    while (p < end) {
        PyObject* next = nullptr;
        if (*p == '.') {
            const char* start = ++p;
            while (p < end && *p != '.' && *p != '[')
                p++;
            if (p == start)
                break;
            // charge d'une ENVELOPPE d'objet : sur l'objet reconstruit, les
            // arguments de __new__ SONT l'objet (tuple), le niveau est donc
            // transparent — avant getattr, qui rendrait la MÉTHODE __new__
            if (p - start == 7 && memcmp(start, "__new__", 7) == 0)
                continue;
            PyObject* key = PyUnicode_FromStringAndSize(start, p - start);
            if (key == nullptr)
                break;
            // chemin vers l'intérieur d'une ENVELOPPE de collection : sur
            // l'objet reconstruit, __init__ est la fabrique d'un defaultdict
            // sinon l'objet lui-même (Counter) — intercepté AVANT getattr,
            // qui résoudrait la MÉTHODE __init__ (même règle que _getattr)
            if (p - start == 8 && memcmp(start, "__init__", 8) == 0) {
                next = PyObject_GetAttrString(current, "default_factory");
                if (next == nullptr) {
                    PyErr_Clear();
                    next = current;
                    Py_INCREF(next);
                }
                Py_DECREF(key);
                Py_DECREF(current);
                current = next;
                continue;
            }
            if (PyDict_Check(current)) {
                next = PyDict_GetItem(current, key);   // empruntée
                Py_XINCREF(next);
                if (next == nullptr) {
                    // chemins « .2 » historiques sur une enveloppe de dict
                    // à clés non-str : même décodage que la forme ['clé']
                    PyObject* decodee = sj_decode_cle_ref(start, p - start);
                    if (decodee != nullptr) {
                        next = PyDict_GetItem(current, decodee);  // empruntée
                        Py_XINCREF(next);
                        Py_DECREF(decodee);
                        if (PyErr_Occurred())
                            PyErr_Clear();
                    }
                }
            }
            if (next == nullptr) {
                next = PyObject_GetAttr(current, key); // forte
                if (next == nullptr)
                    PyErr_Clear();
            }
            if (next == nullptr && p - start == 9
                && memcmp(start, "__items__", 9) == 0) {
                // les éléments d'une collection reconstruite sont l'objet
                // lui-même (deque, OrderedDict, defaultdict)
                next = current;
                Py_INCREF(next);
            }
            Py_DECREF(key);
        } else if (*p == '[' && p + 1 < end && p[1] == '\'') {
            const char* start = p + 2;
            // la clé peut contenir des apostrophes (b'k', 'true'...) : le
            // segment ne se ferme que sur la séquence « '] » — même règle
            // que from_name
            const char* q = start;
            while (q < end
                   && !(*q == '\'' && q + 1 < end && q[1] == ']'))
                q++;
            if (q + 1 >= end || q[1] != ']')
                break;
            // dict : la clé du chemin peut être le texte ENCODÉ d'une clé
            // non-str ('2' pour la clé int 2, b'k'...) — décodage d'abord
            // (une clé int 2 et une clé str '2' coexistantes s'écrivent
            // '2' et "'2'" : sans cette priorité, ['2'] tomberait sur la
            // mauvaise), texte brut ensuite
            if (PyDict_Check(current)) {
                PyObject* decodee = sj_decode_cle_ref(start, q - start);
                if (decodee != nullptr) {
                    next = PyDict_GetItem(current, decodee);  // empruntée
                    Py_XINCREF(next);
                    Py_DECREF(decodee);
                    if (PyErr_Occurred())
                        PyErr_Clear();
                }
            }
            if (next == nullptr) {
                PyObject* key = PyUnicode_FromStringAndSize(start, q - start);
                if (key == nullptr)
                    break;
                next = PyObject_GetItem(current, key);     // forte
                if (next == nullptr)
                    PyErr_Clear();
                Py_DECREF(key);
            }
            p = q + 2;
        } else if (*p == '[') {
            const char* start = ++p;
            Py_ssize_t index = 0;
            while (p < end && *p >= '0' && *p <= '9')
                index = index * 10 + (*p++ - '0');
            if (p == start || p >= end || *p != ']')
                break;
            p++;
            next = PySequence_GetItem(current, index); // forte
            if (next == nullptr)
                PyErr_Clear();
        } else
            break;
        Py_DECREF(current);
        if (next == nullptr)
            return nullptr;
        current = next;
    }
    if (p < end) {   // grammaire non épuisée : repli python
        Py_DECREF(current);
        return nullptr;
    }
    return current;
}


// exposition python du résolveur (post-passe _resolve_duplicates des
// documents à racine liste) : None = repli from_name — une cible de
// référence ne peut pas être le scalaire None, l'ambiguïté est sans objet
static PyObject*
resolve_ref_path_fn(PyObject* Py_UNUSED(self), PyObject* args)
{
    PyObject* path_obj;
    PyObject* root;
    if (!PyArg_ParseTuple(args, "UO", &path_obj, &root))
        return nullptr;
    Py_ssize_t path_length;
    const char* path = PyUnicode_AsUTF8AndSize(path_obj, &path_length);
    if (path == nullptr)
        return nullptr;
    PyObject* resolved = sj_resolve_ref_path(path, path_length, root);
    if (resolved == nullptr)
        Py_RETURN_NONE;
    return resolved;
}


struct PyHandler {
    PyObject* decoderStartObject;
    PyObject* decoderEndObject;
    PyObject* decoderEndArray;
    PyObject* decoderString;
    PyObject* sharedKeys;
    // cache clé -> str par OCTETS BRUTS (sondage linéaire) : la création
    // du str et le passage par sharedKeys sont évités dès la deuxième
    // occurrence d'une clé. Capacité figée : au-delà, les clés inédites
    // repassent par la voie normale (aucun effet sémantique)
    static const unsigned kKeyCacheSize = 1024;   // puissance de deux
    struct KeyCacheSlot {
        uint64_t hash;
        PyObject* str;          // référence possédée, utf-8 accessible
    };
    KeyCacheSlot keyCache[kKeyCacheSize];
    unsigned keyCacheCount;

    static uint64_t KeyHash(const char* s, size_t n) {
        uint64_t h = UINT64_C(0xcbf29ce484222325);   // FNV-1a
        for (size_t i = 0; i < n; i++)
            h = (h ^ (unsigned char) s[i]) * UINT64_C(0x100000001b3);
        return h | 1;           // 0 = case vide
    }

    // rend une référence FORTE sur le str de la clé, en le fabriquant au
    // plus une fois par contenu ; nullptr = erreur Python levée
    PyObject* KeyString(const char* s, size_t n) {
        uint64_t h = KeyHash(s, n);
        unsigned i = (unsigned) h & (kKeyCacheSize - 1);
        for (;;) {
            KeyCacheSlot& slot = keyCache[i];
            if (slot.hash == 0)
                break;
            if (slot.hash == h) {
                Py_ssize_t sl;
                const char* ss = PyUnicode_AsUTF8AndSize(slot.str, &sl);
                if (ss != nullptr && (size_t) sl == n
                    && memcmp(ss, s, n) == 0) {
                    Py_INCREF(slot.str);
                    return slot.str;
                }
                PyErr_Clear();
            }
            i = (i + 1) & (kKeyCacheSize - 1);
        }
        PyObject* key = sj_unicode_from_utf8(s, n);
        if (key == nullptr)
            return nullptr;
        // 3/4 de remplissage au plus : le sondage reste court
        if (keyCacheCount < kKeyCacheSize - (kKeyCacheSize / 4)) {
            KeyCacheSlot& slot = keyCache[i];
            slot.hash = h;
            slot.str = key;
            Py_INCREF(key);
            keyCacheCount++;
        }
        return key;
    }

    // cache ADAPTATIF des VALEURS chaînes courtes, PERSISTANT sur le
    // Decoder (les mêmes documents relus partagent leurs str d'un appel à
    // l'autre — le partage que pickle obtient par son memo) ; interrupteur
    // par parse : si les données ne se répètent pas (échecs dominants), il
    // se coupe pour le reste du parse
    static const unsigned kValCacheSize = 2048;   // puissance de deux
    KeyCacheSlot* valCache;  // table du DecoderObject, nullptr sinon
    unsigned* valCacheCount;
    int* valCacheBudget;     // crédit PERSISTANT du DecoderObject : les
                             // données prouvées distinctes ne repaient que
                             // le plancher de 64 essais par parse
    bool valCacheEnabled;
    // indice posé par le scan SSE du reader (via sjHintOut du flux borné) :
    // 1 = la chaîne en cours est pure ascii sans échappement ; consommé
    // (remis à 0) à chaque String()
    int stringAsciiHint;

    PyObject* ValueString(const char* s, size_t n, int asciiHint) {
        if (!valCacheEnabled || valCache == nullptr || n > 48)
            return sj_unicode_from_utf8_hint(s, n, asciiHint);
        uint64_t h = KeyHash(s, n);
        unsigned i = (unsigned) h & (kValCacheSize - 1);
        for (;;) {
            KeyCacheSlot& slot = valCache[i];
            if (slot.hash == 0)
                break;
            if (slot.hash == h) {
                Py_ssize_t sl;
                const char* ss = PyUnicode_AsUTF8AndSize(slot.str, &sl);
                if (ss != nullptr && (size_t) sl == n
                    && memcmp(ss, s, n) == 0) {
                    *valCacheBudget += 2;
                    if (*valCacheBudget > 4096)
                        *valCacheBudget = 4096;
                    Py_INCREF(slot.str);
                    return slot.str;
                }
                PyErr_Clear();
            }
            i = (i + 1) & (kValCacheSize - 1);
        }
        // échec : l'interrupteur se ferme si le crédit est épuisé, et la
        // table (manifestement du bruit) est rendue — les insertions
        // fraîches repartiront de zéro si les données changent de régime
        if (--(*valCacheBudget) < 0) {
            valCacheEnabled = false;
            for (unsigned k = 0; k < kValCacheSize; k++)
                if (valCache[k].hash != 0) {
                    Py_DECREF(valCache[k].str);
                    valCache[k].hash = 0;
                    valCache[k].str = nullptr;
                }
            *valCacheCount = 0;
        }
        PyObject* value = sj_unicode_from_utf8_hint(s, n, asciiHint);
        if (value == nullptr)
            return nullptr;
        if (*valCacheCount < kValCacheSize - (kValCacheSize / 4)) {
            KeyCacheSlot& slot = valCache[i];
            slot.hash = h;
            slot.str = value;
            Py_INCREF(value);
            (*valCacheCount)++;
        }
        return value;
    }

    void ReleaseKeyCache() {
        for (unsigned i = 0; i < kKeyCacheSize; i++)
            if (keyCache[i].hash != 0) {
                Py_DECREF(keyCache[i].str);
                keyCache[i].hash = 0;
                keyCache[i].str = nullptr;
            }
        keyCacheCount = 0;
    }
    PyObject* root;
    PyObject* objectHook;
    unsigned datetimeMode;
    unsigned uuidMode;
    unsigned numberMode;
    std::vector<HandlerContext> stack;
    // éléments des listes encore ouvertes, dans l'ordre où ils arrivent :
    // chaque niveau y possède une tranche qui commence à son attenteBase, et
    // les tranches s'empilent comme les niveaux. Références POSSÉDÉES jusqu'à
    // leur versement dans la liste (VerseAttente) ou au destructeur.
    std::vector<PyObject*> attente;
    // chemin rapide de décodage : decode_class_plan(nom_de_classe), appelé
    // UNE fois par classe et par chargement, retourne None (end_object
    // Python) ou la CLASSE — l'objet est alors instancié en C++ (tp_new puis
    // assignation du dict d'attributs), sans aucun appel Python par objet
    PyObject* decoderObject;        // le Decoder lui-même (pour poser .root)
    PyObject* decodeClassPlanFn;
    bool fastStartObject;           // start_object Python court-circuité
    bool fastPlainEndObject;        // end_object sauté pour les dicts ordinaires
    // décodage base64 DIFFÉRÉ des charges binaires : validées et mises en
    // file pendant le parse (l'objet destination, créé tout de suite, entre
    // dans l'arbre), remplies en parallèle au premier rappel Python ou en
    // fin de parse. Actif seulement en insitu (deferB64) : les pointeurs
    // source restent valides jusqu'à la fin du parse.
    struct PendingB64 {
        const char* src;
        size_t length;
        size_t decoded_length;      // taille après décodage base64
        unsigned char* dst;
        PyObject* obj;              // référence forte le temps du différé
        // étage optionnel : la charge décodée est une trame blosc2 UNIQUE à
        // décompresser vers dest (objet destination déjà dans l'arbre)
        unsigned char* dest;
        size_t destsize;
        PyObject* destobj;          // référence forte, ou nullptr
        // étage optionnel : défaire la dérivée _diff/_diffb pendant la
        // décompression (postfiltre par bloc si les blocs sont calés, sinon
        // post-passe par blocs) — b64, zstd et cumsum en UNE traversée
        Py_ssize_t cs_itemsize;     // 0 : pas de dérivée
        Py_ssize_t cs_cols;
        Py_ssize_t cs_block_rows;   // 0 : dérivée globale (_diff historique)
        bool cs_fused;              // blocs de trame == blocs de dérivée
    };
    std::vector<PendingB64> pendingB64;
    bool deferB64;
    PyObject* typeValuesCache = nullptr;   // réf forte, dict partagé ou nullptr
    PyObject* rootObject = nullptr;        // réf forte, racine (résolution $ref)
    bool rootAttrSet;
    std::unordered_map<std::string, PyObject*> decodePlans;  // réfs possédées
    // classes dont la charge __init__/__new__[0] est du base64 à décoder
    // directement depuis le tampon de parse (0 -> bytes, 1 -> bytearray)
    std::unordered_map<std::string, int> b64PayloadClasses;
    // repli PAR CLÉ du décodage C des dicts à clés non-str (attribut
    // _decode_cle_exotique du décodeur, résolu une fois par chargement)
    PyObject* decodeCleFn = nullptr;
    // ----- réhydratation AU FIL DU PARSE (Decoder(rehydrate=True)) : l'objet
    // d'une enveloppe est construit — ou son homologue VIVANT adopté — dès
    // que sa première clé d'état arrive (ou qu'il se ferme sans état), donc
    // AVANT ses attributs et ses enfants ; l'instance prend la place du nom
    // dans "__class__", les $ref des enfants la trouvent, la fermeture lui
    // applique l'état sans rejouer __init__. Hors du mode : un test par clé
    bool rehydrateOn = false;
    PyObject* decoderConstruct = nullptr;   // repli python Decoder._construct
    PyObject* liveRoot = nullptr;           // obj= : homologue vivant de la racine
    // Decoder._reconcile : l'homologue vivant trouvé en C, avec arguments,
    // n'est adopté que si ses arguments se réconcilient avec ceux du json
    PyObject* decoderReconcile = nullptr;
    bool rehydrateEnC = true;               // faux si updatables_classes restreint l'adoption
    // plans de classe par TYPE construit (empruntés à decodePlans) : l'état
    // d'une instance déjà rangée dans __class__ s'applique en C
    std::unordered_map<PyTypeObject*, PyObject*> plansParType;
    // cache des chemins $ref RÉSOLUS le temps d'un parse (résolutions
    // acceptées seulement — jamais une cible encore à l'état d'enveloppe)
    PyObject* refPathCache = nullptr;
    // même cache, clé par OCTETS du chemin, pour le raccourci SAX qui résout
    // le $ref à l'événement String sans jamais matérialiser ni la chaîne
    // python du chemin ni le dict {"$ref": ...} (valeurs : réfs possédées)
    std::unordered_map<std::string, PyObject*> refOctetsCache;
    // dicts d'enveloppe RECYCLÉS : une enveloppe reconnue laisse son dict
    // vide — plutôt que le détruire puis en réallouer un au prochain
    // StartObject, les derniers sont gardés ici (réfs possédées ; 3 : la
    // profondeur des enveloppes imbriquées courantes, defaultdict et array)
    PyObject* dictsLibres[3] = {};
    int nDictsLibres = 0;
    // cache des clés EXOTIQUES décodées ('[5,6]' -> (5,6)...), le temps d'un
    // parse : les répliques d'un document répètent leurs clés, et chaque
    // décodage python coûte ~4 µs (résultats immuables : tuple, frozenset,
    // bytes... — le partage entre occurrences est sans effet observable)
    PyObject* cleExotiqueCache = nullptr;

    PyHandler(PyObject* decoder,
              PyObject* hook,
              unsigned dm,
              unsigned um,
              unsigned nm)
        : decoderStartObject(nullptr),
          decoderEndObject(nullptr),
          decoderEndArray(nullptr),
          decoderString(nullptr),
          root(nullptr),
          objectHook(hook),
          datetimeMode(dm),
          uuidMode(um),
          numberMode(nm),
          decoderObject(nullptr),
          decodeClassPlanFn(nullptr),
          valCache(nullptr),
          valCacheCount(nullptr),
          valCacheBudget(nullptr),
          valCacheEnabled(false),
          stringAsciiHint(0),
          fastStartObject(false),
          fastPlainEndObject(false),
          deferB64(false),
          rootAttrSet(false)
        {
            stack.reserve(128);
            if (decoder != nullptr) {
                assert(!objectHook);
                if (PyObject_HasAttr(decoder, start_object_name)) {
                    decoderStartObject = PyObject_GetAttr(decoder, start_object_name);
                }
                if (PyObject_HasAttr(decoder, end_object_name)) {
                    decoderEndObject = PyObject_GetAttr(decoder, end_object_name);
                }
                if (PyObject_HasAttr(decoder, end_array_name)) {
                    decoderEndArray = PyObject_GetAttr(decoder, end_array_name);
                }
                if (PyObject_HasAttr(decoder, string_name)) {
                    decoderString = PyObject_GetAttr(decoder, string_name);
                }
                if (PyObject_HasAttr(decoder, decode_class_plan_name)) {
                    decodeClassPlanFn = PyObject_GetAttr(decoder, decode_class_plan_name);
                }
                if (decoderStartObject != nullptr) {
                    PyObject* fast = PyObject_GetAttr(decoder, fast_start_object_name);
                    if (fast == nullptr)
                        PyErr_Clear();
                    else {
                        fastStartObject = PyObject_IsTrue(fast) == 1;
                        Py_DECREF(fast);
                    }
                }
                if (decoderEndObject != nullptr) {
                    PyObject* fast = PyObject_GetAttr(decoder, fast_plain_end_object_name);
                    if (fast == nullptr)
                        PyErr_Clear();
                    else {
                        fastPlainEndObject = PyObject_IsTrue(fast) == 1;
                        Py_DECREF(fast);
                    }
                }
                decodeCleFn =
                    PyObject_GetAttr(decoder, decode_cle_name);
                if (decodeCleFn == nullptr)
                    PyErr_Clear();
                else if (decodeCleFn == Py_None)
                    Py_CLEAR(decodeCleFn);
                decoderConstruct = PyObject_GetAttr(decoder, construct_name);
                if (decoderConstruct == nullptr)
                    PyErr_Clear();
                else if (decoderConstruct == Py_None)
                    Py_CLEAR(decoderConstruct);
                if (decoderConstruct != nullptr && decodeClassPlanFn != nullptr) {
                    rehydrateOn = true;
                    liveRoot = PyObject_GetAttr(decoder, live_root_name);
                    if (liveRoot == nullptr)
                        PyErr_Clear();
                    else if (liveRoot == Py_None)
                        Py_CLEAR(liveRoot);
                    decoderReconcile = PyObject_GetAttr(decoder, reconcile_name);
                    if (decoderReconcile == nullptr)
                        PyErr_Clear();
                    PyObject* updatables =
                        PyObject_GetAttr(decoder, updatables_name);
                    if (updatables == nullptr)
                        PyErr_Clear();
                    else {
                        rehydrateEnC = PyObject_IsTrue(updatables) <= 0;
                        PyErr_Clear();
                        Py_DECREF(updatables);
                    }
                }
                PyObject* payload_classes =
                    PyObject_GetAttr(decoder, b64_payload_classes_name);
                if (payload_classes == nullptr)
                    PyErr_Clear();
                else {
                    if (PyDict_CheckExact(payload_classes)) {
                        Py_ssize_t pos = 0;
                        PyObject* key;
                        PyObject* value;
                        while (PyDict_Next(payload_classes, &pos, &key, &value)) {
                            Py_ssize_t kl;
                            const char* ks = PyUnicode_AsUTF8AndSize(key, &kl);
                            if (ks != nullptr)
                                b64PayloadClasses.emplace(
                                    std::string(ks, (size_t) kl),
                                    (int) PyLong_AsLong(value));
                        }
                    }
                    Py_DECREF(payload_classes);
                }
                // cache partagé des valeurs de type : le C ne sert que les
                // HITS de ce dict (rempli par instance() côté python, qui
                // garde la machinerie d'import et ses règles)
                typeValuesCache =
                    PyObject_GetAttr(decoder, type_values_cache_name);
                if (typeValuesCache == nullptr)
                    PyErr_Clear();
                else if (!PyDict_CheckExact(typeValuesCache)) {
                    Py_DECREF(typeValuesCache);
                    typeValuesCache = nullptr;
                }
                decoderObject = decoder;
                Py_INCREF(decoder);
                if (PyObject_TypeCheck(decoder, &Decoder_Type)) {
                    DecoderObject* dobj = (DecoderObject*) decoder;
                    if (dobj->sjValCache == nullptr) {
                        dobj->sjValCache = PyMem_Calloc(
                            kValCacheSize, sizeof(KeyCacheSlot));
                        dobj->sjValCacheCount = 0;
                        dobj->sjValCacheBudget = 512;
                    }
                    if (dobj->sjValCache != nullptr) {
                        valCache = (KeyCacheSlot*) dobj->sjValCache;
                        valCacheCount = &dobj->sjValCacheCount;
                        // plancher par parse : un régime distinct installé
                        // ne coûte plus que ~64 essais, un régime répétitif
                        // peut toujours regagner son crédit
                        if (dobj->sjValCacheBudget < 64)
                            dobj->sjValCacheBudget = 64;
                        valCacheBudget = &dobj->sjValCacheBudget;
                        valCacheEnabled = true;
                    }
                }
            }
            sharedKeys = PyDict_New();
            memset(keyCache, 0, sizeof(keyCache));
            keyCacheCount = 0;
        }

    ~PyHandler() {
        // parse interrompu : les éléments jamais versés sont encore à nous
        for (PyObject* v : attente)
            Py_DECREF(v);
        while (!stack.empty()) {
            HandlerContext& ctx = stack.back();
            if (ctx.copiedKey)
                PyMem_Free((void*) ctx.key);
            if (ctx.object != nullptr)
                Py_DECREF(ctx.object);
            Py_CLEAR(ctx.envClass);
            Py_CLEAR(ctx.envArgs);
            Py_CLEAR(ctx.envItems);
            Py_CLEAR(ctx.envDictKey);
            Py_CLEAR(ctx.refResolu);
            stack.pop_back();
        }
        for (auto& entry : refOctetsCache)
            Py_DECREF(entry.second);
        Py_CLEAR(decoderStartObject);
        Py_CLEAR(decoderEndObject);
        Py_CLEAR(decoderEndArray);
        Py_CLEAR(decoderString);
        Py_CLEAR(decodeCleFn);
        Py_CLEAR(decoderConstruct);
        Py_CLEAR(liveRoot);
        Py_CLEAR(decoderReconcile);
        Py_CLEAR(refPathCache);
        Py_CLEAR(cleExotiqueCache);
        Py_CLEAR(sharedKeys);
        ReleaseKeyCache();
        Py_CLEAR(decoderObject);
        Py_CLEAR(decodeClassPlanFn);
        for (auto& entry : decodePlans)
            Py_DECREF(entry.second);
        Py_XDECREF(typeValuesCache);
        Py_XDECREF(rootObject);
        while (nDictsLibres > 0)
            Py_DECREF(dictsLibres[--nDictsLibres]);
        ReleasePendingB64();
    }

    // abandon des différés (chemins d'erreur : l'arbre est jeté avec eux)
    void ReleasePendingB64() {
        for (PendingB64& job : pendingB64) {
            Py_DECREF(job.obj);
            Py_XDECREF(job.destobj);
        }
        pendingB64.clear();
    }

    // vrai si mapping est un dict {"__class__": "numpyB64", ...} dont
    // l'instanciation ne LIRA pas la charge : frombuffer/ndarray ne font
    // qu'envelopper le tampon. Exclusions : une compression (chaîne au-delà
    // de l'index 1 des arguments : blosc_decompress lirait), dtype "bool"
    // (unpackbits lit) — le vidage des différés peut alors être sauté.
    bool NumpyNoReadDict(PyObject* mapping) {
        if (!PyDict_CheckExact(mapping))
            return false;
        PyObject* cls_value = PyDict_GetItem(mapping, class_key_name);
        if (cls_value == nullptr || !PyUnicode_CheckExact(cls_value)
            || PyUnicode_CompareWithASCIIString(cls_value, "numpyB64") != 0)
            return false;
        PyObject* ctor_args = PyDict_GetItem(mapping, new_key_name);
        if (ctor_args == nullptr)
            ctor_args = PyDict_GetItem(mapping, init_key_name);
        if (ctor_args == nullptr || !PyList_CheckExact(ctor_args))
            return false;
        Py_ssize_t nargs = PyList_GET_SIZE(ctor_args);
        if (nargs < 2)
            return false;
        PyObject* dtype_arg = PyList_GET_ITEM(ctor_args, 1);
        if (PyUnicode_CheckExact(dtype_arg)
            && PyUnicode_CompareWithASCIIString(dtype_arg, "bool") == 0)
            return false;
        for (Py_ssize_t i = 2; i < nargs; i++) {
            PyObject* item = PyList_GET_ITEM(ctor_args, i);
            if (PyUnicode_CheckExact(item)
                && PyUnicode_CompareWithASCIIString(item, "b64") != 0)
                return false;   // étiquette de compression : lecture
            // « b64 » (repli non-compressé de l'écriture différée) : la
            // charge est déjà les octets bruts, frombuffer n'y lira rien
        }
        return true;
    }

    // tente de convertir le job base64 de la charge de mapping en job
    // « base64 puis décompression » quand la charge est une trame blosc2
    // UNIQUE : l'objet destination (décompressé, non rempli) remplace la
    // charge dans les arguments et l'étiquette est neutralisée — pour
    // bytes/bytearray elle redevient « b64 », ce qui fait retomber le dict
    // dans le chemin C++ (aucun Python) ; pour numpyB64 elle devient None
    // (frombuffer n'y lira rien). Trames multiples, blosc v1, _diff, bool :
    // voie normale (vidage puis Python).
    void TryDeferDecompress(PyObject* mapping) {
        if (!serializejson_blosc2_ctx_ok || !PyDict_CheckExact(mapping)
            || PyDict_GET_SIZE(mapping) != 2)
            return;
        PyObject* cls_value = PyDict_GetItem(mapping, class_key_name);
        if (cls_value == nullptr || !PyUnicode_CheckExact(cls_value))
            return;
        int kind;
        if (PyUnicode_CompareWithASCIIString(cls_value, "bytes") == 0)
            kind = 0;
        else if (PyUnicode_CompareWithASCIIString(cls_value, "bytearray") == 0)
            kind = 1;
        else if (PyUnicode_CompareWithASCIIString(cls_value, "numpyB64") == 0)
            kind = 2;
        else
            return;
        PyObject* ctor_args = PyDict_GetItem(mapping, new_key_name);
        if (ctor_args == nullptr)
            ctor_args = PyDict_GetItem(mapping, init_key_name);
        if (ctor_args == nullptr || !PyList_CheckExact(ctor_args))
            return;
        Py_ssize_t nargs = PyList_GET_SIZE(ctor_args);
        if (nargs < 2)
            return;
        PyObject* payload = PyList_GET_ITEM(ctor_args, 0);
        size_t job_index = pendingB64.size();
        for (size_t i = 0; i < pendingB64.size(); i++)
            if (pendingB64[i].obj == payload) {
                job_index = i;
                break;
            }
        if (job_index == pendingB64.size())
            return;
        PendingB64& job = pendingB64[job_index];
        if (job.destobj != nullptr)
            return;
        Py_ssize_t label_index;
        Py_ssize_t cs_itemsize = 0;
        Py_ssize_t cs_cols = 1;
        Py_ssize_t cs_block_rows = 0;
        if (kind == 2) {
            if (nargs < 3)
                return;
            PyObject* dtype_arg = PyList_GET_ITEM(ctor_args, 1);
            if (PyUnicode_CheckExact(dtype_arg)
                && PyUnicode_CompareWithASCIIString(dtype_arg, "bool") == 0)
                return;
            label_index = -1;
            bool diff = false;
            for (Py_ssize_t i = 2; i < nargs; i++) {
                PyObject* item = PyList_GET_ITEM(ctor_args, i);
                if (PyUnicode_CheckExact(item)) {
                    const char* label = PyUnicode_AsUTF8(item);
                    if (label == nullptr) {
                        PyErr_Clear();
                        return;
                    }
                    if (strncmp(label, "blosc2", 6) != 0)
                        return;   // blosc v1 : voie normale
                    const char* reste = label + 6;
                    if (*reste == '\0') {
                        // trame blosc2 nue : chemin historique
                    } else if (strcmp(reste, "_diff") == 0) {
                        diff = true;  // dérivée globale
                    } else if (strncmp(reste, "_diffb", 6) == 0
                               && reste[6] >= '1' && reste[6] <= '9') {
                        char* fin = nullptr;
                        cs_block_rows = (Py_ssize_t) strtoll(reste + 6, &fin,
                                                             10);
                        if (*fin != '\0')
                            return;
                        diff = true;  // dérivée par blocs
                    } else
                        return;   // blosc2p, autre variante : voie normale
                    label_index = i;
                    break;
                }
            }
            if (label_index == -1)
                return;
            if (diff) {
                // largeur d'élément depuis le nom du dtype (entiers seuls :
                // la dérivée n'est écrite que pour eux)
                if (!PyUnicode_CheckExact(dtype_arg))
                    return;
                const char* dt = PyUnicode_AsUTF8(dtype_arg);
                if (dt == nullptr) {
                    PyErr_Clear();
                    return;
                }
                if (dt[0] == 'u')
                    dt++;
                if (strcmp(dt, "int8") == 0)
                    cs_itemsize = 1;
                else if (strcmp(dt, "int16") == 0)
                    cs_itemsize = 2;
                else if (strcmp(dt, "int32") == 0)
                    cs_itemsize = 4;
                else if (strcmp(dt, "int64") == 0)
                    cs_itemsize = 8;
                else
                    return;  // dtype inattendu : voie Python
                // colonnes = produit des dimensions après la première
                if (label_index > 2) {
                    PyObject* shape = PyList_GET_ITEM(ctor_args, 2);
                    if (PyList_CheckExact(shape)) {
                        for (Py_ssize_t i = 1; i < PyList_GET_SIZE(shape);
                             i++) {
                            PyObject* dim = PyList_GET_ITEM(shape, i);
                            if (!PyLong_CheckExact(dim))
                                return;
                            cs_cols *= PyLong_AsSsize_t(dim);
                        }
                        if (cs_cols <= 0) {
                            PyErr_Clear();
                            return;
                        }
                    }
                }
            }
        } else {
            PyObject* label = PyList_GET_ITEM(ctor_args, 1);
            if (!PyUnicode_CheckExact(label)
                || PyUnicode_CompareWithASCIIString(label, "b64_blosc2") != 0)
                return;
            label_index = 1;
        }
        // entête de trame : décode les 44 premiers caractères (33 octets,
        // jusqu'aux metas de filtres — octet 28 : cumsum interne du 244)
        if (job.length < 44 || job.decoded_length < 16)
            return;
        unsigned char header[36];
        if (!sj_b64_decode_groups((const unsigned char*) job.src, 11, header,
                                  serializejson_b64_decode_table()))
            return;
        if (header[0] < 4)
            return;                     // trame blosc v1 : voie Python
        size_t nbytes = 0, cbytes = 0, blocksize = 0;
        sj_blosc1_cbuffer_sizes((const char*) header, &nbytes, &cbytes,
                                &blocksize);
        if (cbytes < 16 || cbytes != job.decoded_length)
            return;                     // trames multiples (blosc2p) : voie normale
        if (cs_itemsize > 0 && nbytes % (size_t) (cs_itemsize * cs_cols) != 0)
            return;                     // forme incohérente : voie Python
        PyObject* dest = (kind == 0)
            ? PyBytes_FromStringAndSize(nullptr, (Py_ssize_t) nbytes)
            : PyByteArray_FromStringAndSize(nullptr, (Py_ssize_t) nbytes);
        if (dest == nullptr) {
            PyErr_Clear();
            return;
        }
        Py_INCREF(dest);                // référence du job (destobj)
        Py_INCREF(dest);                // référence donnée à la liste
        PyList_SetItem(ctor_args, 0, dest);   // décrémente l'ancienne charge
        if (kind == 2) {
            Py_INCREF(Py_None);
            PyList_SetItem(ctor_args, label_index, Py_None);
        } else {
            PyObject* b64_label = PyUnicode_InternFromString("b64");
            if (b64_label == nullptr) {
                PyErr_Clear();
                b64_label = Py_None;
                Py_INCREF(Py_None);
            }
            PyList_SetItem(ctor_args, label_index, b64_label);
        }
        job.dest = (kind == 0)
            ? (unsigned char*) PyBytes_AS_STRING(dest)
            : (unsigned char*) PyByteArray_AS_STRING(dest);
        job.destsize = nbytes;
        job.destobj = dest;
        if (cs_itemsize > 0 && job.decoded_length >= 32
            && header[16 + 4] == 244 && (header[24 + 4] >> 4) != 0) {
            // le filtre 244 de la trame porte déjà le cumsum : rien à défaire
            cs_itemsize = 0;
        }
        if (cs_itemsize > 0) {
            job.cs_itemsize = cs_itemsize;
            job.cs_cols = cs_cols;
            job.cs_block_rows = cs_block_rows;
            // fusion par postfiltre si les blocs de la trame SONT les blocs
            // de la dérivée (l'écriture a calé blocksize) ; post-passe sinon
            job.cs_fused = (cs_block_rows > 0
                            && (Py_ssize_t) blocksize
                                   == cs_block_rows * cs_itemsize * cs_cols);
        }
        Py_DECREF(dest);                // compense le double INCREF ci-dessus
    }

    // remplit tous les tampons différés (en parallèle au-delà d'un job) ;
    // à appeler avant tout rappel Python et en fin de parse
    bool FlushPendingB64() {
        if (pendingB64.empty())
            return true;
        const unsigned char* table = serializejson_b64_decode_table();
        bool ok = true;
        size_t count = pendingB64.size();
        // volume total différé : en dessous du seuil, tout se fait EN LIGNE
        // et en mono-thread — créer des threads (ou un contexte blosc2
        // multi-thread) pour quelques Ko coûtait plus que leur décodage,
        // et la file est vidée à CHAQUE rappel Python de fin d'objet
        // (mesuré 05/08 au soir : x4 sur un lot de petits bytes)
        size_t total_bytes = 0;
        for (PendingB64& job : pendingB64)
            total_bytes += job.decoded_length + (size_t) job.destsize;
        bool petit = total_bytes < (1u << 20);
        {
            std::atomic<size_t> next(0);
            std::atomic<bool> good(true);
            std::vector<PendingB64>* jobs = &pendingB64;
            // figé au premier appel : l'interrogation refait un appel
            // système à chaque fois, payé PAR PARSE même pour un job
            static const size_t hw0 = std::thread::hardware_concurrency();
            size_t budget = hw0 ? (hw0 > 8 ? 8 : hw0) : 1;
            // moins de jobs que de coeurs : le parallélisme passe DANS le
            // dctx (MT interne blosc2), sinon un job par thread
            int inner_threads = (count < budget)
                ? (int) (budget / count) : 1;
            if (petit)
                inner_threads = 1;
            auto work = [jobs, &next, &good, table, inner_threads]() {
                blosc2_context* dctx = nullptr;   // créé au premier besoin
                for (;;) {
                    size_t i = next.fetch_add(1);
                    if (i >= jobs->size())
                        break;
                    PendingB64& job = (*jobs)[i];
                    if (!sj_b64_decode_into(job.src, job.length, job.dst,
                                            table)) {
                        good.store(false, std::memory_order_relaxed);
                        continue;
                    }
                    if (job.destobj != nullptr) {
                        int written = -1;
                        if (job.cs_fused) {
                            // fusion complète : b64 -> zstd -> somme cumulée
                            // par bloc dans le postfiltre, une seule traversée
                            SjPostCumsum post = {job.cs_itemsize, job.cs_cols};
                            blosc2_postfilter_params pparams;
                            memset(&pparams, 0, sizeof(pparams));
                            pparams.user_data = (void*) &post;
                            blosc2_dparams dparams = BLOSC2_DPARAMS_DEFAULTS;
                            dparams.nthreads = (int16_t) inner_threads;
                            dparams.postfilter = sj_cumsum_postfilter;
                            dparams.postparams = &pparams;
                            blosc2_context* fctx = sj_blosc2_create_dctx(
                                dparams);
                            if (fctx != nullptr) {
                                written = sj_blosc2_decompress_ctx(
                                    fctx, job.dst,
                                    (int32_t) job.decoded_length,
                                    job.dest, (int32_t) job.destsize);
                                sj_blosc2_free_ctx(fctx);
                            }
                        } else {
                            if (dctx == nullptr) {
                                blosc2_dparams dparams =
                                    BLOSC2_DPARAMS_DEFAULTS;
                                dparams.nthreads = (int16_t) inner_threads;
                                dctx = sj_blosc2_create_dctx(dparams);
                            }
                            written = (dctx == nullptr) ? -1
                                : sj_blosc2_decompress_ctx(
                                      dctx, job.dst,
                                      (int32_t) job.decoded_length,
                                      job.dest, (int32_t) job.destsize);
                            if (written == (int) job.destsize
                                && job.cs_itemsize > 0) {
                                // dérivée sans blocs calés : post-passe par
                                // blocs (SIMD), le tampon sort du L2/L3
                                Py_ssize_t rb = job.cs_itemsize * job.cs_cols;
                                Py_ssize_t rows =
                                    (Py_ssize_t) job.destsize / rb;
                                Py_ssize_t br = (job.cs_block_rows > 0)
                                    ? job.cs_block_rows : rows;
                                for (Py_ssize_t r0 = 0; r0 < rows; r0 += br) {
                                    char* p = (char*) job.dest + r0 * rb;
                                    sj_cumsum_slice(
                                        p, p, job.cs_itemsize,
                                        std::min<Py_ssize_t>(br, rows - r0),
                                        job.cs_cols);
                                }
                            }
                        }
                        if (written != (int) job.destsize)
                            good.store(false, std::memory_order_relaxed);
                    }
                }
                if (dctx != nullptr)
                    sj_blosc2_free_ctx(dctx);
            };
            size_t nthreads = budget;
            if (nthreads > count)
                nthreads = count;
            if (petit)
                nthreads = 1;
            if (nthreads <= 1) {
                work();
            } else {
                Py_BEGIN_ALLOW_THREADS
                std::vector<std::thread> pool;
                for (size_t t = 1; t < nthreads; t++)
                    pool.emplace_back(work);
                work();
                for (std::thread& t : pool)
                    t.join();
                Py_END_ALLOW_THREADS
            }
            ok = good.load();
        }
        ReleasePendingB64();
        if (!ok)
            PyErr_SetString(PyExc_ValueError,
                            "invalid deferred base64 payload");
        return ok;
    }

    // Verse les éléments en attente d'un niveau dans SA liste, en une seule
    // allocation à la taille exacte. La liste garde son identité — des $ref
    // peuvent déjà la désigner, et son parent la tient depuis son ouverture :
    // on ne lui donne que son tampon interne, qu'elle n'a pas encore (elle
    // sort de PyList_New(0) et n'a jamais reçu d'élément, `differe` ne
    // repassant jamais à vrai). PyMem_* est l'allocateur dont CPython se sert
    // lui-même pour ob_item, et c'est lui qui le libérera : la batterie
    // tourne sous PYTHONMALLOC=debug, qui refuse tout mélange d'allocateurs.
    bool VerseAttente(HandlerContext& ctx) {
        if (!ctx.differe)
            return true;
        ctx.differe = false;
        const size_t n = attente.size() - ctx.attenteBase;
        if (n == 0)
            return true;
        // la seule allocation qui puisse vraiment manquer ici : 16 Mo pour un
        // tableau de deux millions d'éléments. Échouer en silence rendrait
        // une liste VIDE, ce que l'appelant ne verrait pas
        PyObject** tampon = (PyObject**) PyMem_Malloc(n * sizeof(PyObject*));
        if (tampon == nullptr) {
            PyErr_NoMemory();   // les éléments restent à `attente`, qui les
            return false;       // relâchera à la destruction du handler
        }
        memcpy(tampon, attente.data() + ctx.attenteBase, n * sizeof(PyObject*));
        PyListObject* liste = (PyListObject*) ctx.object;
        liste->ob_item = tampon;           // avant la taille : un parcours du
        Py_SET_SIZE(liste, (Py_ssize_t) n);   // ramasse-miettes lirait sinon
        liste->allocated = (Py_ssize_t) n;    // n pointeurs dans un tampon nul
        attente.resize(ctx.attenteBase);
        return true;
    }

    // Tous les niveaux versés, du plus profond au plus haut : chaque
    // versement retire SA tranche du sommet de `attente`, donc l'ordre
    // inverse est le seul qui ne jette pas les tranches des fils. Appelé
    // avant de résoudre un $ref, qui parcourt l'arbre depuis la racine et
    // doit y trouver les listes déjà remplies : sans lui, 2 000 renvois vers
    // une liste encore ouverte repartent en post-passe python, cinq fois
    // plus cher. Un échec n'a rien à propager — l'erreur est posée, et la
    // résolution ne trouvera simplement pas sa cible.
    void VerseTout() {
        for (size_t i = stack.size(); i-- > 0;)
            VerseAttente(stack[i]);
    }

    // le fils qui vient d'être fermé est le DERNIER élément de la tranche de
    // son parent, et c'est sa forme finale qui l'y remplace
    void RemplaceDernier(PyObject* replacement) {
        PyObject*& emplacement = attente.back();
        Py_DECREF(emplacement);
        emplacement = replacement;         // référence volée
    }

    // insertion d'une valeur dans un contexte donné (prélude de capture
    // d'enveloppe compris) : stack.back() en temps normal (Handle), ou le
    // PARENT d'une enveloppe différée quand son dict est matérialisé après
    // coup (EnvDeferMaterialize)
    bool HandleInto(HandlerContext& env, PyObject* value) {
        if (env.envState == 1) {
            // valeur de "__class__" : une chaîne, sinon l'enveloppe est
            // démentie. numpyB64 est exclu de la capture : son différé
            // (TryDeferDecompress) lit le dict pendant le parse
            if (PyUnicode_CheckExact(value)
                && !(PyUnicode_GET_LENGTH(value) == 8
                     && PyUnicode_CompareWithASCIIString(
                            value, "numpyB64") == 0)) {
                env.envClass = value;   // référence consommée
                env.envState = 2;
                return true;
            }
            if (!EnvFlush(env)) {
                Py_DECREF(value);
                return false;
            }
        } else if (env.envState == 3) {
            // les arguments (scalaire, chaîne, liste ou dict en cours de
            // construction) : capturés hors du dict d'enveloppe
            env.envArgs = value;        // référence consommée
            env.envState = 4;
            return true;
        } else if (env.envState == 5) {
            env.envItems = value;       // référence consommée
            env.envState = 6;
            return true;
        } else if (env.envState == 7) {
            // paire décodée -> directement dans le dict final ; clé
            // nulle = valeur à jeter (__class__ nu dupliqué). La clé
            // reste vivante : un fils conteneur sera resservi par
            // ReplaceInParent sous la même clé
            int rc = 0;
            if (env.envDictKey != nullptr)
                rc = PyDict_SetItem(env.object, env.envDictKey, value);
            Py_DECREF(value);
            return rc == 0;
        } else if (env.envState != 0) {
            // valeur inattendue pour l'état (JSON exotique) : repli
            if (!EnvFlush(env)) {
                Py_DECREF(value);
                return false;
            }
        }
        const HandlerContext& current = env;

        if (current.isObject) {
            PyObject* key = KeyString(current.key,
                                      (size_t) current.keyLength);
            if (key == nullptr) {
                Py_DECREF(value);
                return false;
            }

            int rc;
            if (current.keyValuePairs) {
                PyObject* pair = PyTuple_Pack(2, key, value);

                Py_DECREF(key);
                Py_DECREF(value);
                if (pair == nullptr) {
                    return false;
                }
                rc = PyList_Append(current.object, pair);
                Py_DECREF(pair);
            } else {
                if (PyDict_CheckExact(current.object))
                    // If it's a standard dictionary, this is +20% faster
                    rc = PyDict_SetItem(current.object, key, value);
                else
                    rc = PyObject_SetItem(current.object, key, value);
                Py_DECREF(key);
                Py_DECREF(value);
            }

            if (rc == -1) {
                return false;
            }
        } else if (current.differe) {
            attente.push_back(value);      // référence volée
            if (attente.size() - current.attenteBase >= SJ_ATTENTE_MAX
                && !VerseAttente(env))            // `current` est const
                return false;
        } else {
            PyList_Append(current.object, value);
            Py_DECREF(value);
        }
        return true;
    }

    bool Handle(PyObject* value) {
        if (root)
            return HandleInto(stack.back(), value);
        root = value;
        return true;
    }

    // résolution directe d'un chemin $ref depuis le tampon de parse, sans
    // chaîne python ni dict intermédiaires. Rend une réf FORTE, ou nullptr
    // sans erreur posée (réf en avant, cible encore à l'état d'enveloppe,
    // racine inconnue) : l'appelant retombe sur la voie classique
    PyObject* ResoudreRefDirect(const char* str, SizeType length,
                                PyObject* dictCourant) {
        std::string clef(str, (size_t) length);
        auto it = refOctetsCache.find(clef);
        if (it != refOctetsCache.end()) {
            Py_INCREF(it->second);
            return it->second;
        }
        if (rootObject == nullptr && root != nullptr) {
            rootObject = root;
            Py_INCREF(rootObject);
        }
        if (rootObject == nullptr)
            return nullptr;
        // même exigence que la résolution à la fermeture : les listes
        // ouvertes doivent être pleines pour que le parcours depuis la
        // racine retrouve leurs éléments déjà lus
        VerseTout();
        PyObject* resolu = sj_resolve_ref_path(str, (Py_ssize_t) length,
                                               rootObject);
        if (resolu == nullptr)
            return nullptr;
        if (resolu == dictCourant || !SjCibleRef(&resolu)) {
            Py_DECREF(resolu);   // pas encore recréé : voie python, sans cache
            return nullptr;
        }
        Py_INCREF(resolu);
        refOctetsCache.emplace(std::move(clef), resolu);
        return resolu;
    }

    // cible d'un $ref résolu (réf possédée par l'appelant) : faux si elle est
    // encore à l'état d'enveloppe — sauf, en réhydratation, quand son objet
    // est déjà construit et rangé dans "__class__" : il prend sa place
    bool SjCibleRef(PyObject** cible) {
        if (!PyDict_CheckExact(*cible))
            return true;
        PyObject* classe = PyDict_GetItem(*cible, class_key_name);
        if (classe == nullptr)
            return true;
        if (!rehydrateOn || PyUnicode_CheckExact(classe))
            return false;
        Py_INCREF(classe);
        Py_SETREF(*cible, classe);
        return true;
    }

    // clé supplémentaire après un $ref déjà résolu au vol ({"$ref": c, x: y},
    // jamais émis par l'encodeur) : la paire est réinsérée dans le dict et la
    // voie classique reprend, octets et sémantique inchangés
    bool RefMaterialise(HandlerContext& ctx) {
        PyObject* chemin = PyUnicode_FromStringAndSize(
            ctx.refCheminBrut, (Py_ssize_t) ctx.refCheminBrutLg);
        Py_CLEAR(ctx.refResolu);
        if (chemin == nullptr)
            return false;
        int rc = PyDict_SetItem(ctx.object, ref_key_name, chemin);
        Py_DECREF(chemin);
        return rc == 0;
    }

    // plan de décodage d'une classe (decode_class_plan du décodeur), résolu
    // une fois par nom et par chargement : réf EMPRUNTÉE (None = pas de plan),
    // nullptr = erreur posée. Pas de vidage ici : decode_class_plan ne
    // consulte que les registres de classes, jamais les charges
    PyObject* SjPlan(PyObject* class_value) {
        Py_ssize_t class_length;
        const char* class_str =
            PyUnicode_AsUTF8AndSize(class_value, &class_length);
        if (class_str == nullptr)
            return nullptr;
        std::string plan_key(class_str, (size_t) class_length);
        auto plan_it = decodePlans.find(plan_key);
        if (plan_it != decodePlans.end())
            return plan_it->second;
        PyObject* plan = PyObject_CallFunctionObjArgs(decodeClassPlanFn,
                                                      class_value, nullptr);
        if (plan == nullptr)
            return nullptr;
        if (plan != Py_None && !PyType_Check(plan)
            && !(PyTuple_Check(plan) && PyTuple_GET_SIZE(plan) == 2
                 && PyType_Check(PyTuple_GET_ITEM(plan, 0)))) {
            Py_DECREF(plan);
            plan = Py_None;
            Py_INCREF(Py_None);
        }
        decodePlans.emplace(std::move(plan_key), plan);
        return plan;
    }

    // ----- réhydratation au fil du parse -----

    // vrai si `ctx` est une enveloppe PAS ENCORE CONSTRUITE dont on parcourt
    // les arguments du constructeur (sa clé courante est le slot __init__/
    // __new__) : `*classe` reçoit son nom (emprunté). Faux pour tout autre
    // niveau (dict de données, enveloppe construite, sous une clé d'état)
    static bool SjEnveloppeTraversee(const HandlerContext& ctx,
                                     PyObject** classe) {
        if (!ctx.isObject || ctx.key == nullptr
            || !((ctx.keyLength == 8 && memcmp(ctx.key, "__init__", 8) == 0)
                 || (ctx.keyLength == 7 && memcmp(ctx.key, "__new__", 7) == 0)))
            return false;
        PyObject* cls = nullptr;
        if (ctx.envState == 3 || ctx.envState == 4)
            cls = ctx.envClass;             // capture en cours
        else if (ctx.envState == 0 && ctx.object != nullptr
                 && PyDict_Check(ctx.object))
            cls = PyDict_GetItem(ctx.object, class_key_name);   // versée
        if (cls == nullptr || !PyUnicode_CheckExact(cls))
            return false;
        *classe = cls;
        return true;
    }

    // chaîne des clés du plus proche ancêtre CONSTRUIT jusqu'au niveau
    // `niveau` exclu (`insere` : son objet est déjà inséré chez son parent).
    // `*ancetre` reçoit cet ancêtre (emprunté ; nullptr = la racine vivante),
    // `*tilde` vaut vrai si une clé commence par '~' (lecteur virtuel, voie
    // python). La chaîne peut traverser les ARGUMENTS d'une enveloppe pas
    // encore construite : un objet donné au constructeur d'un parent
    // (l'enfant Qt anonyme est écrit en plein dans le __init__ de son
    // premier enfant nommé). Le pas est alors un couple (slot, classe) —
    // l'homologue vivant du parent doit être de cette classe exacte (s'il
    // est adopté, ses arguments réconciliés sont ceux du json) et le pas suivant
    // lit l'argument par son accesseur (parent()). Rend une liste NEUVE, ou
    // nullptr sans erreur : aucun homologue vivant possible — sous une clé
    // d'état d'une enveloppe déclinée, sous une clé indécodable ou des
    // __items__, ou le point de départ ne peut rien porter (pas de racine
    // vivante, ancêtre sorti nu de tp_new). Première passe sans
    // allocation : sur une recréation (le cas courant), aucune liste n'est
    // jamais bâtie
    PyObject* SjChaine(size_t niveau, bool insere, PyObject** ancetre,
                       bool* tilde) {
        *ancetre = nullptr;
        *tilde = false;
        size_t depart = 0;   // niveau de l'ancêtre construit (exclu)
        bool possible = liveRoot != nullptr;
        for (size_t i = niveau; i-- > 0;) {
            const HandlerContext& ctx = stack[i];
            if (ctx.isObject) {
                PyObject* classeX;
                if (ctx.envState == 7) {
                    if (ctx.envDictKey == nullptr)
                        return nullptr;
                    if (PyUnicode_Check(ctx.envDictKey)
                        && PyUnicode_GET_LENGTH(ctx.envDictKey) > 0
                        && PyUnicode_READ_CHAR(ctx.envDictKey, 0) == '~')
                        *tilde = true;
                } else if (SjEnveloppeTraversee(ctx, &classeX)) {
                    PyObject* plan = SjPlan(classeX);
                    if (plan == nullptr) {
                        PyErr_Clear();
                        return nullptr;
                    }
                    if (plan == Py_None)
                        *tilde = true;   // classe sans plan : voie python
                } else if (ctx.envState == 0 && ctx.key != nullptr) {
                    if (ctx.keyLength > 0 && ctx.key[0] == '~')
                        *tilde = true;
                    PyObject* classe = PyDict_Check(ctx.object)
                        ? PyDict_GetItem(ctx.object, class_key_name)
                        : nullptr;
                    if (classe != nullptr) {
                        // enveloppe déclinée (classe restée un nom) sous
                        // une clé d'état : rien de vivant dessous
                        if (PyUnicode_CheckExact(classe))
                            return nullptr;
                        *ancetre = classe;   // instance déjà construite :
                        depart = i;          // sa clé courante ouvre la chaîne
                        possible = !ctx.envFresh;
                        break;
                    }
                } else {
                    return nullptr;   // enveloppe ouverte (__class__, __items__)
                }
            }
        }
        if (!possible)
            return nullptr;
        PyObject* cles = PyList_New((Py_ssize_t) (niveau - depart));
        if (cles == nullptr) {
            PyErr_Clear();
            return nullptr;
        }
        for (size_t i = depart; i < niveau; i++) {
            const HandlerContext& ctx = stack[i];
            PyObject* cle;
            if (!ctx.isObject) {
                // l'objet du niveau suivant : inséré chez son parent sauf
                // pour une enveloppe différée (object nul)
                bool insereSuivant = i + 1 < niveau
                    ? stack[i + 1].object != nullptr : insere;
                cle = PyLong_FromSsize_t(NbRecus(ctx) - (insereSuivant ? 1 : 0));
            } else if (ctx.envState == 7) {
                cle = ctx.envDictKey;
                Py_INCREF(cle);
            } else {
                PyObject* classeX;
                cle = KeyString(ctx.key, ctx.keyLength);
                if (cle != nullptr && SjEnveloppeTraversee(ctx, &classeX)) {
                    // pas (slot, classe) : voir l'en-tête
                    PyObject* couple = PyTuple_Pack(2, cle, classeX);
                    Py_DECREF(cle);
                    cle = couple;
                }
            }
            if (cle == nullptr) {
                Py_DECREF(cles);
                PyErr_Clear();
                return nullptr;
            }
            PyList_SET_ITEM(cles, (Py_ssize_t) (i - depart), cle);
        }
        return cles;
    }

    // homologue vivant au bout de la chaîne : NOUVELLE réf, ou nullptr sans
    // erreur (attribut, clé ou indice absent). Un pas (slot, classe) reste
    // sur place si l'objet courant est de cette classe exacte (le parent,
    // s'il est adopté, aura des arguments égaux à ceux du json) ; un
    // attribut servi par une méthode (accesseur Qt : parent(), comme
    // _descend en python) est lu par son appel sans argument
    PyObject* SjVivant(PyObject* depart, PyObject* cles) {
        PyObject* courant = depart;
        Py_INCREF(courant);
        Py_ssize_t n = PyList_GET_SIZE(cles);
        for (Py_ssize_t i = 0; i < n && courant != nullptr; i++) {
            PyObject* cle = PyList_GET_ITEM(cles, i);
            PyObject* suivant;
            if (PyTuple_CheckExact(cle)) {
                PyObject* plan = SjPlan(PyTuple_GET_ITEM(cle, 1));
                PyTypeObject* clsX = nullptr;
                if (plan != nullptr && plan != Py_None)
                    clsX = PyType_Check(plan)
                        ? (PyTypeObject*) plan
                        : (PyTypeObject*) PyTuple_GET_ITEM(plan, 0);
                suivant = nullptr;
                if (Py_TYPE(courant) == clsX) {
                    suivant = courant;
                    Py_INCREF(suivant);
                }
            } else if (PyDict_Check(courant)) {
                suivant = PyDict_GetItemWithError(courant, cle);
                Py_XINCREF(suivant);
            } else if (PyLong_CheckExact(cle)) {
                suivant = (PyList_Check(courant) || PyTuple_Check(courant))
                    ? PySequence_GetItem(courant, PyLong_AsSsize_t(cle))
                    : nullptr;
            } else {
#if PY_VERSION_HEX >= 0x030D0000
                PyObject_GetOptionalAttr(courant, cle, &suivant);
#else
                _PyObject_LookupAttr(courant, cle, &suivant);
#endif
                if (suivant != nullptr
                    && (PyMethod_Check(suivant) || PyCFunction_Check(suivant)))
                    Py_SETREF(suivant, PyObject_CallNoArgs(suivant));
            }
            PyErr_Clear();
            Py_DECREF(courant);
            courant = suivant;
        }
        return courant;
    }

    // vrai si `args` (json) est vide : rien à comparer, l'homologue vivant
    // est adopté sans appel python — le cas des données (forme __new__ ou
    // tp_new seul)
    static bool SjSansArgs(PyObject* args) {
        return args == nullptr
            || ((PyList_CheckExact(args) || PyTuple_CheckExact(args))
                && PySequence_Fast_GET_SIZE(args) == 0)
            || (PyDict_CheckExact(args) && PyDict_GET_SIZE(args) == 0);
    }

    // construction par le plan de classe, mêmes formes que instance() :
    // __new__ (slot 1) ou pas d'__init__ -> tp_new sans __init__, sinon
    // cls(*liste) / cls(**dict) / cls(scalaire). NOUVELLE réf, nullptr = erreur
    static PyObject* SjInstancie(PyTypeObject* cls, PyObject* args, int slot) {
        PyObject* pos;
        PyObject* kw = nullptr;
        if (args == nullptr) {
            pos = empty_args_tuple;
            Py_INCREF(pos);
        } else if (PyList_CheckExact(args)) {
            pos = PyList_AsTuple(args);
        } else if (PyTuple_CheckExact(args)) {
            pos = args;
            Py_INCREF(pos);
        } else if (PyDict_CheckExact(args)) {
            pos = empty_args_tuple;
            Py_INCREF(pos);
            kw = args;
        } else {
            pos = PyTuple_Pack(1, args);
        }
        if (pos == nullptr)
            return nullptr;
        PyObject* inst = (slot == 1 || args == nullptr)
            ? cls->tp_new(cls, pos, kw)
            : PyObject_Call((PyObject*) cls, pos, kw);
        Py_DECREF(pos);
        return inst;
    }

    // l'objet de l'enveloppe au niveau `niveau` : son homologue vivant adopté
    // (même type exact, trouvé par la chaîne des clés depuis l'ancêtre
    // construit ou la racine vivante), sinon construit. NOUVELLE réf ;
    // nullptr = déclin sans erreur (classe native ou sans plan et refusée par
    // python) ou erreur posée. Un vivant de même type est adopté sans
    // condition si le json n'a pas d'arguments, sinon si Decoder._reconcile
    // accepte (arguments égaux, ou différences applicables par nom)
    PyObject* SjConstruit(size_t niveau, bool insere, PyObject* classe,
                          PyObject* args, int slot, bool* fresh = nullptr) {
        Py_ssize_t n;
        const char* s = PyUnicode_AsUTF8AndSize(classe, &n);
        if (s == nullptr)
            return nullptr;
        // natifs : leurs chemins rapides restent les leurs. bytes/bytearray/
        // numpyB64 (b64PayloadClasses) : leur charge peut être un différé
        // (pendingB64) pas encore rempli — construire ici lirait des zéros ;
        // la voie classique vide la file avant d'instancier
        if ((n == 4 && (memcmp(s, "dict", 4) == 0 || memcmp(s, "type", 4) == 0))
            || (n == 17 && memcmp(s, "dict_non_str_keys", 17) == 0)
            || (n == 8 && memcmp(s, "numpyB64", 8) == 0)
            || (n == 5 && memcmp(s, "bytes", 5) == 0)
            || (n == 9 && memcmp(s, "bytearray", 9) == 0))
            return nullptr;
        PyObject* plan = SjPlan(classe);
        if (plan == nullptr)
            return nullptr;
        PyObject* ancetre;
        bool tilde;
        PyObject* cles = SjChaine(niveau, insere, &ancetre, &tilde);
        if (plan == Py_None || tilde || !rehydrateEnC) {
            // voie python : classe sans plan (constructors, non autorisée,
            // setters...), lecteur virtuel '~', ou updatables_classes
            PyObject* res = PyObject_CallFunction(
                decoderConstruct, "OOiOO", classe,
                args != nullptr ? args : Py_None, slot,
                ancetre != nullptr ? ancetre : Py_None,
                cles != nullptr ? cles : Py_None);
            Py_XDECREF(cles);
            if (res == Py_None)
                Py_CLEAR(res);
            return res;
        }
        PyTypeObject* cls = PyType_Check(plan)
            ? (PyTypeObject*) plan
            : (PyTypeObject*) PyTuple_GET_ITEM(plan, 0);
        PyObject* inst = nullptr;
        if (cles != nullptr) {
            if (ancetre == nullptr && PyList_GET_SIZE(cles) == 0) {
                // la racine : l'objet obj= est adopté tel quel
                inst = liveRoot;
                Py_XINCREF(inst);
            } else {
                PyObject* depart = ancetre != nullptr ? ancetre : liveRoot;
                if (depart != nullptr) {
                    inst = SjVivant(depart, cles);
                    if (inst != nullptr && Py_TYPE(inst) != cls)
                        Py_CLEAR(inst);
                    else if (inst != nullptr && !SjSansArgs(args)) {
                        if (decoderReconcile == nullptr) {
                            Py_CLEAR(inst);
                        } else {
                            PyObject* ok = PyObject_CallFunction(
                                decoderReconcile, "OOi", inst, args, slot);
                            if (ok == nullptr) {
                                Py_DECREF(inst);
                                Py_DECREF(cles);
                                return nullptr;
                            }
                            int vrai = PyObject_IsTrue(ok);
                            Py_DECREF(ok);
                            if (vrai != 1)
                                Py_CLEAR(inst);
                            PyErr_Clear();
                        }
                    }
                }
            }
            Py_DECREF(cles);
        }
        if (inst == nullptr) {
            inst = SjInstancie(cls, args, slot);
            if (inst == nullptr)
                return nullptr;
            // sorti nu de object.__new__ : __dict__ vide, rien dessous
            if (fresh != nullptr && args == nullptr
                && cls->tp_new == PyBaseObject_Type.tp_new)
                *fresh = true;
        }
        if (Py_TYPE(inst) == cls && plansParType.find(cls) == plansParType.end())
            plansParType.emplace(cls, plan);
        return inst;
    }

    // première clé d'ÉTAT au niveau d'une enveloppe — capturée (état 2/4)
    // ou classique {__class__ (, __init__|__new__)} — : l'objet est construit
    // ou adopté ICI, avant ses attributs et ses enfants. Faux = erreur posée
    bool SjKeyConstruit(HandlerContext& current, const char* str,
                        SizeType length) {
        // dict ordinaire (aucune clé spéciale vue) ou niveau déjà traité :
        // un test, rien d'autre — c'est le cas de toutes les clés d'un
        // document de données
        if (current.envConstruit || (current.envState == 0 && !current.specialKey))
            return true;
        if (current.envState != 0 && current.envState != 2
            && current.envState != 4)
            return true;
        if ((length == 9 && (memcmp(str, "__class__", 9) == 0
                             || memcmp(str, "__items__", 9) == 0))
            || (length == 4 && memcmp(str, "$ref", 4) == 0)
            || (length == 7 && memcmp(str, "__new__", 7) == 0)
            || (length == 8 && memcmp(str, "__init__", 8) == 0))
            return true;
        PyObject* classe = current.envClass;
        PyObject* args = current.envArgs;
        int slot = current.envState == 4 ? current.envSlot : 0;
        current.envConstruit = true;
        if (current.envState == 0) {
            if (current.object == nullptr
                || !PyDict_CheckExact(current.object)
                || PyDict_GET_SIZE(current.object) > 2)
                return true;
            classe = PyDict_GetItem(current.object, class_key_name);
            if (classe == nullptr || !PyUnicode_CheckExact(classe))
                return true;
            if (PyDict_GET_SIZE(current.object) == 2) {
                args = PyDict_GetItem(current.object, init_key_name);
                slot = 2;
                if (args == nullptr) {
                    args = PyDict_GetItem(current.object, new_key_name);
                    slot = 1;
                }
                if (args == nullptr)
                    return true;   // autre clé : forme inconnue
            }
        }
        PyObject* inst = SjConstruit(stack.size() - 1, current.object != nullptr,
                                     classe, args, slot,
                                     &current.envFresh);
        if (inst == nullptr)
            return !PyErr_Occurred();
        if (current.envState == 0) {
            int rc = PyDict_SetItem(current.object, class_key_name, inst);
            Py_DECREF(inst);
            return rc == 0;
        }
        // capture : l'instance prend la place du nom, EnvFlush (déclenché
        // par cette même clé) la versera dans le dict sous "__class__"
        Py_SETREF(current.envClass, inst);
        return true;
    }

    // état de `mapping` appliqué à `inst` : un setattr par attribut (classe à
    // __slots__), sinon FUSION dans son __dict__ (le __init__ a pu le
    // remplir), jamais de remplacement. Les clés '~…' (lecteurs virtuels du
    // greffon Qt, déjà consommées au passage) sont sautées. Faux = erreur posée
    bool SjAppliqueEtat(PyObject* inst, PyObject* mapping, bool by_setattr) {
        PyObject* inst_dict = nullptr;
        if (!by_setattr) {
            inst_dict = PyObject_GetAttr(inst, dict_dunder_name);
            if (inst_dict == nullptr || !PyDict_CheckExact(inst_dict)) {
                // pas de __dict__ ordinaire : setattr, même effet pour un
                // objet sans descripteurs
                PyErr_Clear();
                Py_CLEAR(inst_dict);
            }
        }
        Py_ssize_t attr_pos = 0;
        PyObject* attr_key;
        PyObject* attr_value;
        while (PyDict_Next(mapping, &attr_pos, &attr_key, &attr_value)) {
            if (PyUnicode_Check(attr_key) && PyUnicode_GET_LENGTH(attr_key) > 0
                && PyUnicode_READ_CHAR(attr_key, 0) == '~')
                continue;
            int rc = inst_dict != nullptr
                ? PyDict_SetItem(inst_dict, attr_key, attr_value)
                : PyObject_SetAttr(inst, attr_key, attr_value);
            if (rc == -1) {
                if (inst_dict == nullptr)
                    sj_enrich_setattr_error(inst, attr_key);
                Py_XDECREF(inst_dict);
                return false;
            }
        }
        Py_XDECREF(inst_dict);
        return true;
    }

    bool Key(const char* str, SizeType length, bool copy) {
        HandlerContext& current = stack.back();

        if (current.refResolu != nullptr && !RefMaterialise(current))
            return false;
        if (rehydrateOn && !SjKeyConstruit(current, str, length))
            return false;

        if (current.envState == 7) {
            // enveloppe de dict à clés non-str : TOUTE clé est une donnée
            // (même "__init__" ou "$ref" — l'encodeur requote les seules
            // '__class__'/'$ref' littérales) ; décodée AU VOL, sa valeur ira
            // directement dans le dict final. "__class__" nu dupliqué :
            // valeur à jeter, comme dict_non_str_keys
            Py_CLEAR(current.envDictKey);
            if (!(length == 9 && memcmp(str, "__class__", 9) == 0)) {
                current.envDictKey = DecodeCleCore(str, (Py_ssize_t) length,
                                                   nullptr);
                if (current.envDictKey == nullptr)
                    return false;
            }
        } else if (length == 9 && memcmp(str, "__class__", 9) == 0) {
            current.specialKey = true;
            // enveloppe candidate : "__class__" en PREMIÈRE clé d'un dict
            // vierge (gaté par le décodeur : jamais en mode update)
            if (fastPlainEndObject && current.envState == 0
                && current.envClass == nullptr && current.key == nullptr
                && PyDict_CheckExact(current.object)
                && PyDict_GET_SIZE(current.object) == 0)
                current.envState = 1;
            else if (current.envState != 0 && !EnvFlush(current))
                return false;
        } else if (length == 4 && memcmp(str, "$ref", 4) == 0) {
            current.specialKey = true;
            // une référence peut viser l'INTÉRIEUR d'une enveloppe encore
            // ouverte (doublon mémoïsé dans les args __init__) : toutes les
            // captures de la pile sont versées, la résolution pendant le
            // parse retrouve alors les dicts vivants de la voie classique.
            // L'état 7 est laissé en place : ses paires vivent DÉJÀ dans le
            // dict (clés décodées), que la résolution décode-d'abord sait
            // adresser — et le repli post-passe couvre le reste
            for (HandlerContext& ouverte : stack)
                if (ouverte.envState != 0 && ouverte.envState != 7
                    && !EnvFlush(ouverte))
                    return false;
        } else if (current.envState == 2
                   && ((length == 7 && memcmp(str, "__new__", 7) == 0)
                       || (length == 8 && memcmp(str, "__init__", 8) == 0))) {
            // le slot d'arguments attendu : capture à venir dans Handle
            current.envSlot = (length == 7) ? 1 : 2;
            current.envState = 3;
        } else if (current.envState == 4 && length == 9
                   && memcmp(str, "__items__", 9) == 0) {
            // troisième slot (deque, OrderedDict, Counter, defaultdict...)
            current.envState = 5;
        } else if (current.envState == 2 && current.envClass != nullptr
                   && fastPlainEndObject
                   && PyUnicode_CheckExact(current.envClass)
                   && PyUnicode_CompareWithASCIIString(current.envClass,
                                                       "dict") == 0) {
            // {"__class__": "dict", ...} : bascule en décodage direct — le
            // dict d'enveloppe DEVIENT le dict final (l'intermédiaire à
            // clés encodées puis sa reconversion pesaient ~80 ns par clé).
            // L'étiquette est abandonnée et la clé courante décodée
            Py_CLEAR(current.envClass);
            current.specialKey = false;
            current.envState = 7;
            current.envDictKey = DecodeCleCore(str, (Py_ssize_t) length,
                                               nullptr);
            if (current.envDictKey == nullptr)
                return false;
        } else if (current.envState != 0) {
            // toute autre clé (état, items, dict d'attributs, attribut
            // libre...) : l'enveloppe stricte est démentie
            if (!EnvFlush(current))
                return false;
        }

        // This happens when operating in stream mode and kParseInsituFlag is not set: we
        // must copy the incoming string in the context, and destroy the duplicate when
        // the context gets reused for the next dictionary key

        if (current.key && current.copiedKey) {
            PyMem_Free((void*) current.key);
            current.key = nullptr;
        }

        if (copy) {
            char* copied_str = (char*) PyMem_Malloc(length+1);
            if (copied_str == nullptr)
                return false;
            memcpy(copied_str, str, length+1);
            str = copied_str;
            assert(!current.key);
        }

        current.key = str;
        current.keyLength = length;
        current.copiedKey = copy;

        return true;
    }

    bool StartObject() {
        PyObject* mapping;
        bool key_value_pairs;

        if (decoderStartObject != nullptr && fastStartObject) {
            // court-circuite le start_object Python : dict natif, et .root
            // posé sur le Decoder si ce dict est la racine du document
            if (nDictsLibres > 0) {
                // dict laissé vide par une enveloppe reconnue
                mapping = dictsLibres[--nDictsLibres];
            } else {
                mapping = PyDict_New();
                if (mapping == nullptr)
                    return false;
            }
            key_value_pairs = false;
            if (!rootAttrSet && stack.empty() && decoderObject != nullptr) {
                if (PyObject_SetAttr(decoderObject, root_attr_name, mapping) == -1) {
                    Py_DECREF(mapping);
                    return false;
                }
                rootAttrSet = true;
            }
        } else if (decoderStartObject != nullptr) {
            if (!pendingB64.empty() && !FlushPendingB64())
                return false;
            mapping = PyObject_CallFunctionObjArgs(decoderStartObject, nullptr);
            if (mapping == nullptr)
                return false;
            key_value_pairs = PyList_Check(mapping);
            if (!PyMapping_Check(mapping) && !key_value_pairs) {
                Py_DECREF(mapping);
                PyErr_SetString(PyExc_ValueError,
                                "start_object() must return a mapping or a list instance");
                return false;
            }
        } else {
            mapping = PyDict_New();
            if (mapping == nullptr) {
                return false;
            }
            key_value_pairs = false;
        }

        if (!Handle(mapping)) {
            return false;
        }

        HandlerContext ctx;
        ctx.isObject = true;
        ctx.keyValuePairs = key_value_pairs;
        ctx.object = mapping;
        ctx.key = nullptr;
        ctx.copiedKey = false;
        ctx.specialKey = false;
        ctx.envState = 0;
        ctx.envSlot = 0;
        ctx.envClass = nullptr;
        ctx.envArgs = nullptr;
        ctx.envItems = nullptr;
        ctx.envDictKey = nullptr;
        ctx.refResolu = nullptr;
        ctx.refCheminBrut = nullptr;
        ctx.refCheminBrutLg = 0;
        ctx.attenteBase = attente.size();
        ctx.differe = false;          // un dict remplit sa table au vol
        ctx.envFresh = false;
        ctx.envConstruit = false;
        Py_INCREF(mapping);

        stack.push_back(ctx);

        return true;
    }

    // tête d'enveloppe reconnue LEXICALEMENT par le reader (voir
    // SjTryEnvelopeHead) : un seul événement remplace StartObject +
    // Key("__class__") + String(nom) + Key(slot). Le dict d'enveloppe
    // n'est PAS créé : le contexte est empilé « différé » (object nul),
    // matérialisé par EnvFlush au premier écart de forme — le cas nominal
    // (EnvelopeConstruct à la fermeture) ne crée ni ne détruit rien.
    // Rend 1 (accepté, le reader consomme la tête), 0 (décliné : rien
    // n'est consommé, voie normale), -1 (erreur python posée).
    int SjEnvelopeHead(const char* cls, SizeType clsLength, int slot,
                       const char* slotKey, SizeType slotKeyLength) {
        // mêmes gardes que la capture classique (Key/StartObject) : dict
        // natif vierge certifié, pas de hook de chaîne (le nom de classe y
        // passerait), jamais à la racine (le .root du décodeur et le repli
        // racine de Handle comptent sur le StartObject classique)
        if (!fastPlainEndObject || stack.empty()
            || decoderString != nullptr
            || (decoderStartObject != nullptr && !fastStartObject))
            return 0;
        // numpyB64 : exclu de la capture — son différé (TryDeferDecompress)
        // lit le dict pendant le parse
        if (clsLength == 8 && memcmp(cls, "numpyB64", 8) == 0)
            return 0;
        // nom pur ascii par construction (le motif du reader l'exige)
        PyObject* classe = ValueString(cls, (size_t) clsLength, 1);
        if (classe == nullptr)
            return -1;
        HandlerContext ctx;
        ctx.isObject = true;
        ctx.keyValuePairs = false;
        ctx.object = nullptr;      // dict DIFFÉRÉ
        ctx.key = slotKey;         // le chemin b64 de String lit cette clé
        ctx.keyLength = slotKeyLength;
        ctx.copiedKey = false;
        ctx.specialKey = true;
        ctx.envState = 3;          // classe capturée, args attendus
        ctx.envSlot = (uint8_t) slot;
        ctx.envClass = classe;     // référence consommée
        ctx.envArgs = nullptr;
        ctx.envItems = nullptr;
        ctx.envDictKey = nullptr;
        ctx.refResolu = nullptr;
        ctx.refCheminBrut = nullptr;
        ctx.refCheminBrutLg = 0;
        ctx.attenteBase = attente.size();
        ctx.differe = false;
        ctx.envFresh = false;
        ctx.envConstruit = false;
        stack.push_back(ctx);
        return 1;
    }

    // verse la capture d'enveloppe dans le dict (écart de forme constaté) :
    // la voie classique reprend avec un dict identique à ce qu'elle aurait
    // construit — l'ordre d'insertion (__class__ puis argument) est celui
    // du document, les clés viennent des interned globaux
    bool EnvFlush(HandlerContext& ctx) {
        // enveloppe différée (tête reconnue par le reader) : le dict n'a
        // pas encore d'existence — matérialisé et inséré chez le parent
        // avant d'y verser la capture
        if (ctx.object == nullptr && !EnvDeferMaterialize(ctx))
            return false;
        if (ctx.envState == 7) {
            // état 7 : les paires vivent DÉJÀ dans object (clés décodées,
            // sans étiquette) — exactement le dict final ; rien à verser
            Py_CLEAR(ctx.envDictKey);
            ctx.envState = 0;
            return true;
        }
        if (ctx.envClass != nullptr) {
            if (PyDict_SetItem(ctx.object, class_key_name, ctx.envClass) < 0)
                return false;
            Py_CLEAR(ctx.envClass);
        }
        if (ctx.envArgs != nullptr) {
            if (PyDict_SetItem(ctx.object,
                               ctx.envSlot == 1 ? new_key_name
                                                : init_key_name,
                               ctx.envArgs) < 0)
                return false;
            Py_CLEAR(ctx.envArgs);
        }
        if (ctx.envItems != nullptr) {
            if (PyDict_SetItem(ctx.object, items_key_name,
                               ctx.envItems) < 0)
                return false;
            Py_CLEAR(ctx.envItems);
        }
        ctx.envState = 0;
        ctx.envSlot = 0;
        return true;
    }

    // matérialise le dict d'une enveloppe DIFFÉRÉE (écart de forme) et
    // l'insère chez le parent, à l'identique de ce que le Handle du
    // StartObject classique aurait fait à l'ouverture — le parent n'a reçu
    // aucun événement depuis, sa clé et sa tranche d'attente sont intactes
    bool EnvDeferMaterialize(HandlerContext& ctx) {
        PyObject* mapping;
        if (nDictsLibres > 0) {
            mapping = dictsLibres[--nDictsLibres];
        } else {
            mapping = PyDict_New();
            if (mapping == nullptr)
                return false;
        }
        ctx.object = mapping;             // la référence du contexte
        size_t idx = (size_t) (&ctx - stack.data());
        HandlerContext& parent = stack[idx - 1];
        Py_INCREF(mapping);               // la référence que consomme l'insertion
        if (parent.differe && idx + 1 < stack.size()) {
            // vidage $ref : des tranches plus profondes vivent au-dessus de
            // celle du parent — insertion à la fin de SA tranche (qui est
            // restée ctx.attenteBase), les bases plus profondes décalées
            attente.insert(attente.begin() + ctx.attenteBase, mapping);
            for (size_t j = idx + 1; j < stack.size(); j++)
                stack[j].attenteBase++;
            return true;
        }
        return HandleInto(parent, mapping);
    }

    // deque / Counter / OrderedDict / defaultdict : construction directe —
    // types résolus UNE fois (import collections au premier besoin)
    PyObject* CollectionsConstruct(PyObject* cls_value, PyObject* ctor_args,
                                   PyObject* items) {
        static PyObject* type_deque = nullptr;
        static PyObject* type_counter = nullptr;
        static PyObject* type_ordered = nullptr;
        static PyObject* type_defaultdict = nullptr;
        if (type_deque == nullptr) {
            PyObject* module = PyImport_ImportModule("collections");
            if (module == nullptr) {
                PyErr_Clear();
                return nullptr;
            }
            type_deque = PyObject_GetAttrString(module, "deque");
            type_counter = PyObject_GetAttrString(module, "Counter");
            type_ordered = PyObject_GetAttrString(module, "OrderedDict");
            type_defaultdict = PyObject_GetAttrString(module, "defaultdict");
            Py_DECREF(module);
            if (type_deque == nullptr || type_counter == nullptr
                || type_ordered == nullptr || type_defaultdict == nullptr) {
                PyErr_Clear();
                Py_CLEAR(type_deque);
                return nullptr;
            }
        }
        PyObject* classe;
        if (PyUnicode_CompareWithASCIIString(cls_value,
                                             "collections.deque") == 0)
            classe = type_deque;
        else if (PyUnicode_CompareWithASCIIString(
                     cls_value, "collections.Counter") == 0)
            classe = type_counter;
        else if (PyUnicode_CompareWithASCIIString(
                     cls_value, "collections.OrderedDict") == 0)
            classe = type_ordered;
        else if (PyUnicode_CompareWithASCIIString(
                     cls_value, "collections.defaultdict") == 0)
            classe = type_defaultdict;
        else
            return nullptr;   // classe à __items__ inconnue : voie classique

        PyObject* inst = nullptr;
        if (PyList_CheckExact(ctor_args)) {
            PyObject* args_tuple = PyList_AsTuple(ctor_args);
            if (args_tuple != nullptr) {
                inst = PyObject_CallObject(classe, args_tuple);
                Py_DECREF(args_tuple);
            }
        } else if (PyDict_CheckExact(ctor_args)) {
            if (classe == type_counter || classe == type_ordered) {
                // Counter/OrderedDict sont dans remove_add_braces : la voie
                // python remet l init sous tuple -> cls(LE dict), POSITIONNEL
                // (c est ce qui permet les Counter à clés non-str)
                inst = PyObject_CallFunctionObjArgs(classe, ctor_args,
                                                    nullptr);
            } else {
                // cls(**init) : exige des clés str (sinon voie classique, qui
                // reproduira l erreur python exacte le cas échéant)
                Py_ssize_t pos = 0;
                PyObject* cle;
                PyObject* valeur;
                bool cles_str = true;
                while (PyDict_Next(ctor_args, &pos, &cle, &valeur))
                    if (!PyUnicode_CheckExact(cle)) {
                        cles_str = false;
                        break;
                    }
                if (!cles_str)
                    return nullptr;
                PyObject* vide = PyTuple_New(0);
                if (vide != nullptr) {
                    inst = PyObject_Call(classe, vide, ctor_args);
                    Py_DECREF(vide);
                }
            }
        } else {
            // scalaire (accolades retirées) : cls(valeur) — la forme
            // defaultdict(type)
            inst = PyObject_CallFunctionObjArgs(classe, ctor_args, nullptr);
        }
        if (inst == nullptr) {
            PyErr_Clear();
            return nullptr;
        }
        if (items == nullptr)
            return inst;   // forme sans __items__ (Counter à init dict...)
        // __items__ : update(items), à défaut extend(items) — l ordre
        // d essai d instance(). La classe est CONNUE : deque part
        // directement sur extend (l essai update levait une AttributeError
        // à CHAQUE deque, ~0,5 µs de machinerie d exception), les
        // dict-like sur update ; l autre méthode reste en filet
        static PyObject* update_name_str = nullptr;
        static PyObject* extend_name_str = nullptr;
        if (update_name_str == nullptr) {
            update_name_str = PyUnicode_InternFromString("update");
            extend_name_str = PyUnicode_InternFromString("extend");
            if (update_name_str == nullptr || extend_name_str == nullptr) {
                Py_DECREF(inst);
                return nullptr;
            }
        }
        PyObject* premiere = classe == type_deque ? extend_name_str
                                                  : update_name_str;
        PyObject* r = PyObject_CallMethodObjArgs(inst, premiere, items,
                                                 nullptr);
        if (r == nullptr) {
            PyErr_Clear();
            r = PyObject_CallMethodObjArgs(
                inst,
                premiere == update_name_str ? extend_name_str
                                            : update_name_str,
                items, nullptr);
        }
        if (r == nullptr) {
            PyErr_Clear();
            Py_DECREF(inst);
            return nullptr;
        }
        Py_DECREF(r);
        return inst;
    }


    // décode UNE clé de dict à clés non-str, miroir exact de _decode_cle
    // python : 'quotée' -> str, b'...' -> bytes (jeu ascii imprimable),
    // b64'...' -> bytes, true/false, nombres (int python arbitraire puis
    // float, formes canoniques de l encodeur) ; les formes exotiques
    // (tuples, frozensets, imbrications) passent au repli python
    // _decode_cle_exotique. Rend une NOUVELLE référence, nullptr = erreur.
    PyObject* DecodeCle(PyObject* key) {
        Py_ssize_t lg;
        const char* u8 = PyUnicode_AsUTF8AndSize(key, &lg);
        if (u8 == nullptr)
            return nullptr;
        return DecodeCleCore(u8, lg, key);
    }

    // coeur à double entrée : depuis une clé python (key_obj, rendue telle
    // quelle pour une clé ordinaire) ou depuis le tampon BRUT du parse
    // (key_obj nul : la str n'est matérialisée que pour les clés ordinaires
    // et exotiques — les clés simples n'allouent QUE leur valeur décodée)
    PyObject* DecodeCleCore(const char* u8, Py_ssize_t lg,
                            PyObject* key_obj) {
        if (lg > 0) {
            char premier = u8[0];
            if (premier == '\'') {
                if (lg >= 2 && u8[lg - 1] == '\'')
                    return PyUnicode_FromStringAndSize(u8 + 1, lg - 2);
            } else if (premier == 'b') {
                if (lg >= 3 && u8[lg - 1] == '\'' && u8[1] == '\'') {
                    // b'...' : mêmes octets que le codec ascii_printables —
                    // jeu {tab, LF, CR} ∪ [0x20..0x7E], sinon repli python
                    bool imprimable = true;
                    for (Py_ssize_t i = 2; i < lg - 1; i++) {
                        unsigned char c = (unsigned char) u8[i];
                        if (!((c >= 0x20 && c <= 0x7E)
                              || c == '\t' || c == '\n' || c == '\r')) {
                            imprimable = false;
                            break;
                        }
                    }
                    if (imprimable)
                        return PyBytes_FromStringAndSize(u8 + 2, lg - 3);
                } else if (lg >= 5 && u8[lg - 1] == '\''
                           && memcmp(u8, "b64'", 4) == 0) {
                    size_t groups, pad, out_length;
                    if (sj_b64_layout(u8 + 4, (size_t) (lg - 5), &groups,
                                      &pad, &out_length,
                                      serializejson_b64_decode_table())) {
                        PyObject* octets = PyBytes_FromStringAndSize(
                            nullptr, (Py_ssize_t) out_length);
                        if (octets == nullptr)
                            return nullptr;
                        if (sj_b64_decode_into(
                                u8 + 4, (size_t) (lg - 5),
                                (unsigned char*) PyBytes_AS_STRING(octets),
                                serializejson_b64_decode_table()))
                            return octets;
                        Py_DECREF(octets);
                    }
                }
            } else if (lg == 4 && memcmp(u8, "true", 4) == 0) {
                Py_RETURN_TRUE;
            } else if (lg == 5 && memcmp(u8, "false", 5) == 0) {
                Py_RETURN_FALSE;
            } else if ((premier >= '0' && premier <= '9') || premier == '-'
                       || premier == 'N' || premier == 'I') {
                // PyLong_FromString exige un tampon TERMINÉ : depuis le
                // tampon brut du parse (key_obj nul), copie bornée d'abord
                PyObject* entier = nullptr;
                if (key_obj != nullptr) {
                    entier = PyLong_FromString(u8, nullptr, 10);
                } else if (lg < 64) {
                    char borne[64];
                    memcpy(borne, u8, (size_t) lg);
                    borne[lg] = '\0';
                    entier = PyLong_FromString(borne, nullptr, 10);
                }
                if (entier != nullptr)
                    return entier;
                PyErr_Clear();
                PyObject* texte_nombre = key_obj != nullptr
                    ? Py_NewRef(key_obj)
                    : PyUnicode_FromStringAndSize(u8, lg);
                if (texte_nombre != nullptr) {
                    if (lg >= 64) {
                        // entier géant : par l'objet unicode, longueur sûre
                        entier = PyLong_FromUnicodeObject(texte_nombre, 10);
                        if (entier != nullptr) {
                            Py_DECREF(texte_nombre);
                            return entier;
                        }
                        PyErr_Clear();
                    }
                    PyObject* flottant = PyFloat_FromString(texte_nombre);
                    Py_DECREF(texte_nombre);
                    if (flottant != nullptr)
                        return flottant;
                }
                PyErr_Clear();
            }
            if (lg == 4 && memcmp(u8, "null", 4) == 0)
                Py_RETURN_NONE;   // le parse python rend None pour « null »
            // seules les formes encore parseables partent au repli python
            // (tuples « [...] », frozensets/enveloppes « {...} », chaînes
            // json « \"...\" », et les marqueurs b/quote mal formés) : le
            // repli à CHAQUE clé ordinaire était précisément le coût python
            if (premier == '[' || premier == '{' || premier == '"'
                || premier == '\'' || premier == 'b') {
                if (decodeCleFn != nullptr) {
                    // ~4 µs par décodage python : mémoïsé par clé le temps
                    // du parse (répliques d'un même document)
                    PyObject* key = key_obj != nullptr
                        ? Py_NewRef(key_obj)
                        : PyUnicode_FromStringAndSize(u8, lg);
                    if (key == nullptr)
                        return nullptr;
                    if (cleExotiqueCache != nullptr) {
                        PyObject* hit = PyDict_GetItemWithError(
                            cleExotiqueCache, key);
                        if (hit != nullptr) {
                            Py_INCREF(hit);
                            Py_DECREF(key);
                            return hit;
                        }
                        if (PyErr_Occurred())
                            PyErr_Clear();
                    }
                    PyObject* decodee = PyObject_CallFunctionObjArgs(
                        decodeCleFn, key, nullptr);
                    if (decodee != nullptr) {
                        if (cleExotiqueCache == nullptr)
                            cleExotiqueCache = PyDict_New();
                        if (cleExotiqueCache != nullptr
                            && PyDict_SetItem(cleExotiqueCache, key,
                                              decodee) < 0)
                            PyErr_Clear();
                    }
                    Py_DECREF(key);
                    return decodee;
                }
            }
        }
        // clé str ordinaire : telle quelle (aucun marqueur ne la réclame)
        if (key_obj != nullptr)
            return Py_NewRef(key_obj);
        return PyUnicode_FromStringAndSize(u8, lg);
    }

    // {"__class__": "dict", clés encodées...} -> dict reconstruit en C,
    // miroir de dict_non_str_keys (l ordre d insertion est celui du
    // document, comme en python)
    PyObject* DictNonStrConstruct(PyObject* mapping) {
        PyObject* resultat = PyDict_New();
        if (resultat == nullptr)
            return nullptr;
        Py_ssize_t pos = 0;
        PyObject* cle;
        PyObject* valeur;
        while (PyDict_Next(mapping, &pos, &cle, &valeur)) {
            if (cle == class_key_name
                || (PyUnicode_CheckExact(cle)
                    && PyUnicode_CompareWithASCIIString(cle,
                                                        "__class__") == 0))
                continue;
            if (!PyUnicode_CheckExact(cle)) {
                Py_DECREF(resultat);
                return nullptr;   // clé déjà décodée ?? voie python
            }
            PyObject* decodee = DecodeCle(cle);
            if (decodee == nullptr) {
                Py_DECREF(resultat);
                return nullptr;
            }
            int rc = PyDict_SetItem(resultat, decodee, valeur);
            Py_DECREF(decodee);
            if (rc < 0) {
                Py_DECREF(resultat);
                return nullptr;
            }
        }
        return resultat;
    }

    // instancie les enveloppes de base {"__class__": nom, "__new__"/"__init__"
    // : args} — mêmes sémantiques que les constructeurs python (tuple(liste),
    // set(liste), date(bytes de reduce), bytes pré-décodés ou ascii,
    // complex/range/slice, valeurs de type via le cache partagé). Rend une
    // NOUVELLE référence, ou nullptr = déclin (au moindre doute sur la forme,
    // voie classique inchangée ; toute erreur interne est effacée, la voie
    // python la reproduira proprement si elle est réelle). Partagée entre la
    // reconnaissance d'enveloppe AU PARSE et la chaîne de fin d'objet.
    PyObject* EnvelopeConstruct(PyObject* cls_value, PyObject* ctor_args,
                                bool from_new, PyObject* items = nullptr) {
        (void) from_new;
        if (!PyUnicode_CheckExact(cls_value))
            return nullptr;   // objet déjà construit (réhydratation)
        PyObject* replacement = nullptr;
        // aiguillage par LONGUEUR du nom : une seule lecture utf8 puis un
        // memcmp par candidat de même taille — la chaîne de comparaisons
        // PyUnicode_CompareWithASCIIString pesait sur CHAQUE fin d'enveloppe
        Py_ssize_t cls_length;
        const char* cls = PyUnicode_AsUTF8AndSize(cls_value, &cls_length);
        if (cls == nullptr) {
            PyErr_Clear();
            return nullptr;
        }
        // les enveloppes à __items__ (capturées au parse seulement) : les
        // quatre collections, sémantique calquée sur instance() — init
        // liste -> cls(*init), init dict -> positionnel (Counter/Ordered)
        // ou cls(**init), init scalaire -> cls(init) ; puis update/extend
        if (items != nullptr
            || (cls_length >= 12 && memcmp(cls, "collections.", 12) == 0))
            return CollectionsConstruct(cls_value, ctor_args, items);
        switch (cls_length) {
        case 3:   // set
            if (memcmp(cls, "set", 3) == 0 && PyList_CheckExact(ctor_args))
                replacement = PySet_New(ctor_args);
            break;
        case 4:   // type : servi depuis le cache partagé seulement (un HIT
            // rend la classe déjà résolue par python ; un miss reste en
            // voie python, qui importe et remplit le cache)
            if (memcmp(cls, "type", 4) == 0 && typeValuesCache != nullptr
                && PyUnicode_CheckExact(ctor_args)) {
                if (PyUnicode_CompareWithASCIIString(ctor_args,
                                                     "NoneType") == 0) {
                    // cas spécial d'instance() : jamais en cache côté python
                    replacement = (PyObject*) Py_TYPE(Py_None);
                    Py_INCREF(replacement);
                } else {
                    PyObject* classe = PyDict_GetItem(typeValuesCache,
                                                      ctor_args);
                    if (classe != nullptr) {
                        Py_INCREF(classe);
                        replacement = classe;
                    }
                }
            }
            break;
        case 5:   // tuple, bytes, range, slice
            if (memcmp(cls, "tuple", 5) == 0) {
                if (PyList_CheckExact(ctor_args))
                    replacement = PyList_AsTuple(ctor_args);
            } else if (memcmp(cls, "bytes", 5) == 0) {
                // pré-décodés : [payload, "b64"] où le payload a déjà été
                // décodé par l'interception base64 -> le payload EST l'objet
                // final ; ou forme chaîne ascii (bytes(s, "ascii"))
                if (PyList_CheckExact(ctor_args)
                    && PyList_GET_SIZE(ctor_args) == 2) {
                    PyObject* payload = PyList_GET_ITEM(ctor_args, 0);
                    PyObject* label = PyList_GET_ITEM(ctor_args, 1);
                    if (PyBytes_CheckExact(payload)
                        && PyUnicode_CheckExact(label)
                        && PyUnicode_CompareWithASCIIString(label,
                                                            "b64") == 0) {
                        Py_INCREF(payload);
                        replacement = payload;
                    }
                } else if (PyUnicode_CheckExact(ctor_args)
                           && PyUnicode_IS_ASCII(ctor_args)) {
                    Py_ssize_t lg;
                    const char* u8 = PyUnicode_AsUTF8AndSize(ctor_args, &lg);
                    if (u8 != nullptr)
                        replacement = PyBytes_FromStringAndSize(u8, lg);
                }
            } else if (memcmp(cls, "range", 5) == 0) {
                if (PyList_CheckExact(ctor_args)
                    && PyList_GET_SIZE(ctor_args) == 3)
                    replacement = PyObject_CallFunctionObjArgs(
                        (PyObject*) &PyRange_Type,
                        PyList_GET_ITEM(ctor_args, 0),
                        PyList_GET_ITEM(ctor_args, 1),
                        PyList_GET_ITEM(ctor_args, 2), nullptr);
            } else if (memcmp(cls, "slice", 5) == 0) {
                if (PyList_CheckExact(ctor_args)
                    && PyList_GET_SIZE(ctor_args) == 3)
                    replacement = PySlice_New(PyList_GET_ITEM(ctor_args, 0),
                                              PyList_GET_ITEM(ctor_args, 1),
                                              PyList_GET_ITEM(ctor_args, 2));
            }
            break;
        case 7:   // complex
            if (memcmp(cls, "complex", 7) == 0
                && PyList_CheckExact(ctor_args)
                && PyList_GET_SIZE(ctor_args) == 2) {
                double re = PyFloat_AsDouble(PyList_GET_ITEM(ctor_args, 0));
                double im = PyFloat_AsDouble(PyList_GET_ITEM(ctor_args, 1));
                if (!PyErr_Occurred())
                    replacement = PyComplex_FromDoubles(re, im);
            }
            break;
        case 9:   // bytearray, frozenset
            if (memcmp(cls, "bytearray", 9) == 0) {
                if (PyList_CheckExact(ctor_args)
                    && PyList_GET_SIZE(ctor_args) == 2) {
                    PyObject* payload = PyList_GET_ITEM(ctor_args, 0);
                    PyObject* label = PyList_GET_ITEM(ctor_args, 1);
                    if (PyByteArray_CheckExact(payload)
                        && PyUnicode_CheckExact(label)
                        && PyUnicode_CompareWithASCIIString(label,
                                                            "b64") == 0) {
                        Py_INCREF(payload);
                        replacement = payload;
                    }
                }
            } else if (memcmp(cls, "frozenset", 9) == 0) {
                if (PyList_CheckExact(ctor_args))
                    replacement = PyFrozenSet_New(ctor_args);
            }
            break;
        case 13:  // datetime.date, datetime.time (formes reduce 4/6 octets ;
            // ces bâtisseurs LISENT le contenu : file différée vidée d'abord
            // — défense en profondeur, les payloads < 64 octets ne sont plus
            // différés)
            if (memcmp(cls, "datetime.date", 13) == 0) {
                if (PyBytes_CheckExact(ctor_args)
                    && PyBytes_GET_SIZE(ctor_args) == 4
                    && (pendingB64.empty() || FlushPendingB64())) {
                    const unsigned char* raw4 =
                        (const unsigned char*) PyBytes_AS_STRING(ctor_args);
                    replacement = PyDate_FromDate(
                        (raw4[0] << 8) | raw4[1], raw4[2], raw4[3]);
                }
            } else if (memcmp(cls, "datetime.time", 13) == 0) {
                if (PyBytes_CheckExact(ctor_args)
                    && PyBytes_GET_SIZE(ctor_args) == 6
                    && (pendingB64.empty() || FlushPendingB64())) {
                    replacement = PyObject_CallFunctionObjArgs(
                        (PyObject*) PyDateTimeAPI->TimeType, ctor_args,
                        nullptr);
                }
            }
            break;
        case 15:  // decimal.Decimal : "<str(d)>" — le constructeur C parse
            if (memcmp(cls, "decimal.Decimal", 15) == 0
                && PyUnicode_CheckExact(ctor_args))
                replacement = PyObject_CallFunctionObjArgs(
                    decimal_type, ctor_args, nullptr);
            break;
        case 16:  // time.struct_time : [tuple de 9 entiers, dict des deux
            // champs hors séquence] — le constructeur accepte (seq, dict)
            if (memcmp(cls, "time.struct_time", 16) == 0
                && PyList_CheckExact(ctor_args)
                && PyList_GET_SIZE(ctor_args) == 2
                && PyTuple_CheckExact(PyList_GET_ITEM(ctor_args, 0))
                && PyDict_CheckExact(PyList_GET_ITEM(ctor_args, 1)))
                replacement = PyObject_CallFunctionObjArgs(
                    struct_time_type, PyList_GET_ITEM(ctor_args, 0),
                    PyList_GET_ITEM(ctor_args, 1), nullptr);
            break;
        case 17:  // datetime.datetime : texte RFC 9557 sans [zone] (celui de
            // l'encodeur depuis le 24/09) par fromisoformat — avec [zone],
            // la voie générique appelle le constructeur du greffon python ;
            // formes reduce 10 octets (06/08 → 24/09) et 7 entiers (avant)
            // relues pour les fichiers existants
            if (memcmp(cls, "datetime.datetime", 17) == 0) {
                if (PyUnicode_CheckExact(ctor_args)) {
                    Py_ssize_t len = PyUnicode_GET_LENGTH(ctor_args);
                    if (len > 0 && PyUnicode_READ_CHAR(ctor_args, len - 1) != ']')
                        replacement = PyObject_CallMethod(
                            (PyObject*) PyDateTimeAPI->DateTimeType,
                            "fromisoformat", "O", ctor_args);
                } else if (PyBytes_CheckExact(ctor_args)
                    && PyBytes_GET_SIZE(ctor_args) == 10
                    && (pendingB64.empty() || FlushPendingB64())) {
                    replacement = PyObject_CallFunctionObjArgs(
                        (PyObject*) PyDateTimeAPI->DateTimeType, ctor_args,
                        nullptr);
                } else if (PyList_CheckExact(ctor_args)
                           && PyList_GET_SIZE(ctor_args) == 7) {
                    PyObject* args_tuple = PyList_AsTuple(ctor_args);
                    if (args_tuple != nullptr) {
                        replacement = PyObject_CallObject(
                            (PyObject*) PyDateTimeAPI->DateTimeType,
                            args_tuple);
                        Py_DECREF(args_tuple);
                    }
                }
            }
            break;
        case 18:  // datetime.timedelta : [jours, secondes, microsecondes],
            // les arguments reduce natifs (déjà normalisés à l'écriture)
            if (memcmp(cls, "datetime.timedelta", 18) == 0
                && PyList_CheckExact(ctor_args)
                && PyList_GET_SIZE(ctor_args) == 3) {
                long long v[3];
                bool td_ok = true;
                for (int i = 0; i < 3; i++) {
                    PyObject* e = PyList_GET_ITEM(ctor_args, i);
                    int td_ovf = 0;
                    v[i] = PyLong_CheckExact(e)
                        ? PyLong_AsLongLongAndOverflow(e, &td_ovf) : 0;
                    if (!PyLong_CheckExact(e) || td_ovf != 0
                        || v[i] < INT_MIN || v[i] > INT_MAX) {
                        td_ok = false;   // exotique : voie python
                        break;
                    }
                }
                if (td_ok)
                    replacement = PyDateTimeAPI->Delta_FromDelta(
                        (int) v[0], (int) v[1], (int) v[2], 1,
                        PyDateTimeAPI->DeltaType);
            }
            break;
        }
        if (replacement == nullptr && PyErr_Occurred())
            PyErr_Clear();   // voie classique en cas d'échec
        return replacement;
    }

    bool EndObject(SizeType member_count) {
        HandlerContext& ctx_ref = stack.back();

        // ----- enveloppe capturée au parse : instanciation directe, sans
        // dict intermédiaire rempli. Si la table décline (classe ou forme
        // inconnue), la capture est versée dans le dict et la voie classique
        // reprend ci-dessous, à l'identique.
        if (ctx_ref.envState == 7) {
            // décodage direct : object contient déjà les paires décodées et
            // vit déjà dans son parent — c'est un dict ordinaire désormais
            Py_CLEAR(ctx_ref.envDictKey);
            ctx_ref.envState = 0;
        }
        if (ctx_ref.envState == 4 || ctx_ref.envState == 6) {
            PyObject* direct = EnvelopeConstruct(ctx_ref.envClass,
                                                 ctx_ref.envArgs,
                                                 ctx_ref.envSlot == 1,
                                                 ctx_ref.envItems);
            // réhydratation : enveloppe sans état d'une classe non native
            if (direct == nullptr && rehydrateOn && ctx_ref.envState == 4
                && !PyErr_Occurred())
                direct = SjConstruit(stack.size() - 1,
                                     ctx_ref.object != nullptr,
                                     ctx_ref.envClass, ctx_ref.envArgs,
                                     ctx_ref.envSlot);
            if (direct != nullptr) {
                if (ctx_ref.copiedKey)
                    PyMem_Free((void*) ctx_ref.key);
                PyObject* vide = ctx_ref.object;
                Py_CLEAR(ctx_ref.envClass);
                Py_CLEAR(ctx_ref.envArgs);
                Py_CLEAR(ctx_ref.envItems);
                Py_CLEAR(ctx_ref.envDictKey);
                stack.pop_back();
                if (vide == nullptr)
                    // enveloppe différée : le dict n'a jamais existé ni été
                    // inséré — insertion simple chez le parent
                    return Handle(direct);
                bool ok = ReplaceInParent(direct);
                // ReplaceInParent a relâché la réf du parent : s'il ne reste
                // que la nôtre, le dict (resté vide) est recyclé pour la
                // prochaine enveloppe au lieu d'être détruit
                if (nDictsLibres < 3 && Py_REFCNT(vide) == 1
                    && PyDict_GET_SIZE(vide) == 0)
                    dictsLibres[nDictsLibres++] = vide;
                else
                    Py_DECREF(vide);
                return ok;
            }
            if (PyErr_Occurred())
                return false;
        }
        if (ctx_ref.envState != 0 && !EnvFlush(ctx_ref))
            return false;

        const HandlerContext& ctx = stack.back();

        if (ctx.copiedKey)
            PyMem_Free((void*) ctx.key);

        PyObject* mapping = ctx.object;
        bool plainDict = !ctx.specialKey && !ctx.keyValuePairs;
        bool envFresh = ctx.envFresh;
        PyObject* refResolu = ctx.refResolu;
        stack.pop_back();

        // ----- $ref résolu au vol (raccourci de String) : le dict est resté
        // vide, il est jeté et la cible prend sa place chez le parent
        if (refResolu != nullptr) {
            Py_DECREF(mapping);
            return ReplaceInParent(refResolu);
        }

        if (!pendingB64.empty() && fastPlainEndObject)
            TryDeferDecompress(mapping);

        // dict ordinaire (aucune clé __class__/$ref) et décodeur ayant
        // certifié qu'aucune transformation Python ne s'applique : le dict
        // est déjà inséré dans son parent (Handle au StartObject), rien à faire
        if (plainDict && fastPlainEndObject && objectHook == nullptr) {
            Py_DECREF(mapping);
            return true;
        }

        PyObject* replacement = nullptr;

        // ----- réhydratation : enveloppe classique sans état {__class__
        // (, __init__|__new__)} d'une classe non native, fermée avant toute
        // clé d'état — construite ou adoptée ici
        if (rehydrateOn && PyDict_CheckExact(mapping)
            && PyDict_GET_SIZE(mapping) <= 2) {
            PyObject* classe = PyDict_GetItem(mapping, class_key_name);
            if (classe != nullptr && PyUnicode_CheckExact(classe)) {
                PyObject* args = nullptr;
                int slot = 0;
                if (PyDict_GET_SIZE(mapping) == 2) {
                    args = PyDict_GetItem(mapping, init_key_name);
                    slot = 2;
                    if (args == nullptr) {
                        args = PyDict_GetItem(mapping, new_key_name);
                        slot = 1;
                    }
                }
                if (PyDict_GET_SIZE(mapping) == 1 || args != nullptr) {
                    replacement = SjConstruit(stack.size(), true, classe,
                                              args, slot);
                    if (replacement == nullptr && PyErr_Occurred()) {
                        Py_DECREF(mapping);
                        return false;
                    }
                    if (replacement != nullptr)
                        Py_DECREF(mapping);
                }
            }
        }

        // ----- chemin rapide de décodage par classe : {"__class__": nom,
        // attributs...} sans clé spéciale -> instanciation directe en C++
        if (replacement == nullptr && decodeClassPlanFn != nullptr
            && PyDict_CheckExact(mapping)) {
            PyObject* class_value = PyDict_GetItem(mapping, class_key_name);
            // __init__ LISTE exacte : cls(*args) pour tous les plans ;
            // __init__ SCALAIRE (accolades retirées) : réservé au mode
            // « constructeur seul » ci-dessous — cls(scalaire), la forme
            // de instance() ; __init__ dict (kwargs) : voie Python
            PyObject* init_list = nullptr;
            bool init_is_list = false;
            if (class_value != nullptr) {
                init_list = PyDict_GetItem(mapping, init_key_name);
                init_is_list = init_list != nullptr
                    && PyList_CheckExact(init_list);
            }
            if (class_value != nullptr && !PyUnicode_CheckExact(class_value)
                && rehydrateOn
                && PyDict_GetItem(mapping, state_key_name) == nullptr
                && PyDict_GetItem(mapping, items_key_name) == nullptr
                && PyDict_GetItem(mapping, dict_dunder_name) == nullptr) {
                // réhydratation : l'objet est déjà construit (rangé dans
                // __class__ à sa première clé d'état) ; son état s'applique
                // en C si son type a un plan __dict__ ou __slots__ — avec
                // setters/properties/__setstate__ (classe, 2), voie python
                auto par_type = plansParType.find(Py_TYPE(class_value));
                if (par_type != plansParType.end()
                    && !(PyTuple_Check(par_type->second)
                         && PyLong_CheckExact(
                                PyTuple_GET_ITEM(par_type->second, 1)))) {
                    PyObject* inst = class_value;
                    Py_INCREF(inst);
                    for (PyObject* cle : {class_key_name, init_key_name,
                                          new_key_name})
                        if (PyDict_GetItem(mapping, cle) != nullptr
                            && PyDict_DelItem(mapping, cle) == -1) {
                            Py_DECREF(inst);
                            Py_DECREF(mapping);
                            return false;
                        }
                    bool by_setattr = !PyType_Check(par_type->second);
                    // instance nue (object.__new__, __dict__ vide) à plan
                    // __dict__ : le dict d'état devient son __dict__ tel
                    // quel, comme sur la voie classique — sinon fusion
                    if (envFresh && !by_setattr) {
                        if (PyObject_SetAttr(inst, dict_dunder_name,
                                             mapping) == -1) {
                            Py_DECREF(inst);
                            Py_DECREF(mapping);
                            return false;
                        }
                    } else if (!SjAppliqueEtat(inst, mapping, by_setattr)) {
                        Py_DECREF(inst);
                        Py_DECREF(mapping);
                        return false;
                    }
                    Py_DECREF(mapping);
                    replacement = inst;
                }
            } else if (class_value != nullptr
                && PyUnicode_CheckExact(class_value)
                && PyDict_GetItem(mapping, new_key_name) == nullptr
                && PyDict_GetItem(mapping, state_key_name) == nullptr
                && PyDict_GetItem(mapping, items_key_name) == nullptr
                && PyDict_GetItem(mapping, dict_dunder_name) == nullptr) {
                PyObject* plan = SjPlan(class_value);
                if (plan == nullptr) {
                    Py_DECREF(mapping);
                    return false;
                }
                // mode « constructeur seul » (classe, 2) : classes C
                // (Decimal, datetime, deque...) appelées directement —
                // uniquement pour l'enveloppe stricte {__class__, __init__} ;
                // toute autre forme (attributs, __state__, kwargs dict)
                // reste en voie python
                bool ctor_only = plan != Py_None && PyTuple_Check(plan)
                    && PyLong_CheckExact(PyTuple_GET_ITEM(plan, 1));
                if (ctor_only
                    && (PyDict_GET_SIZE(mapping) != 2
                        || init_list == nullptr
                        || PyDict_CheckExact(init_list))) {
                    // enveloppe inattendue : voie python
                } else if (plan != Py_None
                           && (init_list == nullptr || init_is_list
                               || ctor_only)) {
                    if (PyDict_DelItem(mapping, class_key_name) == -1) {
                        Py_DECREF(mapping);
                        return false;
                    }
                    PyTypeObject* cls;
                    bool by_setattr;
                    if (PyType_Check(plan)) {
                        cls = (PyTypeObject*) plan;
                        by_setattr = false;
                    } else {
                        cls = (PyTypeObject*) PyTuple_GET_ITEM(plan, 0);
                        by_setattr = !ctor_only;
                    }
                    PyObject* inst;
                    if (init_list != nullptr) {
                        // recette constructeur : cls(*args) — la même forme
                        // que instance() (inst = class_(*__init__) pour une
                        // liste, class_(__init__) pour un scalaire aux
                        // accolades retirées)
                        Py_INCREF(init_list);
                        if (PyDict_DelItem(mapping, init_key_name) == -1) {
                            Py_DECREF(init_list);
                            Py_DECREF(mapping);
                            return false;
                        }
                        PyObject* ctor_args = init_is_list
                            ? PyList_AsTuple(init_list)
                            : PyTuple_Pack(1, init_list);
                        Py_DECREF(init_list);
                        if (ctor_args == nullptr) {
                            Py_DECREF(mapping);
                            return false;
                        }
                        inst = PyObject_Call((PyObject*) cls, ctor_args,
                                             nullptr);
                        Py_DECREF(ctor_args);
                    } else {
                        inst = cls->tp_new(cls, empty_args_tuple, nullptr);
                    }
                    if (inst == nullptr) {
                        Py_DECREF(mapping);
                        return false;
                    }
                    if (by_setattr || init_list != nullptr) {
                        // classe à __slots__ : un setattr par attribut, dans
                        // l'ordre du JSON (celui du setstate Python) ; après
                        // un __init__ qui a pu remplir le __dict__ : FUSION
                        // des attributs restants, jamais de remplacement
                        if (PyDict_GET_SIZE(mapping) != 0
                            && !SjAppliqueEtat(inst, mapping, by_setattr)) {
                            Py_DECREF(inst);
                            Py_DECREF(mapping);
                            return false;
                        }
                    // assignation directe du dict d'attributs (objet neuf au
                    // dict vide : équivalent du update() du chemin Python)
                    } else if (PyObject_SetAttr(inst, dict_dunder_name,
                                                mapping) == -1) {
                        Py_DECREF(inst);
                        Py_DECREF(mapping);
                        return false;
                    }
                    Py_DECREF(mapping);
                    replacement = inst;
                }
            }
        }

        // ----- enveloppes de base {"__class__": nom, "__new__"/"__init__":
        // args} : instanciation directe par la table partagée avec la
        // reconnaissance au parse (EnvelopeConstruct). Gardé par
        // fastPlainEndObject : jamais en mode update.
        if (replacement == nullptr && fastPlainEndObject
            && PyDict_CheckExact(mapping) && PyDict_GET_SIZE(mapping) == 2) {
            PyObject* cls_value = PyDict_GetItem(mapping, class_key_name);
            if (cls_value != nullptr && PyUnicode_CheckExact(cls_value)) {
                bool from_new = true;
                PyObject* ctor_args = PyDict_GetItem(mapping, new_key_name);
                if (ctor_args == nullptr) {
                    ctor_args = PyDict_GetItem(mapping, init_key_name);
                    from_new = false;
                }
                if (ctor_args != nullptr) {
                    replacement = EnvelopeConstruct(cls_value, ctor_args,
                                                    from_new);
                    if (replacement != nullptr)
                        Py_DECREF(mapping);
                }
            }
        }

        // ----- enveloppes de collections à TROIS clés {__class__,
        // __init__/__new__, __items__} dont la capture au parse a été versée
        // (argument imbriqué — enveloppe de type d'un defaultdict...) :
        // même table, __items__ compris. Seules les collections portent
        // __items__ ; classe inconnue -> déclin, voie python inchangée
        if (replacement == nullptr && fastPlainEndObject
            && PyDict_CheckExact(mapping) && PyDict_GET_SIZE(mapping) == 3) {
            PyObject* cls_value = PyDict_GetItem(mapping, class_key_name);
            PyObject* items = PyDict_GetItem(mapping, items_key_name);
            if (cls_value != nullptr && PyUnicode_CheckExact(cls_value)
                && items != nullptr) {
                bool from_new = true;
                PyObject* ctor_args = PyDict_GetItem(mapping, new_key_name);
                if (ctor_args == nullptr) {
                    ctor_args = PyDict_GetItem(mapping, init_key_name);
                    from_new = false;
                }
                if (ctor_args != nullptr) {
                    replacement = EnvelopeConstruct(cls_value, ctor_args,
                                                    from_new, items);
                    if (replacement != nullptr)
                        Py_DECREF(mapping);
                }
            }
        }

        // ----- {"__class__": "dict", ...} : dict à clés non-str reconstruit
        // en C, clé par clé (repli python par clé pour les exotiques)
        if (replacement == nullptr && fastPlainEndObject
            && PyDict_CheckExact(mapping) && PyDict_GET_SIZE(mapping) >= 1) {
            PyObject* cls_value = PyDict_GetItem(mapping, class_key_name);
            if (cls_value != nullptr && PyUnicode_CheckExact(cls_value)
                && PyUnicode_CompareWithASCIIString(cls_value, "dict") == 0) {
                replacement = DictNonStrConstruct(mapping);
                if (replacement != nullptr)
                    Py_DECREF(mapping);
                else if (PyErr_Occurred())
                    PyErr_Clear();   // voie python
            }
        }

                // ----- {"$ref": chemin} : résolution directe en C sur la grammaire
        // émise par l'encodeur (root, .attr, [int], ['clé']) — la voie
        // python demeure pour les cas exotiques, les références en avant
        // (cible = dict à __class__ pas encore recréé) et les racines
        // inconnues (document commençant par une liste)
        if (replacement == nullptr && decoderEndObject != nullptr
            && PyDict_CheckExact(mapping) && PyDict_GET_SIZE(mapping) == 1) {
            PyObject* ref_path = PyDict_GetItem(mapping, ref_key_name);
            if (ref_path != nullptr && PyUnicode_CheckExact(ref_path)) {
                if (rootObject == nullptr && root != nullptr) {
                    // la racine du HANDLER : elle existe pour les documents
                    // à racine dict COMME liste (l'attribut .root du décodeur
                    // n'était posé que pour les dicts — les références des
                    // racines liste partaient toutes en post-passe python,
                    // ~6 µs chacune)
                    rootObject = root;
                    Py_INCREF(rootObject);
                }
                if (rootObject != nullptr) {
                    // cache par CHEMIN le temps du parse : les documents à
                    // répliques émettent des dizaines de fois le même $ref,
                    // et chaque résolution remarche depuis la racine. Seules
                    // les résolutions ACCEPTÉES sont mémorisées : une cible
                    // encore à l'état d'enveloppe (__class__) est déclinée,
                    // et sa forme finale ne s'obtient qu'en re-résolvant
                    PyObject* resolved = nullptr;
                    if (refPathCache != nullptr) {
                        resolved = PyDict_GetItemWithError(refPathCache,
                                                           ref_path);
                        if (resolved != nullptr) {
                            Py_INCREF(resolved);
                            replacement = resolved;
                            Py_DECREF(mapping);
                        } else if (PyErr_Occurred())
                            PyErr_Clear();
                    }
                    if (replacement == nullptr) {
                        // la résolution PARCOURT l'arbre depuis la racine :
                        // les listes encore ouvertes doivent y être pleines,
                        // sans quoi un renvoi vers un élément déjà lu d'une
                        // liste en cours repartirait en post-passe python
                        VerseTout();
                        Py_ssize_t path_length;
                        const char* path_str = PyUnicode_AsUTF8AndSize(
                            ref_path, &path_length);
                        resolved = (path_str == nullptr) ? nullptr
                            : sj_resolve_ref_path(path_str, path_length,
                                                  rootObject);
                        if (path_str == nullptr)
                            PyErr_Clear();
                        if (resolved != nullptr) {
                            bool exotique = resolved == mapping
                                || !SjCibleRef(&resolved);
                            if (exotique)
                                Py_DECREF(resolved);   // voie python
                            else {
                                if (refPathCache == nullptr)
                                    refPathCache = PyDict_New();
                                if (refPathCache != nullptr
                                    && PyDict_SetItem(refPathCache, ref_path,
                                                      resolved) < 0)
                                    PyErr_Clear();
                                replacement = resolved;
                                Py_DECREF(mapping);
                            }
                        }
                    }
                }
            }
        }

        if (replacement == nullptr) {
            if (objectHook == nullptr && decoderEndObject == nullptr) {
                Py_DECREF(mapping);
                return true;
            }

            if (!pendingB64.empty() && !NumpyNoReadDict(mapping)
                && !FlushPendingB64()) {
                Py_DECREF(mapping);
                return false;
            }
            if (decoderEndObject != nullptr) {
                replacement = PyObject_CallFunctionObjArgs(decoderEndObject, mapping, nullptr);
            } else /* if (objectHook != nullptr) */ {
                replacement = PyObject_CallFunctionObjArgs(objectHook, mapping, nullptr);
            }

            Py_DECREF(mapping);
            if (replacement == nullptr)
                return false;
        }

        return ReplaceInParent(replacement);
    }

    // remplace, chez le parent, la valeur que l'objet venait d'y occuper —
    // ou la CAPTURE d'enveloppe du parent si c'est elle qui le tenait (les
    // enveloppes reconnues au parse ne passent pas par le dict). Consomme la
    // référence de replacement.
    bool ReplaceInParent(PyObject* replacement) {
        if (!stack.empty()) {
            HandlerContext& current = stack.back();

            if (current.envState == 4) {
                // le parent capturait : l'objet remplacé est sa capture
                Py_SETREF(current.envArgs, replacement);
                return true;
            }
            if (current.envState == 6) {
                Py_SETREF(current.envItems, replacement);
                return true;
            }
            if (current.envState == 7) {
                // parent en décodage direct : resservir sous la clé DÉCODÉE
                int rc = 0;
                if (current.envDictKey != nullptr)
                    rc = PyDict_SetItem(current.object, current.envDictKey,
                                        replacement);
                Py_DECREF(replacement);
                return rc == 0;
            }
            if (current.isObject) {
                PyObject* key = KeyString(current.key,
                                          (size_t) current.keyLength);
                if (key == nullptr) {
                    Py_DECREF(replacement);
                    return false;
                }

                int rc;
                if (current.keyValuePairs) {
                    PyObject* pair = PyTuple_Pack(2, key, replacement);

                    Py_DECREF(key);
                    Py_DECREF(replacement);
                    if (pair == nullptr) {
                        return false;
                    }

                    Py_ssize_t listLen = PyList_GET_SIZE(current.object);

                    rc = PyList_SetItem(current.object, listLen - 1, pair);

                    // NB: PyList_SetItem() steals a reference on the replacement, so it
                    // must not be DECREFed when the operation succeeds

                    if (rc == -1) {
                        Py_DECREF(pair);
                        return false;
                    }
                } else {
                    if (PyDict_CheckExact(current.object))
                        // If it's a standard dictionary, this is +20% faster
                        rc = PyDict_SetItem(current.object, key, replacement);
                    else
                        rc = PyObject_SetItem(current.object, key, replacement);
                    Py_DECREF(key);
                    Py_DECREF(replacement);
                    if (rc == -1) {
                        return false;
                    }
                }
            } else if (current.differe) {
                RemplaceDernier(replacement);
            } else {
                // Change these to PySequence_Size() and PySequence_SetItem(),
                // should we implement Decoder.start_array()
                Py_ssize_t listLen = PyList_GET_SIZE(current.object);
                int rc = PyList_SetItem(current.object, listLen - 1, replacement);

                // NB: PyList_SetItem() steals a reference on the replacement, so it must
                // not be DECREFed when the operation succeeds

                if (rc == -1) {
                    Py_DECREF(replacement);
                    return false;
                }
            }
        } else {
            Py_SETREF(root, replacement);
        }

        return true;
    }

    bool StartArray() {
        PyObject* list = PyList_New(0);
        if (list == nullptr) {
            return false;
        }

        if (!Handle(list)) {
            return false;
        }

        HandlerContext ctx;
        ctx.isObject = false;
        ctx.object = list;
        ctx.key = nullptr;
        ctx.copiedKey = false;
        ctx.specialKey = false;
        ctx.envState = 0;
        ctx.envSlot = 0;
        ctx.envClass = nullptr;
        ctx.envArgs = nullptr;
        ctx.envItems = nullptr;
        ctx.envDictKey = nullptr;
        ctx.refResolu = nullptr;
        ctx.refCheminBrut = nullptr;
        ctx.refCheminBrutLg = 0;
        ctx.attenteBase = attente.size();
        ctx.differe = true;
        ctx.envFresh = false;
        ctx.envConstruit = false;
        Py_INCREF(list);

        stack.push_back(ctx);

        return true;
    }

    bool EndArray(SizeType elementCount) {
        // la liste doit être pleine avant tout le reste ; le destructeur du
        // handler défera la pile si l'allocation manque
        if (!VerseAttente(stack.back()))
            return false;
        const HandlerContext& ctx = stack.back();

        if (ctx.copiedKey)
            PyMem_Free((void*) ctx.key);

        PyObject* sequence = ctx.object;
        stack.pop_back();

        if (decoderEndArray == nullptr) {
            Py_DECREF(sequence);
            return true;
        }

        // la liste-valeur d'un slot d'enveloppe (__init__/__new__/__items__)
        // n'est pas soumise à end_array : la voie python reconvertissait de
        // toute façon le tableau en liste (tolist dans _inst_from_dict)
        // avant instance() — autant ne pas convertir du tout. Les listes
        // IMBRIQUÉES dans les args, elles, restent converties, comme avant
        if (!stack.empty()) {
            const HandlerContext& parent = stack.back();
            if ((parent.envState == 4 && parent.envArgs == sequence)
                || (parent.envState == 6 && parent.envItems == sequence)) {
                Py_DECREF(sequence);
                return true;
            }
        }

        if (!pendingB64.empty() && !FlushPendingB64()) {
            Py_DECREF(sequence);
            return false;
        }
        PyObject* replacement = PyObject_CallFunctionObjArgs(decoderEndArray, sequence,
                                                             nullptr);
        Py_DECREF(sequence);
        if (replacement == nullptr)
            return false;

        return ReplaceInParent(replacement);
    }

    bool NaN() {
        if (!(numberMode & NM_NAN)) {
            PyErr_SetString(PyExc_ValueError,
                            "Out of range float values are not JSON compliant");
            return false;
        }

        PyObject* value;
        if (numberMode & NM_DECIMAL) {
            value = PyObject_CallFunctionObjArgs(decimal_type, nan_string_value, nullptr);
        } else {
            value = PyFloat_FromString(nan_string_value);
        }

        if (value == nullptr)
            return false;

        return Handle(value);
    }

    bool Infinity(bool minus) {
        if (!(numberMode & NM_NAN)) {
            PyErr_SetString(PyExc_ValueError,
                            "Out of range float values are not JSON compliant");
            return false;
        }

        PyObject* value;
        if (numberMode & NM_DECIMAL) {
            value = PyObject_CallFunctionObjArgs(decimal_type,
                                                 minus
                                                 ? minus_inf_string_value
                                                 : plus_inf_string_value, nullptr);
        } else {
            value = PyFloat_FromString(minus
                                       ? minus_inf_string_value
                                       : plus_inf_string_value);
        }

        if (value == nullptr)
            return false;

        return Handle(value);
    }

    bool Null() {
        PyObject* value = Py_None;
        Py_INCREF(value);

        return Handle(value);
    }

    bool Bool(bool b) {
        PyObject* value = b ? Py_True : Py_False;
        Py_INCREF(value);

        return Handle(value);
    }

    bool Int(int i) {
        PyObject* value = PyLong_FromLong(i);
        return Handle(value);
    }

    bool Uint(unsigned i) {
        PyObject* value = PyLong_FromUnsignedLong(i);
        return Handle(value);
    }

    bool Int64(int64_t i) {
        PyObject* value = PyLong_FromLongLong(i);
        return Handle(value);
    }

    bool Uint64(uint64_t i) {
        PyObject* value = PyLong_FromUnsignedLongLong(i);
        return Handle(value);
    }

    bool Double(double d) {
        PyObject* value = PyFloat_FromDouble(d);
        return Handle(value);
    }

    bool RawNumber(const char* str, SizeType length, bool copy) {
        PyObject* value;
        bool isFloat = false;

        for (int i = length - 1; i >= 0; --i) {
            // consider it a float if there is at least one non-digit character,
            // it may be either a decimal number or +-infinity or nan
            if (!isdigit(str[i]) && str[i] != '-') {
                isFloat = true;
                break;
            }
        }

        if (isFloat) {

            if (numberMode & NM_DECIMAL) {
                PyObject* pystr = PyUnicode_FromStringAndSize(str, length);
                if (pystr == nullptr)
                    return false;
                value = PyObject_CallFunctionObjArgs(decimal_type, pystr, nullptr);
                Py_DECREF(pystr);
            } else {
                std::string zstr(str, length);

                value = float_from_string(zstr.c_str(), length);
            }

        } else {
            // entier : la grammaire JSON garantit [-]chiffres. Jusqu'à 18
            // chiffres il tient sûrement sur 64 bits : parse direct, sans
            // chaîne intermédiaire ni machinerie des grands entiers
            bool negative = (str[0] == '-');
            SizeType digits = length - (negative ? 1 : 0);
            if (digits >= 1 && digits <= 18) {
                long long parsed = 0;
                const char* cursor = str + (negative ? 1 : 0);
                for (SizeType i = 0; i < digits; i++)
                    parsed = parsed * 10 + (cursor[i] - '0');
                value = PyLong_FromLongLong(negative ? -parsed : parsed);
            } else {
                std::string zstr(str, length);

                value = PyLong_FromString(zstr.c_str(), nullptr, 10);
            }
        }

        if (value == nullptr) {
            PyErr_SetString(PyExc_ValueError,
                            isFloat
                            ? "Invalid float value"
                            : "Invalid integer value");
            return false;
        } else {
            return Handle(value);
        }
    }

#define digit(idx) (str[idx] - '0')

    bool IsIso8601Date(const char* str, int& year, int& month, int& day) {
        // we've already checked that str is a valid length and that 5 and 8 are '-'
        if (!isdigit(str[0]) || !isdigit(str[1]) || !isdigit(str[2]) || !isdigit(str[3])
            || !isdigit(str[5]) || !isdigit(str[6])
            || !isdigit(str[8]) || !isdigit(str[9])) return false;

        year = digit(0)*1000 + digit(1)*100 + digit(2)*10 + digit(3);
        month = digit(5)*10 + digit(6);
        day = digit(8)*10 + digit(9);

        return year > 0 && month <= 12 && day <= days_per_month(year, month);
    }

    bool IsIso8601Offset(const char* str, int& tzoff) {
        if (!isdigit(str[1]) || !isdigit(str[2]) || str[3] != ':'
            || !isdigit(str[4]) || !isdigit(str[5])) return false;

        int hofs = 0, mofs = 0, tzsign = 1;
        hofs = digit(1)*10 + digit(2);
        mofs = digit(4)*10 + digit(5);

        if (hofs > 23 || mofs > 59) return false;

        if (str[0] == '-') tzsign = -1;
        tzoff = tzsign * (hofs * 3600 + mofs * 60);
        return true;
    }

    bool IsIso8601Time(const char* str, SizeType length,
                       int& hours, int& mins, int& secs, int& usecs, int& tzoff) {
        // we've already checked that str is a minimum valid length, but nothing else
        if (!isdigit(str[0]) || !isdigit(str[1]) || str[2] != ':'
            || !isdigit(str[3]) || !isdigit(str[4]) || str[5] != ':'
            || !isdigit(str[6]) || !isdigit(str[7])) return false;

        hours = digit(0)*10 + digit(1);
        mins = digit(3)*10 + digit(4);
        secs = digit(6)*10 + digit(7);

        if (hours > 23 || mins > 59 || secs > 59) return false;

        if (length == 8 || (length == 9 && str[8] == 'Z')) {
            // just time
            return true;
        }


        if (length == 14 && (str[8] == '-' || str[8] == '+')) {
            return IsIso8601Offset(&str[8], tzoff);
        }

        // at this point we need a . AND at least 1 more digit
        if (length == 9 || str[8] != '.' || !isdigit(str[9])) return false;

        int usecLength;
        if (str[length - 1] == 'Z') {
            usecLength = length - 10;
        } else if (str[length - 3] == ':') {
            if (!IsIso8601Offset(&str[length - 6], tzoff)) return false;
            usecLength = length - 15;
        } else {
            usecLength = length - 9;
        }

        if (usecLength > 9) return false;

        switch (usecLength) {
            case 9: if (!isdigit(str[17])) { return false; }
            case 8: if (!isdigit(str[16])) { return false; }
            case 7: if (!isdigit(str[15])) { return false; }
            case 6: if (!isdigit(str[14])) { return false; } usecs += digit(14);
            case 5: if (!isdigit(str[13])) { return false; } usecs += digit(13)*10;
            case 4: if (!isdigit(str[12])) { return false; } usecs += digit(12)*100;
            case 3: if (!isdigit(str[11])) { return false; } usecs += digit(11)*1000;
            case 2: if (!isdigit(str[10])) { return false; } usecs += digit(10)*10000;
            case 1: if (!isdigit(str[9])) { return false; } usecs += digit(9)*100000;
        }

        return true;
    }

    bool IsIso8601(const char* str, SizeType length,
                   int& year, int& month, int& day,
                   int& hours, int& mins, int &secs, int& usecs, int& tzoff) {
        year = -1;
        month = day = hours = mins = secs = usecs = tzoff = 0;

        // Early exit for values that are clearly not valid (too short or too long)
        if (length < 8 || length > 35) return false;

        bool isDate = str[4] == '-' && str[7] == '-';

        if (!isDate) {
            return IsIso8601Time(str, length, hours, mins, secs, usecs, tzoff);
        }

        if (length == 10) {
            // if it looks like just a date, validate just the date
            return IsIso8601Date(str, year, month, day);
        }
        if (length > 18 && (str[10] == 'T' || str[10] == ' ')) {
            // if it looks like a date + time, validate date + time
            return IsIso8601Date(str, year, month, day)
                && IsIso8601Time(&str[11], length - 11, hours, mins, secs, usecs, tzoff);
        }
        // can't be valid
        return false;
    }

    bool HandleIso8601(const char* str, SizeType length,
                       int year, int month, int day,
                       int hours, int mins, int secs, int usecs, int tzoff) {
        // we treat year 0 as invalid and thus the default when there is no date
        bool hasDate = year > 0;

        if (length == 10 && hasDate) {
            // just a date, handle quickly
            return Handle(PyDate_FromDate(year, month, day));
        }

        bool isZ = str[length - 1] == 'Z';
        bool hasOffset = !isZ && (str[length - 6] == '-' || str[length - 6] == '+');

        PyObject* value;

        if ((datetimeMode & DM_NAIVE_IS_UTC || isZ) && !hasOffset) {
            if (hasDate) {
                value = PyDateTimeAPI->DateTime_FromDateAndTime(
                    year, month, day, hours, mins, secs, usecs, timezone_utc,
                    PyDateTimeAPI->DateTimeType);
            } else {
                value = PyDateTimeAPI->Time_FromTime(
                    hours, mins, secs, usecs, timezone_utc, PyDateTimeAPI->TimeType);
            }
        } else if (datetimeMode & DM_IGNORE_TZ || (!hasOffset && !isZ)) {
            if (hasDate) {
                value = PyDateTime_FromDateAndTime(year, month, day,
                                                   hours, mins, secs, usecs);
            } else {
                value = PyTime_FromTime(hours, mins, secs, usecs);
            }
        } else if (!hasDate && datetimeMode & DM_SHIFT_TO_UTC && tzoff) {
            PyErr_Format(PyExc_ValueError,
                         "Time literal cannot be shifted to UTC: %s", str);
            value = nullptr;
        } else if (!hasDate && datetimeMode & DM_SHIFT_TO_UTC) {
            value = PyDateTimeAPI->Time_FromTime(
                hours, mins, secs, usecs, timezone_utc, PyDateTimeAPI->TimeType);
        } else {
            PyObject* offset = PyDateTimeAPI->Delta_FromDelta(0, tzoff, 0, 1,
                                                              PyDateTimeAPI->DeltaType);
            if (offset == nullptr) {
                value = nullptr;
            } else {
                PyObject* tz = PyObject_CallFunctionObjArgs(timezone_type, offset, nullptr);
                Py_DECREF(offset);
                if (tz == nullptr) {
                    value = nullptr;
                } else {
                    if (hasDate) {
                        value = PyDateTimeAPI->DateTime_FromDateAndTime(
                            year, month, day, hours, mins, secs, usecs, tz,
                            PyDateTimeAPI->DateTimeType);
                        if (value != nullptr && datetimeMode & DM_SHIFT_TO_UTC) {
                            PyObject* asUTC = PyObject_CallMethodObjArgs(
                                value, astimezone_name, timezone_utc, nullptr);
                            Py_DECREF(value);
                            if (asUTC == nullptr) {
                                value = nullptr;
                            } else {
                                value = asUTC;
                            }
                        }
                    } else {
                        value = PyDateTimeAPI->Time_FromTime(hours, mins, secs, usecs, tz,
                                                             PyDateTimeAPI->TimeType);
                    }
                    Py_DECREF(tz);
                }
            }
        }

        if (value == nullptr)
            return false;

        return Handle(value);
    }

#undef digit

    bool IsUuid(const char* str, SizeType length) {
        if (uuidMode == UM_HEX && length == 32) {
            for (int i = length - 1; i >= 0; --i)
                if (!isxdigit(str[i]))
                    return false;
            return true;
        } else if (length == 36
                   && str[8] == '-' && str[13] == '-'
                   && str[18] == '-' && str[23] == '-') {
            for (int i = length - 1; i >= 0; --i)
                if (i != 8 && i != 13 && i != 18 && i != 23 && !isxdigit(str[i]))
                    return false;
            return true;
        }
        return false;
    }

    bool HandleUuid(const char* str, SizeType length) {
        PyObject* pystr = PyUnicode_FromStringAndSize(str, length);
        if (pystr == nullptr)
            return false;

        PyObject* value = PyObject_CallFunctionObjArgs(uuid_type, pystr, nullptr);
        Py_DECREF(pystr);

        if (value == nullptr)
            return false;
        else
            return Handle(value);
    }

    // Combien d'éléments un niveau liste a DÉJÀ reçus. Sa taille python ne le
    // dit plus : tant que le niveau est différé, ses éléments attendent et
    // elle vaut zéro. Deux tests de « premier élément » en dépendent, celui
    // qui décode une charge base64 depuis le tampon de parse et celui qui
    // l'annonce au lecteur.
    Py_ssize_t NbRecus(const HandlerContext& ctx) const {
        return ctx.differe ? (Py_ssize_t) (attente.size() - ctx.attenteBase)
                           : PyList_GET_SIZE(ctx.object);
    }

    // vrai si la prochaine chaîne est la charge base64 d'une classe binaire
    // (premier élément, encore absent, de la liste __init__/__new__ d'une
    // classe enregistrée) : le parseur peut alors sauter le scan d'une
    // charge préfixée « <n>: » — mêmes conditions que la branche charge de
    // String(), évaluées AVANT le parse de la chaîne
    bool SjExpectB64Payload() const {
        if (b64PayloadClasses.empty() || stack.size() < 2)
            return false;
        const HandlerContext& top = stack.back();
        if (top.isObject || !PyList_CheckExact(top.object)
            || NbRecus(top) != 0)
            return false;
        const HandlerContext& parent = stack[stack.size() - 2];
        if (!parent.isObject || parent.key == nullptr
            || !((parent.keyLength == 8
                  && memcmp(parent.key, "__init__", 8) == 0)
                 || (parent.keyLength == 7
                     && memcmp(parent.key, "__new__", 7) == 0))
            // enveloppe différée : object est nul, la classe vit dans la
            // capture
            || !(parent.envClass != nullptr
                 || PyDict_CheckExact(parent.object)))
            return false;
        // enveloppe capturée au parse : la classe vit dans la capture
        PyObject* cls_value = parent.envClass != nullptr
            ? parent.envClass
            : PyDict_GetItem(parent.object, class_key_name);
        if (cls_value == nullptr || !PyUnicode_CheckExact(cls_value))
            return false;
        Py_ssize_t cls_length;
        const char* cls_str = PyUnicode_AsUTF8AndSize(cls_value, &cls_length);
        if (cls_str == nullptr) {
            PyErr_Clear();
            return false;
        }
        return b64PayloadClasses.find(std::string(cls_str, (size_t) cls_length))
            != b64PayloadClasses.end();
    }

    bool String(const char* str, SizeType length, bool copy) {
        PyObject* value;
        const int asciiHint = stringAsciiHint;
        stringAsciiHint = 0;

        // ----- {"$ref": chemin} : résolution AU VOL, dès la valeur — ni
        // chaîne python du chemin, ni insertion, ni dict à détruire (la
        // version à la fermeture demeure : flux copiés, replis). Réservé au
        // tampon insitu : le chemin brut doit survivre jusqu'à la fermeture
        if (!copy && !stack.empty()) {
            HandlerContext& cur = stack.back();
            if (cur.specialKey && cur.isObject && cur.envState == 0
                && cur.refResolu == nullptr && cur.key != nullptr
                && cur.keyLength == 4 && memcmp(cur.key, "$ref", 4) == 0
                && decoderEndObject != nullptr && decoderString == nullptr
                && PyDict_CheckExact(cur.object)
                && PyDict_GET_SIZE(cur.object) == 0) {
                PyObject* resolu = ResoudreRefDirect(str, length, cur.object);
                if (resolu != nullptr) {
                    cur.refResolu = resolu;
                    cur.refCheminBrut = str;
                    cur.refCheminBrutLg = length;
                    return true;
                }
            }
        }

        // ----- charges binaires : décode le base64 directement depuis le
        // tampon de parse (sans matérialiser la chaîne Python intermédiaire)
        // quand cette chaîne est le premier élément de la liste __init__ ou
        // __new__ d'une classe enregistrée (bytes, bytearray, numpyB64...).
        // Si ce n'est pas du base64 propre, chemin normal.
        // length >= 2 : la plus courte charge légitime est « 0: » (bytearray
        // vide, préfixe de longueur seul) — le seuil 8 la renvoyait au greffon
        // python, seul élément du lot bytearray encore hors table C
        if (!b64PayloadClasses.empty() && length >= 2 && stack.size() >= 2) {
            const HandlerContext& top = stack.back();
            if (!top.isObject && PyList_CheckExact(top.object)
                && NbRecus(top) == 0) {
                const HandlerContext& parent = stack[stack.size() - 2];
                if (parent.isObject && parent.key != nullptr
                    && ((parent.keyLength == 8
                         && memcmp(parent.key, "__init__", 8) == 0)
                        || (parent.keyLength == 7
                            && memcmp(parent.key, "__new__", 7) == 0))
                    // enveloppe différée : object est nul, la classe vit
                    // dans la capture
                    && (parent.envClass != nullptr
                        || PyDict_CheckExact(parent.object))) {
                    // enveloppe capturée au parse : la classe vit dans la
                    // capture, le dict du parent est resté vide
                    PyObject* class_value = parent.envClass != nullptr
                        ? parent.envClass
                        : PyDict_GetItem(parent.object, class_key_name);
                    if (class_value != nullptr
                        && PyUnicode_CheckExact(class_value)) {
                        Py_ssize_t class_length;
                        const char* class_str = PyUnicode_AsUTF8AndSize(
                            class_value, &class_length);
                        if (class_str != nullptr) {
                            auto it = b64PayloadClasses.find(
                                std::string(class_str, (size_t) class_length));
                            if (it != b64PayloadClasses.end()) {
                                // préfixe « <n>: » écrit par le sérialiseur
                                // (saut de scan) : la charge base64 commence
                                // après ':' — ':' est hors de l'alphabet
                                // base64, la détection est sans ambiguïté ;
                                // anciens fichiers : pas de préfixe
                                const char* b64 = str;
                                SizeType b64_length = length;
                                if (str[0] >= '0' && str[0] <= '9') {
                                    SizeType d = 1;
                                    while (d < length && d < 20
                                           && str[d] >= '0' && str[d] <= '9')
                                        d++;
                                    if (d < length && str[d] == ':') {
                                        b64 = str + d + 1;
                                        b64_length = length - d - 1;
                                    }
                                }
                                if (b64_length == 0 && b64 != str) {
                                    // « 0: » : charge vide légitime — le
                                    // préfixe a été reconnu (une chaîne vide
                                    // sans préfixe ne parvient pas ici)
                                    PyObject* decoded = it->second
                                        ? PyByteArray_FromStringAndSize(
                                              nullptr, 0)
                                        : PyBytes_FromStringAndSize(
                                              nullptr, 0);
                                    if (decoded != nullptr)
                                        return Handle(decoded);
                                    PyErr_Clear();
                                } else if (deferB64 && b64_length >= 64) {
                                    // les petits payloads se décodent tout de
                                    // suite : le différé n'y gagne rien et
                                    // leurs consommateurs (date...) lisent
                                    // validation complète tout de suite (le
                                    // repli « chaîne ordinaire » doit rester
                                    // possible), remplissage différé
                                    size_t groups, pad, out_length;
                                    if (sj_b64_layout(b64, (size_t) b64_length,
                                                      &groups, &pad,
                                                      &out_length,
                                                      serializejson_b64_decode_table())) {
                                        PyObject* dest = it->second
                                            ? PyByteArray_FromStringAndSize(
                                                  nullptr,
                                                  (Py_ssize_t) out_length)
                                            : PyBytes_FromStringAndSize(
                                                  nullptr,
                                                  (Py_ssize_t) out_length);
                                        if (dest == nullptr)
                                            return false;
                                        unsigned char* dst = it->second
                                            ? (unsigned char*)
                                                  PyByteArray_AS_STRING(dest)
                                            : (unsigned char*)
                                                  PyBytes_AS_STRING(dest);
                                        Py_INCREF(dest);
                                        pendingB64.push_back(
                                            {b64, (size_t) b64_length,
                                             out_length, dst, dest,
                                             nullptr, 0, nullptr,
                                             0, 0, 0, false});
                                        return Handle(dest);
                                    }
                                } else {
                                    PyObject* decoded =
                                        serializejson_b64_decode_to_pyobject(
                                            b64, (size_t) b64_length,
                                            it->second);
                                    if (decoded != nullptr)
                                        return Handle(decoded);
                                }
                            }
                        }
                    }
                }
            }
        }

        if (datetimeMode != DM_NONE) {
            int year, month, day, hours, mins, secs, usecs, tzoff;

            if (IsIso8601(str, length, year, month, day,
                          hours, mins, secs, usecs, tzoff))
                return HandleIso8601(str, length, year, month, day,
                                     hours, mins, secs, usecs, tzoff);
        }

        if (uuidMode != UM_NONE && IsUuid(str, length))
            return HandleUuid(str, length);

        value = ValueString(str, (size_t) length, asciiHint);
        if (value == nullptr)
            return false;

        if (decoderString != nullptr) {
            if (!pendingB64.empty() && !FlushPendingB64()) {
                Py_DECREF(value);
                return false;
            }
            PyObject* replacement = PyObject_CallFunctionObjArgs(decoderString, value,
                                                                 nullptr);
            Py_DECREF(value);
            if (replacement == nullptr)
                return false;
            value = replacement;
        }

        return Handle(value);
    }
};


// (DecoderObject déplacé avant PyHandler : le handler branche sa table)


PyDoc_STRVAR(loads_docstring,
             "loads(string, *, object_hook=None, number_mode=None, datetime_mode=None,"
             " uuid_mode=None, parse_mode=None, allow_nan=True)\n"
             "\n"
             "Decode a JSON string into a Python object.");


static PyObject*
loads(PyObject* self, PyObject* args, PyObject* kwargs)
{
    /* Converts a JSON encoded string to a Python object. */

    static char const* kwlist[] = {
        "string",
        "object_hook",
        "number_mode",
        "datetime_mode",
        "uuid_mode",
        "parse_mode",

        /* compatibility with stdlib json */
        "allow_nan",

        nullptr
    };
    PyObject* jsonObject;
    PyObject* objectHook = nullptr;
    PyObject* datetimeModeObj = nullptr;
    unsigned datetimeMode = DM_NONE;
    PyObject* uuidModeObj = nullptr;
    unsigned uuidMode = UM_NONE;
    PyObject* numberModeObj = nullptr;
    unsigned numberMode = NM_NAN;
    PyObject* parseModeObj = nullptr;
    unsigned parseMode = PM_NONE;
    int allowNan = -1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|$OOOOOp:rapidjson.loads",
                                     (char**) kwlist,
                                     &jsonObject,
                                     &objectHook,
                                     &numberModeObj,
                                     &datetimeModeObj,
                                     &uuidModeObj,
                                     &parseModeObj,
                                     &allowNan))
        return nullptr;

    if (objectHook && !PyCallable_Check(objectHook)) {
        if (objectHook == Py_None) {
            objectHook = nullptr;
        } else {
            PyErr_SetString(PyExc_TypeError, "object_hook is not callable");
            return nullptr;
        }
    }

    if (!accept_number_mode_arg(numberModeObj, allowNan, numberMode))
        return nullptr;
    if (numberMode & NM_DECIMAL && numberMode & NM_NATIVE) {
        PyErr_SetString(PyExc_ValueError,
                        "Invalid number_mode, combining NM_NATIVE with NM_DECIMAL"
                        " is not supported");
        return nullptr;
    }

    if (!accept_datetime_mode_arg(datetimeModeObj, datetimeMode))
        return nullptr;
    if (datetimeMode && datetime_mode_format(datetimeMode) != DM_ISO8601) {
        PyErr_SetString(PyExc_ValueError,
                        "Invalid datetime_mode, can deserialize only from"
                        " ISO8601");
        return nullptr;
    }

    if (!accept_uuid_mode_arg(uuidModeObj, uuidMode))
        return nullptr;

    if (!accept_parse_mode_arg(parseModeObj, parseMode))
        return nullptr;

    Py_ssize_t jsonStrLen;
    const char* jsonStr;
    PyObject* asUnicode = nullptr;

    if (PyUnicode_Check(jsonObject)) {
        jsonStr = PyUnicode_AsUTF8AndSize(jsonObject, &jsonStrLen);
        if (jsonStr == nullptr) {
            return nullptr;
        }
    } else if (PyBytes_Check(jsonObject) || PyByteArray_Check(jsonObject)) {
        asUnicode = PyUnicode_FromEncodedObject(jsonObject, "utf-8", nullptr);
        if (asUnicode == nullptr)
            return nullptr;
        jsonStr = PyUnicode_AsUTF8AndSize(asUnicode, &jsonStrLen);
        if (jsonStr == nullptr) {
            Py_DECREF(asUnicode);
            return nullptr;
        }
    } else {
        PyErr_SetString(PyExc_TypeError,
                        "Expected string or UTF-8 encoded bytes or bytearray");
        return nullptr;
    }

    PyObject* result = do_decode(nullptr, jsonStr, jsonStrLen, nullptr, 0, objectHook,
                                 numberMode, datetimeMode, uuidMode, parseMode);

    if (asUnicode != nullptr)
        Py_DECREF(asUnicode);

    return result;
}


PyDoc_STRVAR(load_docstring,
             "load(stream, *, object_hook=None, number_mode=None, datetime_mode=None,"
             " uuid_mode=None, parse_mode=None, chunk_size=65536, allow_nan=True)\n"
             "\n"
             "Decode a JSON stream into a Python object.");


static PyObject*
load(PyObject* self, PyObject* args, PyObject* kwargs)
{
    /* Converts a JSON encoded stream to a Python object. */

    static char const* kwlist[] = {
        "stream",
        "object_hook",
        "number_mode",
        "datetime_mode",
        "uuid_mode",
        "parse_mode",
        "chunk_size",

        /* compatibility with stdlib json */
        "allow_nan",

        nullptr
    };
    PyObject* jsonObject;
    PyObject* objectHook = nullptr;
    PyObject* datetimeModeObj = nullptr;
    unsigned datetimeMode = DM_NONE;
    PyObject* uuidModeObj = nullptr;
    unsigned uuidMode = UM_NONE;
    PyObject* numberModeObj = nullptr;
    unsigned numberMode = NM_NAN;
    PyObject* parseModeObj = nullptr;
    unsigned parseMode = PM_NONE;
    PyObject* chunkSizeObj = nullptr;
    size_t chunkSize = 65536;
    int allowNan = -1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|$OOOOOOp:rapidjson.load",
                                     (char**) kwlist,
                                     &jsonObject,
                                     &objectHook,
                                     &numberModeObj,
                                     &datetimeModeObj,
                                     &uuidModeObj,
                                     &parseModeObj,
                                     &chunkSizeObj,
                                     &allowNan))
        return nullptr;

    if (!PyObject_HasAttr(jsonObject, read_name)) {
        PyErr_SetString(PyExc_TypeError, "Expected file-like object");
        return nullptr;
    }

    if (objectHook && !PyCallable_Check(objectHook)) {
        if (objectHook == Py_None) {
            objectHook = nullptr;
        } else {
            PyErr_SetString(PyExc_TypeError, "object_hook is not callable");
            return nullptr;
        }
    }

    if (numberModeObj) {
        if (numberModeObj == Py_None) {
            numberMode = NM_NONE;
        } else if (PyLong_Check(numberModeObj)) {
            int mode = PyLong_AsLong(numberModeObj);
            if (mode < 0 || mode >= NM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid number_mode");
                return nullptr;
            }
            numberMode = (unsigned) mode;
            if (numberMode & NM_DECIMAL && numberMode & NM_NATIVE) {
                PyErr_SetString(PyExc_ValueError,
                                "Combining NM_NATIVE with NM_DECIMAL is not supported");
                return nullptr;
            }
        }
    }
    if (allowNan != -1) {
        if (allowNan)
            numberMode |= NM_NAN;
        else
            numberMode &= ~NM_NAN;
    }

    if (datetimeModeObj) {
        if (datetimeModeObj == Py_None) {
            datetimeMode = DM_NONE;
        } else if (PyLong_Check(datetimeModeObj)) {
            int mode = PyLong_AsLong(datetimeModeObj);
            if (!valid_datetime_mode(mode)) {
                PyErr_SetString(PyExc_ValueError, "Invalid datetime_mode");
                return nullptr;
            }
            datetimeMode = (unsigned) mode;
            if (datetimeMode && datetime_mode_format(datetimeMode) != DM_ISO8601) {
                PyErr_SetString(PyExc_ValueError,
                                "Invalid datetime_mode, can deserialize only from"
                                " ISO8601");
                return nullptr;
            }
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "datetime_mode must be a non-negative integer value or None");
            return nullptr;
        }
    }

    if (uuidModeObj) {
        if (uuidModeObj == Py_None) {
            uuidMode = UM_NONE;
        } else if (PyLong_Check(uuidModeObj)) {
            int mode = PyLong_AsLong(uuidModeObj);
            if (mode < 0 || mode >= UM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid uuid_mode");
                return nullptr;
            }
            uuidMode = (unsigned) mode;
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "uuid_mode must be an integer value or None");
            return nullptr;
        }
    }

    if (parseModeObj) {
        if (parseModeObj == Py_None) {
            parseMode = PM_NONE;
        } else if (PyLong_Check(parseModeObj)) {
            int mode = PyLong_AsLong(parseModeObj);
            if (mode < 0 || mode >= PM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid parse_mode");
                return nullptr;
            }
            parseMode = (unsigned) mode;
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "parse_mode must be an integer value or None");
            return nullptr;
        }
    }

    if (chunkSizeObj && chunkSizeObj != Py_None) {
        if (PyLong_Check(chunkSizeObj)) {
            Py_ssize_t size = PyNumber_AsSsize_t(chunkSizeObj, PyExc_ValueError);
            if (PyErr_Occurred() || size < 4 || size > UINT_MAX) {
                PyErr_SetString(PyExc_ValueError,
                                "Invalid chunk_size, must be an integer between 4 and"
                                " UINT_MAX");
                return nullptr;
            }
            chunkSize = (size_t) size;
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "chunk_size must be an unsigned integer value or None");
            return nullptr;
        }
    }

    return do_decode(nullptr, nullptr, 0, jsonObject, chunkSize, objectHook,
                     numberMode, datetimeMode, uuidMode, parseMode);
}


PyDoc_STRVAR(decoder_doc,
             "Decoder(number_mode=None, datetime_mode=None, uuid_mode=None,"
             " parse_mode=None)\n"
             "\n"
             "Create and return a new Decoder instance.");


static PyMemberDef decoder_members[] = {
    {"datetime_mode",
     T_UINT, offsetof(DecoderObject, datetimeMode), READONLY,
     "The datetime mode, whether and how datetime literals will be recognized."},
    {"uuid_mode",
     T_UINT, offsetof(DecoderObject, uuidMode), READONLY,
     "The UUID mode, whether and how UUID literals will be recognized."},
    {"number_mode",
     T_UINT, offsetof(DecoderObject, numberMode), READONLY,
     "The number mode, whether numeric literals will be decoded."},
    {"parse_mode",
     T_UINT, offsetof(DecoderObject, parseMode), READONLY,
     "The parse mode, whether comments and trailing commas are allowed."},
    {nullptr}
};


static void
decoder_dealloc(PyObject* self)
{
    DecoderObject* d = (DecoderObject*) self;
    if (d->sjValCache != nullptr) {
        struct Slot { uint64_t hash; PyObject* str; };
        Slot* slots = (Slot*) d->sjValCache;
        for (unsigned i = 0; i < 2048; i++)
            if (slots[i].hash != 0)
                Py_DECREF(slots[i].str);
        PyMem_Free(d->sjValCache);
        d->sjValCache = nullptr;
    }
    Py_TYPE(self)->tp_free(self);
}


static PyMethodDef decoder_methods[] = {
    {"_decode", (PyCFunction) decoder_decode_fn, METH_VARARGS | METH_KEYWORDS,
     "Décodage brut, sans le protocole serializejson du __call__ (mise à\n"
     "jour d'objet, itération sur fichier)."},
    {nullptr, nullptr, 0, nullptr}
};


PyTypeObject Decoder_Type = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "rapidjson.Decoder",                      /* tp_name */
    sizeof(DecoderObject),                    /* tp_basicsize */
    0,                                        /* tp_itemsize */
    (destructor) decoder_dealloc,             /* tp_dealloc */
    0,                                        /* tp_print */
    0,                                        /* tp_getattr */
    0,                                        /* tp_setattr */
    0,                                        /* tp_compare */
    0,                                        /* tp_repr */
    0,                                        /* tp_as_number */
    0,                                        /* tp_as_sequence */
    0,                                        /* tp_as_mapping */
    0,                                        /* tp_hash */
    (ternaryfunc) decoder_call,               /* tp_call */
    0,                                        /* tp_str */
    0,                                        /* tp_getattro */
    0,                                        /* tp_setattro */
    0,                                        /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /* tp_flags */
    decoder_doc,                              /* tp_doc */
    0,                                        /* tp_traverse */
    0,                                        /* tp_clear */
    0,                                        /* tp_richcompare */
    0,                                        /* tp_weaklistoffset */
    0,                                        /* tp_iter */
    0,                                        /* tp_iternext */
    decoder_methods,                          /* tp_methods */
    decoder_members,                          /* tp_members */
    0,                                        /* tp_getset */
    0,                                        /* tp_base */
    0,                                        /* tp_dict */
    0,                                        /* tp_descr_get */
    0,                                        /* tp_descr_set */
    0,                                        /* tp_dictoffset */
    0,                                        /* tp_init */
    0,                                        /* tp_alloc */
    decoder_new,                              /* tp_new */
    PyObject_Del,                             /* tp_free */
};


#define Decoder_CheckExact(v) (Py_TYPE(v) == &Decoder_Type)
#define Decoder_Check(v) PyObject_TypeCheck(v, &Decoder_Type)


#define DECODE(r, f, s, h)                                              \
    do {                                                                \
        /* FIXME: isn't there a cleverer way to write the following?    \
                                                                        \
           Ideally, one would do something like:                        \
                                                                        \
               unsigned flags = kParseInsituFlag;                       \
                                                                        \
               if (! (numberMode & NM_NATIVE))                          \
                   flags |= kParseNumbersAsStringsFlag;                 \
               if (numberMode & NM_NAN)                                 \
                   flags |= kParseNanAndInfFlag;                        \
               if (parseMode & PM_COMMENTS)                             \
                   flags |= kParseCommentsFlag;                         \
               if (parseMode & PM_TRAILING_COMMAS)                      \
                   flags |= kParseTrailingCommasFlag;                   \
                                                                        \
               reader.Parse<flags>(ss, handler);                        \
                                                                        \
           but C++ does not allow that...                               \
        */                                                              \
                                                                        \
        if (numberMode & NM_NAN) {                                      \
            if (numberMode & NM_NATIVE) {                               \
                if (parseMode & PM_TRAILING_COMMAS) {                   \
                    if (parseMode & PM_COMMENTS) {                      \
                        r.Parse<f |                                     \
                                kParseNanAndInfFlag |                   \
                                kParseCommentsFlag |                    \
                                kParseTrailingCommasFlag>(s, h);        \
                    } else {                                            \
                        r.Parse<f |                                     \
                                kParseNanAndInfFlag |                   \
                                kParseTrailingCommasFlag>(s, h);        \
                    }                                                   \
                } else if (parseMode & PM_COMMENTS) {                   \
                    r.Parse<f |                                         \
                            kParseNanAndInfFlag |                       \
                            kParseCommentsFlag>(s, h);                  \
                } else {                                                \
                    r.Parse<f |                                         \
                            kParseNanAndInfFlag>(s, h);                 \
                }                                                       \
            } else if (parseMode & PM_TRAILING_COMMAS) {                \
                if (parseMode & PM_COMMENTS) {                          \
                    r.Parse<f |                                         \
                            kParseNumbersAsStringsFlag |                \
                            kParseNanAndInfFlag |                       \
                            kParseCommentsFlag |                        \
                            kParseTrailingCommasFlag>(s, h);            \
                } else {                                                \
                    r.Parse<f |                                         \
                            kParseNumbersAsStringsFlag |                \
                            kParseNanAndInfFlag |                       \
                            kParseTrailingCommasFlag>(s, h);            \
                }                                                       \
            } else if (parseMode & PM_COMMENTS) {                       \
                r.Parse<f |                                             \
                        kParseNumbersAsStringsFlag |                    \
                        kParseNanAndInfFlag |                           \
                        kParseCommentsFlag>(s, h);                      \
            } else {                                                    \
                r.Parse<f |                                             \
                        kParseNumbersAsStringsFlag |                    \
                        kParseNanAndInfFlag>(s, h);                     \
            }                                                           \
        } else if (numberMode & NM_NATIVE) {                            \
            if (parseMode & PM_TRAILING_COMMAS) {                       \
                if (parseMode & PM_COMMENTS) {                          \
                    r.Parse<f |                                         \
                            kParseCommentsFlag |                        \
                            kParseTrailingCommasFlag>(s, h);            \
                } else {                                                \
                    r.Parse<f |                                         \
                            kParseTrailingCommasFlag>(s, h);            \
                }                                                       \
            } else if (parseMode & PM_COMMENTS) {                       \
                r.Parse<f |                                             \
                        kParseCommentsFlag>(s, h);                      \
            } else {                                                    \
                r.Parse<f>(s, h);                                       \
            }                                                           \
        } else if (parseMode & PM_TRAILING_COMMAS) {                    \
            if (parseMode & PM_COMMENTS) {                              \
                r.Parse<f |                                             \
                        kParseCommentsFlag |                            \
                        kParseNumbersAsStringsFlag>(s, h);              \
            } else {                                                    \
                r.Parse<f |                                             \
                        kParseNumbersAsStringsFlag |                    \
                        kParseTrailingCommasFlag>(s, h);                \
            }                                                           \
        } else {                                                        \
            r.Parse<f | kParseNumbersAsStringsFlag>(s, h);              \
        }                                                               \
    } while(0)


static PyObject*
do_decode(PyObject* decoder, const char* jsonStr, Py_ssize_t jsonStrLen,
          PyObject* jsonStream, size_t chunkSize, PyObject* objectHook,
          unsigned numberMode, unsigned datetimeMode, unsigned uuidMode,
          unsigned parseMode)
{
    PyHandler handler(decoder, objectHook, datetimeMode, uuidMode, numberMode);
    Reader reader;

    // pause du GC generationnel pendant le parse : tout ce qui est construit
    // ici est un arbre acyclique entierement accessible, les collections
    // declenchees par les millions d'allocations ne liberent RIEN (mesure
    // gprofng : gc_collect_main ~13% du temps de decodage) ; retabli a la
    // sortie par le destructeur, y compris sur erreur
    struct GCPause {
        int was_enabled;
        GCPause() : was_enabled(PyGC_Disable()) {}
        ~GCPause() { if (was_enabled) PyGC_Enable(); }
    } gc_pause;

    if (jsonStr != nullptr && getenv("SJ_NOCOPY")) {
        StringStream ss(jsonStr);
        DECODE(reader, kParseFullPrecisionFlag | kParseBigIntsAsStringsFlag, ss, handler);
    } else if (jsonStr != nullptr) {
        // insitu sur une COPIE de l'entrée : essayé sans copie (StringStream)
        // le 03/08/2026 à -O0 puis RE-mesuré le même jour en -O3 — REGRESSION
        // dans les deux cas (objets +19%, ints +6% : le dés-échappement des
        // chaînes vers la pile coûte plus que l'unique memcpy d'entrée) :
        // la copie unique de l'entrée est le bon échange
        // ... SAUF quand le parse n'écrira RIEN : sans terminateurs (drapeau
        // du fork) la seule écriture insitu est le dés-échappement — un gros
        // document SANS aucun antislash (memchr) se parse EN PLACE, zéro
        // copie (la copie de 40 Mo dominait le décodage des gros blobs)
        char* jsonStrCopy = nullptr;
        char* parseBuffer;
        // seuil MESURÉ le 09/08/2026 (A/B interlacé 1 Mo contre 0, 7 tours) :
        // l'abaisser ne rend rien (−1,2 % au mieux, bruit) — sous 1 Mo le
        // parse domine la copie d'entrée ; ne pas y revenir sans nouveau cas
        if (jsonStrLen >= (Py_ssize_t) (1 << 20)
            && memchr(jsonStr, '\\', (size_t) jsonStrLen) == nullptr) {
            parseBuffer = const_cast<char*>(jsonStr);
        } else {
            jsonStrCopy = (char*) PyMem_Malloc(sizeof(char) * (jsonStrLen+1));
            if (jsonStrCopy == nullptr)
                return PyErr_NoMemory();
            memcpy(jsonStrCopy, jsonStr, jsonStrLen+1);
            parseBuffer = jsonStrCopy;
        }

        // flux insitu BORNÉ : la fin permet les lectures larges (SWAR) sans
        // jamais dépasser le tampon (l'entrée bytes/str est suivie d'un NUL,
        // mais rien n'est garanti au-delà)
        SjBoundedInsituStream<UTF8<> > ss(parseBuffer,
                                          parseBuffer + jsonStrLen);
        ss.sjHintOut = &handler.stringAsciiHint;

        handler.deferB64 = true;

        // pleine precision + grands entiers exacts : sans effet dans les branches
        // nombres-en-chaines, actifs dans les branches natives (NM_NATIVE)
        DECODE(reader, kParseInsituFlag | kParseInsituNoTerminatorFlag | kParseFullPrecisionFlag | kParseBigIntsAsStringsFlag, ss, handler);

        // vide les différés AVANT de libérer le tampon qu'ils référencent ;
        // sur échec, l'erreur posée est ramassée par le bloc PyErr_Occurred
        if (!reader.HasParseError())
            handler.FlushPendingB64();
        else
            handler.ReleasePendingB64();

        if (jsonStrCopy != nullptr)
            PyMem_Free(jsonStrCopy);
    } else {
        PyReadStreamWrapper sw(jsonStream, chunkSize);

        DECODE(reader, kParseFullPrecisionFlag | kParseBigIntsAsStringsFlag, sw, handler);
    }

    if (reader.HasParseError()) {
        size_t offset = reader.GetErrorOffset();

        // ligne et colonne (base 1, colonne en CARACTÈRES) calculées sur
        // l'entrée INTACTE (jsonStr : l'original n'est jamais muté — le
        // dés-échappement travaille sur la copie, et le sans-copie n'a par
        // construction aucun antislash). Indisponible pour les flux, dont
        // le texte n'est pas retenu : l'offset seul y reste.
        size_t err_line = 0;
        size_t err_col = 0;
        if (jsonStr != nullptr && offset <= (size_t) jsonStrLen) {
            err_line = 1;
            err_col = 1;
            for (size_t k = 0; k < offset; k++) {
                unsigned char c = (unsigned char) jsonStr[k];
                if (c == '\n') {
                    err_line++;
                    err_col = 1;
                } else if ((c & 0xC0) != 0x80) {
                    err_col++;   // les octets de continuation utf-8 ne comptent pas
                }
            }
        }

        if (PyErr_Occurred()) {
            PyObject* etype;
            PyObject* evalue;
            PyObject* etraceback;
            PyErr_Fetch(&etype, &evalue, &etraceback);

            // Try to add the offset in the error message if the exception
            // value is a string.  Otherwise, use the original exception since
            // we can't be sure the exception type takes a single string.
            if (evalue != nullptr && PyUnicode_Check(evalue)) {
                if (err_line)
                    PyErr_Format(etype,
                                 "Parse error at offset %zu (line %zu,"
                                 " column %zu): %S",
                                 offset, err_line, err_col, evalue);
                else
                    PyErr_Format(etype, "Parse error at offset %zu: %S",
                                 offset, evalue);
                Py_DECREF(etype);
                Py_DECREF(evalue);
                Py_XDECREF(etraceback);
            }
            else
                PyErr_Restore(etype, evalue, etraceback);
        }
        else if (err_line)
            PyErr_Format(decode_error,
                         "Parse error at offset %zu (line %zu, column %zu):"
                         " %s",
                         offset, err_line, err_col,
                         GetParseError_En(reader.GetParseErrorCode()));
        else
            PyErr_Format(decode_error, "Parse error at offset %zu: %s",
                         offset, GetParseError_En(reader.GetParseErrorCode()));

        Py_XDECREF(handler.root);
        return nullptr;
    } else if (PyErr_Occurred()) {
        // Catch possible error raised in associated stream operations
        Py_XDECREF(handler.root);
        return nullptr;
    }

    return handler.root;
}


static PyObject*
decoder_raw_decode(PyObject* self, PyObject* jsonObject, PyObject* chunkSizeObj)
{
    size_t chunkSize = 65536;

    if (chunkSizeObj && chunkSizeObj != Py_None) {
        if (PyLong_Check(chunkSizeObj)) {
            Py_ssize_t size = PyNumber_AsSsize_t(chunkSizeObj, PyExc_ValueError);
            if (PyErr_Occurred() || size < 4 || size > UINT_MAX) {
                PyErr_SetString(PyExc_ValueError,
                                "Invalid chunk_size, must be an integer between 4 and"
                                " UINT_MAX");
                return nullptr;
            }
            chunkSize = (size_t) size;
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "chunk_size must be an unsigned integer value or None");
            return nullptr;
        }
    }

    Py_ssize_t jsonStrLen;
    const char* jsonStr;
    PyObject* asUnicode = nullptr;

    if (PyUnicode_Check(jsonObject)) {
        jsonStr = PyUnicode_AsUTF8AndSize(jsonObject, &jsonStrLen);
        if (jsonStr == nullptr)
            return nullptr;
    } else if (PyBytes_Check(jsonObject)) {
        // le tampon bytes est déjà de l'utf-8 (exigence JSON) : parse direct,
        // sans le décoder-recoder via un unicode intermédiaire (deux copies
        // pleines évitées, mesurées +25 ms sur 72 Mo) ; une séquence utf-8
        // invalide dans une chaîne est détectée à la création du str
        char* bytesStr;
        if (PyBytes_AsStringAndSize(jsonObject, &bytesStr, &jsonStrLen) == -1)
            return nullptr;
        jsonStr = bytesStr;
    } else if (PyByteArray_Check(jsonObject)) {
        jsonStr = PyByteArray_AS_STRING(jsonObject);   // NUL-terminé (CPython)
        jsonStrLen = PyByteArray_GET_SIZE(jsonObject);
    } else if (PyObject_HasAttr(jsonObject, read_name)) {
        jsonStr = nullptr;
        jsonStrLen = 0;
    } else {
        PyErr_SetString(PyExc_TypeError,
                        "Expected string or UTF-8 encoded bytes or bytearray");
        return nullptr;
    }

    DecoderObject* d = (DecoderObject*) self;

    PyObject* result = do_decode(self, jsonStr, jsonStrLen, jsonObject, chunkSize, nullptr,
                                 d->numberMode, d->datetimeMode, d->uuidMode,
                                 d->parseMode);

    if (asUnicode != nullptr)
        Py_DECREF(asUnicode);

    return result;
}


// _decode : le décodage brut exposé au Python (voir decoder_methods)
static PyObject*
decoder_decode_fn(PyObject* self, PyObject* args, PyObject* kwargs)
{
    static char const* kwlist[] = {
        "json",
        "chunk_size",
        nullptr
    };
    PyObject* jsonObject;
    PyObject* chunkSizeObj = nullptr;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|$O",
                                     (char**) kwlist,
                                     &jsonObject,
                                     &chunkSizeObj))
        return nullptr;

    return decoder_raw_decode(self, jsonObject, chunkSizeObj);
}


// le __call__ du décodeur : pour un Decoder serializejson enregistré, tout
// le protocole d'appel est fait ici (l'ancien Decoder.__call__ Python) —
// poussée amortie, attributs volatils, drapeaux du chemin rapide, queue des
// doublons. Les chemins rares (défaut de garde, mise à jour d'objet,
// doublons non résolus) rappellent des aides Python.
static PyObject*
decoder_call(PyObject* self, PyObject* args, PyObject* kwargs)
{
    static char const* kwlist[] = {
        "json",
        "obj",
        "chunk_size",
        nullptr
    };
    PyObject* jsonObject;
    PyObject* obj = nullptr;
    PyObject* chunkSizeObj = nullptr;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O$O",
                                     (char**) kwlist,
                                     &jsonObject,
                                     &obj,
                                     &chunkSizeObj))
        return nullptr;

    if (!sj_is_registered(self, sj_decoder_type)) {
        if (obj != nullptr && obj != Py_None) {
            PyErr_SetString(PyExc_TypeError,
                            "obj is only supported by serializejson decoders");
            return nullptr;
        }
        return decoder_raw_decode(self, jsonObject, chunkSizeObj);
    }

    // garde amortie des paramètres globaux : mêmes comparaisons que
    // l'ancienne voie Python (identité, jamais d'égalité par valeur : un
    // défaut à tort ne coûte qu'une repoussée, un succès à tort serait faux)
    PyObject* ownerObj = PyObject_GetAttr(sj_params_module, decoder_owner_name);
    if (ownerObj == nullptr)
        PyErr_Clear();
    bool pushed = (ownerObj == self);
    Py_XDECREF(ownerObj);
    if (pushed) {
        PyObject* guardNames[3] =
            {strict_pickle_name, setters_name, properties_name};
        for (int gi = 0; gi < 3 && pushed; gi++) {
            PyObject* a = PyObject_GetAttr(sj_params_module, guardNames[gi]);
            if (a == nullptr)
                PyErr_Clear();
            PyObject* b = PyObject_GetAttr(self, guardNames[gi]);
            if (b == nullptr)
                PyErr_Clear();
            pushed = (a != nullptr && a == b);
            Py_XDECREF(a);
            Py_XDECREF(b);
        }
    }
    if (!pushed) {
        PyObject* r =
            PyObject_CallMethodNoArgs(self, push_decode_parameters_name);
        if (r == nullptr)
            return nullptr;
        Py_DECREF(r);
    }

    // attributs volatils du chargement
    if (sj_set_new_volatile(self, converted_numpy_name, PySet_New(nullptr)) < 0
        || sj_set_new_volatile(self, not_authorized_name,
                               PySet_New(nullptr)) < 0
        || PyObject_GenericSetAttr(self, updating_name, Py_False) < 0
        || PyObject_GenericSetAttr(self, root_attr_name, Py_None) < 0
        || sj_set_new_volatile(self, duplicates_name, PyList_New(0)) < 0)
        return nullptr;

    // json_startswith_curly : les hooks Python s'en servent pour savoir si
    // .root sera connu pendant le parse (résolution immédiate des $ref)
    bool curly = false;
    if (PyUnicode_Check(jsonObject)) {
        curly = PyUnicode_GET_LENGTH(jsonObject) > 0
            && PyUnicode_READ_CHAR(jsonObject, 0) == '{';
    } else if (PyBytes_Check(jsonObject)) {
        curly = PyBytes_GET_SIZE(jsonObject) > 0
            && PyBytes_AS_STRING(jsonObject)[0] == '{';
    } else if (PyByteArray_Check(jsonObject)) {
        curly = PyByteArray_GET_SIZE(jsonObject) > 0
            && PyByteArray_AS_STRING(jsonObject)[0] == '{';
    } else {
        // flux : lit un caractère puis rembobine, comme la voie Python
        PyObject* one = PyObject_CallMethod(jsonObject, "read", "i", 1);
        if (one == nullptr)
            return nullptr;
        if (PyUnicode_Check(one))
            curly = PyUnicode_GET_LENGTH(one) == 1
                && PyUnicode_READ_CHAR(one, 0) == '{';
        else if (PyBytes_Check(one))
            curly = PyBytes_GET_SIZE(one) == 1
                && PyBytes_AS_STRING(one)[0] == '{';
        Py_DECREF(one);
        PyObject* rewound = PyObject_CallMethod(jsonObject, "seek", "i", 0);
        if (rewound == nullptr)
            return nullptr;
        Py_DECREF(rewound);
    }
    if (PyObject_GenericSetAttr(self, startswith_curly_name,
                                curly ? Py_True : Py_False) < 0)
        return nullptr;

    if (obj != nullptr && obj != Py_None) {
        // mise à jour d'un objet existant (rare) : voie Python entière,
        // queue des doublons et nettoyage compris
        return PyObject_CallMethodObjArgs(self, call_update_name,
                                          jsonObject, obj, nullptr);
    }

    // chemin rapide : le C crée les dicts (start_object) et rend les dicts
    // ordinaires sans repasser par end_object quand aucune transformation
    // Python (dotdict, reconnaissance par attributs) ne s'applique
    bool fastPlain = true;
    PyObject* flagAttr = PyObject_GetAttr(self, dotdict_name);
    if (flagAttr == nullptr)
        PyErr_Clear();
    else {
        if (PyObject_IsTrue(flagAttr) == 1)
            fastPlain = false;
        Py_DECREF(flagAttr);
    }
    if (fastPlain) {
        flagAttr = PyObject_GetAttr(self, class_from_attributes_name);
        if (flagAttr == nullptr)
            PyErr_Clear();
        else {
            if (PyObject_IsTrue(flagAttr) == 1)
                fastPlain = false;
            Py_DECREF(flagAttr);
        }
    }
    if (PyObject_GenericSetAttr(self, fast_start_object_name, Py_True) < 0
        || PyObject_GenericSetAttr(self, fast_plain_end_object_name,
                                   fastPlain ? Py_True : Py_False) < 0)
        return nullptr;

    PyObject* loaded = decoder_raw_decode(self, jsonObject, chunkSizeObj);

    // rabaisse les drapeaux même sur échec (une exception ne doit pas les
    // laisser posés pour l'appel suivant), sans écraser l'exception en cours
    PyObject* etype = nullptr;
    PyObject* evalue = nullptr;
    PyObject* etb = nullptr;
    if (loaded == nullptr)
        PyErr_Fetch(&etype, &evalue, &etb);
    if (PyObject_GenericSetAttr(self, fast_start_object_name, Py_False) < 0)
        PyErr_Clear();
    if (PyObject_GenericSetAttr(self, fast_plain_end_object_name,
                                Py_False) < 0)
        PyErr_Clear();
    if (loaded == nullptr) {
        PyErr_Restore(etype, evalue, etb);
        return nullptr;
    }

    // queue des doublons non résolus pendant le parse (rare) : voie Python
    PyObject* dups = PyObject_GetAttr(self, duplicates_name);
    if (dups == nullptr)
        PyErr_Clear();
    else {
        if (PyList_CheckExact(dups) && PyList_GET_SIZE(dups) > 0) {
            PyObject* replaced = PyObject_CallMethodObjArgs(
                self, resolve_duplicates_name, loaded, nullptr);
            Py_DECREF(loaded);
            if (replaced == nullptr) {
                Py_DECREF(dups);
                return nullptr;
            }
            loaded = replaced;
        }
        Py_DECREF(dups);
        if (PyObject_GenericSetAttr(self, duplicates_name, nullptr) < 0)
            PyErr_Clear();
    }
    return loaded;
}


static PyObject*
decoder_new(PyTypeObject* type, PyObject* args, PyObject* kwargs)
{
    DecoderObject* d;
    PyObject* datetimeModeObj = nullptr;
    unsigned datetimeMode = DM_NONE;
    PyObject* uuidModeObj = nullptr;
    unsigned uuidMode = UM_NONE;
    PyObject* numberModeObj = nullptr;
    unsigned numberMode = NM_NAN;
    PyObject* parseModeObj = nullptr;
    unsigned parseMode = PM_NONE;
    static char const* kwlist[] = {
        "number_mode",
        "datetime_mode",
        "uuid_mode",
        "parse_mode",
        nullptr
    };

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|OOOO:Decoder",
                                     (char**) kwlist,
                                     &numberModeObj,
                                     &datetimeModeObj,
                                     &uuidModeObj,
                                     &parseModeObj))
        return nullptr;

    if (numberModeObj) {
        if (numberModeObj == Py_None) {
            numberMode = NM_NONE;
        } else if (PyLong_Check(numberModeObj)) {
            int mode = PyLong_AsLong(numberModeObj);
            if (mode < 0 || mode >= NM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid number_mode");
                return nullptr;
            }
            numberMode = (unsigned) mode;
            if (numberMode & NM_DECIMAL && numberMode & NM_NATIVE) {
                PyErr_SetString(PyExc_ValueError,
                                "Combining NM_NATIVE with NM_DECIMAL is not supported");
                return nullptr;
            }
        }
    }

    if (datetimeModeObj) {
        if (datetimeModeObj == Py_None) {
            datetimeMode = DM_NONE;
        } else if (PyLong_Check(datetimeModeObj)) {
            int mode = PyLong_AsLong(datetimeModeObj);
            if (!valid_datetime_mode(mode)) {
                PyErr_SetString(PyExc_ValueError, "Invalid datetime_mode");
                return nullptr;
            }
            datetimeMode = (unsigned) mode;
            if (datetimeMode && datetime_mode_format(datetimeMode) != DM_ISO8601) {
                PyErr_SetString(PyExc_ValueError,
                                "Invalid datetime_mode, can deserialize only from"
                                " ISO8601");
                return nullptr;
            }
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "datetime_mode must be a non-negative integer value or None");
            return nullptr;
        }
    }

    if (uuidModeObj) {
        if (uuidModeObj == Py_None) {
            uuidMode = UM_NONE;
        } else if (PyLong_Check(uuidModeObj)) {
            int mode = PyLong_AsLong(uuidModeObj);
            if (mode < 0 || mode >= UM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid uuid_mode");
                return nullptr;
            }
            uuidMode = (unsigned) mode;
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "uuid_mode must be an integer value or None");
            return nullptr;
        }
    }

    if (parseModeObj) {
        if (parseModeObj == Py_None) {
            parseMode = PM_NONE;
        } else if (PyLong_Check(parseModeObj)) {
            int mode = PyLong_AsLong(parseModeObj);
            if (mode < 0 || mode >= PM_MAX) {
                PyErr_SetString(PyExc_ValueError, "Invalid parse_mode");
                return nullptr;
            }
            parseMode = (unsigned) mode;
        } else {
            PyErr_SetString(PyExc_TypeError,
                            "parse_mode must be an integer value or None");
            return nullptr;
        }
    }

    d = (DecoderObject*) type->tp_alloc(type, 0);
    if (d == nullptr)
        return nullptr;

    d->datetimeMode = datetimeMode;
    d->uuidMode = uuidMode;
    d->numberMode = numberMode;
    d->parseMode = parseMode;
    d->sjValCache = nullptr;
    d->sjValCacheCount = 0;
    d->sjValCacheBudget = 512;

    return (PyObject*) d;
}


/////////////
// Encoder //
/////////////


struct DictItem {
    const char* key_str;
    Py_ssize_t key_size;
    PyObject* item;

    DictItem(const char* k,
             Py_ssize_t s,
             PyObject* i)
        : key_str(k),
          key_size(s),
          item(i)
        {}

    bool operator<(const DictItem& other) const {
        Py_ssize_t tks = this->key_size;
        Py_ssize_t oks = other.key_size;
        int cmp = strncmp(this->key_str, other.key_str, tks < oks ? tks : oks);
        return (cmp == 0) ? (tks < oks) : (cmp < 0);
    }
};


static inline bool
sj_all_keys_exact_int64(PyObject* dict) {
    Py_ssize_t pos = 0;
    PyObject* key;
    PyObject* value;
    while (PyDict_Next(dict, &pos, &key, &value)) {
        if (!PyLong_CheckExact(key))
            return false;
        int overflow;
        long long v = PyLong_AsLongLongAndOverflow(key, &overflow);
        (void) v;
        if (overflow != 0)
            return false;
        if (PyErr_Occurred()) {
            PyErr_Clear();
            return false;
        }
    }
    return true;
}

static inline bool
all_keys_are_string(PyObject* dict) {
    Py_ssize_t pos = 0;
    PyObject* key;

    while (PyDict_Next(dict, &pos, &key, nullptr))
        if (!PyUnicode_Check(key))
            return false;
    return true;
}

// un dict utilisateur contenant une clé RÉSERVÉE du format (__class__,
// $ref) serait relu comme un objet ou une référence : il doit passer par
// l'enveloppe {"__class__": "dict", ...} avec la clé échappée entre
// apostrophes (voie Python), comme les dicts à clés non-str
static bool
sj_dict_has_reserved_key(PyObject* dict)
{
    return PyDict_GetItem(dict, class_key_name) != nullptr
        || PyDict_GetItem(dict, ref_key_name) != nullptr;
}

// noms PORTEURS d'une enveloppe d'objet : un attribut ainsi nommé ne peut
// pas être aplati à côté de l'étiquette (il l'écraserait au rechargement) —
// l'état part alors sous "__state__" (via la voie Python, qui décide)
static inline bool
sj_name_is_reserved(const char* s, Py_ssize_t len)
{
    return (len == 9 && (memcmp(s, "__class__", 9) == 0
                         || memcmp(s, "__state__", 9) == 0
                         || memcmp(s, "__items__", 9) == 0))
        || (len == 8 && (memcmp(s, "__init__", 8) == 0
                         || memcmp(s, "__dict__", 8) == 0))
        || (len == 7 && memcmp(s, "__new__", 7) == 0)
        || (len == 4 && memcmp(s, "$ref", 4) == 0);
}

// pré-passe filtrée au premier octet : seules les clés commençant par '_'
// ou '$' paient une comparaison ; au moindre doute (clé illisible), vrai
static bool
sj_state_key_reserved(PyObject* state)
{
    Py_ssize_t pos = 0;
    PyObject* key;
    while (PyDict_Next(state, &pos, &key, nullptr)) {
        if (!PyUnicode_Check(key))
            continue;
        Py_ssize_t len;
        const char* s = PyUnicode_AsUTF8AndSize(key, &len);
        if (s == nullptr) {
            PyErr_Clear();
            return true;
        }
        if (len >= 4 && (s[0] == '_' || s[0] == '$')
            && sj_name_is_reserved(s, len))
            return true;
    }
    return false;
}


// Écrit une valeur numérique du buffer (code de format du protocole buffer).
// Retourne false pour un NaN/Inf refusé par numberMode ou un format inconnu.
template<typename WriterT>
static bool
write_buffer_value(WriterT* writer, char code, const char* ptr, unsigned numberMode)
{
    switch (code) {
    case 'd': case 'f': {
        double value = (code == 'd') ? *(const double*) ptr
                                     : (double) *(const float*) ptr;
        if (IS_NAN(value)) {
            if (!(numberMode & NM_NAN)) {
                PyErr_SetString(PyExc_ValueError,
                                "Out of range float values are not JSON compliant");
                return false;
            }
            writer->RawValue("NaN", 3);
        } else if (IS_INF(value)) {
            if (!(numberMode & NM_NAN)) {
                PyErr_SetString(PyExc_ValueError,
                                "Out of range float values are not JSON compliant");
                return false;
            }
            writer->RawValue(value < 0 ? "-Infinity" : "Infinity",
                             value < 0 ? 9 : 8);
        } else {
            // graphie EXACTE de repr() : Ryu en direct (total, jamais
            // d'échec)
            char repr_buf[40];
            writer->RawValue(repr_buf,
                             (size_t) sjdtoa::ReprDouble(value, repr_buf));
        }
        return true;
    }
    case 'b': writer->Int64(*(const signed char*) ptr); return true;
    case 'h': writer->Int64(*(const short*) ptr); return true;
    case 'i': writer->Int64(*(const int*) ptr); return true;
    case 'l': writer->Int64((int64_t) *(const long*) ptr); return true;
    case 'q': writer->Int64((int64_t) *(const long long*) ptr); return true;
    case 'B': writer->Uint64(*(const unsigned char*) ptr); return true;
    case 'H': writer->Uint64(*(const unsigned short*) ptr); return true;
    case 'I': writer->Uint64(*(const unsigned int*) ptr); return true;
    case 'L': writer->Uint64((uint64_t) *(const unsigned long*) ptr); return true;
    case 'Q': writer->Uint64((uint64_t) *(const unsigned long long*) ptr); return true;
    case '?': writer->Bool(*(const char*) ptr != 0); return true;
    }
    PyErr_Format(PyExc_TypeError, "ArrayRows: unsupported buffer format '%c'", code);
    return false;
}


// Écrit un buffer numérique 1D/2D en lignes lisibles : lignes compactes
// [v,v,...], tableau extérieur indenté pour la 2D.
template<typename WriterT>
static bool
write_buffer_rows(WriterT* writer, PyObject* arrayObj, unsigned numberMode)
{
    Py_buffer view;
    if (PyObject_GetBuffer(arrayObj, &view,
                           PyBUF_C_CONTIGUOUS | PyBUF_FORMAT) != 0)
        return false;
    const char* format = view.format ? view.format : "B";
    if (*format == '@' || *format == '=' || *format == '<' || *format == '>'
        || *format == '!')
        format++;
    char code = *format;
    bool ok = true;
    size_t itemsize = (size_t) view.itemsize;
    const char* data = (const char*) view.buf;
    if (view.ndim == 1) {
        bool pushed = !writer->InCompact();
        if (pushed)
            writer->PushCompact();
        writer->StartArray();
        Py_ssize_t count = view.shape[0];
        for (Py_ssize_t i = 0; ok && i < count; i++)
            ok = write_buffer_value(writer, code, data + i * itemsize, numberMode);
        if (ok)
            writer->EndArray();
        if (pushed)
            writer->PopCompact();
    } else if (view.ndim == 2) {
        writer->StartArray();
        Py_ssize_t rows = view.shape[0];
        Py_ssize_t columns = view.shape[1];
        for (Py_ssize_t row = 0; ok && row < rows; row++) {
            bool pushed = !writer->InCompact();
            if (pushed)
                writer->PushCompact();
            writer->StartArray();
            const char* row_data = data + row * columns * itemsize;
            for (Py_ssize_t column = 0; ok && column < columns; column++)
                ok = write_buffer_value(writer, code,
                                        row_data + column * itemsize, numberMode);
            if (ok)
                writer->EndArray();
            if (pushed)
                writer->PopCompact();
        }
        if (ok)
            writer->EndArray();
    } else {
        PyErr_SetString(PyExc_TypeError, "ArrayRows: only 1D and 2D buffers");
        ok = false;
    }
    PyBuffer_Release(&view);
    return ok;
}


// préfiltre des clés str des dicts à clés non-str, miroir exact de la regex
// python _cle_nombre_json : -?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?$ — une clé
// qui EST un nombre json serait relue comme nombre, donc doit être échappée
static bool
sj_cle_nombre_json(const char* s, size_t l)
{
    size_t i = 0;
    if (i < l && s[i] == '-')
        i++;
    if (i >= l)
        return false;
    if (s[i] == '0') {
        i++;
    } else if (s[i] >= '1' && s[i] <= '9') {
        i++;
        while (i < l && s[i] >= '0' && s[i] <= '9')
            i++;
    } else {
        return false;
    }
    if (i < l && s[i] == '.') {
        i++;
        size_t debut = i;
        while (i < l && s[i] >= '0' && s[i] <= '9')
            i++;
        if (i == debut)
            return false;
    }
    if (i < l && (s[i] == 'e' || s[i] == 'E')) {
        i++;
        if (i < l && (s[i] == '+' || s[i] == '-'))
            i++;
        size_t debut = i;
        while (i < l && s[i] >= '0' && s[i] <= '9')
            i++;
        if (i == debut)
            return false;
    }
    return i == l;
}


// sonde du préfiltre pour les clés commençant par [, { ou " : une clé qui se
// parse comme du json valide serait relue comme autre chose qu'une chaîne —
// mêmes acceptations que rapidjson.loads par défaut (NaN/Infinity admis,
// grands entiers relus en chaînes, pas de virgule traînante ni commentaire).
// s est le tampon utf8 de PyUnicode_AsUTF8 : terminé par NUL à s[l]
static bool
sj_cle_parse_json(const char* s)
{
    Reader reader;
    BaseReaderHandler<UTF8<> > handler;
    StringStream ss(s);
    reader.Parse<kParseFullPrecisionFlag | kParseBigIntsAsStringsFlag
                 | kParseNanAndInfFlag>(ss, handler);
    return !reader.HasParseError();
}


// Écrit la GRAPHIE JSON d'une clé tuple ou frozenset dans `texte` (voir la
// définition, après dumps_internal). Retourne false, erreur python posée.
static bool
sj_cle_native(PyObject* key, PathTracker* pathTracker, unsigned datetimeMode,
              unsigned uuidMode, unsigned bytesMode, unsigned iterableMode,
              unsigned mappingMode, std::string& texte, bool* non_ascii);


template<typename WriterT>
static bool
dumps_internal(
    WriterT* writer,
    PyObject* object,
    PyObject* defaultFn,
    PyObject* defaultDictFn,
    PyObject* defaultListFn,
    PathTracker* pathTracker,
    unsigned numberMode,
    unsigned datetimeMode,
    unsigned uuidMode,
    unsigned bytesMode,
    unsigned iterableMode,
    unsigned mappingMode)
{
    int is_decimal;

    // consomme le marqueur "dict d'attributs" posé par la branche defaultFn :
    // il ne concerne que la valeur immédiatement recursée après default()
    bool attrsDict = false;
    if (pathTracker) {
        attrsDict = pathTracker->next_dict_is_attrs;
        pathTracker->next_dict_is_attrs = false;
    } else {
        // dumps SANS pathTracker (encodage des clés complexes, API brute) :
        // même marqueur one-shot, porté par un drapeau de module sous GIL —
        // sans lui, l'enveloppe produite par default() (qui contient
        // "__class__" par construction) serait renvoyée à default() en boucle
        attrsDict = sj_next_dict_is_attrs_noplan;
        sj_next_dict_is_attrs_noplan = false;
    }

    // Consomme une unité du budget de récursion de CPython à chaque niveau,
    // en plus de celles prises autour des RECURSE : la détection de profondeur
    // se déclenche ainsi bien avant l'épuisement de la pile C, quelle que soit
    // la taille des frames (segfault constaté sinon sur 3.12/3.13, dont la
    // marge C_RECURSION_LIMIT est plus étroite que 3.10/3.11/3.14).
    struct DepthGuard {
        bool ok;
        explicit DepthGuard(const char* msg) {
            ok = !Py_EnterRecursiveCall(msg);
        }
        ~DepthGuard() {
            if (ok)
                Py_LeaveRecursiveCall();
        }
    } depth_guard(" while JSONifying value");
    if (!depth_guard.ok)
        return false;

#define RECURSE(v) dumps_internal(writer, v, defaultFn,                 \
                                  defaultDictFn, defaultListFn,         \
                                  pathTracker,                          \
                                  numberMode, datetimeMode, uuidMode,   \
                                  bytesMode, iterableMode, mappingMode)

#define PATH_PUSH_INDEX(i)                                              \
    if (pathTracker) {                                                  \
        pathTracker->segments.push_back(                                \
            {PathSegment::INDEX, nullptr, 0, (Py_ssize_t) (i)});        \
        pathTracker->registered.push_back(-1);                          \
    }
#define PATH_PUSH_KEY(s, l)                                             \
    if (pathTracker) {                                                  \
        pathTracker->segments.push_back(                                \
            {attrsDict ? PathSegment::ATTR : PathSegment::KEY,          \
             s, (size_t) (l), 0});                                      \
        pathTracker->registered.push_back(-1);                          \
    }
#define PATH_POP()                                                      \
    if (pathTracker) {                                                  \
        pathTracker->segments.pop_back();                               \
        pathTracker->registered.pop_back();                             \
        if (pathTracker->firstUnregistered                              \
                > pathTracker->registered.size())                       \
            pathTracker->firstUnregistered =                            \
                pathTracker->registered.size();                         \
    }

// Mémo C++ des conteneurs (encoder memo_refs=True) : si le dict/liste a déjà
// été écrit, émet {"$ref": "chemin"} et sort de la branche ; sinon l'insère
// dans le mémo (référence forte relâchée en fin d'encodage) et continue.
#define CONTAINER_MEMO_OR_REF()                                         \
    if (pathTracker && pathTracker->memoContainers) {                   \
        bool memo_found;                                                \
        PtrMemo::Slot* memo_slot =                                      \
            pathTracker->memo.find_or_reserve(object, &memo_found);     \
        if (memo_found) {                                               \
            const std::string& ref_ =                                   \
                sj_ref_json(pathTracker, memo_slot->second);            \
            writer->RawValue(ref_.data(), ref_.size());                 \
            return true;                                                \
        }                                                               \
        memo_slot->second = path_tracker_materialize(pathTracker);      \
        Py_INCREF(object);                                              \
    }

// Appelle le hook default_dict/default_list de l'Encoder s'il existe : s'il
// retourne un autre objet (ex: RawString {"$ref": ...}), on sérialise ce
// remplacant à la place ; s'il retourne l'objet lui-même, chemin natif.
#define CALL_CONTAINER_HOOK(hookFn, msg)                                \
    if (hookFn) {                                                       \
        PyObject* replacement =                                         \
            PyObject_CallFunctionObjArgs(hookFn, object, nullptr);      \
        if (replacement == nullptr)                                     \
            return false;                                               \
        if (replacement != object) {                                    \
            if (Py_EnterRecursiveCall(msg)) {                           \
                Py_DECREF(replacement);                                 \
                return false;                                           \
            }                                                           \
            bool hook_r = RECURSE(replacement);                         \
            Py_LeaveRecursiveCall();                                    \
            Py_DECREF(replacement);                                     \
            return hook_r;                                              \
        }                                                               \
        Py_DECREF(replacement);                                         \
    }

#define ASSERT_VALID_SIZE(l) do {                                       \
    if (l < 0 || l > UINT_MAX) {                                        \
        PyErr_SetString(PyExc_ValueError, "Out of range string size");  \
        return false;                                                   \
    } } while(0)

    // str unicode (exact) — testé en PREMIER : c'est le type le plus fréquent
    // et il était aiguillé après une douzaine d'autres branches
    if (PyUnicode_CheckExact(object)) {
        Py_ssize_t l;
        const char* s = PyUnicode_AsUTF8AndSize(object, &l);
        if (!PyUnicode_IS_ASCII(object))
            writer->MarkMaybeNonAscii();
        // PyString_ plutôt que String : en connaissant l'objet, un flux vers
        // fichier remet les grands str propres en zéro-copie à son thread
        // d'écriture ; partout ailleurs, même chemin qu'avant
        writer->PyString_(object, s, (SizeType) l);
    }

    // None -------------------------------------
    else if (object == Py_None) {
        writer->Null();
    }

	// True, False  -----------------------------
	else if (PyBool_Check(object)) {
        writer->Bool(object == Py_True);
    }
	
    // Decimal ----------------------------------
	else if (numberMode & NM_DECIMAL
               && (is_decimal = PyObject_IsInstance(object, decimal_type))) {
        if (is_decimal == -1) {
            return false;
        }

        if (!(numberMode & NM_NAN)) {
            bool is_inf_or_nan;
            PyObject* is_inf = PyObject_CallMethodObjArgs(object, is_infinite_name,
                                                          nullptr);

            if (is_inf == nullptr) {
                return false;
            }
            is_inf_or_nan = is_inf == Py_True;
            Py_DECREF(is_inf);

            if (!is_inf_or_nan) {
                PyObject* is_nan = PyObject_CallMethodObjArgs(object, is_nan_name,
                                                              nullptr);

                if (is_nan == nullptr) {
                    return false;
                }
                is_inf_or_nan = is_nan == Py_True;
                Py_DECREF(is_nan);
            }

            if (is_inf_or_nan) {
                PyErr_SetString(PyExc_ValueError,
                                "Out of range decimal values are not JSON compliant");
                return false;
            }
        }

        PyObject* decStrObj = PyObject_Str(object);
        if (decStrObj == nullptr)
            return false;

        Py_ssize_t size;
        const char* decStr = PyUnicode_AsUTF8AndSize(decStrObj, &size);
        if (decStr == nullptr) {
            Py_DECREF(decStrObj);
            return false;
        }

        writer->RawValue(decStr, size);
        Py_DECREF(decStrObj);
    } 
	
	// int ---------------------------------------------------------------
	else if (PyLong_Check(object)) {
        if (numberMode & NM_NATIVE) {
            int overflow;
            long long i = PyLong_AsLongLongAndOverflow(object, &overflow);
            if (i == -1 && PyErr_Occurred())
                return false;

            if (overflow == 0) {
                writer->Int64(i);
            } else {
                unsigned long long ui = PyLong_AsUnsignedLongLong(object);
                if (PyErr_Occurred())
                    return false;

                writer->Uint64(ui);
            }
        } else if (PyLong_CheckExact(object)) {
            // un int EXACT qui tient sur 64 bits s'écrit à l'identique de son
            // repr() (chiffres décimaux minimaux) : écriture directe, sans
            // créer de chaîne Python — repr() ne reste nécessaire que pour
            // les entiers hors gamme 64 bits et les sous-classes (IntEnum...)
            int overflow;
            long long i = PyLong_AsLongLongAndOverflow(object, &overflow);
            if (i == -1 && PyErr_Occurred())
                return false;
            if (overflow == 0) {
                writer->Int64(i);
            } else if (overflow > 0) {
                unsigned long long ui = PyLong_AsUnsignedLongLong(object);
                if (!PyErr_Occurred()) {
                    writer->Uint64(ui);
                } else {
                    PyErr_Clear();  // > 64 bits : repr()
                    PyObject* intStrObj = PyLong_Type.tp_repr(object);
                    if (intStrObj == nullptr)
                        return false;
                    Py_ssize_t repr_size;
                    const char* intStr =
                        PyUnicode_AsUTF8AndSize(intStrObj, &repr_size);
                    if (intStr == nullptr) {
                        Py_DECREF(intStrObj);
                        return false;
                    }
                    writer->RawValue(intStr, repr_size);
                    Py_DECREF(intStrObj);
                }
            } else {  // < -2^63 : repr()
                PyObject* intStrObj = PyLong_Type.tp_repr(object);
                if (intStrObj == nullptr)
                    return false;
                Py_ssize_t repr_size;
                const char* intStr =
                    PyUnicode_AsUTF8AndSize(intStrObj, &repr_size);
                if (intStr == nullptr) {
                    Py_DECREF(intStrObj);
                    return false;
                }
                writer->RawValue(intStr, repr_size);
                Py_DECREF(intStrObj);
            }
        } else {
            // Mimic stdlib json: subclasses of int may override __repr__, but we still
            // want to encode them as integers in JSON; one example within the standard
            // library is IntEnum

            PyObject* intStrObj = PyLong_Type.tp_repr(object);
            if (intStrObj == nullptr)
                return false;

            Py_ssize_t size;
            const char* intStr = PyUnicode_AsUTF8AndSize(intStrObj, &size);
            if (intStr == nullptr) {
                Py_DECREF(intStrObj);
                return false;
            }
            writer->RawValue(intStr,size);
            Py_DECREF(intStrObj);
        }
    } 
	
	// float ---------------------------------------------------------------
	else if (PyFloat_Check(object)) {
        double d = PyFloat_AsDouble(object);
        if (d == -1.0 && PyErr_Occurred())
            return false;
        if (IS_NAN(d)) {
            if (numberMode & NM_NAN) {
                writer->RawValue("NaN", 3);
            } else {
                PyErr_SetString(PyExc_ValueError,
                                "Out of range float values are not JSON compliant");
                return false;
            }
        } else if (IS_INF(d)) {
            if (!(numberMode & NM_NAN)) {
                PyErr_SetString(PyExc_ValueError,
                                "Out of range float values are not JSON compliant");
                return false;
            } else if (d < 0) {
                writer->RawValue("-Infinity", 9);
            } else {
                writer->RawValue("Infinity", 8);
            }
        } else {
            // graphie EXACTE de repr(), sans passer par le __repr__ des
            // sous-classes (numpy 2 float64 donnerait "np.float64(0.0)") :
            // Ryu mémoïsé par motif de bits (sj_float_repr)
            size_t repr_len;
            const char* repr_str = sj_float_repr(d, &repr_len);
            writer->RawValue(repr_str, repr_len);
        }
    }
	
	// str unicode ---------------------------------------------------------------
	else if (PyUnicode_Check(object)) {
        Py_ssize_t l;
        const char* s = PyUnicode_AsUTF8AndSize(object, &l);
        if (!PyUnicode_IS_ASCII(object))
            writer->MarkMaybeNonAscii();
        writer->PyString_(object, s, (SizeType) l);
    }
	
	// liste  ---------------------------------------------------------------
	else if ((!(iterableMode & IM_ONLY_LISTS) && PyList_Check(object))
               ||
               PyList_CheckExact(object)) {
        CONTAINER_MEMO_OR_REF()
        CALL_CONTAINER_HOOK(defaultListFn, " while JSONifying list object")

        Py_ssize_t size = PyList_GET_SIZE(object);

        // liste homogène de nombres -> une seule ligne (même sémantique que
        // _onlyOneDimSameTypeNumbers : tous les éléments du type EXACT du
        // premier, qui doit être numérique et non complexe)
        bool compact_numbers = false;
        PyTypeObject* first_type = nullptr;
        if (pathTracker && pathTracker->singleLineNumbers && size > 0) {
            PyObject* first = PyList_GET_ITEM(object, 0);
            first_type = Py_TYPE(first);
            if (first_type == &PyFloat_Type || first_type == &PyLong_Type
                || first_type == &PyBool_Type
                || (PyNumber_Check(first) && !PyComplex_Check(first))) {
                compact_numbers = true;
                for (Py_ssize_t i = 1; i < size; i++) {
                    if (Py_TYPE(PyList_GET_ITEM(object, i)) != first_type) {
                        compact_numbers = false;
                        break;
                    }
                }
            }
        }
        // ne bascule que si on n'est pas déjà en compact (imbrication redondante,
        // qui déséquilibrerait le compteur si deux demandes précédaient le 1er jeton)
        bool pushed_compact = compact_numbers && !writer->InCompact();
        if (pushed_compact)
            writer->PushCompact();

        writer->StartArray();

        if (compact_numbers
            && (first_type == &PyBool_Type || first_type == &PyLong_Type
                || first_type == &PyFloat_Type)) {
            // boucle serrée pour les listes homogènes de scalaires : mêmes
            // écritures que le chemin générique (octets identiques), sans
            // aiguillage de type, garde de récursion ni chemin par élément
            if (first_type == &PyBool_Type) {
                for (Py_ssize_t i = 0; i < size; i++)
                    writer->Bool(PyList_GET_ITEM(object, i) == Py_True);
            } else if (first_type == &PyLong_Type) {
                // au-delà du seuil : extraction sous GIL puis conversion en
                // texte par tranches sur plusieurs threads (octets identiques,
                // repli séquentiel si un entier déborde 64 bits)
                bool mt_written = false;
                if (size >= SJ_NUM_MT_MIN && pathTracker
                    && pathTracker->mtScratch) {
                    std::vector<long long>& vals = pathTracker->mtScratch->ivals;
                    vals.resize((size_t) size);
                    bool extractable = true;
                    for (Py_ssize_t i = 0; i < size; i++) {
                        int mt_overflow;
                        vals[(size_t) i] = PyLong_AsLongLongAndOverflow(
                            PyList_GET_ITEM(object, i), &mt_overflow);
                        if (mt_overflow != 0) {
                            extractable = false;
                            break;
                        }
                    }
                    if (extractable) {
                        static const size_t sj_hw =
                            std::thread::hardware_concurrency();
                        size_t nthreads = std::min<size_t>(
                            std::min<size_t>(8, sj_hw),
                            (size_t) size / SJ_NUM_MT_CHUNK);
                        if (nthreads >= 2) {
                            size_t nchunks = ((size_t) size + SJ_NUM_MT_CHUNK - 1)
                                             / SJ_NUM_MT_CHUNK;
                            std::vector<sj_numchunk>& chunks =
                                pathTracker->mtScratch->chunks;
                            chunks.resize(nchunks);
                            Py_BEGIN_ALLOW_THREADS
                            sj_render_chunks_parallel<long long, sj_render_int_chunk>(
                                vals.data(), (size_t) size, chunks, nthreads);
                            Py_END_ALLOW_THREADS
                            if (!sj_splice_chunks(writer, chunks)) {
                                if (pushed_compact)
                                    writer->PopCompact();
                                return false;
                            }
                            writer->AnnounceArrayValues((size_t) size);
                            mt_written = true;
                        }
                    }
                }
                if (!mt_written)
                for (Py_ssize_t i = 0; i < size; i++) {
                    PyObject* item = PyList_GET_ITEM(object, i);
                    int overflow;
                    long long value = PyLong_AsLongLongAndOverflow(item, &overflow);
                    if (value == -1 && PyErr_Occurred()) {
                        if (pushed_compact)
                            writer->PopCompact();
                        return false;
                    }
                    if (overflow == 0) {
                        writer->Int64(value);
                    } else {
                        // hors gamme 64 bits : même écriture que la branche int
                        unsigned long long uvalue = PyLong_AsUnsignedLongLong(item);
                        if (!PyErr_Occurred()) {
                            writer->Uint64(uvalue);
                        } else {
                            PyErr_Clear();
                            PyObject* intStrObj = PyLong_Type.tp_repr(item);
                            if (intStrObj == nullptr) {
                                if (pushed_compact)
                                    writer->PopCompact();
                                return false;
                            }
                            Py_ssize_t repr_size;
                            const char* intStr =
                                PyUnicode_AsUTF8AndSize(intStrObj, &repr_size);
                            if (intStr == nullptr) {
                                Py_DECREF(intStrObj);
                                if (pushed_compact)
                                    writer->PopCompact();
                                return false;
                            }
                            writer->RawValue(intStr, repr_size);
                            Py_DECREF(intStrObj);
                        }
                    }
                }
            } else {  // PyFloat_Type : repr() conservé (graphie de Python)
                bool mt_written = false;
                if (size >= SJ_NUM_MT_MIN && pathTracker
                    && pathTracker->mtScratch) {
                    std::vector<double>& vals = pathTracker->mtScratch->dvals;
                    vals.resize((size_t) size);
                    bool extractable = true;
                    for (Py_ssize_t i = 0; i < size; i++) {
                        double v = PyFloat_AS_DOUBLE(PyList_GET_ITEM(object, i));
                        if ((IS_NAN(v) || IS_INF(v)) && !(numberMode & NM_NAN)) {
                            extractable = false;  // la boucle séquentielle lèvera
                            break;
                        }
                        vals[(size_t) i] = v;
                    }
                    if (extractable) {
                        static const size_t sj_hw =
                            std::thread::hardware_concurrency();
                        size_t nthreads = std::min<size_t>(
                            std::min<size_t>(8, sj_hw),
                            (size_t) size / SJ_NUM_MT_CHUNK);
                        if (nthreads >= 2) {
                            size_t nchunks = ((size_t) size + SJ_NUM_MT_CHUNK - 1)
                                             / SJ_NUM_MT_CHUNK;
                            std::vector<sj_numchunk>& chunks =
                                pathTracker->mtScratch->chunks;
                            chunks.resize(nchunks);
                            Py_BEGIN_ALLOW_THREADS
                            sj_render_chunks_parallel<double, sj_render_double_chunk>(
                                vals.data(), (size_t) size, chunks, nthreads);
                            Py_END_ALLOW_THREADS
                            if (!sj_splice_chunks(writer, chunks)) {
                                if (pushed_compact)
                                    writer->PopCompact();
                                return false;
                            }
                            writer->AnnounceArrayValues((size_t) size);
                            mt_written = true;
                        }
                    }
                }
                if (!mt_written)
                for (Py_ssize_t i = 0; i < size; i++) {
                    PyObject* item = PyList_GET_ITEM(object, i);
                    double value = PyFloat_AS_DOUBLE(item);
                    if (IS_NAN(value) || IS_INF(value)) {
                        if (!(numberMode & NM_NAN)) {
                            PyErr_SetString(
                                PyExc_ValueError,
                                "Out of range float values are not JSON compliant");
                            if (pushed_compact)
                                writer->PopCompact();
                            return false;
                        }
                        if (IS_NAN(value))
                            writer->RawValue("NaN", 3);
                        else
                            writer->RawValue(value < 0 ? "-Infinity" : "Infinity",
                                             value < 0 ? 9 : 8);
                    } else {
                        char repr_buf[40];
                        writer->RawValue(repr_buf,
                                         (size_t) sjdtoa::ReprDouble(
                                             value, repr_buf));
                    }
                }
            }
        } else {
            for (Py_ssize_t i = 0; i < size; i++) {
                PyObject* item = PyList_GET_ITEM(object, i);
                if (PyUnicode_CheckExact(item)) {
                    // raccourci : écrit la chaîne sur place, sans payer
                    // l appel récursif complet (garde, chemin, aiguillage)
                    Py_ssize_t inline_length;
                    const char* inline_str =
                        PyUnicode_AsUTF8AndSize(item, &inline_length);
                    if (inline_str == nullptr) {
                        if (pushed_compact)
                            writer->PopCompact();
                        return false;
                    }
                    if (!PyUnicode_IS_ASCII(item))
                        writer->MarkMaybeNonAscii();
                    writer->PyString_(item, inline_str, (SizeType) inline_length);
                    continue;
                }
                if (Py_EnterRecursiveCall(" while JSONifying list object")) {
                    if (pushed_compact)
                        writer->PopCompact();
                    return false;
                }
                PATH_PUSH_INDEX(i);
                bool r = RECURSE(item);
                PATH_POP();
                Py_LeaveRecursiveCall();
                if (!r) {
                    if (pushed_compact)
                        writer->PopCompact();
                    return false;
                }
            }
        }

        writer->EndArray();
        if (pushed_compact)
            writer->PopCompact();
    } 
	else if (!(iterableMode & IM_ONLY_LISTS) && PyTuple_Check(object)) {
        writer->StartArray();

        Py_ssize_t size = PyTuple_GET_SIZE(object);

        for (Py_ssize_t i = 0; i < size; i++) {
            if (Py_EnterRecursiveCall(" while JSONifying tuple object"))
                return false;
            PyObject* item = PyTuple_GET_ITEM(object, i);
            PATH_PUSH_INDEX(i);
            bool r = RECURSE(item);
            PATH_POP();
            Py_LeaveRecursiveCall();
            if (!r)
                return false;
        }

        writer->EndArray();
    } 
	else if (!(iterableMode & IM_ONLY_LISTS) && PyIter_Check(object)) {
        PyObject* iterator = PyObject_GetIter(object);
        if (iterator == nullptr)
            return false;

        writer->StartArray();

        PyObject* item;
        Py_ssize_t iter_index = 0;
        while ((item = PyIter_Next(iterator))) {
            if (Py_EnterRecursiveCall(" while JSONifying iterable object")) {
                Py_DECREF(item);
                Py_DECREF(iterator);
                return false;
            }
            PATH_PUSH_INDEX(iter_index++);
            bool r = RECURSE(item);
            PATH_POP();
            Py_LeaveRecursiveCall();
            Py_DECREF(item);
            if (!r) {
                Py_DECREF(iterator);
                return false;
            }
        }

        Py_DECREF(iterator);

        // PyIter_Next() may exit with an error
        if (PyErr_Occurred())
            return false;

        writer->EndArray();
    } 
	
	// tuple : {"__class__": "tuple", "__new__": [éléments]} — le __new__
	// en compact quand single_line_new (défaut), octets identiques au chemin
	// Python (default + SingleLine)
	else if (PyTuple_CheckExact(object) && (iterableMode & IM_ONLY_LISTS)
             && pathTracker != nullptr) {
        CONTAINER_MEMO_OR_REF()
        writer->EnvelopeHead("tuple", 5, "__new__", 7);
        // segments en style ".attr" : le chemin qu'écrit la recette, et que le
        // balayage lit dans le fichier — sans lui, un $ref vers l'intérieur du
        // tuple désignait « root['t'][0] », que rien n'écrit ni ne balaye.
        // (pathTracker non nul : la branche l'exige)
        pathTracker->segments.push_back({PathSegment::ATTR, "__new__", 7, 0});
        pathTracker->registered.push_back(-1);
        // compact si single_line_new, ou si single_line_numbers et tuple
        // homogène de nombres (même règle que les listes)
        bool tuple_numbers = false;
        Py_ssize_t tuple_size_probe = PyTuple_GET_SIZE(object);
        if (!pathTracker->singleLineNew && pathTracker->singleLineNumbers
            && tuple_size_probe > 0) {
            PyTypeObject* first_type =
                Py_TYPE(PyTuple_GET_ITEM(object, 0));
            if (first_type == &PyFloat_Type || first_type == &PyLong_Type
                || first_type == &PyBool_Type) {
                tuple_numbers = true;
                for (Py_ssize_t pi = 1; pi < tuple_size_probe; pi++)
                    if (Py_TYPE(PyTuple_GET_ITEM(object, pi)) != first_type) {
                        tuple_numbers = false;
                        break;
                    }
            }
        }
        bool tuple_compact = (pathTracker->singleLineNew || tuple_numbers)
                             && !writer->InCompact();
        if (tuple_compact)
            writer->PushCompact();
        writer->StartArray();
        Py_ssize_t tuple_size = PyTuple_GET_SIZE(object);
        for (Py_ssize_t ti = 0; ti < tuple_size; ti++) {
            PyObject* item = PyTuple_GET_ITEM(object, ti);
            if (PyUnicode_CheckExact(item)) {
                Py_ssize_t inline_length;
                const char* inline_str =
                    PyUnicode_AsUTF8AndSize(item, &inline_length);
                if (inline_str == nullptr) {
                    if (tuple_compact)
                        writer->PopCompact();
                    return false;
                }
                if (!PyUnicode_IS_ASCII(item))
                    writer->MarkMaybeNonAscii();
                writer->PyString_(item, inline_str, (SizeType) inline_length);
                continue;
            }
            if (sj_write_scalar_inline(writer, item))
                continue;
            PATH_PUSH_INDEX(ti)
            bool r = RECURSE(item);
            PATH_POP()
            if (!r) {
                if (tuple_compact)
                    writer->PopCompact();
                return false;
            }
        }
        writer->EndArray();
        PATH_POP()
        if (tuple_compact)
            writer->PopCompact();
        writer->EndObject();
    }

	// datetime.datetime naïf : {"__class__": "datetime.datetime", "__init__":
	// "2026-09-24T18:26:00"} — texte RFC 9557, identique à isoformat() (le
	// greffon python écrit les datetimes avec fuseau : décalage, [zone])
	else if (PyDateTime_CheckExact(object) && pathTracker != nullptr
             && !pathTracker->strictPickle
             && PyDateTime_DATE_GET_TZINFO(object) == Py_None) {
        CONTAINER_MEMO_OR_REF()
        writer->EnvelopeHead("datetime.datetime", 17, "__init__", 8);
        int us = PyDateTime_DATE_GET_MICROSECOND(object);
        char iso[32];
        int n = snprintf(iso, sizeof(iso), "%04d-%02d-%02dT%02d:%02d:%02d",
                         PyDateTime_GET_YEAR(object),
                         PyDateTime_GET_MONTH(object),
                         PyDateTime_GET_DAY(object),
                         PyDateTime_DATE_GET_HOUR(object),
                         PyDateTime_DATE_GET_MINUTE(object),
                         PyDateTime_DATE_GET_SECOND(object));
        if (us)
            n += snprintf(iso + n, sizeof(iso) - n, ".%06d", us);
        writer->String(iso, n);
        writer->EndObject();
    }

	// datetime.time sans fuseau : {"__class__": "datetime.time", "__init__":
	// {"__class__": "bytes", "__new__": ["<b64 de 6 octets>","b64"]}} — la
	// forme reduce native (heure|0x80 si fold, mn, s, µs sur 3 octets)
	else if (PyTime_CheckExact(object)
             // PyDateTime_TIME_GET_TZINFO : le champ brut n'existe que si
             // hastzinfo — le lire directement rendait la branche MORTE
             // pour les times naïfs (mémoire indéfinie, jamais Py_None)
             && PyDateTime_TIME_GET_TZINFO(object) == Py_None
             && pathTracker != nullptr) {
        CONTAINER_MEMO_OR_REF()
        writer->EnvelopeHead("datetime.time", 13, "__init__", 8);
        writer->EnvelopeHead("bytes", 5, "__new__", 7);
        bool time_compact = pathTracker->singleLineNew && !writer->InCompact();
        if (time_compact)
            writer->PushCompact();
        writer->StartArray();
        {
            int us = PyDateTime_TIME_GET_MICROSECOND(object);
            unsigned char raw6[6] = {
                (unsigned char) (PyDateTime_TIME_GET_HOUR(object)
                                 | (PyDateTime_TIME_GET_FOLD(object)
                                    ? 0x80 : 0)),
                (unsigned char) PyDateTime_TIME_GET_MINUTE(object),
                (unsigned char) PyDateTime_TIME_GET_SECOND(object),
                (unsigned char) ((us >> 16) & 0xFF),
                (unsigned char) ((us >> 8) & 0xFF),
                (unsigned char) (us & 0xFF)};
            char b64_buf[9];
            serializejson_b64_encode(raw6, 6, b64_buf);
            writer->String(b64_buf, 8);
            writer->String("b64", 3);
        }
        writer->EndArray();
        if (time_compact)
            writer->PopCompact();
        writer->EndObject();
        writer->EndObject();
    }

	// datetime.date : {"__class__": "datetime.date", "__init__": {"__class__":
	// "bytes", "__new__": ["<b64 de 4 octets>","b64"]}} — la forme reduce
	// native (année big-endian, mois, jour)
	else if (PyDate_CheckExact(object) && pathTracker != nullptr) {
        CONTAINER_MEMO_OR_REF()
        writer->EnvelopeHead("datetime.date", 13, "__init__", 8);
        writer->EnvelopeHead("bytes", 5, "__new__", 7);
        bool date_compact = pathTracker->singleLineNew && !writer->InCompact();
        if (date_compact)
            writer->PushCompact();
        writer->StartArray();
        {
            int year = PyDateTime_GET_YEAR(object);
            unsigned char raw4[4] = {
                (unsigned char) ((year >> 8) & 0xFF),
                (unsigned char) (year & 0xFF),
                (unsigned char) PyDateTime_GET_MONTH(object),
                (unsigned char) PyDateTime_GET_DAY(object)};
            char b64_buf[9];
            serializejson_b64_encode(raw4, 4, b64_buf);
            writer->String(b64_buf, 8);
            writer->String("b64", 3);
        }
        writer->EndArray();
        if (date_compact)
            writer->PopCompact();
        writer->EndObject();
        writer->EndObject();
    }

	// datetime.timedelta : {"__class__": "datetime.timedelta", "__init__":
	// [jours, secondes, microsecondes]} — les arguments reduce natifs
	else if (PyDelta_CheckExact(object) && pathTracker != nullptr) {
        CONTAINER_MEMO_OR_REF()
        writer->EnvelopeHead("datetime.timedelta", 18, "__init__", 8);
        bool td_compact = pathTracker->singleLineInit && !writer->InCompact();
        if (td_compact)
            writer->PushCompact();
        writer->StartArray();
        writer->Int(PyDateTime_DELTA_GET_DAYS(object));
        writer->Int(PyDateTime_DELTA_GET_SECONDS(object));
        writer->Int(PyDateTime_DELTA_GET_MICROSECONDS(object));
        writer->EndArray();
        if (td_compact)
            writer->PopCompact();
        writer->EndObject();
    }

	// time.struct_time : {"__class__": "time.struct_time", "__init__":
	// [{"__class__": "tuple", "__new__": [9 entiers]}, {"tm_zone": ...,
	// "tm_gmtoff": ...}]} — la forme reduce de la voie python. Un struct
	// sequence EST un tuple : les 9 champs se lisent par PyTuple_GET_ITEM
	else if (pathTracker != nullptr && PyTuple_Check(object)
             && (PyObject*) Py_TYPE(object) == struct_time_type
             && PyTuple_GET_SIZE(object) >= 9) {
        CONTAINER_MEMO_OR_REF()
        writer->EnvelopeHead("time.struct_time", 16, "__init__", 8);
        bool st_compact = pathTracker->singleLineInit && !writer->InCompact();
        if (st_compact)
            writer->PushCompact();
        writer->StartArray();
        // les deux éléments du __init__ sont des CONTENEURS : sans leur rang,
        // ils porteraient le chemin de la liste elle-même
        PATH_PUSH_INDEX(0)
        writer->EnvelopeHead("tuple", 5, "__new__", 7);
        writer->StartArray();
        bool st_ok = true;
        for (Py_ssize_t sti = 0; sti < 9 && st_ok; sti++)
            st_ok = sj_write_scalar_inline(writer, PyTuple_GET_ITEM(object,
                                                                    sti))
                    || RECURSE(PyTuple_GET_ITEM(object, sti));
        writer->EndArray();
        writer->EndObject();
        PATH_POP()
        static const char* st_attrs[2] = {"tm_zone", "tm_gmtoff"};
        if (st_ok) {
            PATH_PUSH_INDEX(1)
            writer->StartObject();
            for (int sta = 0; sta < 2 && st_ok; sta++) {
                writer->Key(st_attrs[sta], sta == 0 ? 7 : 9);
                PyObject* champ = PyObject_GetAttrString(object,
                                                         st_attrs[sta]);
                if (champ == nullptr) {
                    PyErr_Clear();
                    writer->Null();
                    continue;
                }
                st_ok = sj_write_scalar_inline(writer, champ)
                        || RECURSE(champ);
                Py_DECREF(champ);
            }
            writer->EndObject();
            PATH_POP()
        }
        writer->EndArray();
        if (st_compact)
            writer->PopCompact();
        writer->EndObject();
        if (!st_ok)
            return false;
    }

	// decimal.Decimal : {"__class__": "decimal.Decimal", "__init__":
	// "<str(d)>"} — la graphie de Decimal est toujours ascii sans échappement
	else if (pathTracker != nullptr
             && (PyObject*) Py_TYPE(object) == decimal_type) {
        CONTAINER_MEMO_OR_REF()
        PyObject* graphie = PyObject_Str(object);
        if (graphie == nullptr)
            return false;
        Py_ssize_t dec_lg;
        const char* dec_u8 = PyUnicode_AsUTF8AndSize(graphie, &dec_lg);
        if (dec_u8 == nullptr) {
            Py_DECREF(graphie);
            return false;
        }
        writer->EnvelopeHead("decimal.Decimal", 15, "__init__", 8);
        writer->String(dec_u8, (SizeType) dec_lg);
        writer->EndObject();
        Py_DECREF(graphie);
    }

	// complex / range / slice : {"__class__": ..., "__init__": [...]} — les
	// mêmes listes d'arguments que la voie Python
	else if ((PyComplex_CheckExact(object)
              || Py_TYPE(object) == &PyRange_Type
              || Py_TYPE(object) == &PySlice_Type)
             && pathTracker != nullptr) {
        CONTAINER_MEMO_OR_REF()
        bool simple_ok = true;
        if (PyComplex_CheckExact(object))
            writer->EnvelopeHead("complex", 7, "__init__", 8);
        else if (Py_TYPE(object) == &PyRange_Type)
            writer->EnvelopeHead("range", 5, "__init__", 8);
        else
            writer->EnvelopeHead("slice", 5, "__init__", 8);
        bool simple_compact =
            pathTracker->singleLineInit && !writer->InCompact();
        if (simple_compact)
            writer->PushCompact();
        writer->StartArray();
        if (PyComplex_CheckExact(object)) {
            Py_complex cv = PyComplex_AsCComplex(object);
            double parts[2] = {cv.real, cv.imag};
            for (int pi = 0; pi < 2 && simple_ok; pi++) {
                PyObject* tmp = PyFloat_FromDouble(parts[pi]);
                if (tmp == nullptr) {
                    simple_ok = false;
                    break;
                }
                simple_ok = RECURSE(tmp);
                Py_DECREF(tmp);
            }
        } else if (Py_TYPE(object) == &PyRange_Type) {
            static const char* range_attrs[3] = {"start", "stop", "step"};
            for (int pi = 0; pi < 3 && simple_ok; pi++) {
                PyObject* tmp = PyObject_GetAttrString(object,
                                                       range_attrs[pi]);
                if (tmp == nullptr) {
                    simple_ok = false;
                    break;
                }
                simple_ok = RECURSE(tmp);
                Py_DECREF(tmp);
            }
        } else {
            PySliceObject* sl = (PySliceObject*) object;
            PyObject* parts[3] = {sl->start, sl->stop, sl->step};
            for (int pi = 0; pi < 3 && simple_ok; pi++)
                simple_ok = RECURSE(parts[pi]);
        }
        writer->EndArray();
        if (simple_compact)
            writer->PopCompact();
        writer->EndObject();
        if (!simple_ok)
            return false;
    }

	// dictionnaire à clés toutes entières (int exacts, 64 bits) : forme
	// {"__class__": "dict", "<entier>": valeur, ...} écrite
	// directement en C++, à l'octet près du chemin Python historique — les
	// autres clés non-str (bool, tuples, mixtes, >64 bits) restent en Python
	else if (PyDict_CheckExact(object) && (mappingMode & MM_ONLY_DICTS)
             && !(mappingMode & MM_SORT_KEYS)
             && PyDict_GET_SIZE(object) > 0
             && sj_all_keys_exact_int64(object)) {
        CONTAINER_MEMO_OR_REF()
        CALL_CONTAINER_HOOK(defaultDictFn, " while JSONifying dict object")
        writer->StartObject();
        writer->Key("__class__", 9);
        writer->String("dict", 4);
        Py_ssize_t int_pos = 0;
        PyObject* int_key;
        PyObject* int_item;
        while (PyDict_Next(object, &int_pos, &int_key, &int_item)) {
            char key_buf[24];
            int overflow;
            long long key_value =
                PyLong_AsLongLongAndOverflow(int_key, &overflow);
            char* key_end = rapidjson::internal::i64toa(key_value, key_buf);
            SizeType key_length = (SizeType) (key_end - key_buf);
            writer->Key(key_buf, key_length);
            // littéraux inline : un scalaire n'est jamais cible de $ref ni
            // parent d'un conteneur, le segment de chemin serait du vide
            if (int_item == Py_None) {
                writer->Null();
                continue;
            }
            if (int_item == Py_True || int_item == Py_False) {
                writer->Bool(int_item == Py_True);
                continue;
            }
            PATH_PUSH_KEY(key_buf, key_length)
            bool r = RECURSE(int_item);
            PATH_POP()
            if (!r)
                return false;
        }
        writer->EndObject();
    }

	// dictionnaires ---------------------------------------------------------
	else if (((!(mappingMode & MM_ONLY_DICTS) && PyDict_Check(object))
                ||
                PyDict_CheckExact(object))
               &&
               ((mappingMode & MM_SKIP_NON_STRING_KEYS)
                ||
                (mappingMode & MM_COERCE_KEYS_TO_STRINGS)
                ||
                (all_keys_are_string(object)
                 // les enveloppes produites par default() (attrsDict)
                 // contiennent "__class__" par construction : elles
                 // s'écrivent telles quelles — sans cette garde, la
                 // détection les renverrait à default() en boucle
                 && (attrsDict || !sj_dict_has_reserved_key(object))))) {
        // les dicts d'attributs construits par default() sont uniques par
        // construction : inutile de les mémoïser (le VRAI __dict__ de l'objet
        // est, lui, enregistré par memo_state_dict au moment de l'aplatissement)
        if (!attrsDict) {
            CONTAINER_MEMO_OR_REF()
        }
        CALL_CONTAINER_HOOK(defaultDictFn, " while JSONifying dict object")
        writer->StartObject();

        // --- plan de forme : même séquence de clés que le dict précédent à
        // cette profondeur -> clés écrites en RawValue pré-échappé
        bool shape_written = false;
        if (pathTracker && !attrsDict && !(mappingMode & MM_SORT_KEYS)) {
            DictShape& shape =
                pathTracker->shapes[pathTracker->segments.size() & 3];
            size_t dsize = (size_t) PyDict_GET_SIZE(object);
            if (dsize && dsize == shape.keys.size()) {
                PyObject* shape_values[SJ_SHAPE_MAX_KEYS];
                Py_ssize_t spos = 0;
                PyObject* skey;
                PyObject* sval;
                size_t sidx = 0;
                bool shape_match = true;
                while (PyDict_Next(object, &spos, &skey, &sval)) {
                    if (skey != shape.keys[sidx]) {
                        shape_match = false;
                        break;
                    }
                    shape_values[sidx++] = sval;
                }
                if (shape_match) {
                    for (size_t i = 0; i < dsize; i++) {
                        writer->RawValue(shape.fragments[i].data(),
                                         shape.fragments[i].size());
                        PyObject* shape_item = shape_values[i];
                        if (sj_write_scalar_inline(writer, shape_item))
                            continue;
                        if (PyUnicode_CheckExact(shape_item)) {
                            Py_ssize_t inline_length;
                            const char* inline_str = PyUnicode_AsUTF8AndSize(
                                shape_item, &inline_length);
                            if (inline_str == nullptr)
                                return false;
                            if (!PyUnicode_IS_ASCII(shape_item))
                                writer->MarkMaybeNonAscii();
                            writer->PyString_(shape_item, inline_str,
                                              (SizeType) inline_length);
                            continue;
                        }
                        PATH_PUSH_KEY(shape.key_strs[i].first,
                                      shape.key_strs[i].second);
                        bool r = RECURSE(shape_item);
                        PATH_POP();
                        if (!r)
                            return false;
                    }
                    shape_written = true;
                }
            }
            if (!shape_written && dsize && dsize <= SJ_SHAPE_MAX_KEYS) {
                // (ré)apprend la forme depuis ce dict : clés str ascii sans
                // caractère à échapper, sinon pas de plan pour cette séquence
                shape.clear_refs();
                Py_ssize_t bpos = 0;
                PyObject* bkey;
                PyObject* bval;
                bool learnable = true;
                while (PyDict_Next(object, &bpos, &bkey, &bval)) {
                    if (!PyUnicode_CheckExact(bkey)
                        || !PyUnicode_IS_ASCII(bkey)) {
                        learnable = false;
                        break;
                    }
                    Py_ssize_t blen;
                    const char* bstr = PyUnicode_AsUTF8AndSize(bkey, &blen);
                    if (bstr == nullptr) {
                        PyErr_Clear();
                        learnable = false;
                        break;
                    }
                    bool clean = true;
                    for (Py_ssize_t j = 0; j < blen; j++) {
                        unsigned char c = (unsigned char) bstr[j];
                        if (c == '"' || c == '\\' || c < 0x20) {
                            clean = false;
                            break;
                        }
                    }
                    if (!clean) {
                        learnable = false;
                        break;
                    }
                    Py_INCREF(bkey);
                    shape.keys.push_back(bkey);
                    std::string frag;
                    frag.reserve((size_t) blen + 2);
                    frag += '"';
                    frag.append(bstr, (size_t) blen);
                    frag += '"';
                    shape.fragments.push_back(std::move(frag));
                    shape.key_strs.push_back({bstr, (size_t) blen});
                }
                if (!learnable)
                    shape.clear_refs();
            }
        }

        Py_ssize_t pos = 0;
        PyObject* key;
        PyObject* item;
        PyObject* coercedKey = nullptr;

            if (shape_written) {
            // déjà écrit par le plan de forme
            } else if (!(mappingMode & MM_SORT_KEYS)) {
            while (PyDict_Next(object, &pos, &key, &item)) {
                if (mappingMode & MM_COERCE_KEYS_TO_STRINGS) {
                    if (!PyUnicode_Check(key)) {
                        coercedKey = PyObject_Str(key);
                        if (coercedKey == nullptr)
                            return false;
                        key = coercedKey;
                    }
                }
                if (coercedKey || PyUnicode_Check(key)) {
                    Py_ssize_t l;
                    const char* key_str = PyUnicode_AsUTF8AndSize(key, &l);
                    if (key_str == nullptr) {
                        Py_XDECREF(coercedKey);
                        return false;
                    }
                    ASSERT_VALID_SIZE(l);
                    if (!PyUnicode_IS_ASCII(key))
                        writer->MarkMaybeNonAscii();
                    writer->Key(key_str, (SizeType) l);
                    if (PyUnicode_CheckExact(item)) {
                        Py_ssize_t inline_length;
                        const char* inline_str =
                            PyUnicode_AsUTF8AndSize(item, &inline_length);
                        if (inline_str == nullptr) {
                            Py_XDECREF(coercedKey);
                            return false;
                        }
                        if (!PyUnicode_IS_ASCII(item))
                            writer->MarkMaybeNonAscii();
                        writer->PyString_(item, inline_str, (SizeType) inline_length);
                        Py_CLEAR(coercedKey);
                        continue;
                    }
                    if (sj_write_scalar_inline(writer, item)) {
                        Py_CLEAR(coercedKey);
                        continue;
                    }
                    if (Py_EnterRecursiveCall(" while JSONifying dict object")) {
                        Py_XDECREF(coercedKey);
                        return false;
                    }
                    // règle du writer (ex-emballage SingleLine de default) :
                    // les listes __init__/__new__ d'une ENVELOPPE s'écrivent
                    // compactes selon single_line_init/new — isinstance côté
                    // init, type exact côté new, comme la voie python
                    bool env_compact = attrsDict && pathTracker
                        && !writer->InCompact()
                        && ((l == 8 && memcmp(key_str, "__init__", 8) == 0
                             && pathTracker->singleLineInit
                             && PyList_Check(item))
                            || (l == 7 && memcmp(key_str, "__new__", 7) == 0
                                && pathTracker->singleLineNew
                                && PyList_CheckExact(item)));
                    if (env_compact)
                        writer->PushCompact();
                    PATH_PUSH_KEY(key_str, l);
                    bool r = RECURSE(item);
                    PATH_POP();
                    if (env_compact)
                        writer->PopCompact();
                    Py_LeaveRecursiveCall();
                    if (!r) {
                        Py_XDECREF(coercedKey);
                        return false;
                    }
                } else if (!(mappingMode & MM_SKIP_NON_STRING_KEYS)) {
                    PyErr_SetString(PyExc_TypeError, "keys must be strings");
                    // No need to dispose coercedKey here, because it can be set *only*
                    // when mapping_mode is MM_COERCE_KEYS_TO_STRINGS
                    assert(!coercedKey);
                    return false;
                }
                Py_CLEAR(coercedKey);
            }
        } else {
            std::vector<DictItem> items;

            while (PyDict_Next(object, &pos, &key, &item)) {
                if (mappingMode & MM_COERCE_KEYS_TO_STRINGS) {
                    if (!PyUnicode_Check(key)) {
                        coercedKey = PyObject_Str(key);
                        if (coercedKey == nullptr)
                            return false;
                        key = coercedKey;
                    }
                }
                if (coercedKey || PyUnicode_Check(key)) {
                    Py_ssize_t l;
                    const char* key_str = PyUnicode_AsUTF8AndSize(key, &l);
                    if (key_str == nullptr) {
                        Py_XDECREF(coercedKey);
                        return false;
                    }
                    ASSERT_VALID_SIZE(l);
                    if (!PyUnicode_IS_ASCII(key))
                        writer->MarkMaybeNonAscii();
                    items.push_back(DictItem(key_str, l, item));
                } else if (!(mappingMode & MM_SKIP_NON_STRING_KEYS)) {
                    PyErr_SetString(PyExc_TypeError, "keys must be strings");
                    assert(!coercedKey);
                    return false;
                }
                Py_CLEAR(coercedKey);
            }

            std::sort(items.begin(), items.end());

            for (size_t i=0, s=items.size(); i < s; i++) {
                writer->Key(items[i].key_str, (SizeType) items[i].key_size);
                if (PyUnicode_CheckExact(items[i].item)) {
                    Py_ssize_t inline_length;
                    const char* inline_str =
                        PyUnicode_AsUTF8AndSize(items[i].item, &inline_length);
                    if (inline_str == nullptr)
                        return false;
                    if (!PyUnicode_IS_ASCII(items[i].item))
                        writer->MarkMaybeNonAscii();
                    writer->PyString_(items[i].item, inline_str,
                                      (SizeType) inline_length);
                    continue;
                }
                if (sj_write_scalar_inline(writer, items[i].item))
                    continue;
                if (Py_EnterRecursiveCall(" while JSONifying dict object"))
                    return false;
                // même règle que la boucle non triée (ex-SingleLine)
                bool env_compact = attrsDict && pathTracker
                    && !writer->InCompact()
                    && ((items[i].key_size == 8
                         && memcmp(items[i].key_str, "__init__", 8) == 0
                         && pathTracker->singleLineInit
                         && PyList_Check(items[i].item))
                        || (items[i].key_size == 7
                            && memcmp(items[i].key_str, "__new__", 7) == 0
                            && pathTracker->singleLineNew
                            && PyList_CheckExact(items[i].item)));
                if (env_compact)
                    writer->PushCompact();
                PATH_PUSH_KEY(items[i].key_str, items[i].key_size);
                bool r = RECURSE(items[i].item);
                PATH_POP();
                if (env_compact)
                    writer->PopCompact();
                Py_LeaveRecursiveCall();
                if (!r)
                    return false;
            }
        }

        writer->EndObject();
    } 

	// RawString, RawBytes , RawBytesToPutInQuotes----------------------------------
	else if (PyObject_TypeCheck(object, &RawString_Type)) {
        if (!PyUnicode_IS_ASCII(((RawString*) object)->value))
            writer->MarkMaybeNonAscii();
        writer->RawString_(object);
    } 
	else if (PyObject_TypeCheck(object, &RawBytes_Type)) {
        writer->MarkMaybeNonAscii();  // contenu opaque : conservateur
        writer->RawBytes_(object);
    } 
	else if (PyObject_TypeCheck(object, &RawBytesToPutInQuotes_Type)) {
        writer->MarkMaybeNonAscii();  // contenu opaque : conservateur
        writer->RawBytesToPutInQuotes_(object);
    }
	else if (PyObject_TypeCheck(object, &SingleLine_Type)) {
        // sous-arbre écrit au format compact par le MÊME encodeur : mémo,
        // hooks et traqueur de chemin restent actifs à l'intérieur
        SingleLine* wrapper = (SingleLine*) object;
        unsigned savedNumberMode = numberMode;
        if (wrapper->numberMode >= 0)
            numberMode = (unsigned) wrapper->numberMode;
        bool pushed_compact = !writer->InCompact();
        if (pushed_compact)
            writer->PushCompact();
        if (Py_EnterRecursiveCall(" while JSONifying single line value")) {
            if (pushed_compact)
                writer->PopCompact();
            return false;
        }
        bool r = RECURSE(wrapper->value);
        Py_LeaveRecursiveCall();
        if (pushed_compact)
            writer->PopCompact();
        numberMode = savedNumberMode;
        if (!r)
            return false;
    }
	else if (PyObject_TypeCheck(object, &ArrayRows_Type)) {
        if (!write_buffer_rows(writer, ((ArrayRows*) object)->value, numberMode))
            return false;
    }
	else if (PyObject_TypeCheck(object, &BloscToBase64_Type)) {
        writer->BloscToBase64_(object);
    }
	else if (PyObject_TypeCheck(object, &BloscDiffere_Type)) {
        // compression déférée au fil d'écriture (ou synchrone hors flux
        // fichier) : peut échouer, contrairement aux formes déjà compressées
        if (!writer->BloscDiffere_(object))
            return false;
    }
	else if (PyObject_TypeCheck(object, &EtiquetteDiffere_Type)) {
        // l'étiquette séparée d'une charge numpy différée : choisie par le
        // fil, ou lue de la décision synchrone — échoue si la charge n'a
        // pas encore été écrite
        if (!writer->EtiquetteDiffere_(object))
            return false;
    }
	else if (PyObject_TypeCheck(object, &RawBytesToBase64_Type)) {
        writer->RawBytesToBase64_(object);
    } 
	
	// all others ojects --------------------------------------------------------
	else if (defaultFn) {
        // ----- petits bytes/bytearray NATIFS : enveloppe écrite entièrement
        // en C, sans rappel python — mêmes octets que la recette du greffon :
        // bytes ascii imprimable ({tab, LF, CR} ∪ [0x20..0x7E]) en forme
        // chaîne « __new__ », sinon base64 préfixée « n: » ; bytearray
        // toujours en base64 sous « __init__ ». Seuil posé par l'Encoder
        // python (_bytes_natif_seuil : 0 si les greffons bytes ont été
        // remplacés — on ne court-circuite jamais un greffon utilisateur)
        if (pathTracker && pathTracker->bytesNatifSeuil > 0
            && (PyBytes_CheckExact(object) || PyByteArray_CheckExact(object))
            && Py_SIZE(object) < pathTracker->bytesNatifSeuil) {
            const bool is_bytearray = PyByteArray_CheckExact(object);
            const unsigned char* data = is_bytearray
                ? (const unsigned char*) PyByteArray_AS_STRING(object)
                : (const unsigned char*) PyBytes_AS_STRING(object);
            Py_ssize_t length = Py_SIZE(object);

            bool printable = !is_bytearray;  // la forme ascii n'existe que
                                             // pour bytes (fidèle au greffon)
            if (printable)
                for (Py_ssize_t i = 0; i < length; i++) {
                    unsigned char c = data[i];
                    if (!((c >= 0x20 && c <= 0x7E)
                          || c == '\t' || c == '\n' || c == '\r')) {
                        printable = false;
                        break;
                    }
                }
            // liste base64 multi-ligne (single_line_init/new=False) : forme
            // rare, voie recette python inchangée — la décision se prend
            // AVANT le mémo (sinon la recette retrouverait l'objet tout
            // juste mémorisé et écrirait un $ref vers lui-même)
            if (printable
                || (is_bytearray ? pathTracker->singleLineInit
                                 : pathTracker->singleLineNew)) {
                CONTAINER_MEMO_OR_REF()

                if (pathTracker->dumpedClasses != nullptr)
                    sj_ajoute_classe_dumpee(pathTracker,
                                            is_bytearray
                                                ? bytearray_class_name_str
                                                : bytes_class_name_str);

                writer->BytesEnvelope(data, (size_t) length, printable,
                                      is_bytearray);
                return true;
            }
        }
        // ----- dict à clés non-str NATIF : l'enveloppe plate
        // {"__class__": "dict", clés encodées...} est composée ici, octet
        // pour octet comme _dict_from_instance ; python n'est rappelé que
        // pour les clés exotiques (_cle_json : tuple, frozenset, float non
        // fini, objet...), avec un cache par égalité le temps du dump.
        // Un cas non porté (clé "__init__"/"__new__" nue — la voie python
        // leur applique l'emballage SingleLine de l'enveloppe) rend le DICT
        // ENTIER au chemin python ci-dessous, sans rien avoir écrit
        if (pathTracker && pathTracker->cleJsonFn && !attrsDict
            && defaultDictFn == nullptr && PyDict_CheckExact(object)) {
            struct CleNative {
                std::string texte;
                PyObject* value;
                bool non_ascii;
            };
            std::vector<CleNative> entrees;
            entrees.reserve((size_t) PyDict_GET_SIZE(object));
            // instantané possédé du dict AVANT tout rappel python : _cle_json
            // peut exécuter du code utilisateur (reduce d'une clé objet)
            SjOwnedRefs instantane;
            instantane.refs.reserve((size_t) PyDict_GET_SIZE(object) * 2);
            {
                Py_ssize_t dpos = 0;
                PyObject* dkey;
                PyObject* dval;
                while (PyDict_Next(object, &dpos, &dkey, &dval)) {
                    Py_INCREF(dkey);
                    instantane.refs.push_back(dkey);
                    Py_INCREF(dval);
                    instantane.refs.push_back(dval);
                }
            }
            bool porte = true;
            for (size_t i = 0; porte && i * 2 < instantane.refs.size(); i++) {
                PyObject* dkey = instantane.refs[i * 2];
                PyObject* dval = instantane.refs[i * 2 + 1];
                CleNative entree;
                entree.value = dval;
                entree.non_ascii = false;
                if (PyUnicode_CheckExact(dkey)) {
                    Py_ssize_t kl;
                    const char* ks = PyUnicode_AsUTF8AndSize(dkey, &kl);
                    if (ks == nullptr)
                        return false;
                    entree.non_ascii = !PyUnicode_IS_ASCII(dkey);
                    // clés réservées du format : toujours échappées ; sinon
                    // préfiltre exact du premier caractère (miroir python),
                    // sonde de parse pour les seules clés [, { ou "
                    bool requote;
                    if ((kl == 9 && memcmp(ks, "__class__", 9) == 0)
                        || (kl == 4 && memcmp(ks, "$ref", 4) == 0)) {
                        requote = true;
                    } else if (kl == 0) {
                        requote = false;
                    } else if (ks[0] == '\'') {
                        requote = ks[kl - 1] == '\'';
                    } else if (ks[0] == 'b') {
                        requote = ks[kl - 1] == '\''
                            && ((kl >= 2 && ks[1] == '\'')
                                || (kl >= 4 && memcmp(ks, "b64'", 4) == 0));
                    } else if (ks[0] == '-' || (ks[0] >= '0' && ks[0] <= '9')) {
                        requote = sj_cle_nombre_json(ks, (size_t) kl)
                            || (kl == 9 && memcmp(ks, "-Infinity", 9) == 0);
                    } else if (ks[0] == 't' || ks[0] == 'f' || ks[0] == 'n'
                               || ks[0] == 'N' || ks[0] == 'I') {
                        requote = (kl == 4 && memcmp(ks, "true", 4) == 0)
                            || (kl == 5 && memcmp(ks, "false", 5) == 0)
                            || (kl == 4 && memcmp(ks, "null", 4) == 0)
                            || (kl == 3 && memcmp(ks, "NaN", 3) == 0)
                            || (kl == 8 && memcmp(ks, "Infinity", 8) == 0);
                    } else if (ks[0] == '[' || ks[0] == '{' || ks[0] == '"') {
                        requote = sj_cle_parse_json(ks);
                    } else {
                        requote = false;
                    }
                    if (requote) {
                        entree.texte.reserve((size_t) kl + 2);
                        entree.texte += '\'';
                        entree.texte.append(ks, (size_t) kl);
                        entree.texte += '\'';
                    } else {
                        entree.texte.assign(ks, (size_t) kl);
                        if ((kl == 8 && memcmp(ks, "__init__", 8) == 0)
                            || (kl == 7 && memcmp(ks, "__new__", 7) == 0)) {
                            porte = false;   // quirk SingleLine : voie python
                            break;
                        }
                    }
                } else if (PyLong_CheckExact(dkey)) {
                    PyObject* txt = PyObject_Str(dkey);
                    if (txt == nullptr)
                        return false;
                    Py_ssize_t tl;
                    const char* ts = PyUnicode_AsUTF8AndSize(txt, &tl);
                    if (ts == nullptr) {
                        Py_DECREF(txt);
                        return false;
                    }
                    entree.texte.assign(ts, (size_t) tl);
                    Py_DECREF(txt);
                } else if (dkey == Py_True) {
                    entree.texte = "true";
                } else if (dkey == Py_False) {
                    entree.texte = "false";
                } else if (dkey == Py_None) {
                    entree.texte = "null";
                } else if (PyFloat_CheckExact(dkey)
                           && !IS_NAN(PyFloat_AS_DOUBLE(dkey))
                           && !IS_INF(PyFloat_AS_DOUBLE(dkey))) {
                    // graphie repr() (Ryu), la même que le dumps une-ligne
                    char repr_buf[40];
                    entree.texte.assign(
                        repr_buf,
                        (size_t) sjdtoa::ReprDouble(PyFloat_AS_DOUBLE(dkey),
                                                    repr_buf));
                } else if (PyBytes_CheckExact(dkey)) {
                    const unsigned char* bd =
                        (const unsigned char*) PyBytes_AS_STRING(dkey);
                    Py_ssize_t bl = PyBytes_GET_SIZE(dkey);
                    bool imprimable = true;   // jeu du codec ascii_printables
                    for (Py_ssize_t j = 0; j < bl; j++) {
                        unsigned char c = bd[j];
                        if (!((c >= 0x20 && c <= 0x7E)
                              || c == '\t' || c == '\n' || c == '\r')) {
                            imprimable = false;
                            break;
                        }
                    }
                    if (imprimable) {
                        entree.texte.reserve((size_t) bl + 3);
                        entree.texte += "b'";
                        entree.texte.append((const char*) bd, (size_t) bl);
                        entree.texte += '\'';
                    } else {
                        size_t b64l = ((size_t) bl + 2) / 3 * 4;
                        entree.texte.resize(b64l + 5);
                        memcpy(&entree.texte[0], "b64'", 4);
                        serializejson_b64_encode(bd, (size_t) bl,
                                                 &entree.texte[4]);
                        entree.texte[b64l + 4] = '\'';
                    }
                } else if ((PyTuple_CheckExact(dkey)
                            || PyFrozenSet_CheckExact(dkey))
                           && pathTracker->defaultOneLineFn != nullptr) {
                    // clé tuple ou frozenset : sous-document écrit ici
                    if (!sj_cle_native(dkey, pathTracker, datetimeMode,
                                       uuidMode, bytesMode, iterableMode,
                                       mappingMode, entree.texte,
                                       &entree.non_ascii))
                        return false;
                } else {
                    // clé exotique restante (float non fini, complexe, objet)
                    // : rappel python _cle_json, mémoïsé
                    // par égalité — les clés sont hashables par construction
                    PyObject* txt = nullptr;
                    if (pathTracker->cleJsonCache != nullptr) {
                        txt = PyDict_GetItemWithError(
                            pathTracker->cleJsonCache, dkey);
                        if (txt == nullptr && PyErr_Occurred())
                            return false;
                        Py_XINCREF(txt);
                    }
                    if (txt == nullptr) {
                        txt = PyObject_CallFunctionObjArgs(
                            pathTracker->cleJsonFn, dkey, nullptr);
                        if (txt == nullptr)
                            return false;   // même erreur que la voie python
                        if (!PyUnicode_CheckExact(txt)) {
                            Py_DECREF(txt);
                            porte = false;   // forme inattendue : voie python
                            break;
                        }
                        if (pathTracker->cleJsonCache == nullptr)
                            pathTracker->cleJsonCache = PyDict_New();
                        if (pathTracker->cleJsonCache != nullptr
                            && PyDict_SetItem(pathTracker->cleJsonCache,
                                              dkey, txt) < 0)
                            PyErr_Clear();
                    }
                    Py_ssize_t tl;
                    const char* ts = PyUnicode_AsUTF8AndSize(txt, &tl);
                    if (ts == nullptr) {
                        Py_DECREF(txt);
                        return false;
                    }
                    entree.non_ascii = !PyUnicode_IS_ASCII(txt);
                    entree.texte.assign(ts, (size_t) tl);
                    Py_DECREF(txt);
                }
                entrees.push_back(std::move(entree));
            }
            if (porte) {
                CONTAINER_MEMO_OR_REF()
                writer->StartObject();
                writer->Key("__class__", 9);
                writer->String("dict", 4);
                for (const CleNative& entree : entrees) {
                    if (entree.non_ascii)
                        writer->MarkMaybeNonAscii();
                    writer->Key(entree.texte.data(),
                                (SizeType) entree.texte.size());
                    if (PyUnicode_CheckExact(entree.value)) {
                        Py_ssize_t vl;
                        const char* vs =
                            PyUnicode_AsUTF8AndSize(entree.value, &vl);
                        if (vs == nullptr)
                            return false;
                        if (!PyUnicode_IS_ASCII(entree.value))
                            writer->MarkMaybeNonAscii();
                        writer->String(vs, (SizeType) vl);
                        continue;
                    }
                    if (sj_write_scalar_inline(writer, entree.value))
                        continue;
                    if (Py_EnterRecursiveCall(" while JSONifying dict object"))
                        return false;
                    PATH_PUSH_KEY(entree.texte.data(), entree.texte.size());
                    bool r = RECURSE(entree.value);
                    PATH_POP();
                    Py_LeaveRecursiveCall();
                    if (!r)
                        return false;
                }
                writer->EndObject();
                return PyErr_Occurred() ? false : true;
            }
        }
        // ----- valeurs de TYPE natives : {"__class__": "type", "__init__":
        // "<nom>"} servi depuis le cache classe -> nom (rempli au premier
        // passage par la recette python) — la recette rappelait python à
        // CHAQUE dump pour les mêmes classes. `type` lui-même reste en
        // recette (forme sans __init__), comme les classes jamais vues
        if (Py_TYPE(object) == &PyType_Type
            && object != (PyObject*) &PyType_Type
            && sj_type_names_cache != nullptr
            && pathTracker && pathTracker->classPlanFn
            && !pathTracker->strictPickle) {
            PyObject* nom = PyDict_GetItem(sj_type_names_cache, object);
            if (nom != nullptr) {
                // aligné sur class_plan : le plan de `type` doit être la
                // recette marquée (un plugin utilisateur le change)
                PyObject* type_plan;
                auto type_plan_it =
                    pathTracker->classPlans.find(&PyType_Type);
                if (type_plan_it != pathTracker->classPlans.end()) {
                    type_plan = type_plan_it->second;
                } else {
                    type_plan = PyObject_CallFunctionObjArgs(
                        pathTracker->classPlanFn, (PyObject*) &PyType_Type,
                        nullptr);
                    if (type_plan == nullptr)
                        return false;
                    if (type_plan != Py_None
                        && (!PyTuple_Check(type_plan)
                            || PyTuple_GET_SIZE(type_plan) < 2
                            || PyTuple_GET_SIZE(type_plan) > 5)) {
                        Py_DECREF(type_plan);
                        type_plan = Py_None;
                        Py_INCREF(Py_None);
                    }
                    pathTracker->classPlans.emplace(&PyType_Type, type_plan);
                }
                if (type_plan != Py_None
                    && PyTuple_GET_SIZE(type_plan) == 4
                    && PyTuple_GET_ITEM(type_plan, 0) == Py_None
                    && PyUnicode_Check(PyTuple_GET_ITEM(type_plan, 3))
                    && PyUnicode_CompareWithASCIIString(
                           PyTuple_GET_ITEM(type_plan, 3), "type") == 0) {
                    CONTAINER_MEMO_OR_REF()
                    if (pathTracker->dumpedClasses != nullptr)
                        sj_ajoute_classe_dumpee(pathTracker,
                                                PyTuple_GET_ITEM(type_plan,
                                                                 3));
                    writer->EnvelopeHead("type", 4, "__init__", 8);
                    Py_ssize_t nom_length;
                    const char* nom_str =
                        PyUnicode_AsUTF8AndSize(nom, &nom_length);
                    if (nom_str == nullptr)
                        return false;
                    if (!PyUnicode_IS_ASCII(nom))
                        writer->MarkMaybeNonAscii();
                    writer->String(nom_str, (SizeType) nom_length);
                    writer->EndObject();
                    return PyErr_Occurred() ? false : true;
                }
            }
            // classe jamais vue (ou plan inattendu) : voie recette, qui
            // remplit le cache
        }
        // ----- set / frozenset NATIFS : {"__class__": "set", "__init__":
        // [éléments]} écrit directement, même règle de compactage que la
        // branche tuple — la recette générique repassait par la branche
        // liste entière (mémo d'une liste TEMPORAIRE que rien ne peut
        // référencer, balayage d'homogénéité sous compact : ~180 ns par set
        // mesurés). Gardé par le plan de classe (mêmes gardes que la
        // recette : plugin utilisateur ou strict_pickle -> plan différent,
        // repli sur la voie recette/python ci-dessous)
        if ((PySet_CheckExact(object) || PyFrozenSet_CheckExact(object))
            && pathTracker && pathTracker->classPlanFn
            && !pathTracker->strictPickle) {
            PyTypeObject* set_type = Py_TYPE(object);
            PyObject* set_plan;
            auto set_plan_it = pathTracker->classPlans.find(set_type);
            if (set_plan_it != pathTracker->classPlans.end()) {
                set_plan = set_plan_it->second;
            } else {
                set_plan = PyObject_CallFunctionObjArgs(
                    pathTracker->classPlanFn, (PyObject*) set_type, nullptr);
                if (set_plan == nullptr)
                    return false;
                if (set_plan != Py_None
                    && (!PyTuple_Check(set_plan)
                        || PyTuple_GET_SIZE(set_plan) < 2
                        || PyTuple_GET_SIZE(set_plan) > 5)) {
                    Py_DECREF(set_plan);
                    set_plan = Py_None;
                    Py_INCREF(Py_None);
                }
                pathTracker->classPlans.emplace(set_type, set_plan);
            }
            if (set_plan != Py_None && PyTuple_GET_SIZE(set_plan) == 4
                && PyTuple_GET_ITEM(set_plan, 0) == Py_None
                && PyUnicode_Check(PyTuple_GET_ITEM(set_plan, 3))) {
                CONTAINER_MEMO_OR_REF()

                // dumped_classes : "set"/"frozenset", comme la recette
                if (pathTracker->dumpedClasses != nullptr)
                    sj_ajoute_classe_dumpee(pathTracker,
                                            PyTuple_GET_ITEM(set_plan, 3));

                if (PyFrozenSet_CheckExact(object))
                    writer->EnvelopeHead("frozenset", 9, "__init__", 8);
                else
                    writer->EnvelopeHead("set", 3, "__init__", 8);
                // segments en style ".attr" : le chemin qu'écrivait la
                // recette (attrsDict actif dans sa branche)
                if (pathTracker) {
                    pathTracker->segments.push_back(
                        {PathSegment::ATTR, "__init__", 8, 0});
                    pathTracker->registered.push_back(-1);
                }
                PyObject* elements = PySequence_List(object);
                if (elements == nullptr)
                    return false;
                Py_ssize_t set_size = PyList_GET_SIZE(elements);
                // compact si single_line_init, ou si single_line_numbers et
                // éléments homogènes de nombres (règle de la branche liste,
                // que la recette empruntait pour la forme liste-nue)
                bool set_numbers = false;
                if (!pathTracker->singleLineInit
                    && pathTracker->singleLineNumbers && set_size > 0) {
                    PyTypeObject* first_type =
                        Py_TYPE(PyList_GET_ITEM(elements, 0));
                    if (first_type == &PyFloat_Type
                        || first_type == &PyLong_Type
                        || first_type == &PyBool_Type) {
                        set_numbers = true;
                        for (Py_ssize_t pi = 1; pi < set_size; pi++)
                            if (Py_TYPE(PyList_GET_ITEM(elements, pi))
                                != first_type) {
                                set_numbers = false;
                                break;
                            }
                    }
                }
                bool set_compact =
                    (pathTracker->singleLineInit || set_numbers)
                    && !writer->InCompact();
                if (set_compact)
                    writer->PushCompact();
                writer->StartArray();
                bool set_ok = true;
                for (Py_ssize_t si = 0; si < set_size && set_ok; si++) {
                    PyObject* item = PyList_GET_ITEM(elements, si);
                    if (PyUnicode_CheckExact(item)) {
                        Py_ssize_t inline_length;
                        const char* inline_str =
                            PyUnicode_AsUTF8AndSize(item, &inline_length);
                        if (inline_str == nullptr) {
                            set_ok = false;
                            break;
                        }
                        if (!PyUnicode_IS_ASCII(item))
                            writer->MarkMaybeNonAscii();
                        writer->PyString_(item, inline_str,
                                          (SizeType) inline_length);
                        continue;
                    }
                    if (sj_write_scalar_inline(writer, item))
                        continue;
                    PATH_PUSH_INDEX(si)
                    set_ok = RECURSE(item);
                    PATH_POP()
                }
                if (set_ok)
                    writer->EndArray();
                if (set_compact)
                    writer->PopCompact();
                Py_DECREF(elements);
                PATH_POP()
                if (!set_ok)
                    return false;
                writer->EndObject();
                return PyErr_Occurred() ? false : true;
            }
            // plan inattendu : voie recette / python classique ci-dessous
        }
        // ----- chemin rapide par classe : objet ordinaire écrit tout en C++,
        // sans passer par default()/reduce Python. La décision est prise UNE
        // fois par classe (class_plan), le résultat doit être identique octet
        // pour octet au chemin Python pour les classes éligibles.
        if (pathTracker && pathTracker->classPlanFn) {
            PyTypeObject* object_type = Py_TYPE(object);
            PyObject* plan;
            auto plan_it = pathTracker->classPlans.find(object_type);
            if (plan_it != pathTracker->classPlans.end()) {
                plan = plan_it->second;
            } else {
                plan = PyObject_CallFunctionObjArgs(
                    pathTracker->classPlanFn, (PyObject*) object_type, nullptr);
                if (plan == nullptr)
                    return false;
                if (plan != Py_None
                    && (!PyTuple_Check(plan)
                        || PyTuple_GET_SIZE(plan) < 2
                        || PyTuple_GET_SIZE(plan) > 5)) {
                    Py_DECREF(plan);
                    plan = Py_None;
                    Py_INCREF(Py_None);
                }
                pathTracker->classPlans.emplace(object_type, plan);
            }
            if (plan != Py_None
                && PyTuple_GET_ITEM(plan, 0) == Py_None) {
                // ----- recette __serializejson__ : (None, méthode,
                // numpy_array_to_list). La méthode de l'objet est appelée —
                // seul Python restant —, l'emballage complet est écrit ici,
                // octet pour octet comme _dict_from_instance. Un tuple de
                // forme inattendue retombe sur le chemin Python (defaultFn).
                PyObject* recipe_fn = PyTuple_GET_ITEM(plan, 1);
                bool numpy_keeps_list =
                    PyObject_IsTrue(PyTuple_GET_ITEM(plan, 2)) == 1;

                // mémo des doublons : mémorise à la première rencontre,
                // $ref ensuite — le comportement de default()
                CONTAINER_MEMO_OR_REF()

                // ----- variante __getstate__ (plan à 5 éléments) : la
                // méthode rend l'ÉTAT seul ; l'enveloppe est
                // {"__class__": nom précalculé, état à plat} — jamais de
                // __init__/__new__, ni getters/properties/tri/filtre (le
                // chemin Python les réserve aux classes SANS __getstate__)
                if (PyTuple_GET_SIZE(plan) == 5) {
                    PyObject* plan_class_str = PyTuple_GET_ITEM(plan, 3);
                    bool has_setstate =
                        PyObject_IsTrue(PyTuple_GET_ITEM(plan, 4)) == 1;
                    PyObject* state_obj = PyObject_CallFunctionObjArgs(
                        recipe_fn, object, nullptr);
                    if (state_obj == nullptr)
                        return false;
                    // formes déléguées à la voie Python : état 2-tuple
                    // (fusion __dict__/slots) et dict à clés non-str sans
                    // __setstate__ (enveloppe dict_non_str_keys)
                    bool gs_fallback = false;
                    bool gs_flat = PyDict_CheckExact(state_obj);
                    if (PyTuple_CheckExact(state_obj)
                        && PyTuple_GET_SIZE(state_obj) == 2)
                        gs_fallback = true;
                    if (gs_flat && sj_state_key_reserved(state_obj))
                        gs_fallback = true;   // nom porteur -> voie Python
                    if (gs_flat) {
                        Py_ssize_t gs_pos = 0;
                        PyObject* gs_key;
                        PyObject* gs_val;
                        while (PyDict_Next(state_obj, &gs_pos,
                                           &gs_key, &gs_val)) {
                            if (!PyUnicode_Check(gs_key)) {
                                if (has_setstate)
                                    gs_flat = false;   // -> "__state__"
                                else
                                    gs_fallback = true;
                                break;
                            }
                        }
                    }
                    if (gs_fallback) {
                        Py_DECREF(state_obj);
                        // defaultFn rappellera __getstate__ (méthode pure
                        // par contrat) ; le mémo C déjà posé reste celui
                        // qui répondra aux prochaines rencontres
                    } else {
                        int state_truth = PyObject_IsTrue(state_obj);
                        if (state_truth < 0) {
                            Py_DECREF(state_obj);
                            return false;
                        }
                        if (pathTracker->dumpedClasses != nullptr)
                            sj_ajoute_classe_dumpee(pathTracker,
                                                    plan_class_str);
                        bool wrote_ok = true;
                        bool saved_attrs_style = attrsDict;
                        attrsDict = true;
                        writer->StartObject();
                        writer->Key("__class__", 9);
                        Py_ssize_t gcls_len;
                        const char* gcls_str = PyUnicode_AsUTF8AndSize(
                            plan_class_str, &gcls_len);
                        if (gcls_str == nullptr) {
                            Py_DECREF(state_obj);
                            return false;
                        }
                        if (!PyUnicode_IS_ASCII(plan_class_str))
                            writer->MarkMaybeNonAscii();
                        writer->String(gcls_str, (SizeType) gcls_len);
                        if (state_truth == 1 && !gs_flat) {
                            // état non-dict (ou dict non-str avec
                            // __setstate__) : "__state__"
                            writer->Key("__state__", 9);
                            PATH_PUSH_KEY("__state__", 9)
                            wrote_ok = RECURSE(state_obj);
                            PATH_POP()
                        } else if (state_truth == 1) {
                            // dict : attributs à plat dans son ordre, avec
                            // la rigueur du __dict__ réel partagé
                            PyObject* real_dict =
                                PyObject_GetAttr(object, dict_dunder_name);
                            if (real_dict == nullptr)
                                PyErr_Clear();
                            bool is_real_dict = (real_dict == state_obj);
                            Py_XDECREF(real_dict);
                            bool state_done = false;
                            if (is_real_dict && pathTracker->memoContainers) {
                                auto dict_it =
                                    pathTracker->memo.find(state_obj);
                                if (dict_it != pathTracker->memo.end()) {
                                    writer->Key("__dict__", 8);
                                    const std::string& ref_ = sj_ref_json(
                                        pathTracker, dict_it->second);
                                    writer->RawValue(ref_.data(),
                                                     ref_.size());
                                    state_done = true;
                                } else {
                                    long gs_node =
                                        path_tracker_materialize(pathTracker);
                                    PathNode node;
                                    node.parent = (int) gs_node;
                                    node.kind = PathSegment::ATTR;
                                    node.key = "__dict__";
                                    node.index = 0;
                                    pathTracker->nodes.push_back(
                                        std::move(node));
                                    pathTracker->memo.emplace(
                                        state_obj,
                                        (long) pathTracker->nodes.size() - 1);
                                    Py_INCREF(state_obj);
                                }
                            }
                            if (!state_done) {
                                Py_ssize_t gs_pos = 0;
                                PyObject* gs_key;
                                PyObject* gs_val;
                                while (wrote_ok
                                       && PyDict_Next(state_obj, &gs_pos,
                                                      &gs_key, &gs_val)) {
                                    Py_ssize_t gk_len;
                                    const char* gk = PyUnicode_AsUTF8AndSize(
                                        gs_key, &gk_len);
                                    if (gk == nullptr) {
                                        wrote_ok = false;
                                        break;
                                    }
                                    if (!PyUnicode_IS_ASCII(gs_key))
                                        writer->MarkMaybeNonAscii();
                                    writer->Key(gk, (SizeType) gk_len);
                                    PATH_PUSH_KEY(gk, gk_len)
                                    wrote_ok = RECURSE(gs_val);
                                    PATH_POP()
                                }
                            }
                        }
                        attrsDict = saved_attrs_style;
                        Py_DECREF(state_obj);
                        if (!wrote_ok)
                            return false;
                        writer->EndObject();
                        return PyErr_Occurred() ? false : true;
                    }
                } else {

                // (set/frozenset ne passent plus ici : branche native en
                // amont — un plan inattendu retombe sur la recette normale)
                PyObject* tup = PyObject_CallFunctionObjArgs(
                    recipe_fn, object, nullptr);
                if (tup == nullptr)
                    return false;
                // plan marqué "type" : mémorise classe -> nom émis, la
                // branche native servira les prochains dumps sans python
                if (PyTuple_GET_SIZE(plan) == 4
                    && PyUnicode_Check(PyTuple_GET_ITEM(plan, 3))
                    && PyUnicode_CompareWithASCIIString(
                           PyTuple_GET_ITEM(plan, 3), "type") == 0
                    && PyTuple_Check(tup) && PyTuple_GET_SIZE(tup) >= 2) {
                    PyObject* targs = PyTuple_GET_ITEM(tup, 1);
                    if (PyTuple_CheckExact(targs)
                        && PyTuple_GET_SIZE(targs) == 1
                        && PyUnicode_CheckExact(PyTuple_GET_ITEM(targs, 0))) {
                        if (sj_type_names_cache == nullptr)
                            sj_type_names_cache = PyDict_New();
                        if (sj_type_names_cache != nullptr
                            && PyDict_SetItem(sj_type_names_cache, object,
                                              PyTuple_GET_ITEM(targs, 0)) < 0)
                            PyErr_Clear();
                    }
                }
                Py_ssize_t tup_size =
                    PyTuple_Check(tup) ? PyTuple_GET_SIZE(tup) : 0;
                PyObject* class_str_obj =
                    (tup_size >= 2) ? PyTuple_GET_ITEM(tup, 0) : nullptr;
                PyObject* init_args =
                    (tup_size >= 2) ? PyTuple_GET_ITEM(tup, 1) : nullptr;
                PyObject* state_obj =
                    (tup_size > 2) ? PyTuple_GET_ITEM(tup, 2) : Py_None;
                PyObject* list_items =
                    (tup_size > 3) ? PyTuple_GET_ITEM(tup, 3) : Py_None;
                PyObject* dict_items =
                    (tup_size > 4) ? PyTuple_GET_ITEM(tup, 4) : Py_None;
                PyObject* new_args =
                    (tup_size > 5) ? PyTuple_GET_ITEM(tup, 5) : Py_None;
                // formes prises en charge : nom str — ou la CLASSE de
                // l'objet elle-même (plugins du registre), remplacée par le
                // nom précalculé du plan — et arguments None ou tuple/liste/
                // dict EXACTS (les mêmes tests de type que
                // _dict_from_instance, qui compare par type exact)
                bool shape_ok = tup_size >= 2 && tup_size <= 6;
                if (shape_ok && !PyUnicode_Check(class_str_obj)) {
                    if (class_str_obj == (PyObject*) Py_TYPE(object)
                        && PyTuple_GET_SIZE(plan) >= 4
                        && PyUnicode_Check(PyTuple_GET_ITEM(plan, 3)))
                        class_str_obj = PyTuple_GET_ITEM(plan, 3);
                    else
                        shape_ok = false;
                }
                for (PyObject* args : {init_args, new_args})
                    if (shape_ok && args != Py_None && args != nullptr
                        && !PyTuple_CheckExact(args)
                        && !PyList_CheckExact(args)
                        && !PyDict_CheckExact(args))
                        shape_ok = false;

                if (shape_ok) {
                    if (pathTracker->dumpedClasses != nullptr)
                        sj_ajoute_classe_dumpee(pathTracker, class_str_obj);

                    bool wrote_ok = true;
                    bool saved_attrs_style = attrsDict;
                    attrsDict = true;   // segments de chemin en style ".attr"
                    writer->StartObject();
                    writer->Key("__class__", 9);
                    Py_ssize_t cls_len;
                    const char* cls_str =
                        PyUnicode_AsUTF8AndSize(class_str_obj, &cls_len);
                    if (cls_str == nullptr) {
                        Py_DECREF(tup);
                        return false;
                    }
                    if (!PyUnicode_IS_ASCII(class_str_obj))
                        writer->MarkMaybeNonAscii();
                    writer->String(cls_str, (SizeType) cls_len);

                    // __new__ puis __init__ (l'ordre d'écriture de
                    // _dict_from_instance), règles de déballage identiques
                    struct ArgSlot {
                        const char* key;
                        SizeType key_length;
                        PyObject* args;
                    };
                    ArgSlot arg_slots[2] = {
                        {"__new__", 7, new_args},
                        {"__init__", 8, init_args},
                    };
                    for (int slot_index = 0;
                         slot_index < 2 && wrote_ok; slot_index++) {
                        PyObject* args = arg_slots[slot_index].args;
                        if (args == Py_None || args == nullptr)
                            continue;
                        writer->Key(arg_slots[slot_index].key,
                                    arg_slots[slot_index].key_length);
                        PATH_PUSH_KEY(arg_slots[slot_index].key,
                                      arg_slots[slot_index].key_length)
                        PyObject* single = nullptr;
                        bool write_list = false;
                        bool verbatim_list = false;
                        if (PyDict_CheckExact(args)) {
                            single = args;   // arguments nommés : dict tel quel
                        } else if (PyList_CheckExact(args)) {
                            // liste EXACTE = valeur TELLE QUELLE : le
                            // déballage remove_add_braces des recettes
                            // set/frozenset (un set d'un seul élément
                            // reste [x], jamais dépouillé en scalaire)
                            verbatim_list = true;
                        } else {
                            Py_ssize_t nargs = PySequence_Fast_GET_SIZE(args);
                            if (nargs == 1) {
                                PyObject* first =
                                    PySequence_Fast_GET_ITEM(args, 0);
                                bool keep_list = PyTuple_CheckExact(first)
                                    || PyList_CheckExact(first)
                                    || (numpy_keeps_list
                                        && strcmp(Py_TYPE(first)->tp_name,
                                                  "numpy.ndarray") == 0);
                                if (!keep_list && PyDict_CheckExact(first))
                                    keep_list = PyDict_GetItem(
                                        first, class_key_name) == nullptr;
                                if (!keep_list)
                                    single = first;
                                else
                                    write_list = true;
                            } else {
                                write_list = true;
                            }
                        }
                        if (verbatim_list) {
                            bool args_compact = (slot_index == 0
                                                 ? pathTracker->singleLineNew
                                                 : pathTracker->singleLineInit)
                                && !writer->InCompact();
                            if (args_compact)
                                writer->PushCompact();
                            wrote_ok = RECURSE(args);
                            if (args_compact)
                                writer->PopCompact();
                        } else if (single != nullptr) {
                            wrote_ok = RECURSE(single);
                        } else if (write_list) {
                            // default() enveloppe les listes __init__/__new__
                            // dans SingleLine (single_line_init/new) : même
                            // forme compacte ici
                            bool args_compact = (slot_index == 0
                                                 ? pathTracker->singleLineNew
                                                 : pathTracker->singleLineInit)
                                && !writer->InCompact();
                            if (args_compact)
                                writer->PushCompact();
                            writer->StartArray();
                            Py_ssize_t nargs = PySequence_Fast_GET_SIZE(args);
                            for (Py_ssize_t ai = 0;
                                 ai < nargs && wrote_ok; ai++) {
                                PyObject* arg_item =
                                    PySequence_Fast_GET_ITEM(args, ai);
                                if (sj_write_scalar_inline(writer, arg_item))
                                    continue;
                                PATH_PUSH_INDEX(ai)
                                wrote_ok = RECURSE(arg_item);
                                PATH_POP()
                            }
                            if (wrote_ok)
                                writer->EndArray();
                            if (args_compact)
                                writer->PopCompact();
                        }
                        PATH_POP()
                    }

                    // __items__ : listitems prioritaire, sinon dictitems
                    if (wrote_ok) {
                        PyObject* items = nullptr;
                        if (list_items != Py_None && list_items != nullptr
                            && PyObject_IsTrue(list_items) == 1)
                            items = list_items;
                        else if (dict_items != Py_None && dict_items != nullptr
                                 && PyObject_IsTrue(dict_items) == 1)
                            items = dict_items;
                        if (items != nullptr) {
                            writer->Key("__items__", 9);
                            PATH_PUSH_KEY("__items__", 9)
                            wrote_ok = RECURSE(items);
                            PATH_POP()
                        }
                    }

                    // état : dict à clés str -> attributs à plat (l'ordre du
                    // dict, ni tri ni filtre : dictionnaire.update(state)),
                    // avec la rigueur du __dict__ réel partagé ; sinon
                    // "__state__"
                    if (wrote_ok && state_obj != Py_None
                        && state_obj != nullptr
                        && PyObject_IsTrue(state_obj) == 1) {
                        bool flat = PyDict_CheckExact(state_obj)
                            && !sj_state_key_reserved(state_obj);
                        if (flat
                            && PyObject_HasAttrString(object, "__setstate__")) {
                            Py_ssize_t key_pos = 0;
                            PyObject* key;
                            PyObject* val;
                            while (PyDict_Next(state_obj, &key_pos,
                                               &key, &val)) {
                                if (!PyUnicode_Check(key)) {
                                    flat = false;
                                    break;
                                }
                            }
                        }
                        if (!flat) {
                            writer->Key("__state__", 9);
                            PATH_PUSH_KEY("__state__", 9)
                            wrote_ok = RECURSE(state_obj);
                            PATH_POP()
                        } else {
                            PyObject* real_dict =
                                PyObject_GetAttr(object, dict_dunder_name);
                            if (real_dict == nullptr)
                                PyErr_Clear();
                            bool is_real_dict = (real_dict == state_obj);
                            Py_XDECREF(real_dict);
                            bool state_done = false;
                            if (is_real_dict && pathTracker->memoContainers) {
                                auto dict_it =
                                    pathTracker->memo.find(state_obj);
                                if (dict_it != pathTracker->memo.end()) {
                                    // déjà écrit ailleurs : {"__dict__":
                                    // {"$ref": ...}} et rien d'autre
                                    writer->Key("__dict__", 8);
                                    const std::string& ref_ = sj_ref_json(
                                        pathTracker, dict_it->second);
                                    writer->RawValue(ref_.data(),
                                                     ref_.size());
                                    state_done = true;
                                } else {
                                    // memo_state_dict : le vrai __dict__
                                    // devient adressable "<chemin>.__dict__"
                                    long recipe_node =
                                        path_tracker_materialize(pathTracker);
                                    PathNode node;
                                    node.parent = (int) recipe_node;
                                    node.kind = PathSegment::ATTR;
                                    node.key = "__dict__";
                                    node.index = 0;
                                    pathTracker->nodes.push_back(
                                        std::move(node));
                                    pathTracker->memo.emplace(
                                        state_obj,
                                        (long) pathTracker->nodes.size() - 1);
                                    Py_INCREF(state_obj);
                                }
                            }
                            if (!state_done) {
                                Py_ssize_t state_pos = 0;
                                PyObject* state_key;
                                PyObject* state_val;
                                while (wrote_ok
                                       && PyDict_Next(state_obj, &state_pos,
                                                      &state_key,
                                                      &state_val)) {
                                    if (!PyUnicode_Check(state_key)) {
                                        wrote_ok = false;   // clés non-str
                                        break;              // sans setstate :
                                    }                       // erreur en aval
                                    Py_ssize_t sk_len;
                                    const char* sk = PyUnicode_AsUTF8AndSize(
                                        state_key, &sk_len);
                                    if (sk == nullptr) {
                                        wrote_ok = false;
                                        break;
                                    }
                                    if (!PyUnicode_IS_ASCII(state_key))
                                        writer->MarkMaybeNonAscii();
                                    writer->Key(sk, (SizeType) sk_len);
                                    PATH_PUSH_KEY(sk, sk_len)
                                    wrote_ok = RECURSE(state_val);
                                    PATH_POP()
                                }
                            }
                        }
                    }
                    attrsDict = saved_attrs_style;
                    if (wrote_ok)
                        writer->EndObject();
                    Py_DECREF(tup);
                    if (!wrote_ok)
                        return false;
                    return PyErr_Occurred() ? false : true;
                }
                // tuple inattendu : voie Python (defaultFn ci-dessous) —
                // le mémo C reste le bon, les rencontres suivantes du même
                // objet y répondront par le même $ref que default()
                Py_DECREF(tup);
                }   // fin de la variante tuple (__serializejson__/registre)
            } else if (plan != Py_None && PyTuple_GET_SIZE(plan) == 2
                       && PyLong_CheckExact(PyTuple_GET_ITEM(plan, 1))) {
                // ----- recette collections native (plan (nom, genre)) :
                // l'enveloppe {__class__, __init__[, __items__]} du reduce à
                // listitems/dictitems est composée ici, octet pour octet
                // comme la voie python — plus aucun rappel par objet.
                // Genres : 2 deque, 3 Counter, 4 OrderedDict, 5 defaultdict
                long genre = PyLong_AsLong(PyTuple_GET_ITEM(plan, 1));
                PyObject* class_name = PyTuple_GET_ITEM(plan, 0);
                bool eligible = genre >= 2 && genre <= 5;
                PyObject* factory = nullptr;   // defaultdict.default_factory
                if (genre == 2) {
                    // deque à maxlen : init composite (tuple vide, maxlen),
                    // voie python — décidé par OBJET
                    PyObject* maxlen =
                        PyObject_GetAttrString(object, "maxlen");
                    if (maxlen == nullptr) {
                        PyErr_Clear();
                        eligible = false;
                    } else {
                        eligible = maxlen == Py_None;
                        Py_DECREF(maxlen);
                    }
                } else if (genre == 5) {
                    factory =
                        PyObject_GetAttrString(object, "default_factory");
                    if (factory == nullptr) {
                        PyErr_Clear();
                        eligible = false;
                    }
                }
                if (eligible) {
                    CONTAINER_MEMO_OR_REF()

                    if (pathTracker->dumpedClasses != nullptr)
                        sj_ajoute_classe_dumpee(pathTracker, class_name);

                    Py_ssize_t name_length;
                    const char* name_str =
                        PyUnicode_AsUTF8AndSize(class_name, &name_length);
                    if (name_str == nullptr) {
                        Py_XDECREF(factory);
                        return false;
                    }
                    writer->StartObject();
                    writer->Key("__class__", 9);
                    writer->String(name_str, (SizeType) name_length);
                    writer->Key("__init__", 8);

                    // __init__ : [] (deque, OrderedDict, defaultdict sans
                    // fabrique), la fabrique (defaultdict), ou la COPIE
                    // plate du contenu (Counter) — même arbre que le reduce
                    bool ok = true;
                    if (genre == 3) {
                        PyObject* copie = PyDict_Copy(object);
                        if (copie == nullptr) {
                            Py_XDECREF(factory);
                            return false;
                        }
                        if (pathTracker) {
                            pathTracker->segments.push_back(
                                {PathSegment::ATTR, "__init__", 8, 0});
                            pathTracker->registered.push_back(-1);
                        }
                        ok = RECURSE(copie);
                        PATH_POP();
                        Py_DECREF(copie);
                    } else if (genre == 5 && factory != Py_None) {
                        if (pathTracker) {
                            pathTracker->segments.push_back(
                                {PathSegment::ATTR, "__init__", 8, 0});
                            pathTracker->registered.push_back(-1);
                        }
                        ok = RECURSE(factory);
                        PATH_POP();
                    } else {
                        writer->StartArray();
                        writer->EndArray();
                    }
                    Py_XDECREF(factory);
                    if (!ok)
                        return false;

                    // __items__ : liste des éléments (deque) ou copie plate
                    // (OrderedDict, defaultdict), omis si vide — comme les
                    // listitems/dictitems du reduce
                    Py_ssize_t taille = PyObject_Size(object);
                    if (taille < 0) {
                        PyErr_Clear();
                        taille = 0;
                    }
                    if (genre != 3 && taille > 0) {
                        PyObject* contenu = genre == 2
                            ? PySequence_List(object)
                            : PyDict_Copy(object);
                        if (contenu == nullptr)
                            return false;
                        writer->Key("__items__", 9);
                        if (pathTracker) {
                            pathTracker->segments.push_back(
                                {PathSegment::ATTR, "__items__", 9, 0});
                            pathTracker->registered.push_back(-1);
                        }
                        ok = RECURSE(contenu);
                        PATH_POP();
                        Py_DECREF(contenu);
                        if (!ok)
                            return false;
                    }
                    writer->EndObject();
                    return PyErr_Occurred() ? false : true;
                }
                Py_XDECREF(factory);
                // objet particulier (deque à maxlen) : chemin Python
            } else if (plan != Py_None) {
                PyObject* class_name = PyTuple_GET_ITEM(plan, 0);
                bool filter_underscore =
                    PyObject_IsTrue(PyTuple_GET_ITEM(plan, 1)) == 1;
                // recette __slots__ : tuple de noms PRÉ-TRIÉS par le Python
                // (copyreg._slotnames : héritage et name mangling compris)
                PyObject* slotsNames = nullptr;
                if (PyTuple_GET_SIZE(plan) == 3) {
                    slotsNames = PyTuple_GET_ITEM(plan, 2);
                    if (slotsNames == Py_None || !PyTuple_CheckExact(slotsNames))
                        slotsNames = nullptr;
                }

                // doublon ou cycle -> $ref
                auto memo_it = pathTracker->memo.find(object);
                if (memo_it != pathTracker->memo.end()) {
                    const std::string& ref_ =
                        sj_ref_json(pathTracker, memo_it->second);
                    writer->RawValue(ref_.data(), ref_.size());
                    return true;
                }

                PyObject* object_dict = PyObject_GetAttr(object, dict_dunder_name);
                if (object_dict == nullptr)
                    PyErr_Clear();  // objet sans __dict__ : aucun attribut

                // collecte et validation des attributs AVANT toute écriture
                struct FastAttr {
                    const char* key;
                    Py_ssize_t len;
                    PyObject* value;
                };
                std::vector<FastAttr> attrs;
                bool eligible = true;
                bool all_kept = true;
                bool already_sorted = true;
                if (object_dict != nullptr) {
                    if (PyDict_CheckExact(object_dict)) {
                        attrs.reserve((size_t) PyDict_GET_SIZE(object_dict));
                        Py_ssize_t pos = 0;
                        PyObject* key;
                        PyObject* value;
                        while (PyDict_Next(object_dict, &pos, &key, &value)) {
                            if (!PyUnicode_Check(key)) {
                                eligible = false;  // clés non-chaînes : chemin Python
                                break;
                            }
                            Py_ssize_t key_length;
                            const char* key_str =
                                PyUnicode_AsUTF8AndSize(key, &key_length);
                            if (key_str == nullptr) {
                                Py_DECREF(object_dict);
                                return false;
                            }
                            if (filter_underscore && key_length
                                && key_str[0] == '_') {
                                all_kept = false;
                                continue;
                            }
                            // APRÈS le filtre : un nom porteur écarté par le
                            // filtre ne déclenche pas de repli inutile
                            if (key_length >= 4
                                && (key_str[0] == '_' || key_str[0] == '$')
                                && sj_name_is_reserved(key_str, key_length)) {
                                // attribut au nom porteur : voie Python,
                                // qui route l'état sous "__state__"
                                eligible = false;
                                break;
                            }
                            if (!PyUnicode_IS_ASCII(key))
                                writer->MarkMaybeNonAscii();
                            if (!attrs.empty()) {
                                const FastAttr& previous = attrs.back();
                                size_t common = (size_t)
                                    (previous.len < key_length ? previous.len
                                                               : key_length);
                                int compare = memcmp(previous.key, key_str, common);
                                if (compare > 0
                                    || (compare == 0 && previous.len > key_length))
                                    already_sorted = false;
                            }
                            attrs.push_back({key_str, key_length, value});
                        }
                    } else {
                        eligible = false;  // __dict__ exotique : chemin Python
                    }
                }
                // slots : valeurs par getattr, dans l'ordre trié de la
                // recette ; un slot jamais assigné est simplement absent
                // (comme le __getstate__ du chemin Python). La recette
                // garantit dictoffset == 0, donc pas de __dict__ à fusionner
                // — s'il y en a un malgré tout, prudence : voie Python.
                SjOwnedRefs ownedSlotValues;
                if (slotsNames != nullptr) {
                    if (object_dict != nullptr) {
                        eligible = false;
                    } else {
                        Py_ssize_t slots_count = PyTuple_GET_SIZE(slotsNames);
                        attrs.reserve((size_t) slots_count);
                        for (Py_ssize_t si = 0; si < slots_count; si++) {
                            PyObject* slot_name =
                                PyTuple_GET_ITEM(slotsNames, si);
                            Py_ssize_t key_length;
                            const char* key_str = PyUnicode_AsUTF8AndSize(
                                slot_name, &key_length);
                            if (key_str == nullptr)
                                return false;
                            if (filter_underscore && key_length
                                && key_str[0] == '_')
                                continue;
                            PyObject* value =
                                PyObject_GetAttr(object, slot_name);
                            if (value == nullptr) {
                                PyErr_Clear();   // slot jamais assigné
                                continue;
                            }
                            ownedSlotValues.refs.push_back(value);
                            if (!PyUnicode_IS_ASCII(slot_name))
                                writer->MarkMaybeNonAscii();
                            attrs.push_back({key_str, key_length, value});
                        }
                    }
                }
                if (eligible) {
                    if (!already_sorted)
                        std::sort(attrs.begin(), attrs.end(),
                                  [](const FastAttr& a, const FastAttr& b) {
                                      size_t common = (size_t)
                                          (a.len < b.len ? a.len : b.len);
                                      int compare = memcmp(a.key, b.key, common);
                                      return compare < 0
                                          || (compare == 0 && a.len < b.len);
                                  });

                    // rigueur du __dict__ réel partagé, comme le chemin Python :
                    // s'il a déjà été écrit ailleurs, on le référence au lieu
                    // de l'aplatir une seconde fois
                    long shared_dict_node = -2;
                    if (object_dict != nullptr && pathTracker->memoContainers) {
                        auto dict_it = pathTracker->memo.find(object_dict);
                        if (dict_it != pathTracker->memo.end())
                            shared_dict_node = dict_it->second;
                    }

                    // mémo de l'objet lui-même (avant les valeurs : cycles)
                    long object_node = path_tracker_materialize(pathTracker);
                    pathTracker->memo.emplace(object, object_node);
                    Py_INCREF(object);

                    writer->StartObject();
                    writer->Key("__class__", 9);
                    Py_ssize_t name_length;
                    const char* name_str =
                        PyUnicode_AsUTF8AndSize(class_name, &name_length);
                    if (name_str == nullptr) {
                        Py_XDECREF(object_dict);
                        return false;
                    }
                    if (!PyUnicode_IS_ASCII(class_name))
                        writer->MarkMaybeNonAscii();
                    writer->String(name_str, (SizeType) name_length);

                    if (shared_dict_node != -2) {
                        writer->Key("__dict__", 8);
                        const std::string& ref_ =
                            sj_ref_json(pathTracker, shared_dict_node);
                        writer->RawValue(ref_.data(), ref_.size());
                    } else {
                        // rend le vrai __dict__ adressable pour la suite s'il
                        // est écrit à l'identique (rien filtré, déjà trié)
                        if (object_dict != nullptr && pathTracker->memoContainers
                            && all_kept && already_sorted) {
                            PathNode node;
                            node.parent = (int) object_node;
                            node.kind = PathSegment::ATTR;
                            node.key = "__dict__";
                            node.index = 0;
                            pathTracker->nodes.push_back(std::move(node));
                            pathTracker->memo.emplace(
                                object_dict,
                                (long) pathTracker->nodes.size() - 1);
                            Py_INCREF(object_dict);
                        }
                        attrsDict = true;  // segments de chemin en style ".attr"
                        for (const FastAttr& attr : attrs) {
                            writer->Key(attr.key, (SizeType) attr.len);
                            if (sj_write_scalar_inline(writer, attr.value))
                                continue;
                            if (PyUnicode_CheckExact(attr.value)) {
                                Py_ssize_t inline_length;
                                const char* inline_str = PyUnicode_AsUTF8AndSize(
                                    attr.value, &inline_length);
                                if (inline_str == nullptr) {
                                    Py_XDECREF(object_dict);
                                    return false;
                                }
                                if (!PyUnicode_IS_ASCII(attr.value))
                                    writer->MarkMaybeNonAscii();
                                writer->PyString_(attr.value, inline_str,
                                                  (SizeType) inline_length);
                                continue;
                            }
                            if (Py_EnterRecursiveCall(" while JSONifying object")) {
                                Py_XDECREF(object_dict);
                                return false;
                            }
                            PATH_PUSH_KEY(attr.key, attr.len);
                            bool r = RECURSE(attr.value);
                            PATH_POP();
                            Py_LeaveRecursiveCall();
                            if (!r) {
                                Py_XDECREF(object_dict);
                                return false;
                            }
                        }
                    }
                    writer->EndObject();
                    Py_XDECREF(object_dict);
                    return PyErr_Occurred() ? false : true;
                }
                Py_XDECREF(object_dict);
                // classe éligible mais objet particulier : chemin Python
            }
        }
        PyObject* retval = PyObject_CallFunctionObjArgs(defaultFn, object, nullptr);
        if (retval == nullptr)
            return false;
        if (Py_EnterRecursiveCall(" while JSONifying default function result")) {
            Py_DECREF(retval);
            return false;
        }
        // le résultat de default() est l'état de l'objet : si c'est un dict,
        // ses clés sont des attributs pour le chemin JSON (".attr")
        if (pathTracker)
            pathTracker->next_dict_is_attrs = true;
        else
            sj_next_dict_is_attrs_noplan = true;
        bool r = RECURSE(retval);
        if (pathTracker)
            pathTracker->next_dict_is_attrs = false;
        else
            sj_next_dict_is_attrs_noplan = false;
        Py_LeaveRecursiveCall();
        Py_DECREF(retval);
        if (!r)
            return false;
    }
	else {
        PyErr_Format(PyExc_TypeError, "%R is not JSON serializable", object);
        return false;
    }

    // Catch possible error raised in associated stream operations.
    // ⚠ pas de Flush() ici : dumps_internal est appelé pour CHAQUE valeur, et
    // le Flush de PyBytesBuffer RÉTRÉCIT le buffer à sa taille — chaque valeur
    // suivante devait alors le ré-agrandir (realloc + copie), rendant
    // l'encodage QUADRATIQUE sur les longues listes de scalaires. Le Flush
    // final est fait une seule fois par les macros DUMPS_INTERNAL_CALL*.
    return PyErr_Occurred() ? false : true;

#undef RECURSE
#undef CONTAINER_MEMO_OR_REF
#undef CALL_CONTAINER_HOOK
#undef PATH_PUSH_INDEX
#undef PATH_PUSH_KEY
#undef PATH_POP
#undef ASSERT_VALID_SIZE
}


// Graphie JSON d'une clé tuple ou frozenset, écrite par dumps_internal dans
// un tampon à part — mêmes octets que le rappel python _cle_json, qui
// appelait rapidjson.dumps(clé, default=_default_one_line, NM_NATIVE,
// IM_ONLY_LISTS), sans le rappel.
//   - le tuple EXTÉRIEUR est aplati en liste ("[5, 6]"), comme le faisait
//     _cle_json ; les tuples IMBRIQUÉS gardent leur enveloppe __new__ ;
//   - le traqueur extérieur est réemprunté (branches natives tuple,
//     frozenset et plans de classe), mais son MÉMO est suspendu : une clé
//     n'émet ni "$ref" ni entrée de mémo — la voie python dumpait sans
//     traqueur, donc sans mémo.
static bool
sj_cle_native(PyObject* key, PathTracker* pathTracker, unsigned datetimeMode,
              unsigned uuidMode, unsigned bytesMode, unsigned iterableMode,
              unsigned mappingMode, std::string& texte, bool* non_ascii)
{
    PyObject* cible = key;
    if (PyTuple_CheckExact(key)) {
        cible = PySequence_List(key);
        if (cible == nullptr)
            return false;
    } else
        Py_INCREF(cible);
    bool ok = false;
    const bool memo = pathTracker->memoContainers;
    pathTracker->memoContainers = false;
    try {
        PyBytesBuffer buf(64);
        Writer<PyBytesBuffer> keywriter(buf);
        if (dumps_internal(&keywriter, cible, pathTracker->defaultOneLineFn,
                           nullptr, nullptr, pathTracker, NM_NATIVE,
                           datetimeMode, uuidMode, bytesMode, iterableMode,
                           mappingMode)) {
            buf.Flush();
            texte.assign(buf.GetBuffer(), buf.GetSize());
            *non_ascii = buf.maybe_non_ascii;
            ok = true;
        }
    } catch (const std::bad_alloc&) {
        if (!PyErr_Occurred())
            PyErr_NoMemory();
    }
    pathTracker->memoContainers = memo;
    Py_DECREF(cible);
    return ok;
}


typedef struct {
    PyObject_HEAD
    bool ensureAscii;
    unsigned writeMode;
    char indentChar;
    unsigned indentCount;
    unsigned datetimeMode;
    unsigned uuidMode;
    unsigned numberMode;
    unsigned bytesMode;
    unsigned iterableMode;
    unsigned mappingMode;
    bool returnBytes;
    // mémo C++ des dicts/listes déjà écrits (doublons et cycles -> $ref)
    bool memoRefs;
    // listes homogènes de nombres sur une seule ligne, partout
    bool singleLineNumbers;
    bool singleLineInit;
    bool singleLineNew;
    bool strictPickle;
    // traqueur de chemin actif pendant un encodage (nullptr sinon),
    // consulté par la méthode json_path()
    PathTracker* activePathTracker;
    // tailles atteintes au dump précédent : pré-réservation du prochain
    // (évite les réallocations-copies mesurées ~8% sur les gros graphes)
    size_t pathNodesHighWater;
    size_t memoHighWater;
    // brouillons réutilisables du multithread numérique (voir SjMtScratch)
    SjMtScratch* mtScratch;
    // taille de sortie atteinte au dump précédent (capacité initiale du suivant)
    size_t outputHighWater;
    // entrées d'index des maillons déjà appendés, en attente que la liste se
    // referme : rien ne part sur le disque avant, et rien ne repasse par un
    // objet python entre deux appends
    std::string* indexAppend;
    // écrivain et tampon d'une liste en cours de remplissage par appends : ils
    // VIVENT d'un maillon à l'autre, sans quoi chaque maillon coûterait un
    // write(2) de quelques dizaines d'octets (voir SjAppend)
    WriterThread* ecrivainAppend;
    FdWriteStream* fluxAppend;
    // le dernier appel a dû composer un "$ref" alors que la place du maillon
    // dans la liste était inconnue : le chemin écrit est relatif au maillon,
    // donc illisible dans le document. Python le relève après coup
    // (_ref_impossible) pour retirer le maillon, compter ceux déjà là, et
    // recommencer — un balayage qui ne se paie que dans ce cas
    bool refImpossible;
    // Rappels de l'Encoder python cherchés à chaque appel (default,
    // default_dict, class_plan, _cle_json…). Trois d'entre eux sont ABSENTS
    // de l'Encoder de serializejson, et une recherche qui échoue lève une
    // AttributeError puis l'efface : ~220 ns pièce, contre 44 ns quand
    // l'attribut est là. À elles trois, ces absences coûtaient plus que
    // l'encodage d'un petit objet. On garde donc l'ABSENCE d'un appel à
    // l'autre — jamais les méthodes elles-mêmes : une méthode liée référence
    // son Encoder, et l'Encoder n'étant pas suivi par le ramasse-miettes, la
    // garder ici le rendrait incollectable (mesuré : 50 encodeurs vivants sur
    // 50 au lieu d'un). Le cache vaut tant que la poussée amortie des
    // paramètres globaux vaut (`_owner is self` : le __setattr__ python la
    // casse dès qu'un attribut d'instance change) ET que le type n'a pas bougé
    // (tp_version_tag : une classe repiquée en cours de route, ce que fait un
    // espion de test, doit être vue).
    unsigned char cbAbsents;
    // valeurs, elles aussi cherchées à chaque appel, et sans lien retour vers
    // l'Encoder : un entier se garde sans rien retenir (-1 : pas encore lu)
    PyObject* cbChunkSize;
    Py_ssize_t cbBytesSeuil;
    unsigned int cbTypeVersion;
} EncoderObject;


// bits de EncoderObject::cbAbsents
enum {
    SJ_ABS_DEFAULT   = 1,
    SJ_ABS_DICT      = 2,
    SJ_ABS_LIST      = 4,
    SJ_ABS_PLAN      = 8,
    SJ_ABS_CLE       = 16,
    SJ_ABS_ONE_LINE  = 32,
    SJ_ABS_SEUIL     = 64,
    SJ_ABS_CHUNK     = 128,
};


// Cherche un rappel de l'Encoder en se souvenant de son absence (voir
// EncoderObject::cbAbsents). Rend une référence FORTE, ou nullptr si
// l'attribut manque ou vaut None (rappel désactivé) — sans erreur posée.
static PyObject*
sj_rappel(EncoderObject* e, PyObject* self, PyObject* name, unsigned char bit)
{
    if (e->cbAbsents & bit)
        return nullptr;
    PyObject* fn = PyObject_GetAttr(self, name);
    if (fn == nullptr) {
        PyErr_Clear();
        e->cbAbsents |= bit;
    }
    else if (fn == Py_None) {
        Py_DECREF(fn);
        return nullptr;
    }
    return fn;
}


// Chemin JSON de la valeur en cours d'encodage, au format des "$ref" de
// serializejson : "root", "root[0]", "root['clef']", "root.attribut"...
// À appeler depuis les hooks default/default_dict/default_list ;
// retourne None en dehors d'un encodage.
static PyObject*
encoder_json_path(PyObject* self, PyObject* Py_UNUSED(unused))
{
    EncoderObject* e = (EncoderObject*) self;
    PathTracker* tracker = e->activePathTracker;
    if (tracker == nullptr)
        Py_RETURN_NONE;
    std::string out(tracker->racine.empty() ? "root" : tracker->racine);
    char index_buffer[32];
    for (const PathSegment& segment : tracker->segments) {
        switch (segment.kind) {
        case PathSegment::INDEX:
            snprintf(index_buffer, sizeof(index_buffer), "[%zd]",
                     (ssize_t) segment.index);
            out += index_buffer;
            break;
        case PathSegment::KEY:
            out += "['";
            out.append(segment.str, segment.len);
            out += "']";
            break;
        case PathSegment::ATTR:
            out += '.';
            out.append(segment.str, segment.len);
            break;
        }
    }
    return PyUnicode_FromStringAndSize(out.data(), (Py_ssize_t) out.size());
}


// Identifiant O(1) du chemin courant : matérialise (une seule fois par
// position) la chaîne des noeuds jusqu'à la racine et retourne l'index du
// dernier (-1 = racine). La chaîne de caractères n'est construite que si
// json_path_from_id() est appelé — c'est ce qui rend le mémo des doublons
// bon marché quand il n'y a pas de répétition.
static PyObject*
encoder_json_path_id(PyObject* self, PyObject* Py_UNUSED(unused))
{
    EncoderObject* e = (EncoderObject*) self;
    PathTracker* tracker = e->activePathTracker;
    if (tracker == nullptr)
        Py_RETURN_NONE;
    return PyLong_FromLong(path_tracker_materialize(tracker));
}


// Enregistre le VRAI __dict__ d'un objet au moment où ses attributs sont
// aplatis : un noeud virtuel "<chemin de l'objet>.__dict__" est matérialisé
// et le dict y est mémorisé (référence forte relâchée en fin d'encodage).
// S'il est revu plus tard — directement, ou comme état d'un autre objet qui
// le partage — il devient {"$ref": "....__dict__"} au lieu d'être ré-écrit.
static PyObject*
encoder_memo_state_dict(PyObject* self, PyObject* arg)
{
    EncoderObject* e = (EncoderObject*) self;
    PathTracker* tracker = e->activePathTracker;
    if (tracker == nullptr || !tracker->memoContainers)
        Py_RETURN_NONE;
    if (tracker->memo.find(arg) != tracker->memo.end())
        Py_RETURN_NONE;
    long object_node = path_tracker_materialize(tracker);
    PathNode node;
    node.parent = (int) object_node;
    node.kind = PathSegment::ATTR;
    node.key = "__dict__";
    node.index = 0;
    tracker->nodes.push_back(std::move(node));
    tracker->memo.emplace(arg, (long) tracker->nodes.size() - 1);
    Py_INCREF(arg);
    Py_RETURN_NONE;
}


// identifiant de chemin mémorisé pour un dict/liste déjà écrit par le mémo
// C++ (encoder memo_refs=True) ; None si inconnu — utile pour les Reference
static PyObject*
encoder_json_path_id_of(PyObject* self, PyObject* arg)
{
    EncoderObject* e = (EncoderObject*) self;
    PathTracker* tracker = e->activePathTracker;
    if (tracker == nullptr)
        Py_RETURN_NONE;
    auto it = tracker->memo.find(arg);
    if (it == tracker->memo.end())
        Py_RETURN_NONE;
    return PyLong_FromLong(it->second);
}


static PyObject*
encoder_json_path_from_id(PyObject* self, PyObject* arg)
{
    EncoderObject* e = (EncoderObject*) self;
    PathTracker* tracker = e->activePathTracker;
    if (tracker == nullptr)
        Py_RETURN_NONE;
    long node_index = PyLong_AsLong(arg);
    if (node_index == -1 && PyErr_Occurred())
        return nullptr;
    if (node_index < -1 || node_index >= (long) tracker->nodes.size()) {
        PyErr_SetString(PyExc_ValueError, "unknown json path id");
        return nullptr;
    }
    std::string out = path_tracker_string(tracker, node_index);
    return PyUnicode_FromStringAndSize(out.data(), (Py_ssize_t) out.size());
}


// définies plus bas, avec le rangement d'index dont elles se servent
static PyObject* encoder_index_append_range(PyObject* self, PyObject* args);
static PyObject* encoder_index_append_oublie(PyObject* self, PyObject* unused);
static PyObject* encoder_append_ferme(PyObject* self, PyObject* unused);
static int sj_append_ferme(EncoderObject* e);

// Le dernier encodage a-t-il dû composer un "$ref" sans connaître la place du
// maillon dans la liste ? Voir EncoderObject::refImpossible.
static PyObject*
encoder_ref_impossible(PyObject* self, PyObject* Py_UNUSED(unused))
{
    return PyBool_FromLong(((EncoderObject*) self)->refImpossible ? 1 : 0);
}

static PyMethodDef encoder_methods[] = {
    {"_append_ferme", (PyCFunction) encoder_append_ferme, METH_NOARGS,
     "Vide le tampon de la liste en cours d'appends et ferme son écrivain."},
    {"_ref_impossible", (PyCFunction) encoder_ref_impossible, METH_NOARGS,
     "Le dernier encodage a écrit un $ref sans connaître la place du maillon."},
    {"_index_append_range", (PyCFunction) encoder_index_append_range,
     METH_VARARGS,
     "Range l'index accumulé par les appends, la liste refermée."},
    {"_index_append_oublie", (PyCFunction) encoder_index_append_oublie,
     METH_NOARGS,
     "Jette l'index accumulé par les appends (fichier vidé, index abandonné)."},
    {"json_path", (PyCFunction) encoder_json_path, METH_NOARGS,
     "Chemin JSON de la valeur en cours d'encodage (None hors encodage)."},
    {"json_path_id", (PyCFunction) encoder_json_path_id, METH_NOARGS,
     "Identifiant O(1) du chemin courant, à repasser à json_path_from_id()."},
    {"json_path_from_id", (PyCFunction) encoder_json_path_from_id, METH_O,
     "Chemin JSON correspondant à un identifiant retourné par json_path_id()."},
    {"json_path_id_of", (PyCFunction) encoder_json_path_id_of, METH_O,
     "Identifiant de chemin d'un dict/liste déjà écrit (mémo memo_refs), sinon None."},
    {"memo_state_dict", (PyCFunction) encoder_memo_state_dict, METH_O,
     "Mémorise le vrai __dict__ d'un objet sous '<chemin>.__dict__' (rigueur doublons)."},
    {nullptr, nullptr, 0, nullptr}
};

// dumps =====================================================================

PyDoc_STRVAR(dumps_docstring,
             "dumps(obj, *, skipkeys=False, ensure_ascii=True, write_mode=WM_COMPACT,"
             " indent=4, default=None, sort_keys=False, number_mode=None,"
             " datetime_mode=None, uuid_mode=None, bytes_mode=BM_UTF8,"
             " iterable_mode=IM_ANY_ITERABLE, mapping_mode=MM_ANY_MAPPING,"
             " allow_nan=True)\n"
             "\n"
             "Encode a Python object into a JSON string.");


static PyObject*
dumps(PyObject* self, PyObject* args, PyObject* kwargs)
{
    /* Converts a Python object to a JSON-encoded string. */

    PyObject* value;
    int ensureAscii = true;
    PyObject* indent = nullptr;
    PyObject* defaultFn = nullptr;
    PyObject* numberModeObj = nullptr;
    unsigned numberMode = NM_NAN;
    PyObject* datetimeModeObj = nullptr;
    unsigned datetimeMode = DM_NONE;
    PyObject* uuidModeObj = nullptr;
    unsigned uuidMode = UM_NONE;
    PyObject* bytesModeObj = nullptr;
    unsigned bytesMode = BM_UTF8;
    PyObject* writeModeObj = nullptr;
    unsigned writeMode = WM_COMPACT;
    PyObject* iterableModeObj = nullptr;
    unsigned iterableMode = IM_ANY_ITERABLE;
    PyObject* mappingModeObj = nullptr;
    unsigned mappingMode = MM_ANY_MAPPING;
    int allowNan = -1;
    int returnBytes = false;
    char indentChar = ' ';
    unsigned indentCount = 4;
    static char const* kwlist[] = {
        "obj",
        "skipkeys",             // alias of MM_SKIP_NON_STRING_KEYS
        "ensure_ascii",
        "indent",
        "default",
        "sort_keys",            // alias of MM_SORT_KEYS
        "number_mode",
        "datetime_mode",
        "uuid_mode",
        "bytes_mode",
        "write_mode",
        "iterable_mode",
        "mapping_mode",
        "allow_nan",  /* compatibility with stdlib json */
        "return_bytes",

        nullptr
    };
    int skipKeys = false;
    int sortKeys = false;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|$ppOOpOOOOOOOpp:rapidjson.dumps",
                                     (char**) kwlist,
                                     &value,
                                     &skipKeys,
                                     &ensureAscii,
                                     &indent,
                                     &defaultFn,
                                     &sortKeys,
                                     &numberModeObj,
                                     &datetimeModeObj,
                                     &uuidModeObj,
                                     &bytesModeObj,
                                     &writeModeObj,
                                     &iterableModeObj,
                                     &mappingModeObj,
                                     &allowNan,
                                     &returnBytes
                                     ))
        return nullptr;

    if (defaultFn && !PyCallable_Check(defaultFn)) {
        if (defaultFn == Py_None) {
            defaultFn = nullptr;
        } else {
            PyErr_SetString(PyExc_TypeError, "default must be a callable");
            return nullptr;
        }
    }

    if (!accept_indent_arg(indent, writeMode, indentCount, indentChar))
        return nullptr;

    if (!accept_write_mode_arg(writeModeObj, writeMode))
        return nullptr;

    if (!accept_number_mode_arg(numberModeObj, allowNan, numberMode))
        return nullptr;

    if (!accept_datetime_mode_arg(datetimeModeObj, datetimeMode))
        return nullptr;

    if (!accept_uuid_mode_arg(uuidModeObj, uuidMode))
        return nullptr;

    if (!accept_bytes_mode_arg(bytesModeObj, bytesMode))
        return nullptr;

    if (!accept_iterable_mode_arg(iterableModeObj, iterableMode))
        return nullptr;

    if (!accept_mapping_mode_arg(mappingModeObj, mappingMode))
        return nullptr;

    if (skipKeys)
        mappingMode |= MM_SKIP_NON_STRING_KEYS;

    if (sortKeys)
        mappingMode |= MM_SORT_KEYS;

    return do_encode(value, defaultFn, nullptr, nullptr, nullptr,
                     ensureAscii ? true : false, writeMode, indentChar,
                     indentCount, numberMode, datetimeMode, uuidMode, bytesMode,
                     iterableMode, mappingMode, returnBytes,
                           nullptr);
}

// dumpb =====================================================================

PyDoc_STRVAR(dumpb_docstring,
             "dumpb(obj, *, skipkeys=False, ensure_ascii=True, write_mode=WM_COMPACT,"
             " indent=4, default=None, sort_keys=False, number_mode=None,"
             " datetime_mode=None, uuid_mode=None, bytes_mode=BM_UTF8,"
             " iterable_mode=IM_ANY_ITERABLE, mapping_mode=MM_ANY_MAPPING,"
             " allow_nan=True)\n"
             "\n"
             "Encode a Python object into a JSON bytes.");


static PyObject*
dumpb(PyObject* self, PyObject* args, PyObject* kwargs)
{
    /* Converts a Python object to a JSON-encoded string. */

    PyObject* value;
    int ensureAscii = true;
    PyObject* indent = nullptr;
    PyObject* defaultFn = nullptr;
    PyObject* numberModeObj = nullptr;
    unsigned numberMode = NM_NAN;
    PyObject* datetimeModeObj = nullptr;
    unsigned datetimeMode = DM_NONE;
    PyObject* uuidModeObj = nullptr;
    unsigned uuidMode = UM_NONE;
    PyObject* bytesModeObj = nullptr;
    unsigned bytesMode = BM_UTF8;
    PyObject* writeModeObj = nullptr;
    unsigned writeMode = WM_COMPACT;
    PyObject* iterableModeObj = nullptr;
    unsigned iterableMode = IM_ANY_ITERABLE;
    PyObject* mappingModeObj = nullptr;
    unsigned mappingMode = MM_ANY_MAPPING;
    int allowNan = -1;
    char indentChar = ' ';
    unsigned indentCount = 4;
    static char const* kwlist[] = {
        "obj",
        "skipkeys",             // alias of MM_SKIP_NON_STRING_KEYS
        "ensure_ascii",
        "indent",
        "default",
        "sort_keys",            // alias of MM_SORT_KEYS
        "number_mode",
        "datetime_mode",
        "uuid_mode",
        "bytes_mode",
        "write_mode",
        "iterable_mode",
        "mapping_mode",
        "allow_nan",  /* compatibility with stdlib json */
        nullptr
    };
    int skipKeys = false;
    int sortKeys = false;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|$ppOOpOOOOOOOp:rapidjson.dumpb",
                                     (char**) kwlist,
                                     &value,
                                     &skipKeys,
                                     &ensureAscii,
                                     &indent,
                                     &defaultFn,
                                     &sortKeys,
                                     &numberModeObj,
                                     &datetimeModeObj,
                                     &uuidModeObj,
                                     &bytesModeObj,
                                     &writeModeObj,
                                     &iterableModeObj,
                                     &mappingModeObj,
                                     &allowNan
                                     ))
        return nullptr;

    if (defaultFn && !PyCallable_Check(defaultFn)) {
        if (defaultFn == Py_None) {
            defaultFn = nullptr;
        } else {
            PyErr_SetString(PyExc_TypeError, "default must be a callable");
            return nullptr;
        }
    }

    if (!accept_indent_arg(indent, writeMode, indentCount, indentChar))
        return nullptr;

    if (!accept_write_mode_arg(writeModeObj, writeMode))
        return nullptr;

    if (!accept_number_mode_arg(numberModeObj, allowNan, numberMode))
        return nullptr;

    if (!accept_datetime_mode_arg(datetimeModeObj, datetimeMode))
        return nullptr;

    if (!accept_uuid_mode_arg(uuidModeObj, uuidMode))
        return nullptr;

    if (!accept_bytes_mode_arg(bytesModeObj, bytesMode))
        return nullptr;

    if (!accept_iterable_mode_arg(iterableModeObj, iterableMode))
        return nullptr;

    if (!accept_mapping_mode_arg(mappingModeObj, mappingMode))
        return nullptr;

    if (skipKeys)
        mappingMode |= MM_SKIP_NON_STRING_KEYS;

    if (sortKeys)
        mappingMode |= MM_SORT_KEYS;

    return do_encode(value, defaultFn, nullptr, nullptr, nullptr,
                     ensureAscii ? true : false, writeMode, indentChar,
                     indentCount, numberMode, datetimeMode, uuidMode, bytesMode,
                     iterableMode, mappingMode, true, nullptr);
}


// dump ==========================================================

PyDoc_STRVAR(dump_docstring,
             "dump(obj, stream, *, skipkeys=False, ensure_ascii=True,"
             " write_mode=WM_COMPACT, indent=4, default=None, sort_keys=False,"
             " number_mode=None, datetime_mode=None, uuid_mode=None, bytes_mode=BM_UTF8,"
             " iterable_mode=IM_ANY_ITERABLE, mapping_mode=MM_ANY_MAPPING,"
             " chunk_size=65536, allow_nan=True)\n"
             "\n"
             "Encode a Python object into a JSON stream.");


static PyObject*
dump(PyObject* self, PyObject* args, PyObject* kwargs)
{
    /* Converts a Python object to a JSON-encoded stream. */

    PyObject* value;
    PyObject* stream;
    int ensureAscii = true;
    PyObject* indent = nullptr;
    PyObject* defaultFn = nullptr;
    PyObject* numberModeObj = nullptr;
    unsigned numberMode = NM_NAN;
    PyObject* datetimeModeObj = nullptr;
    unsigned datetimeMode = DM_NONE;
    PyObject* uuidModeObj = nullptr;
    unsigned uuidMode = UM_NONE;
    PyObject* bytesModeObj = nullptr;
    unsigned bytesMode = BM_UTF8;
    PyObject* writeModeObj = nullptr;
    unsigned writeMode = WM_COMPACT;
    PyObject* iterableModeObj = nullptr;
    unsigned iterableMode = IM_ANY_ITERABLE;
    PyObject* mappingModeObj = nullptr;
    unsigned mappingMode = MM_ANY_MAPPING;
    char indentChar = ' ';
    unsigned indentCount = 4;
    PyObject* chunkSizeObj = nullptr;
    size_t chunkSize = 65536;
    int allowNan = -1;
    static char const* kwlist[] = {
        "obj",
        "stream",
        "skipkeys",             // alias of MM_SKIP_NON_STRING_KEYS
        "ensure_ascii",
        "indent",
        "default",
        "sort_keys",            // alias of MM_SORT_KEYS
        "number_mode",
        "datetime_mode",
        "uuid_mode",
        "bytes_mode",
        "chunk_size",
        "write_mode",
        "iterable_mode",
        "mapping_mode",
        "allow_nan",         /* compatibility with stdlib json */
        nullptr
    };
    int skipKeys = false;
    int sortKeys = false;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|$ppOOpOOOOOOOOpp:rapidjson.dump",
                                     (char**) kwlist,
                                     &value,
                                     &stream,
                                     &skipKeys,
                                     &ensureAscii,
                                     &indent,
                                     &defaultFn,
                                     &sortKeys,
                                     &numberModeObj,
                                     &datetimeModeObj,
                                     &uuidModeObj,
                                     &bytesModeObj,
                                     &chunkSizeObj,
                                     &writeModeObj,
                                     &iterableModeObj,
                                     &mappingModeObj,
                                     &allowNan
                                     ))
        return nullptr;

    if (defaultFn && !PyCallable_Check(defaultFn)) {
        if (defaultFn == Py_None) {
            defaultFn = nullptr;
        } else {
            PyErr_SetString(PyExc_TypeError, "default must be a callable");
            return nullptr;
        }
    }

    if (!accept_indent_arg(indent, writeMode, indentCount, indentChar))
        return nullptr;

    if (!accept_write_mode_arg(writeModeObj, writeMode))
        return nullptr;

    if (!accept_number_mode_arg(numberModeObj, allowNan, numberMode))
        return nullptr;

    if (!accept_datetime_mode_arg(datetimeModeObj, datetimeMode))
        return nullptr;

    if (!accept_uuid_mode_arg(uuidModeObj, uuidMode))
        return nullptr;

    if (!accept_bytes_mode_arg(bytesModeObj, bytesMode))
        return nullptr;

    if (!accept_chunk_size_arg(chunkSizeObj, chunkSize))
        return nullptr;

    if (!accept_iterable_mode_arg(iterableModeObj, iterableMode))
        return nullptr;

    if (!accept_mapping_mode_arg(mappingModeObj, mappingMode))
        return nullptr;

    if (skipKeys)
        mappingMode |= MM_SKIP_NON_STRING_KEYS;

    if (sortKeys)
        mappingMode |= MM_SORT_KEYS;

    return do_stream_encode(value, stream, chunkSize, defaultFn, nullptr, nullptr, nullptr,
                            ensureAscii ? true : false, writeMode, indentChar,
                            indentCount, numberMode, datetimeMode, uuidMode, bytesMode,
                            iterableMode, mappingMode);
}

PyDoc_STRVAR(encoder_doc,
             "Encoder(skip_invalid_keys=False, ensure_ascii=True, write_mode=WM_COMPACT,"
             " indent=4, sort_keys=False, number_mode=None, datetime_mode=None,"
             " uuid_mode=None, bytes_mode=None, iterable_mode=IM_ANY_ITERABLE,"
             " mapping_mode=MM_ANY_MAPPING)\n\n"
             "Create and return a new Encoder instance.");


static PyMemberDef encoder_members[] = {
    {"ensure_ascii",
     T_BOOL, offsetof(EncoderObject, ensureAscii), READONLY,
     "whether the output should contain only ASCII characters."},
    {"indent_char",
     T_CHAR, offsetof(EncoderObject, indentChar), READONLY,
     "What will be used as end-of-line character."},
    {"indent_count",
     T_UINT, offsetof(EncoderObject, indentCount), READONLY,
     "The indentation width."},
    {"datetime_mode",
     T_UINT, offsetof(EncoderObject, datetimeMode), READONLY,
     "Whether and how datetime values should be encoded."},
    {"uuid_mode",
     T_UINT, offsetof(EncoderObject, uuidMode), READONLY,
     "Whether and how UUID values should be encoded"},
    {"number_mode",
     T_UINT, offsetof(EncoderObject, numberMode), READONLY,
     "The encoding behavior with regards to numeric values."},
    {"bytes_mode",
     T_UINT, offsetof(EncoderObject, bytesMode), READONLY,
     "How bytes values should be treated."},
    {"write_mode",
     T_UINT, offsetof(EncoderObject, writeMode), READONLY,
     "Whether the output should be pretty printed or not."},
    {"iterable_mode",
     T_UINT, offsetof(EncoderObject, iterableMode), READONLY,
     "Whether iterable values other than lists shall be encoded as JSON arrays or not."},
    {"mapping_mode",
     T_UINT, offsetof(EncoderObject, mappingMode), READONLY,
     "Whether mapping values other than dicts shall be encoded as JSON objects or not."},
    {"return_bytes",
     T_BOOL, offsetof(EncoderObject, returnBytes), READONLY,
     "Whether encoder return Bytes instead of string."},
    {nullptr}
};


static PyObject*
encoder_get_skip_invalid_keys(EncoderObject* e, void* closure)
{
    return PyBool_FromLong(e->mappingMode & MM_SKIP_NON_STRING_KEYS);
}

static PyObject*
encoder_get_sort_keys(EncoderObject* e, void* closure)
{
    return PyBool_FromLong(e->mappingMode & MM_SORT_KEYS);
}

// Backward compatibility, previously they were members of EncoderObject

static PyGetSetDef encoder_props[] = {
    {"skip_invalid_keys", (getter) encoder_get_skip_invalid_keys, nullptr,
     "Whether invalid keys shall be skipped."},
    {"sort_keys", (getter) encoder_get_sort_keys, nullptr,
     "Whether dictionary keys shall be sorted alphabetically."},
    {nullptr}
};

static void encoder_dealloc(PyObject* self)
{
    // libère les brouillons réutilisables du multithread numérique
    delete (SjMtScratch*) ((EncoderObject*) self)->mtScratch;
    // une liste laissée ouverte se referme ici : son crochet fermant dort
    // encore dans le tampon, et le perdre laisserait un json tronqué
    sj_append_ferme((EncoderObject*) self);
    Py_CLEAR(((EncoderObject*) self)->cbChunkSize);
    delete ((EncoderObject*) self)->indexAppend;
    Py_TYPE(self)->tp_free(self);
}

static PyTypeObject Encoder_Type = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "rapidjson.Encoder",                      /* tp_name */
    sizeof(EncoderObject),                    /* tp_basicsize */
    0,                                        /* tp_itemsize */
    (destructor) encoder_dealloc,             /* tp_dealloc */
    0,                                        /* tp_print */
    0,                                        /* tp_getattr */
    0,                                        /* tp_setattr */
    0,                                        /* tp_compare */
    0,                                        /* tp_repr */
    0,                                        /* tp_as_number */
    0,                                        /* tp_as_sequence */
    0,                                        /* tp_as_mapping */
    0,                                        /* tp_hash */
    (ternaryfunc) encoder_call,               /* tp_call */
    0,                                        /* tp_str */
    0,                                        /* tp_getattro */
    0,                                        /* tp_setattro */
    0,                                        /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /* tp_flags */
    encoder_doc,                              /* tp_doc */
    0,                                        /* tp_traverse */
    0,                                        /* tp_clear */
    0,                                        /* tp_richcompare */
    0,                                        /* tp_weaklistoffset */
    0,                                        /* tp_iter */
    0,                                        /* tp_iternext */
    encoder_methods,                          /* tp_methods */
    encoder_members,                          /* tp_members */
    encoder_props,                            /* tp_getset */
    0,                                        /* tp_base */
    0,                                        /* tp_dict */
    0,                                        /* tp_descr_get */
    0,                                        /* tp_descr_set */
    0,                                        /* tp_dictoffset */
    0,                                        /* tp_init */
    0,                                        /* tp_alloc */
    encoder_new,                              /* tp_new */
    PyObject_Del,                             /* tp_free */
};


#define Encoder_CheckExact(v) (Py_TYPE(v) == &Encoder_Type)
#define Encoder_Check(v) PyObject_TypeCheck(v, &Encoder_Type)


#define DUMPS_INTERNAL_CALL                             \
    (dumps_internal(&writer,                            \
                    value,                              \
                    defaultFn,                          \
                    numberMode,                         \
                    datetimeMode,                       \
                    uuidMode,                           \
                    bytesMode,                          \
                    iterableMode,                       \
                    mappingMode)                        \
     ? (returnBytes ? PyBytes_FromString(buf.GetString()) : PyUnicode_FromStringAndSize(buf.GetString(),buf.GetSize())): nullptr)
     
     

#define DUMPS_INTERNAL_CALL_WITH_MEMORYBUFFER           \
    (dumps_internal(&writer,                            \
                    value,                              \
                    defaultFn,                          \
                    numberMode,                         \
                    datetimeMode,                       \
                    uuidMode,                           \
                    bytesMode,                          \
                    iterableMode,                       \
                    mappingMode)                        \
     ? (returnBytes ? PyBytes_FromStringAndSize(buf.GetBuffer(),buf.GetSize()) : PyUnicode_FromStringAndSize(buf.GetBuffer(), buf.GetSize())): nullptr)


     //? PyUnicode_FromString(buf.GetString()) : nullptr) // 140 msec?
     //? _PyUnicode_FromASCII(buf.GetString(), strlen(buf.GetString())) : nullptr)  // 135 msec
     //? PyUnicode_FromStringAndSize(buf.GetBuffer(), buf.GetSize())) : nullptr) //145 msec for 120000000 length
     //? PyBytes_FromString(buf.GetString()) : nullptr)
     //? PyBytes_FromStringAndSize(buf.GetBuffer(),buf.GetSize()) : nullptr)
     
     
// haute-eau à décroissance : retient la taille du dump, ou la moitié du
// niveau précédent si elle est plus grande — après un gros dump isolé, la
// marge fond de moitié en moitié au lieu de rester (effet cliquet) ou de
// disparaître d'un coup (alternance gros/petit repayait ses reallocs)
static inline size_t sj_decayed_high_water(size_t previous, size_t size) {
    size_t decayed = previous / 2;
    return size > decayed ? size : decayed;
}

#define DUMPS_INTERNAL_CALL_WITH_PYBYTESBUFFER           \
    (dumps_internal(&writer,                            \
                    value,                              \
                    defaultFn,                          \
                    defaultDictFn,                      \
                    defaultListFn,                      \
                    pathTracker,                        \
                    numberMode,                         \
                    datetimeMode,                       \
                    uuidMode,                           \
                    bytesMode,                          \
                    iterableMode,                       \
                    mappingMode)                        \
     ? ((outputHighWater ? (void)(*outputHighWater = sj_decayed_high_water(*outputHighWater, buf.GetSize())) : (void)0), buf.Flush(), (returnBytes ? buf.stealPyBytes()         : (buf.maybe_non_ascii            ? PyUnicode_DecodeUTF8(buf.GetBuffer(), (Py_ssize_t) buf.GetSize(), errors)            : buf.stealPyStrAscii()))) : nullptr)


static PyObject*
do_encode(PyObject* value, PyObject* defaultFn,
          PyObject* defaultDictFn, PyObject* defaultListFn,
          PathTracker* pathTracker,
          bool ensureAscii, unsigned writeMode,
          char indentChar, unsigned indentCount, unsigned numberMode,
          unsigned datetimeMode, unsigned uuidMode, unsigned bytesMode,
          unsigned iterableMode, unsigned mappingMode, bool returnBytes,
          size_t* outputHighWater)
{
    // nullptr = "strict" ; jamais sollicité en pratique (l'utf-8 produit
    // par l'encodeur est toujours valide), mais l'ancien pointeur non
    // initialisé était de l'UB latent
    const char *errors = nullptr;
    // préallocation : DEUX fois la haute-eau décroissante (règle choisie le
    // 3/08 : marge de croissance ×2 permanente en régime établi — un dump
    // qui grossit jusqu'au double ne paie aucun realloc — et sur-allouer
    // coûte ~300 fois moins cher que sous-allouer, mesuré 15 µs contre
    // 5 ms sur 90 Mo) ; 0 -> capacité par défaut
    // sortie str : tampon adossé à un str ascii compact, pris tel quel en
    // fin d'encodage si le document est resté ascii (zéro copie terminale)
    PyBytesBuffer buf(outputHighWater && *outputHighWater
                      ? 2 * *outputHighWater : 0, !returnBytes);
    // mémoire insuffisante : Resize lève bad_alloc (MemoryError déjà posée
    // par l'allocateur CPython) — avant, le code déréférençait le NULL
    // laissé par _PyBytes_Resize et plantait le processus
    try {
        if (writeMode == WM_COMPACT) {
            Writer<PyBytesBuffer> writer(buf);
            return DUMPS_INTERNAL_CALL_WITH_PYBYTESBUFFER;
        } else {
            PrettyWriter<PyBytesBuffer> writer(buf);
            writer.SetIndent(indentChar, indentCount);
            if (writeMode & WM_SINGLE_LINE_ARRAY) {
                writer.SetFormatOptions(kFormatSingleLineArray);
            }
            return DUMPS_INTERNAL_CALL_WITH_PYBYTESBUFFER;
        }
    } catch (const std::bad_alloc&) {
        if (!PyErr_Occurred())
            PyErr_NoMemory();
        return nullptr;
    }
}


#define DUMP_INTERNAL_RUN                       \
    dumps_internal(&writer,                     \
                   value,                       \
                   defaultFn,                   \
                   defaultDictFn,               \
                   defaultListFn,               \
                   pathTracker,                 \
                   numberMode,                  \
                   datetimeMode,                \
                   uuidMode,                    \
                   bytesMode,                   \
                   iterableMode,                \
                   mappingMode)

#define DUMP_INTERNAL_CALL                      \
    (DUMP_INTERNAL_RUN ? (writer.Flush(), Py_INCREF(Py_None), Py_None) : nullptr)

// `append` garde son tampon d'un maillon à l'autre : le vider à chaque maillon
// rendrait un write(2) pour quelques dizaines d'octets, et c'est justement ce
// que le tampon persistant évite. Il se vide à la fermeture de la liste.
#define DUMP_INTERNAL_CALL_SANS_VIDAGE          \
    (DUMP_INTERNAL_RUN ? (Py_INCREF(Py_None), Py_None) : nullptr)


static PyObject*
do_stream_encode(PyObject* value, PyObject* stream, size_t chunkSize, PyObject* defaultFn,
                 PyObject* defaultDictFn, PyObject* defaultListFn,
                 PathTracker* pathTracker,
                 bool ensureAscii, unsigned writeMode, char indentChar,
                 unsigned indentCount, unsigned numberMode, unsigned datetimeMode,
                 unsigned uuidMode, unsigned bytesMode, unsigned iterableMode,
                 unsigned mappingMode)
{
    PyWriteStreamWrapper os(stream, chunkSize);

    if (writeMode == WM_COMPACT) {
        Writer<PyWriteStreamWrapper> writer(os);
        return DUMP_INTERNAL_CALL;
    } else {
        PrettyWriter<PyWriteStreamWrapper> writer(os);
        writer.SetIndent(indentChar, indentCount);
        if (writeMode & WM_SINGLE_LINE_ARRAY) {
            writer.SetFormatOptions(kFormatSingleLineArray);
        }
        return DUMP_INTERNAL_CALL;
    }
}


// Où ranger l'index d'un document qui part droit dans un descripteur : les
// deux destinations et la forme retenue, en octets à NOUS. Le thread
// d'écriture les relit après le retour de dump, quand plus aucun objet python
// ne peut être touché — d'où la copie, plutôt que les bytes du convertisseur.
struct SjIndexRangement {
    std::string chemin;
    std::string sidecar;
    bool en_sidecar = false;
    size_t seuil = 0;
};

// (chemin du json, chemin du sidecar, index dans le sidecar), tel que le dump
// python le compose AVANT d'écrire — c'est ce qui permet à l'écrivain de
// ranger seul, sans plus rien demander à personne.
static bool
sj_index_ou_ranger(PyObject* tuple, SjIndexRangement& out)
{
    PyObject* chemin = nullptr;
    PyObject* sidecar = nullptr;
    int en_sidecar;
    if (!PyArg_ParseTuple(tuple, "O&O&p:index_range",
                          PyUnicode_FSConverter, &chemin,
                          PyUnicode_FSConverter, &sidecar, &en_sidecar))
        return false;
    out.chemin.assign(PyBytes_AS_STRING(chemin),
                      (size_t) PyBytes_GET_SIZE(chemin));
    out.sidecar.assign(PyBytes_AS_STRING(sidecar),
                       (size_t) PyBytes_GET_SIZE(sidecar));
    out.en_sidecar = en_sidecar != 0;
    Py_DECREF(chemin);
    Py_DECREF(sidecar);
    return true;
}

// Le rangement lui-même : la queue éventuelle du fichier donne la fin du
// document, le texte des chemins se complète de `root`, se dégonfle et se
// pose. Rend un ERRNO plutôt qu'une exception : il tourne dans le thread
// d'écriture, où plus aucun objet python n'est à portée. `expansions` (voir
// WriterThread::expansions) corrige les positions relevées en compte brut —
// nul quand les entrées sont déjà réelles : dump mémoire (aucun bloc Echappe)
// ou appends (corrigés écrivain par écrivain à sa fermeture, sj_append_ferme).
static int
sj_index_range_fichier(const SjIndexRangement& ou, const char* chemins,
                       size_t len,
                       const std::vector<std::pair<size_t, size_t>>*
                           expansions = nullptr)
{
    SjIndexQueue q;
    errno = 0;
    if (!sj_index_fichier_queue(ou.chemin.c_str(), &q))
        return errno ? errno : EIO;
    std::string corrige;
    if (len && expansions != nullptr && !expansions->empty()) {
        sj_index_corrige(chemins, len, *expansions, corrige);
        chemins = corrige.data();
        len = corrige.size();
    }
    // élagage final au vrai seuil : les entrées retenues par prudence à
    // l'écriture (un bloc à taille variable dans le conteneur) sortent ici si
    // leurs positions corrigées restent sous le seuil — voir sj_index_elague
    std::string elague;
    if (len && ou.seuil > 0) {
        sj_index_elague(chemins, len, ou.seuil, elague);
        chemins = elague.data();
        len = elague.size();
    }
    std::string texte;
    if (len)
        sj_index_compose(ou.seuil, chemins, len, q.fin, texte);
    errno = 0;
    if (!sj_index_fichier_range(ou.chemin.c_str(), ou.sidecar.c_str(),
                                ou.en_sidecar, q.taille, q.fin, texte))
        return errno ? errno : EIO;
    return 0;
}


// L'index accumulé au fil des appends, une fois la liste refermée : composé
// avec `root`, dégonflé et posé, exactement comme celui d'un dump. En
// libération rapide il l'est par un écrivain SANS descripteur, qui ne porte
// que cette tâche — close() rend alors la main sans attendre le dégonflage, et
// tout ce qui relit le fichier (load, paths, index) attend déjà les écrivains.
static PyObject*
encoder_index_append_range(PyObject* self, PyObject* args)
{
    EncoderObject* e = (EncoderObject*) self;
    PyObject* ouObj;
    Py_ssize_t seuil;
    int bloquant;
    if (!PyArg_ParseTuple(args, "Onp:_index_append_range", &ouObj, &seuil,
                          &bloquant))
        return nullptr;
    SjIndexRangement ou;
    if (!sj_index_ou_ranger(ouObj, ou))
        return nullptr;
    ou.seuil = seuil > 0 ? (size_t) seuil : 0;

    // les entrées sont COPIÉES, pas prises : `close=True` à chaque tour est un
    // usage courant, et la liste continue de se remplir derrière lui. Le
    // rangement qui suit compose et dégonfle ces mêmes octets — le memcpy ne
    // pèse rien à côté, et c'est lui qui permet à chaque index posé d'être
    // celui de la liste ENTIÈRE. L'encodeur les oublie quand il change de
    // fichier (_index_append_oublie).
    std::shared_ptr<std::string> chemins(
        e->indexAppend != nullptr ? new std::string(*e->indexAppend)
                                  : new std::string());
    if (bloquant) {
        int rate;
        Py_BEGIN_ALLOW_THREADS
        rate = sj_index_range_fichier(ou, chemins->data(), chemins->size());
        Py_END_ALLOW_THREADS
        if (rate) {
            errno = rate;
            return PyErr_SetFromErrno(PyExc_OSError);
        }
    } else {
        WriterThread* poseur = new WriterThread(-1);
        poseur->rangeApres([ou, chemins]() {
            return sj_index_range_fichier(ou, chemins->data(),
                                          chemins->size());
        });
        poseur->laisseFiler();
    }
    Py_RETURN_NONE;
}

static PyObject*
encoder_index_append_oublie(PyObject* self, PyObject* Py_UNUSED(unused))
{
    delete ((EncoderObject*) self)->indexAppend;
    ((EncoderObject*) self)->indexAppend = nullptr;
    Py_RETURN_NONE;
}


// Vide le tampon de la liste remplie par appends, puis détruit son écrivain.
// Le crochet fermant y dort depuis le dernier maillon : c'est ici, et
// seulement ici, que le fichier devient un json complet. Le descripteur est
// celui de l'appelant (l'écrivain d'un append n'est jamais lâché, donc pas de
// dup), et l'écrivain ne le referme pas. Rend un errno, 0 si tout va bien.
static int
sj_append_ferme(EncoderObject* e)
{
    if (e->ecrivainAppend == nullptr)
        return 0;
    e->fluxAppend->Flush();
    const int erreur = e->fluxAppend->Erreur();
    delete e->fluxAppend;
    e->fluxAppend = nullptr;
    const int fin = e->ecrivainAppend->termine();
    // les entrées relevées pendant la vie de cet écrivain sont en compte
    // BRUT (blocs Echappe, voir WriterThread::expansions) : corrigées ICI,
    // l'écrivain jointe et ses expansions closes, elles redeviennent des
    // positions réelles du fichier. Un écrivain ultérieur (la liste rouverte
    // pour d'autres maillons) lira son `debut` du descripteur, donc en
    // coordonnées réelles : ses expansions ne concerneront que ses propres
    // entrées, jamais celles corrigées ici.
    const std::vector<std::pair<size_t, size_t>>& exp =
        e->ecrivainAppend->expansions();
    if (e->indexAppend != nullptr && !e->indexAppend->empty()
            && !exp.empty()) {
        std::string reel;
        sj_index_corrige(e->indexAppend->data(), e->indexAppend->size(),
                         exp, reel);
        e->indexAppend->swap(reel);
    }
    delete e->ecrivainAppend;
    e->ecrivainAppend = nullptr;
    return erreur != 0 ? erreur : fin;
}

static PyObject*
encoder_append_ferme(PyObject* self, PyObject* Py_UNUSED(unused))
{
    const int erreur = sj_append_ferme((EncoderObject*) self);
    if (erreur != 0) {
        errno = erreur;
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    Py_RETURN_NONE;
}


// Ce qu'un `append` ajoute à un dump ordinaire. L'élément n'est pas un
// document à lui seul : c'est un maillon d'une liste déjà ouverte, indenté
// d'un cran de plus, suivi du crochet qui la referme — et son index vient
// s'ajouter à celui des maillons précédents plutôt que de partir sur le
// disque, puisque la liste n'est pas finie.
//
// Le décalage d'indentation se faisait jusqu'ici côté python, en remplaçant
// les sauts de ligne de chaque morceau écrit ; c'est ce qui interdisait
// d'écrire droit dans le descripteur, donc l'index relevé au vol. Il est
// désormais ouvert à `append`.
//
// Le tampon d'écriture, lui, VIT D'UN MAILLON À L'AUTRE, et c'est là tout le
// prix du chemin : un maillon fait quelques dizaines d'octets, si bien qu'un
// flux par append rendait un write(2) par maillon, là où le détour python
// remplissait tranquillement son tampon de 64 Ko. Mesuré sur 20 000 maillons
// de ~57 octets : 140 ms par le détour python, 270 par un flux jeté à chaque
// maillon, 1000 avec en plus un thread d'écriture par maillon.
struct SjAppend {
    long long rang = -1;          // place du maillon, -1 = maillon non indexé
    std::string* index = nullptr; // entrées des maillons déjà écrits
    size_t seuil = 0;
    // ce qui sépare ce maillon du précédent, écrit devant lui. Vide quand
    // c'est python qui vient d'ouvrir le fichier : il l'a alors écrit
    // lui-même, avec le crochet ouvrant
    const char* debut = nullptr;
    Py_ssize_t debutLen = 0;
    const char* fin = nullptr;    // ce qui referme la liste, écrit derrière
    Py_ssize_t finLen = 0;
    unsigned indente = 0;         // niveaux d'indentation ajoutés
    // emplacements de l'encodeur, où l'écrivain et son tampon survivent à
    // l'appel : nuls au premier maillon, renseignés ensuite
    WriterThread** ecrivain = nullptr;
    FdWriteStream** flux = nullptr;
};

// (rang, séparateur, octets de fermeture, niveaux d'indentation), tel que
// Encoder.append le compose. Le rang vaut -1 quand l'index n'est pas relevé —
// le reste sert de toute façon, `append` passant par le descripteur avec ou
// sans index.
static bool
sj_append_lit(PyObject* tuple, SjAppend& out)
{
    return PyArg_ParseTuple(tuple, "Ly#y#I:append", &out.rang, &out.debut,
                            &out.debutLen, &out.fin, &out.finLen,
                            &out.indente) != 0;
}


// Même chose, mais droit dans un descripteur, et par un thread d'écriture :
// les octets déposés n'appartenant à aucun objet python, la sérialisation et
// l'écriture se RECOUVRENT au lieu de se suivre (voir writerthread.h pour la
// mesure qui justifie ce chemin). Le choix de l'y envoyer est pris côté
// python, qui seul sait si l'objet fichier écrit bien ses octets tels quels —
// un GzipFile a un fileno() et le court-circuiter écrirait à côté de la
// compression.
static PyObject*
do_fd_encode(PyObject* value, int fd, size_t chunkSize, bool bloquant,
             PyObject* defaultFn,
             PyObject* defaultDictFn, PyObject* defaultListFn,
             PathTracker* pathTracker,
             const SjIndexRangement* indexOu, const SjAppend* app,
             bool ensureAscii, unsigned writeMode, char indentChar,
             unsigned indentCount, unsigned numberMode, unsigned datetimeMode,
             unsigned uuidMode, unsigned bytesMode, unsigned iterableMode,
             unsigned mappingMode)
{
    // En libération rapide, le thread écrit APRÈS notre retour : il lui faut
    // un descripteur à lui, que l'appelant ne puisse pas refermer sous ses
    // pieds. dup() en donne un second sur le même fichier, que l'écrivain
    // refermera lui-même. En écriture bloquante on attend avant de rendre la
    // main, donc celui de l'appelant fait l'affaire.
    // L'écrivain d'un `append` SURVIT à l'appel, son tampon avec lui (voir
    // SjAppend), et son thread aussi : lancé une fois pour toute la liste, il
    // ne coûte plus les 50 µs par maillon d'un thread relancé à chaque fois, et
    // il prend à sa charge ce qu'un maillon a de lourd — l'écriture, mais
    // surtout le BASE64 des trames compressées, qui se payait jusqu'ici dans
    // l'append. Mesuré, 200 maillons d'un mégaoctet de bruit, A/B entrelacé sur
    // deux arbres identiques : les appends rendent la main en 126 ms au lieu de
    // 987. Sans le moindre `bytes`, en revanche, il n'y a rien à recouvrir et
    // les deux se valent (86 ms sur 20 000 maillons de 57 octets, 954 contre
    // 997 sur 200 Mo) : ce chemin ne se juge que sur des charges binaires.
    // Il n'a pas besoin de dup() : rien ne le lâche dans la nature, et
    // sj_append_ferme le joint avant que python ne referme le fichier.
    const bool persistant = app != nullptr;
    WriterThread* ecrivain = persistant ? *app->ecrivain : nullptr;
    FdWriteStream* flux = persistant ? *app->flux : nullptr;
    if (ecrivain == nullptr) {
        int fdEcrivain = fd;
        if (!bloquant && !persistant) {
#ifdef _WIN32
            fdEcrivain = _dup(fd);
#else
            fdEcrivain = dup(fd);
#endif
            if (fdEcrivain < 0)
                return PyErr_SetFromErrno(PyExc_OSError);
        }
        ecrivain = new WriterThread(fdEcrivain);
        flux = new FdWriteStream(chunkSize, ecrivain);
        if (persistant) {
            *app->ecrivain = ecrivain;
            *app->flux = flux;
        }
    } else {
        // le crochet fermant du maillon précédent dort encore dans le tampon :
        // le maillon qui vient l'écrase
        flux->Recule((size_t) app->finLen);
    }
    PyObject* result;
    int erreur;
    {
        FdWriteStream& os = *flux;
        // index de position relevé À L'ÉCRITURE : les bornes viennent du flux
        // lui-même, et les chemins des mêmes segments que les $ref. Réservé à
        // ce chemin-ci, le seul dont les positions soient celles du FICHIER.
        SjIndexEcriture index;
        index.segments = &pathTracker->segments;
        index.seuil = indexOu ? indexOu->seuil : 0;
        index.blocsVariables = &os.blocsVariables;
        // un maillon d'append s'indexe sous « root[rang] », et il s'indexe
        // LUI-MÊME : c'est même lui qu'on cherchera à charger seul. Ses
        // entrées reprennent celles des maillons déjà écrits, que l'encodeur
        // garde d'un append à l'autre — rien ne repart sur le disque tant que
        // la liste n'est pas refermée.
        // c'est le SEUIL qui dit si l'index est tenu, pas le rang : celui-ci
        // sert aussi, et d'abord, à composer les chemins $ref du maillon
        const bool releve = indexOu != nullptr
                            || (app != nullptr && app->seuil > 0);
        if (app != nullptr && app->seuil > 0) {
            index.seuil = app->seuil;
            index.racine = "root[";
            index.racine += std::to_string(app->rang);
            index.racine += ']';
            index.indexeRacine = true;
            index.texte.swap(*app->index);
        }
        // la virgule qui suit le maillon précédent, et l'indentation du nôtre :
        // python les écrivait en rouvrant le fichier, ce que le tampon
        // persistant lui épargne
        if (app != nullptr && app->debutLen)
            os.RawValue(app->debut, (size_t) app->debutLen);

        if (writeMode == WM_COMPACT) {
            Writer<FdWriteStream> writer(os);
            if (releve) writer.SetIndex(&index);
            result = app != nullptr ? DUMP_INTERNAL_CALL_SANS_VIDAGE
                                    : DUMP_INTERNAL_CALL;
        } else {
            PrettyWriter<FdWriteStream> writer(os);
            writer.SetIndent(indentChar, indentCount);
            if (app != nullptr) writer.SetIndentBase(app->indente);
            if (writeMode & WM_SINGLE_LINE_ARRAY) {
                writer.SetFormatOptions(kFormatSingleLineArray);
            }
            if (releve) writer.SetIndex(&index);
            result = app != nullptr ? DUMP_INTERNAL_CALL_SANS_VIDAGE
                                    : DUMP_INTERNAL_CALL;
        }
        if (app != nullptr) {
            // les entrées repartent chez l'encodeur, même après un échec : ce
            // qui a été relevé du maillon raté ne vaut rien, mais le fichier
            // non plus — python abandonne alors l'index incrémental
            if (app->seuil > 0)
                app->index->swap(index.texte);
            // le crochet fermant vient DERRIÈRE l'élément, donc après que sa
            // borne de fin a été relevée : le document est un json complet dès
            // qu'il est posé, sans que l'index s'en trouve décalé. Il DORT
            // dans le tampon jusqu'à la fermeture, ou jusqu'au maillon suivant
            // qui l'écrase — l'écrire coûterait un write(2) par maillon
            if (result != nullptr && app->finLen)
                os.RawValue(app->fin, (size_t) app->finLen);
        }
        if (indexOu != nullptr && result != nullptr) {
            // l'écrivain range l'index lui-même, son dernier octet posé : dump
            // rend la main sans attendre ni le disque, ni le dégonflage du
            // bloc. Le texte passe par un pointeur partagé — la lambda est
            // copiée, les 800 ko de chemins ne le sont pas
            std::shared_ptr<std::string> chemins(
                new std::string(std::move(index.texte)));
            const SjIndexRangement ou = *indexOu;
            // la tâche tourne dans le thread de `ecrivain`, l'objet encore
            // vivant et ses blocs tous écrits : ses expansions sont complètes
            ecrivain->rangeApres([ou, chemins, ecrivain]() {
                return sj_index_range_fichier(ou, chemins->data(),
                                              chemins->size(),
                                              &ecrivain->expansions());
            });
        }
        // tout est déposé (writer.Flush) : la taille du document est connue,
        // et c'est le dernier moment où le disque peut encore dire non. Une
        // liste remplie par appends n'a pas de taille finale : elle grandit à
        // chaque maillon, et réserver celle d'un seul ne veut rien dire
        if (!persistant)
            ecrivain->reservePlace();
        erreur = os.Erreur();   // à lire AVANT de lâcher l'écrivain
    }
    if (persistant) {
        // l'écrivain et son tampon restent en place pour le maillon suivant ;
        // c'est la fermeture de la liste qui les vide et les détruit
        if (bloquant) {
            // écriture bloquante demandée : on attend le disque avant de
            // rendre la main, mais le thread, lui, reste en place
            ecrivain->attends();
            if (erreur == 0)
                erreur = ecrivain->erreur();
        }
        if (erreur != 0) {
            Py_XDECREF(result);
            errno = erreur;
            return PyErr_SetFromErrno(PyExc_OSError);
        }
        return result;
    }
    if (bloquant) {
        ecrivain->attends();
        // termine() joint le thread, et c'est LÀ que l'index se range :
        // l'erreur du rangement n'existe pas encore avant, `erreur()` seul ne
        // verrait que les écritures
        const int fin = ecrivain->termine();
        if (erreur == 0)
            erreur = fin;
        delete ecrivain;
    } else {
        // à partir d'ici l'écrivain vit sa vie : plus un seul accès au pointeur
        ecrivain->laisseFiler(erreur != 0);
    }

    // une écriture déjà ratée (descripteur fermé) n'a pas d'exception python
    // attachée : elle est relevée ici, à partir de l'errno gardé. Celles qui
    // rateront après notre retour sont relevées par le prochain wait_writes.
    if (erreur != 0) {
        Py_XDECREF(result);
        errno = erreur;
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    return result;
}


// Attend que toutes les écritures encore en vol soient posées sur le disque.
// Appelé avant toute RELECTURE d'un fichier qu'on vient peut-être d'écrire —
// sans quoi on lirait un document tronqué — et à la fin de l'interpréteur.
static PyObject*
wait_writes(PyObject* Py_UNUSED(module), PyObject* Py_UNUSED(unused))
{
    int erreur = WriterThread::attendsToutes();
    if (erreur != 0) {
        errno = erreur;
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    Py_RETURN_NONE;
}


static PyObject*
encoder_call(PyObject* self, PyObject* args, PyObject* kwargs)
{
    static char const* kwlist[] = {
        "obj",
        "fp",
        "return_bytes",
        "stream",
        "chunk_size",
        "fd",
        "blocking_write",
        "index_threshold",
        "index_range",
        "append",
        nullptr
    };
    PyObject* value;
    PyObject* fp = nullptr;
    PyObject* returnBytesObj = nullptr;
    PyObject* stream = nullptr;
    PyObject* chunkSizeObj = nullptr;
    PyObject* fdObj = nullptr;
    int bloquant = false;
    // seuil de l'index de position construit à l'écriture, 0 = pas d'index
    Py_ssize_t indexSeuil = 0;
    // où le ranger, quand l'écrivain peut s'en charger lui-même (voir dump)
    PyObject* indexRangeObj = nullptr;
    // maillon d'une liste ouverte, plutôt que document entier (voir SjAppend)
    PyObject* appendObj = nullptr;
    size_t chunkSize = 65536;
    PyObject* defaultFn = nullptr;
    PyObject* defaultDictFn = nullptr;
    PyObject* defaultListFn = nullptr;
    PyObject* result;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OO$OOOpnOO",
                                     (char**) kwlist,
                                     &value,
                                     &fp,
                                     &returnBytesObj,
                                     &stream,
                                     &chunkSizeObj,
                                     &fdObj,
                                     &bloquant,
                                     &indexSeuil,
                                     &indexRangeObj,
                                     &appendObj))
        return nullptr;

    SjIndexRangement indexRange;
    const SjIndexRangement* indexOu = nullptr;
    if (indexRangeObj != nullptr && indexRangeObj != Py_None
            && indexSeuil > 0) {
        if (!sj_index_ou_ranger(indexRangeObj, indexRange))
            return nullptr;
        indexRange.seuil = (size_t) indexSeuil;
        indexOu = &indexRange;
    }

    SjAppend append;
    const SjAppend* appendOu = nullptr;
    if (appendObj != nullptr && appendObj != Py_None) {
        if (!sj_append_lit(appendObj, append))
            return nullptr;
        append.ecrivain = &((EncoderObject*) self)->ecrivainAppend;
        append.flux = &((EncoderObject*) self)->fluxAppend;
        // un seuil, ici, veut dire que python tient l'index maillon par
        // maillon : il ne le passe qu'à cette condition
        if (indexSeuil > 0) {
            if (((EncoderObject*) self)->indexAppend == nullptr)
                ((EncoderObject*) self)->indexAppend = new std::string();
            append.index = ((EncoderObject*) self)->indexAppend;
            append.seuil = (size_t) indexSeuil;
        }
        appendOu = &append;
    }

    EncoderObject* e = (EncoderObject*) self;
    // protocole serializejson (l'ancien Encoder.__call__ Python) : poussée
    // amortie des paramètres globaux, remise à zéro des attributs volatils
    bool sjProtocol = sj_is_registered(self, sj_encoder_type);
    // la poussée tenait-elle en entrant ? Rien n'a alors changé sur
    // l'instance depuis le dernier appel — ce qui valide aussi le cache des
    // rappels, plus bas
    bool pushed = false;
    if (sjProtocol) {
        PyObject* ownerObj = PyObject_GetAttr(sj_params_module, owner_name);
        if (ownerObj == nullptr)
            PyErr_Clear();
        pushed = (ownerObj == self);
        Py_XDECREF(ownerObj);
        if (!pushed) {
            PyObject* r =
                PyObject_CallMethodNoArgs(self, update_parameters_name);
            if (r == nullptr)
                return nullptr;
            Py_DECREF(r);
        }
        // l'équivalent C de _reset : mémo des doublons et classes rencontrées
        if (sj_set_new_volatile(self, dumped_classes_name,
                                PySet_New(nullptr)) < 0
            || sj_set_new_volatile(self, already_serialized_name,
                                   PyDict_New()) < 0
            || sj_set_new_volatile(self, keep_alive_name, PyList_New(0)) < 0
            || PyObject_GenericSetAttr(self, root_underscore_name, value) < 0)
            return nullptr;
    }

    // fp est l'alias serializejson de stream (signature historique du
    // __call__ Python : obj, fp=None, return_bytes=None)
    if (fp != nullptr && fp != Py_None)
        stream = fp;

    // return_bytes par appel (dumps()/dumpb()) : prime sur celui du
    // constructeur
    bool returnBytes = e->returnBytes;
    if (returnBytesObj != nullptr && returnBytesObj != Py_None) {
        int rb = PyObject_IsTrue(returnBytesObj);
        if (rb < 0)
            return nullptr;
        returnBytes = rb ? true : false;
    }

    // Les rappels de l'Encoder python se cherchent à chaque appel ; le prix,
    // ce sont les ABSENTS, dont la recherche lève une AttributeError. La
    // mémoire de ces absences (cbAbsents) ne vaut que sous le protocole
    // serializejson, où la poussée amortie garantit qu'aucun attribut
    // d'instance n'a bougé depuis le dernier appel.
    if (!sjProtocol || !pushed
            || e->cbTypeVersion != Py_TYPE(self)->tp_version_tag) {
        e->cbAbsents = 0;
        e->cbBytesSeuil = -1;
        Py_CLEAR(e->cbChunkSize);
        e->cbTypeVersion = Py_TYPE(self)->tp_version_tag;
    }
    defaultFn = sj_rappel(e, self, default_name, SJ_ABS_DEFAULT);
    defaultDictFn = sj_rappel(e, self, default_dict_name, SJ_ABS_DICT);
    defaultListFn = sj_rappel(e, self, default_list_name, SJ_ABS_LIST);
    PyObject* classPlanFn = sj_rappel(e, self, class_plan_name, SJ_ABS_PLAN);

    PathTracker pathTracker;
    if (e->mtScratch == nullptr)
        e->mtScratch = new SjMtScratch();
    pathTracker.mtScratch = e->mtScratch;
    if (e->pathNodesHighWater) {
        pathTracker.nodes.reserve(e->pathNodesHighWater);
        pathTracker.registered.reserve(64);
        pathTracker.segments.reserve(64);
    }
    if (e->memoHighWater)
        pathTracker.memo.reserve(e->memoHighWater);
    pathTracker.memoContainers = e->memoRefs;
    // un maillon d'`append` n'est pas la racine du document : ses $ref doivent
    // se dire « root[3]… », le chemin ABSOLU, seul que la relecture sache
    // suivre. Sans rang connu (liste déjà remplie par un autre), aucun chemin
    // n'est composable et un doublon fera échouer l'encodage plutôt que
    // d'écrire un fichier illisible.
    if (appendOu != nullptr) {
        if (appendOu->rang >= 0) {
            pathTracker.racine = "root[";
            pathTracker.racine += std::to_string(appendOu->rang);
            pathTracker.racine += ']';
        } else {
            pathTracker.racineInconnue = true;
        }
    }
    pathTracker.singleLineNumbers = e->singleLineNumbers;
    pathTracker.singleLineInit = e->singleLineInit;
    pathTracker.singleLineNew = e->singleLineNew;
    pathTracker.strictPickle = e->strictPickle;
    pathTracker.classPlanFn = classPlanFn;
    // seuil d'écriture native des petits bytes/bytearray, calculé par
    // l'Encoder python (_bytes_natif_seuil : 0 si greffons remplacés ;
    // absent de la classe de base, d'où la mémoire de son absence)
    if (e->cbBytesSeuil < 0) {
        PyObject* seuil_obj = sj_rappel(e, self, bytes_natif_seuil_name,
                                       SJ_ABS_SEUIL);
        if (seuil_obj != nullptr) {
            if (PyLong_CheckExact(seuil_obj)) {
                Py_ssize_t seuil = PyLong_AsSsize_t(seuil_obj);
                if (seuil == -1 && PyErr_Occurred())
                    PyErr_Clear();
                else
                    e->cbBytesSeuil = seuil;
            }
            Py_DECREF(seuil_obj);
        }
    }
    if (e->cbBytesSeuil >= 0)
        pathTracker.bytesNatifSeuil = e->cbBytesSeuil;
    // rappel _cle_json pour l'écriture native des dicts à clés non-str, et
    // recette des sous-documents de clés natives (voir defaultOneLineFn).
    // None : désactivé — sort_keys, ou recettes redéfinies par une
    // sous-classe. Références fortes, relâchées par ~PathTracker
    pathTracker.cleJsonFn = sj_rappel(e, self, cle_json_name, SJ_ABS_CLE);
    pathTracker.defaultOneLineFn = sj_rappel(e, self, default_one_line_name,
                                             SJ_ABS_ONE_LINE);
    PyObject* dumpedClassesSet = PyObject_GetAttr(self, dumped_classes_name);
    if (dumpedClassesSet == nullptr)
        PyErr_Clear();
    else if (!PySet_Check(dumpedClassesSet))
        Py_CLEAR(dumpedClassesSet);
    pathTracker.dumpedClasses = dumpedClassesSet;
    e->activePathTracker = &pathTracker;

    if (stream != nullptr && stream != Py_None) {
        if (!PyObject_HasAttr(stream, write_name)) {
            PyErr_SetString(PyExc_TypeError, "Expected a writable stream");
            e->activePathTracker = nullptr;
            Py_XDECREF(defaultFn);
            Py_XDECREF(defaultDictFn);
            Py_XDECREF(defaultListFn);
            Py_XDECREF(classPlanFn);
            return nullptr;
        }

        // chunk_size implicite : l'attribut chunk_size de l'instance (la
        // voie Python le passait explicitement à chaque appel)
        PyObject* ownedChunk = nullptr;
        if (sjProtocol && chunkSizeObj == nullptr) {
            if (e->cbChunkSize == nullptr)
                e->cbChunkSize = sj_rappel(e, self, chunk_size_name,
                                           SJ_ABS_CHUNK);
            ownedChunk = Py_XNewRef(e->cbChunkSize);
            if (ownedChunk != nullptr)
                chunkSizeObj = ownedChunk;
        }
        bool chunkOk = accept_chunk_size_arg(chunkSizeObj, chunkSize);
        Py_XDECREF(ownedChunk);
        if (!chunkOk) {
            e->activePathTracker = nullptr;
            Py_XDECREF(defaultFn);
            Py_XDECREF(defaultDictFn);
            Py_XDECREF(defaultListFn);
            Py_XDECREF(classPlanFn);
            return nullptr;
        }

        // fd donné par l'Encoder python quand le flux écrit ses octets tels
        // quels : on écrit alors dans le descripteur, sans passer par write()
        int fd = -1;
        if (fdObj != nullptr && fdObj != Py_None) {
            fd = (int) PyLong_AsLong(fdObj);
            if (fd == -1 && PyErr_Occurred()) {
                e->activePathTracker = nullptr;
                Py_XDECREF(defaultFn);
                Py_XDECREF(defaultDictFn);
                Py_XDECREF(defaultListFn);
                Py_XDECREF(classPlanFn);
                return nullptr;
            }
        }

        if (fd >= 0)
            result = do_fd_encode(value, fd, chunkSize, bloquant, defaultFn,
                                  defaultDictFn, defaultListFn, &pathTracker,
                                  indexOu, appendOu,
                                  e->ensureAscii,
                                  e->writeMode, e->indentChar, e->indentCount,
                                  e->numberMode, e->datetimeMode, e->uuidMode,
                                  e->bytesMode, e->iterableMode, e->mappingMode);
        else
            result = do_stream_encode(value, stream, chunkSize, defaultFn,
                                      defaultDictFn, defaultListFn, &pathTracker,
                                      e->ensureAscii,
                                      e->writeMode, e->indentChar, e->indentCount,
                                      e->numberMode, e->datetimeMode, e->uuidMode,
                                      e->bytesMode, e->iterableMode,
                                      e->mappingMode);
    } else {
        result = do_encode(value, defaultFn, defaultDictFn, defaultListFn,
                           &pathTracker,
                           e->ensureAscii, e->writeMode, e->indentChar,
                           e->indentCount, e->numberMode, e->datetimeMode, e->uuidMode,
                           e->bytesMode, e->iterableMode, e->mappingMode, returnBytes,
                           &e->outputHighWater);
    }

    e->activePathTracker = nullptr;
    // un doublon a demandé son chemin alors que la place du maillon dans la
    // liste est inconnue : les chemins écrits sont relatifs au maillon, et la
    // relecture du document irait les chercher dans la liste elle-même.
    // Python le relève et recommence (voir Encoder.append)
    e->refImpossible = pathTracker.refImpossible;
    Py_XDECREF(pathTracker.dumpedClasses);
    pathTracker.dumpedClasses = nullptr;
    if (pathTracker.nodes.size() > e->pathNodesHighWater)
        e->pathNodesHighWater = pathTracker.nodes.size();
    if (pathTracker.memo.size() > e->memoHighWater)
        e->memoHighWater = pathTracker.memo.size();
    Py_XDECREF(defaultFn);
    Py_XDECREF(defaultDictFn);
    Py_XDECREF(defaultListFn);
    Py_XDECREF(classPlanFn);

    // l'équivalent C de _clean (sur succès seulement, comme la voie Python)
    if (sjProtocol && result != nullptr) {
        if (PyObject_GenericSetAttr(self, already_serialized_name,
                                    nullptr) < 0)
            PyErr_Clear();
        if (PyObject_GenericSetAttr(self, keep_alive_name, nullptr) < 0)
            PyErr_Clear();
    }
    return result;
}


static PyObject*
encoder_new(PyTypeObject* type, PyObject* args, PyObject* kwargs)
{
    EncoderObject* e;
    int ensureAscii = true;
    PyObject* indent = nullptr;
    PyObject* numberModeObj = nullptr;
    unsigned numberMode = NM_NAN;
    PyObject* datetimeModeObj = nullptr;
    unsigned datetimeMode = DM_NONE;
    PyObject* uuidModeObj = nullptr;
    unsigned uuidMode = UM_NONE;
    PyObject* bytesModeObj = nullptr;
    unsigned bytesMode = BM_UTF8;
    PyObject* writeModeObj = nullptr;
    unsigned writeMode = WM_COMPACT;
    PyObject* iterableModeObj = nullptr;
    unsigned iterableMode = IM_ANY_ITERABLE;
    PyObject* mappingModeObj = nullptr;
    unsigned mappingMode = MM_ANY_MAPPING;
    int allowNan = -1;
    int returnBytes = false;
    char indentChar = ' ';
    unsigned indentCount = 4;
    static char const* kwlist[] = {
        "skip_invalid_keys",    // alias of MM_SKIP_NON_STRING_KEYS
        "ensure_ascii",
        "indent",
        "sort_keys",            // alias of MM_SORT_KEYS
        "number_mode",
        "datetime_mode",
        "uuid_mode",
        "bytes_mode",
        "write_mode",
        "iterable_mode",
        "mapping_mode",
        "allow_nan",
        "return_bytes",
        "memo_refs",
        "single_line_numbers",
        "single_line_init",
        "single_line_new",
        "strict_pickle",
        nullptr
    };
    int skipInvalidKeys = false;
    int sortKeys = false;
    int memoRefs = false;
    int singleLineNumbers = false;
    int singleLineInit = true;
    int singleLineNew = true;
    int strictPickle = false;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|ppOpOOOOOOOppppppp:Encoder",
                                     (char**) kwlist,
                                     &skipInvalidKeys,
                                     &ensureAscii,
                                     &indent,
                                     &sortKeys,
                                     &numberModeObj,
                                     &datetimeModeObj,
                                     &uuidModeObj,
                                     &bytesModeObj,
                                     &writeModeObj,
                                     &iterableModeObj,
                                     &mappingModeObj,
                                     &allowNan,
                                     &returnBytes,
                                     &memoRefs,
                                     &singleLineNumbers,
                                     &singleLineInit,
                                     &singleLineNew,
                                     &strictPickle
                                     ))
        return nullptr;

    if (!accept_indent_arg(indent, writeMode, indentCount, indentChar))
        return nullptr;

    if (!accept_write_mode_arg(writeModeObj, writeMode))
        return nullptr;

    if (!accept_number_mode_arg(numberModeObj, allowNan, numberMode))
        return nullptr;

    if (!accept_datetime_mode_arg(datetimeModeObj, datetimeMode))
        return nullptr;

    if (!accept_uuid_mode_arg(uuidModeObj, uuidMode))
        return nullptr;

    if (!accept_bytes_mode_arg(bytesModeObj, bytesMode))
        return nullptr;

    if (!accept_iterable_mode_arg(iterableModeObj, iterableMode))
        return nullptr;

    if (!accept_mapping_mode_arg(mappingModeObj, mappingMode))
        return nullptr;

    if (skipInvalidKeys)
        mappingMode |= MM_SKIP_NON_STRING_KEYS;

    if (sortKeys)
        mappingMode |= MM_SORT_KEYS;

    e = (EncoderObject*) type->tp_alloc(type, 0);
    if (e == nullptr)
        return nullptr;

    e->ensureAscii = ensureAscii ? true : false;
    e->writeMode = writeMode;
    e->indentChar = indentChar;
    e->indentCount = indentCount;
    e->datetimeMode = datetimeMode;
    e->uuidMode = uuidMode;
    e->numberMode = numberMode;
    e->bytesMode = bytesMode;
    e->iterableMode = iterableMode;
    e->mappingMode = mappingMode;
    e->returnBytes = returnBytes? true : false;
    e->memoRefs = memoRefs? true : false;
    e->pathNodesHighWater = 0;
    e->memoHighWater = 0;
    e->mtScratch = nullptr;
    e->outputHighWater = 0;
    e->indexAppend = nullptr;
    e->ecrivainAppend = nullptr;
    e->fluxAppend = nullptr;
    e->refImpossible = false;
    e->cbAbsents = 0;
    e->cbChunkSize = nullptr;
    e->cbBytesSeuil = -1;
    e->cbTypeVersion = 0;
    e->singleLineNumbers = singleLineNumbers? true : false;
    e->singleLineInit = singleLineInit? true : false;
    e->singleLineNew = singleLineNew? true : false;
    e->strictPickle = strictPickle? true : false;
    e->activePathTracker = nullptr;

    return (PyObject*) e;
}


///////////////
// Validator //
///////////////


typedef struct {
    PyObject_HEAD
    SchemaDocument *schema;
} ValidatorObject;


PyDoc_STRVAR(validator_doc,
             "Validator(json_schema)\n"
             "\n"
             "Create and return a new Validator instance from the given `json_schema`"
             " string.");


static PyTypeObject Validator_Type = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "rapidjson.Validator",          /* tp_name */
    sizeof(ValidatorObject),        /* tp_basicsize */
    0,                              /* tp_itemsize */
    (destructor) validator_dealloc, /* tp_dealloc */
    0,                              /* tp_print */
    0,                              /* tp_getattr */
    0,                              /* tp_setattr */
    0,                              /* tp_compare */
    0,                              /* tp_repr */
    0,                              /* tp_as_number */
    0,                              /* tp_as_sequence */
    0,                              /* tp_as_mapping */
    0,                              /* tp_hash */
    (ternaryfunc) validator_call,   /* tp_call */
    0,                              /* tp_str */
    0,                              /* tp_getattro */
    0,                              /* tp_setattro */
    0,                              /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,             /* tp_flags */
    validator_doc,                  /* tp_doc */
    0,                              /* tp_traverse */
    0,                              /* tp_clear */
    0,                              /* tp_richcompare */
    0,                              /* tp_weaklistoffset */
    0,                              /* tp_iter */
    0,                              /* tp_iternext */
    0,                              /* tp_methods */
    0,                              /* tp_members */
    0,                              /* tp_getset */
    0,                              /* tp_base */
    0,                              /* tp_dict */
    0,                              /* tp_descr_get */
    0,                              /* tp_descr_set */
    0,                              /* tp_dictoffset */
    0,                              /* tp_init */
    0,                              /* tp_alloc */
    validator_new,                  /* tp_new */
    PyObject_Del,                   /* tp_free */
};


static PyObject* validator_call(PyObject* self, PyObject* args, PyObject* kwargs)
{
    PyObject* jsonObject;

    if (!PyArg_ParseTuple(args, "O", &jsonObject))
        return nullptr;

    const char* jsonStr;

    if (PyBytes_Check(jsonObject)) {
        jsonStr = PyBytes_AsString(jsonObject);
        if (jsonStr == nullptr)
            return nullptr;
    } else if (PyUnicode_Check(jsonObject)) {
        jsonStr = PyUnicode_AsUTF8(jsonObject);
        if (jsonStr == nullptr)
            return nullptr;
    } else {
        PyErr_SetString(PyExc_TypeError, "Expected string or UTF-8 encoded bytes");
        return nullptr;
    }

    Document d;
    bool error;

    Py_BEGIN_ALLOW_THREADS
    error = d.Parse(jsonStr).HasParseError();
    Py_END_ALLOW_THREADS

    if (error) {
        PyErr_SetString(decode_error, "Invalid JSON");
        return nullptr;
    }

    SchemaValidator validator(*((ValidatorObject*) self)->schema);
    bool accept;

    Py_BEGIN_ALLOW_THREADS
    accept = d.Accept(validator);
    Py_END_ALLOW_THREADS

    if (!accept) {
        StringBuffer sptr;
        StringBuffer dptr;

        Py_BEGIN_ALLOW_THREADS
        validator.GetInvalidSchemaPointer().StringifyUriFragment(sptr);
        validator.GetInvalidDocumentPointer().StringifyUriFragment(dptr);
        Py_END_ALLOW_THREADS

        PyObject* error = Py_BuildValue("sss", validator.GetInvalidSchemaKeyword(),
                                        sptr.GetString(), dptr.GetString());
        PyErr_SetObject(validation_error, error);

        Py_XDECREF(error);
        sptr.Clear();
        dptr.Clear();

        return nullptr;
    }

    Py_RETURN_NONE;
}


static void validator_dealloc(PyObject* self)
{
    ValidatorObject* s = (ValidatorObject*) self;
    delete s->schema;
    Py_TYPE(self)->tp_free(self);
}


static PyObject* validator_new(PyTypeObject* type, PyObject* args, PyObject* kwargs)
{
    PyObject* jsonObject;

    if (!PyArg_ParseTuple(args, "O", &jsonObject))
        return nullptr;

    const char* jsonStr;

    if (PyBytes_Check(jsonObject)) {
        jsonStr = PyBytes_AsString(jsonObject);
        if (jsonStr == nullptr)
            return nullptr;
    } else if (PyUnicode_Check(jsonObject)) {
        jsonStr = PyUnicode_AsUTF8(jsonObject);
        if (jsonStr == nullptr)
            return nullptr;
    } else {
        PyErr_SetString(PyExc_TypeError, "Expected string or UTF-8 encoded bytes");
        return nullptr;
    }

    Document d;
    bool error;

    Py_BEGIN_ALLOW_THREADS
    error = d.Parse(jsonStr).HasParseError();
    Py_END_ALLOW_THREADS

    if (error) {
        PyErr_SetString(decode_error, "Invalid JSON");
        return nullptr;
    }

    ValidatorObject* v = (ValidatorObject*) type->tp_alloc(type, 0);
    if (v == nullptr)
        return nullptr;

    v->schema = new SchemaDocument(d);

    return (PyObject*) v;
}


////////////
// Module //
////////////


// Charge libblosc2 à l'exécution (celle de la roue python-blosc2 ou du
// système) et résout les symboles blosc2 utilisés par BloscToBase64 et la
// décompression. Le handle n'est jamais refermé : la bibliothèque vit
// aussi longtemps que le processus.
static PyObject*
load_blosc_library(PyObject* Py_UNUSED(self), PyObject* arg)
{
    const char* path = PyUnicode_AsUTF8(arg);
    if (path == nullptr)
        return nullptr;
    void* handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (handle == nullptr) {
        PyErr_Format(PyExc_OSError, "dlopen(%s) : %s", path, dlerror());
        return nullptr;
    }
    serializejson_blosc2_set_nthreads_t set_nthreads =
        (serializejson_blosc2_set_nthreads_t) dlsym(handle, "blosc2_set_nthreads");
    serializejson_blosc2_init_t init =
        (serializejson_blosc2_init_t) dlsym(handle, "blosc2_init");
    if (init == nullptr) {
        dlclose(handle);
        PyErr_SetString(PyExc_OSError,
                        "blosc2 symbols not found in library");
        return nullptr;
    }
    init();
    serializejson_blosc2_set_nthreads = set_nthreads;

    // API par contextes pour le parallélisme déterministe : activée seulement
    // si la version majeure de la bibliothèque correspond aux en-têtes
    // vendorés (les structures de paramètres passent par valeur)
    sj_blosc2_create_cctx =
        (sj_blosc2_create_cctx_t) dlsym(handle, "blosc2_create_cctx");
    sj_blosc2_create_dctx =
        (sj_blosc2_create_dctx_t) dlsym(handle, "blosc2_create_dctx");
    sj_blosc2_compress_ctx =
        (sj_blosc2_compress_ctx_t) dlsym(handle, "blosc2_compress_ctx");
    sj_blosc2_decompress_ctx =
        (sj_blosc2_decompress_ctx_t) dlsym(handle, "blosc2_decompress_ctx");
    sj_blosc2_free_ctx =
        (sj_blosc2_free_ctx_t) dlsym(handle, "blosc2_free_ctx");
    sj_blosc2_compname_to_compcode =
        (sj_blosc2_compname_to_compcode_t) dlsym(handle, "blosc2_compname_to_compcode");
    sj_blosc1_cbuffer_sizes =
        (sj_blosc1_cbuffer_sizes_t) dlsym(handle, "blosc1_cbuffer_sizes");
    sj_blosc2_get_version_string_t version_fn =
        (sj_blosc2_get_version_string_t) dlsym(handle, "blosc2_get_version_string");
    serializejson_blosc2_ctx_ok = false;
    if (sj_blosc2_create_cctx && sj_blosc2_create_dctx && sj_blosc2_compress_ctx
        && sj_blosc2_decompress_ctx && sj_blosc2_free_ctx
        && sj_blosc2_compname_to_compcode && sj_blosc1_cbuffer_sizes
        && version_fn) {
        const char* version = version_fn();
        if (version != nullptr
            && version[0] == ('0' + BLOSC2_VERSION_MAJOR)
            && version[1] == '.')
            serializejson_blosc2_ctx_ok = true;
    }

    // filtre « delta arithmétique par bloc » : enregistré dans la lib
    // chargée (fork ou roue) — nécessaire à la compression ET à la
    // décompression des trames qui l'utilisent
    serializejson_blosc2_delta_ok = false;
    if (serializejson_blosc2_ctx_ok) {
        sj_blosc2_register_filter_t register_filter =
            (sj_blosc2_register_filter_t) dlsym(handle,
                                                "blosc2_register_filter");
        if (register_filter != nullptr) {
            static char sj_delta_name[] = "serializejson_delta";
            static blosc2_filter sj_delta_filter = {
                SJ_BLOSC2_FILTER_DELTA, sj_delta_name, 1,
                sj_delta_filter_forward, sj_delta_filter_backward};
            if (register_filter(&sj_delta_filter) == 0)
                serializejson_blosc2_delta_ok = true;
            // filtre « zigzag » (avant bitshuffle) : ±ε repliés pour que les
            // plans de bits restent propres — même besoin des deux côtés
            static char sj_zigzag_name[] = "serializejson_zigzag";
            static blosc2_filter sj_zigzag_filter = {
                SJ_BLOSC2_FILTER_ZIGZAG, sj_zigzag_name, 1,
                sj_zigzag_filter_forward, sj_zigzag_filter_backward};
            serializejson_blosc2_zigzag_ok = false;
            if (register_filter(&sj_zigzag_filter) == 0)
                serializejson_blosc2_zigzag_ok = true;
        }
    }

    Py_RETURN_TRUE;
}


PyDoc_STRVAR(blosc_decompress_chunks_docstring,
             "blosc_decompress_chunks(data, as_bytearray=0, nthreads=0,"
             " itemsize=0, row_elems=0, block_rows=0)\n\n"
             "Décompresse une concaténation ordonnée de trames blosc"
             " (compression parallèle déterministe) — en parallèle aussi,"
             " chaque trame vers sa position finale. nthreads=0 : automatique."
             " itemsize > 0 : défait aussi la dérivée _diff/_diffb (somme"
             " cumulée FUSIONNÉE dans le postfiltre par bloc quand la trame"
             " s'y prête, en post-passe par blocs sinon).");

static PyObject*
blosc_decompress_chunks_fn(PyObject* Py_UNUSED(self), PyObject* args)
{
    Py_buffer view;
    int as_bytearray = 0;
    int nthreads = 0;
    Py_ssize_t cs_itemsize = 0;
    Py_ssize_t cs_row_elems = 0;
    Py_ssize_t cs_block_rows = 0;
    if (!PyArg_ParseTuple(args, "y*|iinnn", &view, &as_bytearray, &nthreads,
                          &cs_itemsize, &cs_row_elems, &cs_block_rows))
        return nullptr;
    if (!serializejson_blosc2_ctx_ok) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_RuntimeError,
                        "blosc2 context API not available");
        return nullptr;
    }
    const char* base = (const char*) view.buf;
    size_t length = (size_t) view.len;
    // parcours des trames (chacune connaît ses tailles dans son entête)
    std::vector<SjDecompressJob> jobs;
    size_t offset = 0;
    size_t total = 0;
    size_t first_blocksize = 0;
    bool valid = true;
    while (offset < length) {
        if (length - offset < 16) {
            valid = false;
            break;
        }
        size_t nbytes = 0, cbytes = 0, blocksize = 0;
        sj_blosc1_cbuffer_sizes(base + offset, &nbytes, &cbytes, &blocksize);
        if (cbytes < 16 || offset + cbytes > length) {
            valid = false;
            break;
        }
        if (jobs.empty())
            first_blocksize = blocksize;
        jobs.push_back({base + offset, (int32_t) cbytes, nullptr,
                        (int32_t) nbytes, 0});
        total += nbytes;
        offset += cbytes;
    }
    if (!valid || jobs.empty()) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_ValueError, "corrupted blosc chunked payload");
        return nullptr;
    }
    PyObject* result = as_bytearray
        ? PyByteArray_FromStringAndSize(nullptr, (Py_ssize_t) total)
        : PyBytes_FromStringAndSize(nullptr, (Py_ssize_t) total);
    if (result == nullptr) {
        PyBuffer_Release(&view);
        return nullptr;
    }
    char* dest = as_bytearray ? PyByteArray_AS_STRING(result)
                              : PyBytes_AS_STRING(result);
    for (SjDecompressJob& job : jobs) {
        job.dest = dest;
        dest += job.destsize;
    }
    if (nthreads <= 0) {
        unsigned hardware = std::thread::hardware_concurrency();
        nthreads = (int) (hardware ? hardware : 1);
        if (nthreads > 8)
            nthreads = 8;
    }
    // moins de trames que de coeurs -> le parallélisme passe à l'intérieur
    // des trames (MT interne blosc2), sinon une trame par thread
    int inner_threads = 1;
    if ((int) jobs.size() < nthreads) {
        inner_threads = nthreads / (int) jobs.size();
        nthreads = (int) jobs.size();
    }
    // somme cumulée demandée (étiquettes _diff/_diffb) : FUSIONNÉE dans le
    // postfiltre par bloc quand la trame est unique et que ses blocs sont
    // exactement les blocs de la dérivée (l'écriture a calé blocksize sur
    // block_rows lignes) ; sinon post-passe par blocs après décompression
    SjPostCumsum post_cfg = {cs_itemsize, cs_row_elems};
    const SjPostCumsum* post = nullptr;
    bool post_pass = false;
    // trame dont le filtre 244 porte déjà le cumsum (quartet haut du meta,
    // octet 28 de l'en-tête étendu) : rien à défaire après la décompression
    if (cs_itemsize > 0 && jobs.size() == 1 && jobs[0].srcsize >= 32
        && ((const uint8_t*) jobs[0].src)[20] == 244
        && (((const uint8_t*) jobs[0].src)[28] >> 4) != 0)
        cs_itemsize = 0;
    if (cs_itemsize > 0 && cs_row_elems > 0) {
        Py_ssize_t rb = cs_itemsize * cs_row_elems;
        if (jobs.size() == 1 && cs_block_rows > 0
            && (Py_ssize_t) first_blocksize == cs_block_rows * rb)
            post = &post_cfg;
        else
            post_pass = true;
    }
    bool failed = false;
    Py_BEGIN_ALLOW_THREADS
    std::atomic<size_t> next(0);
    std::vector<std::thread> threads;
    for (int t = 1; t < nthreads; t++)
        threads.emplace_back(sj_decompress_worker, &jobs, &next, inner_threads,
                             post);
    sj_decompress_worker(&jobs, &next, inner_threads, post);
    for (std::thread& worker : threads)
        worker.join();
    for (SjDecompressJob& job : jobs)
        if (job.result != job.destsize)
            failed = true;
    if (!failed && post_pass) {
        char* buf = as_bytearray ? PyByteArray_AS_STRING(result)
                                 : PyBytes_AS_STRING(result);
        Py_ssize_t rb = cs_itemsize * cs_row_elems;
        Py_ssize_t rows = (Py_ssize_t) total / rb;
        Py_ssize_t br = (cs_block_rows > 0) ? cs_block_rows : rows;
        for (Py_ssize_t r0 = 0; r0 < rows; r0 += br)
            sj_cumsum_slice(buf + r0 * rb, buf + r0 * rb, cs_itemsize,
                            std::min<Py_ssize_t>(br, rows - r0),
                            cs_row_elems);
    }
    Py_END_ALLOW_THREADS
    PyBuffer_Release(&view);
    if (failed) {
        Py_DECREF(result);
        PyErr_SetString(PyExc_ValueError, "blosc chunked decompression failed");
        return nullptr;
    }
    return result;
}


static PyObject*
blosc_set_nthreads_fn(PyObject* Py_UNUSED(self), PyObject* arg)
{
    long nthreads = PyLong_AsLong(arg);
    if (nthreads == -1 && PyErr_Occurred())
        return nullptr;
    // retenu pour les compressions par contexte (le filtre delta) : le
    // réglage global blosc1 ne s'applique pas aux contextes
    serializejson_blosc2_nthreads_global =
        (int) (nthreads > 0 ? nthreads : 1);
    if (serializejson_blosc2_set_nthreads == nullptr)
        Py_RETURN_NONE;
    return PyLong_FromLong(
        serializejson_blosc2_set_nthreads((int16_t) nthreads));
}


// enregistre les types serializejson et le module serialize_parameters :
// à partir de là, les tp_call des Encoder/Decoder de ces types exécutent le
// protocole d'appel en C (ex-__call__ Python)
static PyObject*
register_serializejson_fn(PyObject* Py_UNUSED(module), PyObject* args)
{
    PyObject* encoderType;
    PyObject* decoderType;
    PyObject* params;

    if (!PyArg_ParseTuple(args, "OOO", &encoderType, &decoderType, &params))
        return nullptr;
    if (!PyType_Check(encoderType) || !PyType_Check(decoderType)) {
        PyErr_SetString(PyExc_TypeError,
                        "expected (encoder_type, decoder_type,"
                        " serialize_parameters)");
        return nullptr;
    }
    Py_INCREF(encoderType);
    Py_XSETREF(sj_encoder_type, encoderType);
    Py_INCREF(decoderType);
    Py_XSETREF(sj_decoder_type, decoderType);
    Py_INCREF(params);
    Py_XSETREF(sj_params_module, params);
    Py_RETURN_NONE;
}


// scanner C des fichiers d'objets appendés (« [obj\n,\nobj...] ») : la
// machine à états de _json_object_file_iterator.read(), portée telle
// quelle (l'équivalent moderne du « passer en cython ? » des notes).
// Entrée : (tampon bytes, in_chunk_start, in_quotes, in_curlys, in_squares,
// in_simple, in_object, backslash_escape). Sortie : (ret_start, ret_end,
// mêmes états mis à jour, in_chunk_start, shedule_break) — ret_start -1 =
// fin de la liste (« "" »), sinon tranche [ret_start:ret_end] du tampon.
static PyObject*
sj_scan_appended(PyObject* Py_UNUSED(module), PyObject* args)
{
    Py_buffer view;
    Py_ssize_t in_chunk_start;
    int in_quotes;
    Py_ssize_t in_curlys;
    Py_ssize_t in_squares;
    int in_simple;
    int in_object;
    int backslash_escape;
    if (!PyArg_ParseTuple(args, "y*npnnppp:_scan_appended", &view,
                          &in_chunk_start, &in_quotes, &in_curlys,
                          &in_squares, &in_simple, &in_object,
                          &backslash_escape))
        return nullptr;
    const unsigned char* s = (const unsigned char*) view.buf;
    const Py_ssize_t n = view.len;
    Py_ssize_t ret_start = -2;      // -2 : continuation de fin de tampon
    Py_ssize_t ret_end = n;
    int shedule_break = 0;
    // la fin de liste rend les états d'ENTRÉE tels quels, comme le scanner
    // Python d'origine (états morts : plus rien ne sera lu ensuite)
    const Py_ssize_t entry_chunk_start = in_chunk_start;
    const int entry_quotes = in_quotes;
    const Py_ssize_t entry_curlys = in_curlys;
    const Py_ssize_t entry_squares = in_squares;
    const int entry_simple = in_simple;
    const int entry_object = in_object;
    const int entry_escape = backslash_escape;
    for (Py_ssize_t i = in_chunk_start; i < n; i++) {
        const unsigned char ch = s[i];
        // dans une chaîne, le caractère qui suit un antislash est consommé
        // QUEL QU'IL SOIT (le scanner d'origine ne consommait le drapeau que
        // sur les caractères « intéressants » : une chaîne finissant par \n
        // avalait son guillemet fermant et faussait toutes les bornes)
        if (in_quotes) {
            if (backslash_escape) {
                backslash_escape = 0;
                continue;
            }
            if (ch != '\\' && ch != '"') {
                // saut direct au prochain « \ » ou « " » : l'intérieur d'une
                // chaîne est transparent pour la machine à états, et une
                // charge base64 de plusieurs Mo se traverse alors en memchr
                // (mesuré : ~190 Mo/s octet à octet, le scan dominait le
                // décodage entier du maillon)
                const unsigned char* base = s + i + 1;
                const size_t reste = (size_t) (n - i - 1);
                const unsigned char* q =
                    (const unsigned char*) memchr(base, '"', reste);
                const unsigned char* b = (const unsigned char*) memchr(
                    base, '\\', q ? (size_t) (q - base) : reste);
                const unsigned char* coupe = b ? b : q;
                if (coupe == nullptr)
                    break;      // tout le reste du tampon est dans la chaîne
                i = (Py_ssize_t) (coupe - s) - 1;   // le for repasse dessus
                continue;
            }
        }
        if (in_simple) {
            if (ch == ',' || ch == ' ' || ch == '\t' || ch == '\n'
                || ch == '\r' || ch == ']') {
                if (in_chunk_start < i)
                    shedule_break = 1;
                ret_start = in_chunk_start;
                ret_end = i;
                in_chunk_start = (i + 1) % n;
                in_quotes = 0;
                in_curlys = 0;      // in_squares conservé (quirk d'origine)
                in_simple = 0;
                in_object = 0;
                goto done;
            }
        } else if (ch == '\\' || ch == '"' || ch == '{' || ch == '}'
                   || ch == '[' || ch == ']') {
            int check = 0;
            if (in_quotes) {
                if (ch == '\\')
                    backslash_escape = 1;
                else if (ch == '"') {
                    in_quotes = 0;
                    check = 1;
                }
            } else if (ch == '"') {
                in_quotes = 1;
                in_object = 1;
            } else if (ch == '{') {
                in_curlys++;
                in_object = 1;
            } else if (ch == '}') {
                in_curlys--;
                check = 1;
            } else if (ch == '[') {
                in_squares++;
                if (in_squares > 1)
                    in_object = 1;
                else
                    in_chunk_start = (i + 1) % n;
            } else {                // ']'
                in_squares--;
                check = 1;
                if (in_squares == 0) {
                    // fin de la liste json : états d'entrée rendus tels quels
                    PyBuffer_Release(&view);
                    return Py_BuildValue("nninniiini", (Py_ssize_t) -1,
                                         (Py_ssize_t) -1, entry_quotes,
                                         entry_curlys, entry_squares,
                                         entry_simple, entry_object,
                                         entry_escape, entry_chunk_start, 0);
                }
            }
            if (check && !in_quotes && !in_curlys && in_squares < 2) {
                if (in_chunk_start < i + 1)
                    shedule_break = 1;
                ret_start = in_chunk_start;
                ret_end = i + 1;
                in_chunk_start = (i + 1) % n;
                in_quotes = 0;
                in_curlys = 0;
                in_simple = 0;
                in_object = 0;
                goto done;
            }
        } else if (!in_object) {
            if (ch == ',' || ch == ' ' || ch == '\t' || ch == '\n'
                || ch == '\r')
                in_chunk_start = i + 1;
            else
                in_simple = 1;
        }
    }
    // fin de tampon sans borne : continuation depuis le curseur courant
    ret_start = in_chunk_start;
    ret_end = n;
    in_chunk_start = 0;
done:
    PyBuffer_Release(&view);
    return Py_BuildValue("nninniiini", ret_start, ret_end, in_quotes,
                         in_curlys, in_squares, in_simple, in_object,
                         backslash_escape, in_chunk_start, shedule_break);
}


// balayage d'index : {chemin: [début, fin]} des conteneurs d'au moins `seuil`
// octets (voir indexscan.h). `fin` borne le document dans le tampon, la forme
// « comment » ayant son index écrit derrière.
static PyObject*
sj_scan_index(PyObject* Py_UNUSED(module), PyObject* args)
{
    Py_buffer view;
    Py_ssize_t seuil;
    Py_ssize_t fin = -1;
    if (!PyArg_ParseTuple(args, "y*n|n:_scan_index", &view, &seuil, &fin))
        return nullptr;
    if (fin < 0 || fin > view.len)
        fin = view.len;
    PyObject* entrees = PyDict_New();
    if (entrees == nullptr) {
        PyBuffer_Release(&view);
        return nullptr;
    }
    bool ok = sj_index_balaye((const char*) view.buf, (size_t) fin,
                              seuil > 0 ? (size_t) seuil : 0, entrees);
    PyBuffer_Release(&view);
    if (!ok) {
        Py_DECREF(entrees);
        return nullptr;
    }
    // la racine est indexée quelle que soit sa taille : c'est elle qui donne
    // l'étendue du document, et le point de départ de toute recherche
    PyObject* bornes = Py_BuildValue("[nn]", (Py_ssize_t) 0, fin);
    if (bornes == nullptr
            || PyDict_SetItemString(entrees, "root", bornes) != 0) {
        Py_XDECREF(bornes);
        Py_DECREF(entrees);
        return nullptr;
    }
    Py_DECREF(bornes);
    return entrees;
}

// --- rangement de l'index sur le disque (voir indexscan.h) -----------------
// serializejson/indexation.py ne fait plus AUCUNE mise en forme : composition
// du bloc, dégonflage zstd, base 64, queue de la forme "comment" et relecture
// se font toutes ici. Il lui reste le mémo, la grammaire des chemins et le
// chargement par tranches, qui sont de la politique, pas de la mise en forme.

// chemin de fichier vers un char*, sous l'encodage du système de fichiers
struct SjIndexChemin {
    PyObject* octets = nullptr;
    ~SjIndexChemin() { Py_XDECREF(octets); }
    const char* operator*() const {
        return octets == nullptr ? nullptr : PyBytes_AS_STRING(octets);
    }
};

static int
sj_index_chemin_converti(PyObject* obj, void* adresse)
{
    SjIndexChemin* out = (SjIndexChemin*) adresse;
    if (obj == Py_None)
        return 1;                    // sidecar absent : la forme "comment"
    return PyUnicode_FSConverter(obj, &out->octets);
}

// Fin du document json dans un tampon qui porte peut-être sa queue d'index.
static PyObject*
sj_index_fin_py(PyObject* Py_UNUSED(module), PyObject* arg)
{
    Py_buffer view;
    if (PyObject_GetBuffer(arg, &view, PyBUF_SIMPLE) != 0)
        return nullptr;
    const size_t fin = sj_index_fin((const char*) view.buf, (size_t) view.len);
    PyBuffer_Release(&view);
    return PyLong_FromSize_t(fin);
}

// (fin du document, date de composition de l'index) d'un fichier qui porte une
// queue, None sinon — en UNE lecture de seize octets, donc sans rien
// dégonfler : c'est ce qui permet de décider si cet index-ci vaut le seek.
static PyObject*
sj_index_queue_py(PyObject* Py_UNUSED(module), PyObject* arg)
{
    SjIndexChemin chemin;
    if (!PyUnicode_FSConverter(arg, &chemin.octets))
        return nullptr;
    SjIndexQueue q;
    if (!sj_index_fichier_queue(*chemin, &q) || !q.present)
        Py_RETURN_NONE;
    return Py_BuildValue("(nK)", (Py_ssize_t) q.fin,
                         (unsigned long long) q.date);
}

// Index d'un fichier déjà écrit : balayé, composé, rangé, et rendu tel qu'il
// est composé — l'appelant n'a plus qu'à le relire en json.
static PyObject*
sj_index_construit_py(PyObject* Py_UNUSED(module), PyObject* args)
{
    SjIndexChemin chemin, sidecar;
    int en_sidecar;
    Py_ssize_t seuil;
    if (!PyArg_ParseTuple(args, "O&O&pn:_index_construit",
                          PyUnicode_FSConverter, &chemin.octets,
                          sj_index_chemin_converti, &sidecar, &en_sidecar,
                          &seuil))
        return nullptr;
    SjIndexQueue q;
    std::string document;
    if (!sj_index_fichier_queue(*chemin, &q)
            || !sj_index_fichier_lit(*chemin, 0, q.fin, document))
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, *chemin);
    std::string chemins;
    if (!sj_index_balaye(document.data(), q.fin,
                         seuil > 0 ? (size_t) seuil : 0, nullptr, &chemins))
        return nullptr;
    std::string texte;
    sj_index_compose((size_t) seuil, chemins.data(), chemins.size(), q.fin,
                     texte);
    if (!sj_index_fichier_range(*chemin, *sidecar, en_sidecar != 0, q.taille,
                                q.fin, chemins.empty() ? std::string() : texte))
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, *chemin);
    return PyUnicode_FromStringAndSize(texte.data(),
                                       (Py_ssize_t) texte.size());
}

// (fin du document, index en json) tel qu'il est rangé, None s'il n'y en a
// pas — base 64 défaite et zstd dégonflé.
static PyObject*
sj_index_lit_py(PyObject* Py_UNUSED(module), PyObject* args)
{
    SjIndexChemin chemin, sidecar;
    if (!PyArg_ParseTuple(args, "O&O&:_index_lit",
                          PyUnicode_FSConverter, &chemin.octets,
                          sj_index_chemin_converti, &sidecar))
        return nullptr;
    SjIndexQueue q;
    if (!sj_index_fichier_queue(*chemin, &q))
        Py_RETURN_NONE;
    std::string bloc;
    if (*sidecar != nullptr) {
        if (!sj_index_fichier_tout(*sidecar, bloc))
            Py_RETURN_NONE;
    } else if (!q.present
               || !sj_index_fichier_lit(*chemin, q.debut, q.longueur, bloc)) {
        Py_RETURN_NONE;
    }
    std::string texte;
    if (!sj_index_debloc(bloc.data(), bloc.size(), *sidecar == nullptr, texte))
        Py_RETURN_NONE;
    return Py_BuildValue("(ny#)", (Py_ssize_t) q.fin, texte.data(),
                         (Py_ssize_t) texte.size());
}

// (sj_cumsum_rows et sj_cumsum_slice vivent dans serializejson.h, où le
// postfiltre de fusion cache et le worker de décompression les utilisent)

// dérivée le long de l'axe 0, en UNE allocation (le bytes retourné) et une
// passe : out[0] = src[0] (le « prepend 0 » de numpy fusionné), puis
// out[i] = src[i] - src[i-1]. Même arithmétique non-signée que le cumsum.
template <typename T>
static void
sj_diff_range(const T* src, T* out, Py_ssize_t row_begin, Py_ssize_t row_end,
              Py_ssize_t cols)
{
    if (row_begin == 0) {
        for (Py_ssize_t j = 0; j < cols; j++)
            out[j] = src[j];
        row_begin = 1;
    }
    for (Py_ssize_t i = row_begin; i < row_end; i++) {
        const T* prev = src + (i - 1) * cols;
        const T* cur = src + i * cols;
        T* dst = out + i * cols;
        for (Py_ssize_t j = 0; j < cols; j++)
            dst[j] = (T) (cur[j] - prev[j]);
    }
}

// chaque sortie ne dépend que de src[i] et src[i-1] (lecture seule) : la
// dérivée se découpe par plages de lignes sans aucune dépendance
static void
sj_diff_dispatch(const void* src, void* out, Py_ssize_t itemsize,
                 Py_ssize_t row_begin, Py_ssize_t row_end, Py_ssize_t cols)
{
    switch (itemsize) {
    case 1:
        sj_diff_range((const uint8_t*) src, (uint8_t*) out, row_begin,
                      row_end, cols);
        break;
    case 2:
        sj_diff_range((const uint16_t*) src, (uint16_t*) out, row_begin,
                      row_end, cols);
        break;
    case 4:
        sj_diff_range((const uint32_t*) src, (uint32_t*) out, row_begin,
                      row_end, cols);
        break;
    default:
        sj_diff_range((const uint64_t*) src, (uint64_t*) out, row_begin,
                      row_end, cols);
        break;
    }
}

// plage de blocs : chaque bloc redémarre sa dérivée (première ligne brute),
// pour que la somme cumulée de lecture soit indépendante par bloc
static void
sj_diff_blocks(const void* src, void* out, Py_ssize_t itemsize,
               Py_ssize_t rows, Py_ssize_t row_elems, Py_ssize_t block_rows,
               Py_ssize_t b_begin, Py_ssize_t b_end)
{
    Py_ssize_t row_bytes = row_elems * itemsize;
    for (Py_ssize_t b = b_begin; b < b_end; b++) {
        Py_ssize_t r0 = b * block_rows;
        Py_ssize_t rn = rows - r0;
        if (rn > block_rows)
            rn = block_rows;
        sj_diff_dispatch((const char*) src + r0 * row_bytes,
                         (char*) out + r0 * row_bytes, itemsize, 0, rn,
                         row_elems);
    }
}

static PyObject*
sj_diff_axis0(PyObject* Py_UNUSED(module), PyObject* args)
{
    Py_buffer view;
    Py_ssize_t itemsize;
    Py_ssize_t row_elems;
    Py_ssize_t block_rows = 0;  // 0 = dérivée globale (comportement historique)
    if (!PyArg_ParseTuple(args, "y*nn|n:_diff_axis0", &view, &itemsize,
                          &row_elems, &block_rows))
        return nullptr;
    if ((itemsize != 1 && itemsize != 2 && itemsize != 4 && itemsize != 8)
        || row_elems <= 0 || view.len % itemsize != 0
        || (view.len / itemsize) % row_elems != 0) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_ValueError,
                        "_diff_axis0: itemsize (1/2/4/8) ou forme invalide");
        return nullptr;
    }
    PyObject* out = PyBytes_FromStringAndSize(nullptr, view.len);
    if (out == nullptr) {
        PyBuffer_Release(&view);
        return nullptr;
    }
    Py_ssize_t rows = (view.len / itemsize) / row_elems;
    void* dst = PyBytes_AS_STRING(out);
    // multithread au-delà de 1 Mo (en dessous, les threads coûtent plus
    // qu'ils ne rapportent) — par plages de lignes (dérivée globale, aucune
    // dépendance en écriture) ou par plages de blocs (dérivée par blocs)
    bool blocked = (block_rows > 0 && block_rows < rows);
    Py_ssize_t unites = blocked ? (rows + block_rows - 1) / block_rows : rows;
    int nthreads = 1;
    if (view.len >= (Py_ssize_t) (1 << 20)) {
        unsigned hardware = std::thread::hardware_concurrency();
        nthreads = (int) (hardware ? (hardware > 8 ? 8 : hardware) : 1);
        if ((Py_ssize_t) nthreads > unites)
            nthreads = (int) unites;
    }
    if (nthreads <= 1) {
        if (blocked)
            sj_diff_blocks(view.buf, dst, itemsize, rows, row_elems,
                           block_rows, 0, unites);
        else
            sj_diff_dispatch(view.buf, dst, itemsize, 0, rows, row_elems);
    } else {
        Py_BEGIN_ALLOW_THREADS
        Py_ssize_t per = (unites + nthreads - 1) / nthreads;
        std::vector<std::thread> pool;
        for (int t = 1; t < nthreads; t++) {
            Py_ssize_t u0 = t * per;
            Py_ssize_t u1 = std::min<Py_ssize_t>(u0 + per, unites);
            if (u0 >= u1)
                break;
            if (blocked)
                pool.emplace_back(sj_diff_blocks, view.buf, dst, itemsize,
                                  rows, row_elems, block_rows, u0, u1);
            else
                pool.emplace_back(sj_diff_dispatch, view.buf, dst, itemsize,
                                  u0, u1, row_elems);
        }
        if (blocked)
            sj_diff_blocks(view.buf, dst, itemsize, rows, row_elems,
                           block_rows, 0, std::min<Py_ssize_t>(per, unites));
        else
            sj_diff_dispatch(view.buf, dst, itemsize, 0,
                             std::min<Py_ssize_t>(per, unites), row_elems);
        for (std::thread& worker : pool)
            worker.join();
        Py_END_ALLOW_THREADS
    }
    PyBuffer_Release(&view);
    return out;
}

// plage de blocs indépendants : chaque bloc a redémarré sa dérivée (première
// ligne brute), sa somme cumulée ne dépend donc de rien d'autre
static void
sj_cumsum_blocks(void* buf, Py_ssize_t itemsize, Py_ssize_t rows,
                 Py_ssize_t row_elems, Py_ssize_t block_rows,
                 Py_ssize_t b_begin, Py_ssize_t b_end)
{
    Py_ssize_t row_bytes = row_elems * itemsize;
    for (Py_ssize_t b = b_begin; b < b_end; b++) {
        Py_ssize_t r0 = b * block_rows;
        Py_ssize_t rn = rows - r0;
        if (rn > block_rows)
            rn = block_rows;
        char* p = (char*) buf + r0 * row_bytes;
        sj_cumsum_slice(p, p, itemsize, rn, row_elems);
    }
}

static PyObject*
sj_cumsum_axis0(PyObject* Py_UNUSED(module), PyObject* args)
{
    Py_buffer view;
    Py_ssize_t itemsize;
    Py_ssize_t row_elems;
    Py_ssize_t block_rows = 0;  // 0 = global (fichiers _diff historiques)
    if (!PyArg_ParseTuple(args, "w*nn|n:_cumsum_axis0", &view, &itemsize,
                          &row_elems, &block_rows))
        return nullptr;
    if ((itemsize != 1 && itemsize != 2 && itemsize != 4 && itemsize != 8)
        || row_elems <= 0 || view.len % itemsize != 0
        || (view.len / itemsize) % row_elems != 0) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_ValueError,
                        "_cumsum_axis0: itemsize (1/2/4/8) ou forme invalide");
        return nullptr;
    }
    Py_ssize_t rows = (view.len / itemsize) / row_elems;
    if (block_rows <= 0 || block_rows >= rows) {
        sj_cumsum_slice(view.buf, view.buf, itemsize, rows, row_elems);
        PyBuffer_Release(&view);
        Py_RETURN_NONE;
    }
    // blocs indépendants : multithread au-delà de 1 Mo (le gain de la
    // dérivée par blocs est justement de rendre la lecture parallèle)
    Py_ssize_t blocks = (rows + block_rows - 1) / block_rows;
    int nthreads = 1;
    if (view.len >= (Py_ssize_t) (1 << 20)) {
        unsigned hardware = std::thread::hardware_concurrency();
        nthreads = (int) (hardware ? (hardware > 8 ? 8 : hardware) : 1);
        if ((Py_ssize_t) nthreads > blocks)
            nthreads = (int) blocks;
    }
    if (nthreads <= 1) {
        sj_cumsum_blocks(view.buf, itemsize, rows, row_elems, block_rows, 0,
                         blocks);
    } else {
        Py_BEGIN_ALLOW_THREADS
        Py_ssize_t per = (blocks + nthreads - 1) / nthreads;
        std::vector<std::thread> pool;
        for (int t = 1; t < nthreads; t++) {
            Py_ssize_t b0 = t * per;
            Py_ssize_t b1 = std::min<Py_ssize_t>(b0 + per, blocks);
            if (b0 >= b1)
                break;
            pool.emplace_back(sj_cumsum_blocks, view.buf, itemsize, rows,
                              row_elems, block_rows, b0, b1);
        }
        sj_cumsum_blocks(view.buf, itemsize, rows, row_elems, block_rows, 0,
                         std::min<Py_ssize_t>(per, blocks));
        for (std::thread& worker : pool)
            worker.join();
        Py_END_ALLOW_THREADS
    }
    PyBuffer_Release(&view);
    Py_RETURN_NONE;
}

static PyMethodDef functions[] = {
    {"wait_writes", (PyCFunction) wait_writes, METH_NOARGS,
     "Attend que les écritures encore en vol soient posées sur le disque,"
     " et relève l'erreur de celle qui aurait raté après le retour de dump."},
    {"_cumsum_axis0", (PyCFunction) sj_cumsum_axis0, METH_VARARGS,
     "Somme cumulée en place le long de l'axe 0 (tampon, itemsize,"
     " éléments par ligne) — défait la dérivée _diff au chargement."},
    {"_diff_axis0", (PyCFunction) sj_diff_axis0, METH_VARARGS,
     "Dérivée le long de l'axe 0 (tampon, itemsize, éléments par ligne),"
     " rendue en un bytes d'une seule allocation — prepend 0 fusionné."},
    {"_scan_index", (PyCFunction) sj_scan_index, METH_VARARGS,
     "Balayage d'index : {chemin: [début, fin]} des conteneurs d'au moins"
     " `seuil` octets (tampon, seuil[, fin du document])."},
    {"_index_fin", (PyCFunction) sj_index_fin_py, METH_O,
     "Fin du document json dans un tampon qui porte peut-être son index."},
    {"_index_queue", (PyCFunction) sj_index_queue_py, METH_O,
     "(fin du document, date de l'index) d'un json à index en commentaire,"
     " None s'il n'en porte pas — sans rien dégonfler."},
    {"_index_construit", (PyCFunction) sj_index_construit_py, METH_VARARGS,
     "Balaye, compose et range l'index d'un json écrit (json, sidecar ou"
     " None, seuil) ; rend l'index composé."},
    {"_index_lit", (PyCFunction) sj_index_lit_py, METH_VARARGS,
     "(fin du document, index en json) d'un fichier (json, sidecar ou None),"
     " None s'il n'en porte pas."},
    {"_scan_appended", (PyCFunction) sj_scan_appended, METH_VARARGS,
     "Scanner C des fichiers d'objets appendés (machine à états de"
     " _json_object_file_iterator.read())."},
    {"register_serializejson", (PyCFunction) register_serializejson_fn,
     METH_VARARGS,
     "Enregistre (Encoder, Decoder, serialize_parameters) : leurs __call__"
     " passent en C."},
    {"loads", (PyCFunction) loads, METH_VARARGS | METH_KEYWORDS,
     loads_docstring},
    {"load", (PyCFunction) load, METH_VARARGS | METH_KEYWORDS,
     load_docstring},
    {"dumps", (PyCFunction) dumps, METH_VARARGS | METH_KEYWORDS,
     dumps_docstring},
    {"dumpb", (PyCFunction) dumpb, METH_VARARGS | METH_KEYWORDS,
     dumpb_docstring},
    {"dump", (PyCFunction) dump, METH_VARARGS | METH_KEYWORDS,
     dump_docstring},
    {"load_blosc_library", (PyCFunction) load_blosc_library, METH_O,
     "Charge libblosc2 (chemin du .so) pour compresser en C via BloscToBase64."},
    {"load_crypto_library", (PyCFunction) load_crypto_library, METH_O,
     "Charge libcrypto (chemin du .so) : charge utile age chiffrée en C."},
    {"_age_payload", (PyCFunction) age_payload, METH_VARARGS,
     "Segments age ChaCha20-Poly1305 (clé de flux, données, chiffre[,"
     " préfixe]) : bytes chiffré, ou bytearray clair / None si falsifié."},
    {"load_sodium_library", (PyCFunction) load_sodium_library, METH_O,
     "Charge libsodium (chemin du .so ; ignoré si déjà là, liée en wasm) :"
     " scrypt, ChaCha20-Poly1305 et charge utile age sans cryptography."},
    {"_scrypt", (PyCFunction) sj_scrypt, METH_VARARGS,
     "scrypt (mot de passe, sel, n, r, p, longueur) par libsodium -> bytes."},
    {"_chacha20poly1305", (PyCFunction) sj_chacha20poly1305, METH_VARARGS,
     "ChaCha20-Poly1305 IETF (clé, nonce, données, chiffre) par libsodium :"
     " bytes, ou None si l'étiquette ne s'authentifie pas."},
    {"blosc_set_nthreads", (PyCFunction) blosc_set_nthreads_fn, METH_O,
     "Nombre de threads de la libblosc2 chargée (None si non chargée)."},
    {"blosc_decompress_chunks", (PyCFunction) blosc_decompress_chunks_fn,
     METH_VARARGS, blosc_decompress_chunks_docstring},
    {"_resolve_ref_path", (PyCFunction) resolve_ref_path_fn, METH_VARARGS,
     "Résolution C d'un chemin $ref (root, .attr, [int], ['clé']) depuis"
     " l'objet racine donné ; None = repli python (chemin exotique ou"
     " navigation en échec)."},
    {nullptr, nullptr, 0, nullptr} /* sentinel */
};


static int
module_exec(PyObject* m)
{
    PyObject* datetimeModule;
    PyObject* decimalModule;
    PyObject* uuidModule;

    if (PyType_Ready(&Decoder_Type) < 0)
        return -1;

    if (PyType_Ready(&Encoder_Type) < 0)
        return -1;

    if (PyType_Ready(&Validator_Type) < 0)
        return -1;

    if (PyType_Ready(&RawString_Type) < 0)
        return -1;
    
    if (PyType_Ready(&RawBytes_Type) < 0)
        return -1;
    
    if (PyType_Ready(&RawBytesToBase64_Type) < 0)
        return -1;

    if (PyType_Ready(&SingleLine_Type) < 0)
        return -1;

    if (PyType_Ready(&BloscToBase64_Type) < 0)
        return -1;

    if (PyType_Ready(&BloscDiffere_Type) < 0)
        return -1;

    if (PyType_Ready(&EtiquetteDiffere_Type) < 0)
        return -1;

    if (PyType_Ready(&ArrayRows_Type) < 0)
        return -1;

    if (PyType_Ready(&RawBytesToPutInQuotes_Type) < 0)
        return -1;

    PyDateTime_IMPORT;
    if(!PyDateTimeAPI)
        return -1;

    datetimeModule = PyImport_ImportModule("datetime");
    if (datetimeModule == nullptr)
        return -1;

    decimalModule = PyImport_ImportModule("decimal");
    if (decimalModule == nullptr)
        return -1;

    decimal_type = PyObject_GetAttrString(decimalModule, "Decimal");
    Py_DECREF(decimalModule);

    if (decimal_type == nullptr)
        return -1;

    timezone_type = PyObject_GetAttrString(datetimeModule, "timezone");
    Py_DECREF(datetimeModule);

    if (timezone_type == nullptr)
        return -1;

    timezone_utc = PyObject_GetAttrString(timezone_type, "utc");
    if (timezone_utc == nullptr)
        return -1;

    uuidModule = PyImport_ImportModule("uuid");
    if (uuidModule == nullptr)
        return -1;

    uuid_type = PyObject_GetAttrString(uuidModule, "UUID");
    Py_DECREF(uuidModule);

    if (uuid_type == nullptr)
        return -1;

    PyObject* timeModule = PyImport_ImportModule("time");
    if (timeModule == nullptr)
        return -1;

    struct_time_type = PyObject_GetAttrString(timeModule, "struct_time");
    Py_DECREF(timeModule);

    if (struct_time_type == nullptr)
        return -1;

    astimezone_name = PyUnicode_InternFromString("astimezone");
    if (astimezone_name == nullptr)
        return -1;

    hex_name = PyUnicode_InternFromString("hex");
    if (hex_name == nullptr)
        return -1;

    timestamp_name = PyUnicode_InternFromString("timestamp");
    if (timestamp_name == nullptr)
        return -1;

    total_seconds_name = PyUnicode_InternFromString("total_seconds");
    if (total_seconds_name == nullptr)
        return -1;

    utcoffset_name = PyUnicode_InternFromString("utcoffset");
    if (utcoffset_name == nullptr)
        return -1;

    is_infinite_name = PyUnicode_InternFromString("is_infinite");
    if (is_infinite_name == nullptr)
        return -1;

    is_nan_name = PyUnicode_InternFromString("is_nan");
    if (is_infinite_name == nullptr)
        return -1;

    minus_inf_string_value = PyUnicode_InternFromString("-Infinity");
    if (minus_inf_string_value == nullptr)
        return -1;

    nan_string_value = PyUnicode_InternFromString("nan");
    if (nan_string_value == nullptr)
        return -1;

    plus_inf_string_value = PyUnicode_InternFromString("+Infinity");
    if (plus_inf_string_value == nullptr)
        return -1;

    start_object_name = PyUnicode_InternFromString("start_object");
    if (start_object_name == nullptr)
        return -1;

    end_object_name = PyUnicode_InternFromString("end_object");
    if (end_object_name == nullptr)
        return -1;

    default_name = PyUnicode_InternFromString("default");
    if (default_name == nullptr)
        return -1;

    default_dict_name = PyUnicode_InternFromString("default_dict");
    if (default_dict_name == nullptr)
        return -1;

    default_list_name = PyUnicode_InternFromString("default_list");
    if (default_list_name == nullptr)
        return -1;

    class_plan_name = PyUnicode_InternFromString("class_plan");
    if (class_plan_name == nullptr)
        return -1;

    dict_dunder_name = PyUnicode_InternFromString("__dict__");
    if (dict_dunder_name == nullptr)
        return -1;

    decode_class_plan_name = PyUnicode_InternFromString("decode_class_plan");
    if (decode_class_plan_name == nullptr)
        return -1;

    fast_start_object_name = PyUnicode_InternFromString("_fast_start_object");
    fast_plain_end_object_name = PyUnicode_InternFromString("_fast_plain_end_object");
    if (fast_start_object_name == nullptr)
        return -1;

    root_attr_name = PyUnicode_InternFromString("root");
    if (root_attr_name == nullptr)
        return -1;

    owner_name = PyUnicode_InternFromString("_owner");
    decoder_owner_name = PyUnicode_InternFromString("_decoder_owner");
    update_parameters_name =
        PyUnicode_InternFromString("_update_serialize_parameters");
    push_decode_parameters_name =
        PyUnicode_InternFromString("_push_decode_parameters");
    call_update_name = PyUnicode_InternFromString("_call_update");
    resolve_duplicates_name = PyUnicode_InternFromString("_resolve_duplicates");
    dumped_classes_name = PyUnicode_InternFromString("dumped_classes");
    bytes_natif_seuil_name = PyUnicode_InternFromString("_bytes_natif_seuil");
    cle_json_name = PyUnicode_InternFromString("_cle_json");
    default_one_line_name = PyUnicode_InternFromString("_default_one_line");
    bytes_class_name_str = PyUnicode_InternFromString("bytes");
    bytearray_class_name_str = PyUnicode_InternFromString("bytearray");
    collections_prefix_str = PyUnicode_InternFromString("collections.");
    decode_cle_name = PyUnicode_InternFromString("_decode_cle_exotique");
    construct_name = PyUnicode_InternFromString("construct");
    live_root_name = PyUnicode_InternFromString("_live_root");
    reconcile_name = PyUnicode_InternFromString("_reconcile");
    updatables_name = PyUnicode_InternFromString("updatableClassStrs");
    already_serialized_name = PyUnicode_InternFromString("_already_serialized");
    keep_alive_name =
        PyUnicode_InternFromString("_already_serialized_keep_alive");
    root_underscore_name = PyUnicode_InternFromString("_root");
    chunk_size_name = PyUnicode_InternFromString("chunk_size");
    converted_numpy_name =
        PyUnicode_InternFromString("converted_numpy_array_from_lists");
    not_authorized_name = PyUnicode_InternFromString("not_authorized_classes");
    updating_name = PyUnicode_InternFromString("_updating");
    startswith_curly_name = PyUnicode_InternFromString("json_startswith_curly");
    duplicates_name = PyUnicode_InternFromString("duplicates_to_replace");
    dotdict_name = PyUnicode_InternFromString("dotdict");
    class_from_attributes_name =
        PyUnicode_InternFromString("_class_from_attributes_names");
    strict_pickle_name = PyUnicode_InternFromString("strict_pickle");
    setters_name = PyUnicode_InternFromString("setters");
    properties_name = PyUnicode_InternFromString("properties");
    if (properties_name == nullptr)
        return -1;

    class_key_name = PyUnicode_InternFromString("__class__");
    ref_key_name = PyUnicode_InternFromString("$ref");
    if (class_key_name == nullptr)
        return -1;

    init_key_name = PyUnicode_InternFromString("__init__");
    if (init_key_name == nullptr)
        return -1;

    new_key_name = PyUnicode_InternFromString("__new__");
    if (new_key_name == nullptr)
        return -1;

    state_key_name = PyUnicode_InternFromString("__state__");
    if (state_key_name == nullptr)
        return -1;

    items_key_name = PyUnicode_InternFromString("__items__");
    if (items_key_name == nullptr)
        return -1;

    empty_args_tuple = PyTuple_New(0);
    if (empty_args_tuple == nullptr)
        return -1;

    b64_payload_classes_name = PyUnicode_InternFromString("_b64_payload_classes");
    if (b64_payload_classes_name == nullptr)
        return -1;

    type_values_cache_name = PyUnicode_InternFromString("_type_values_cache");
    if (type_values_cache_name == nullptr)
        return -1;

    end_array_name = PyUnicode_InternFromString("end_array");
    if (end_array_name == nullptr)
        return -1;

    string_name = PyUnicode_InternFromString("string");
    if (string_name == nullptr)
        return -1;

    read_name = PyUnicode_InternFromString("read");
    if (read_name == nullptr)
        return -1;

    write_name = PyUnicode_InternFromString("write");
    if (write_name == nullptr)
        return -1;

    encoding_name = PyUnicode_InternFromString("encoding");
    if (encoding_name == nullptr)
        return -1;

#define STRINGIFY(x) XSTRINGIFY(x)
#define XSTRINGIFY(x) #x

    if (PyModule_AddIntConstant(m, "DM_NONE", DM_NONE)
        || PyModule_AddIntConstant(m, "DM_ISO8601", DM_ISO8601)
        || PyModule_AddIntConstant(m, "DM_UNIX_TIME", DM_UNIX_TIME)
        || PyModule_AddIntConstant(m, "DM_ONLY_SECONDS", DM_ONLY_SECONDS)
        || PyModule_AddIntConstant(m, "DM_IGNORE_TZ", DM_IGNORE_TZ)
        || PyModule_AddIntConstant(m, "DM_NAIVE_IS_UTC", DM_NAIVE_IS_UTC)
        || PyModule_AddIntConstant(m, "DM_SHIFT_TO_UTC", DM_SHIFT_TO_UTC)

        || PyModule_AddIntConstant(m, "UM_NONE", UM_NONE)
        || PyModule_AddIntConstant(m, "UM_HEX", UM_HEX)
        || PyModule_AddIntConstant(m, "UM_CANONICAL", UM_CANONICAL)

        || PyModule_AddIntConstant(m, "NM_NONE", NM_NONE)
        || PyModule_AddIntConstant(m, "NM_NAN", NM_NAN)
        || PyModule_AddIntConstant(m, "NM_DECIMAL", NM_DECIMAL)
        || PyModule_AddIntConstant(m, "NM_NATIVE", NM_NATIVE)

        || PyModule_AddIntConstant(m, "PM_NONE", PM_NONE)
        || PyModule_AddIntConstant(m, "PM_COMMENTS", PM_COMMENTS)
        || PyModule_AddIntConstant(m, "PM_TRAILING_COMMAS", PM_TRAILING_COMMAS)

        || PyModule_AddIntConstant(m, "BM_NONE", BM_NONE)
        || PyModule_AddIntConstant(m, "BM_UTF8", BM_UTF8)

        || PyModule_AddIntConstant(m, "WM_COMPACT", WM_COMPACT)
        || PyModule_AddIntConstant(m, "WM_PRETTY", WM_PRETTY)
        || PyModule_AddIntConstant(m, "WM_SINGLE_LINE_ARRAY", WM_SINGLE_LINE_ARRAY)

        || PyModule_AddIntConstant(m, "IM_ANY_ITERABLE", IM_ANY_ITERABLE)
        || PyModule_AddIntConstant(m, "IM_ONLY_LISTS", IM_ONLY_LISTS)

        || PyModule_AddIntConstant(m, "MM_ANY_MAPPING", MM_ANY_MAPPING)
        || PyModule_AddIntConstant(m, "MM_ONLY_DICTS", MM_ONLY_DICTS)
        || PyModule_AddIntConstant(m, "MM_COERCE_KEYS_TO_STRINGS",
                                   MM_COERCE_KEYS_TO_STRINGS)
        || PyModule_AddIntConstant(m, "MM_SKIP_NON_STRING_KEYS", MM_SKIP_NON_STRING_KEYS)
        || PyModule_AddIntConstant(m, "MM_SORT_KEYS", MM_SORT_KEYS)

        || PyModule_AddStringConstant(m, "__version__",
                                      STRINGIFY(PYTHON_RAPIDJSON_VERSION))
        || PyModule_AddStringConstant(m, "__author__",
                                      "Ken Robbins <ken@kenrobbins.com>"
                                      ", Lele Gaifax <lele@metapensiero.it>")
        || PyModule_AddStringConstant(m, "__rapidjson_version__",
                                      RAPIDJSON_VERSION_STRING)
#ifdef RAPIDJSON_EXACT_VERSION
        || PyModule_AddStringConstant(m, "__rapidjson_exact_version__",
                                      STRINGIFY(RAPIDJSON_EXACT_VERSION))
#endif
        )
        return -1;

    Py_INCREF(&Decoder_Type);
    if (PyModule_AddObject(m, "Decoder", (PyObject*) &Decoder_Type) < 0) {
        Py_DECREF(&Decoder_Type);
        return -1;
    }

    Py_INCREF(&Encoder_Type);
    if (PyModule_AddObject(m, "Encoder", (PyObject*) &Encoder_Type) < 0) {
        Py_DECREF(&Encoder_Type);
        return -1;
    }

    Py_INCREF(&Validator_Type);
    if (PyModule_AddObject(m, "Validator", (PyObject*) &Validator_Type) < 0) {
        Py_DECREF(&Validator_Type);
        return -1;
    }

    Py_INCREF(&RawString_Type);
    if (PyModule_AddObject(m, "RawString", (PyObject*) &RawString_Type) < 0) {
        Py_DECREF(&RawString_Type);
        return -1;
    }
    
    Py_INCREF(&RawBytes_Type);
    if (PyModule_AddObject(m, "RawBytes", (PyObject*) &RawBytes_Type) < 0) {
        Py_DECREF(&RawBytes_Type);
        return -1;
    }
    
    Py_INCREF(&RawBytesToPutInQuotes_Type);
    if (PyModule_AddObject(m, "RawBytesToPutInQuotes", (PyObject*) &RawBytesToPutInQuotes_Type) < 0) {
        Py_DECREF(&RawBytesToPutInQuotes_Type);
        return -1;
    }

    Py_INCREF(&RawBytesToBase64_Type);
    if (PyModule_AddObject(m, "RawBytesToBase64", (PyObject*) &RawBytesToBase64_Type) < 0) {
        Py_DECREF(&RawBytesToBase64_Type);
        return -1;
    }

    Py_INCREF(&SingleLine_Type);
    if (PyModule_AddObject(m, "SingleLine", (PyObject*) &SingleLine_Type) < 0) {
        Py_DECREF(&SingleLine_Type);
        return -1;
    }

    Py_INCREF(&BloscToBase64_Type);
    if (PyModule_AddObject(m, "BloscToBase64", (PyObject*) &BloscToBase64_Type) < 0) {
        Py_DECREF(&BloscToBase64_Type);
        return -1;
    }

    Py_INCREF(&BloscDiffere_Type);
    if (PyModule_AddObject(m, "BloscDiffere", (PyObject*) &BloscDiffere_Type) < 0) {
        Py_DECREF(&BloscDiffere_Type);
        return -1;
    }

    Py_INCREF(&EtiquetteDiffere_Type);
    if (PyModule_AddObject(m, "EtiquetteDiffere",
                           (PyObject*) &EtiquetteDiffere_Type) < 0) {
        Py_DECREF(&EtiquetteDiffere_Type);
        return -1;
    }

    Py_INCREF(&ArrayRows_Type);
    if (PyModule_AddObject(m, "ArrayRows", (PyObject*) &ArrayRows_Type) < 0) {
        Py_DECREF(&ArrayRows_Type);
        return -1;
    }

    validation_error = PyErr_NewException("rapidjson.ValidationError",
                                          PyExc_ValueError, nullptr);
    if (validation_error == nullptr)
        return -1;
    Py_INCREF(validation_error);
    if (PyModule_AddObject(m, "ValidationError", validation_error) < 0) {
        Py_DECREF(validation_error);
        return -1;
    }

    decode_error = PyErr_NewException("rapidjson.JSONDecodeError",
                                      PyExc_ValueError, nullptr);
    if (decode_error == nullptr)
        return -1;
    Py_INCREF(decode_error);
    if (PyModule_AddObject(m, "JSONDecodeError", decode_error) < 0) {
        Py_DECREF(decode_error);
        return -1;
    }

    return 0;
}


static struct PyModuleDef_Slot slots[] = {
    {Py_mod_exec, (void*) module_exec},
    {0, nullptr}
};


static PyModuleDef module = {
    PyModuleDef_HEAD_INIT,      /* m_base */
    "rapidjson",                /* m_name */
    PyDoc_STR("Fast, simple JSON encoder and decoder. Based on RapidJSON C++ library."),
    0,                          /* m_size */
    functions,                  /* m_methods */
    slots,                      /* m_slots */
    nullptr,                       /* m_traverse */
    nullptr,                       /* m_clear */
    nullptr                        /* m_free */
};


PyMODINIT_FUNC
PyInit_rapidjson()
{
    return PyModuleDef_Init(&module);
}
