// -*- coding: utf-8 -*-
// :Project:   python-rapidjson -- Python extension module
// :Author:    Ken Robbins <ken@kenrobbins.com>
// :License:   MIT License
// :Copyright: © 2015 Ken Robbins
// :Copyright: © 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022 Lele Gaifax
//

// chemins SIMD de rapidjson (saut d'espaces et scan des chaînes sans
// échappement) — la machine cible compile déjà en -march=native
#define RAPIDJSON_SSE42

#include <locale.h>
#include <Python.h>
#include <datetime.h>
#include <structmember.h>
#include <algorithm>
#include <cmath>
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

// création d'un str depuis de l'utf-8 : scan ascii par mots de 8 octets
// (cas ultra-majoritaire) -> copie brute sans la passe de validation du
// décodeur utf-8 ; sinon chemin normal
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
    return PyUnicode_FromStringAndSize(s, (Py_ssize_t) len);
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
static PyObject* root_attr_name = nullptr;
static PyObject* class_key_name = nullptr;
static PyObject* init_key_name = nullptr;
static PyObject* new_key_name = nullptr;
static PyObject* state_key_name = nullptr;
static PyObject* items_key_name = nullptr;
static PyObject* empty_args_tuple = nullptr;
static PyObject* b64_payload_classes_name = nullptr;
static PyObject* end_array_name = nullptr;
static PyObject* string_name = nullptr;
static PyObject* read_name = nullptr;
static PyObject* write_name = nullptr;
static PyObject* encoding_name = nullptr;

static PyObject* minus_inf_string_value = nullptr;
static PyObject* nan_string_value = nullptr;
static PyObject* plus_inf_string_value = nullptr;


struct HandlerContext {
    PyObject* object;
    const char* key;
    SizeType keyLength;
    bool isObject;
    bool keyValuePairs;
    bool copiedKey;
};


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
static PyObject* decoder_call(PyObject* self, PyObject* args, PyObject* kwargs);
static PyObject* decoder_new(PyTypeObject* type, PyObject* args, PyObject* kwargs);


// Suivi du chemin JSON courant pendant l'encodage ("root[0].attr['clef']"),
// pour que les hooks default/default_dict/default_list puissent mémoriser où
// chaque objet a été écrit et émettre des {"$ref": chemin} sans avoir à
// remonter le graphe avec gc.get_referrers côté Python.
struct PathSegment {
    enum Kind { INDEX, KEY, ATTR } kind;
    const char* str;   // clé utf-8 empruntée, valide pendant la récursion sous cette clé
    size_t len;
    Py_ssize_t index;
};
// noeud matérialisé d'un chemin : arbre à partage structurel, un noeud par
// position réellement demandée via json_path_id() (la clé y est COPIÉE car
// les pointeurs empruntés des segments peuvent mourir avant la fin du dump)
struct PathNode {
    int parent;   // index dans nodes, -1 pour un enfant direct de root
    PathSegment::Kind kind;
    std::string key;
    Py_ssize_t index;
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
        uintptr_t h = (uintptr_t) k;
        h ^= h >> 33; h *= (uintptr_t) 0xff51afd7ed558ccdULL; h ^= h >> 29;
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
// Les rares flottants dont Grisu3 ne garantit pas l'arrondi sont notés
// (position de coupe, valeur) et rendus sous GIL au recollage via
// PyOS_double_to_string.

#define SJ_NUM_MT_MIN 32768
#define SJ_NUM_MT_CHUNK 16384

struct sj_numchunk {
    std::vector<char> text;
    std::vector<std::pair<size_t, double>> fallbacks;  // coupe -> valeur
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
            int len = sjdtoa::ReprDouble(v, cursor);
            if (len > 0)
                cursor += len;
            else
                out.fallbacks.push_back({(size_t) (cursor - base), v});
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

// recolle les tranches dans le flux, en rendant les replis sous GIL ;
// l'appelant a déjà écrit StartArray et fera AnnounceArrayValues+EndArray
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
        size_t pos = 0;
        for (auto& fb : chunk.fallbacks) {
            if (fb.first > pos)
                os.RawValue(chunk.text.data() + pos, fb.first - pos);
            pos = fb.first;
            char* repr_str = PyOS_double_to_string(fb.second, 'r', 0,
                                                   Py_DTSF_ADD_DOT_0, nullptr);
            if (repr_str == nullptr)
                return false;
            os.RawValue(repr_str, strlen(repr_str));
            PyMem_Free(repr_str);
        }
        if (chunk.text.size() > pos)
            os.RawValue(chunk.text.data() + pos, chunk.text.size() - pos);
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
    // chemin rapide par classe : class_plan(classe) est appelé UNE fois par
    // classe et par dump ; il retourne None (chemin Python complet) ou un
    // tuple (nom_de_classe, filtrer_underscores) autorisant l'écriture de
    // l'objet entièrement en C++ (attributs du __dict__, triés)
    PyObject* classPlanFn = nullptr;   // référence empruntée (encoder_call)
    std::unordered_map<PyTypeObject*, PyObject*> classPlans;  // réfs possédées
    // écrit sur une seule ligne les listes homogènes de nombres, où qu'elles
    // soient (valeurs de dicts purs et sous-listes comprises)
    bool singleLineNumbers = false;
    // vrai si le prochain dict rencontré est l'état d'un objet retourné par
    // default() : ses clés sont alors des attributs (".attr" et non "['clef']")
    bool next_dict_is_attrs = false;

    // 4 plans de forme, indexés par profondeur : des dicts imbriqués de
    // formes différentes ne s'écrasent pas mutuellement le cache
    DictShape shapes[4];

    ~PathTracker() {
        for (DictShape& s : shapes)
            s.clear_refs();
        memo.decref_keys();
        for (auto& entry : classPlans)
            Py_DECREF(entry.second);
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

// chaîne "root[0].attr['clef']" du noeud node_index (-1 = "root")
static std::string
path_tracker_string(PathTracker* tracker, long node_index)
{
    std::vector<int> chain;
    while (node_index != -1) {
        chain.push_back((int) node_index);
        node_index = tracker->nodes[(size_t) node_index].parent;
    }
    std::string out("root");
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
                           unsigned iterableMode, unsigned mappingMode, bool returnBytes);
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


struct PyHandler {
    PyObject* decoderStartObject;
    PyObject* decoderEndObject;
    PyObject* decoderEndArray;
    PyObject* decoderString;
    PyObject* sharedKeys;
    PyObject* root;
    PyObject* objectHook;
    unsigned datetimeMode;
    unsigned uuidMode;
    unsigned numberMode;
    std::vector<HandlerContext> stack;
    // chemin rapide de décodage : decode_class_plan(nom_de_classe), appelé
    // UNE fois par classe et par chargement, retourne None (end_object
    // Python) ou la CLASSE — l'objet est alors instancié en C++ (tp_new puis
    // assignation du dict d'attributs), sans aucun appel Python par objet
    PyObject* decoderObject;        // le Decoder lui-même (pour poser .root)
    PyObject* decodeClassPlanFn;
    bool fastStartObject;           // start_object Python court-circuité
    bool rootAttrSet;
    std::unordered_map<std::string, PyObject*> decodePlans;  // réfs possédées
    // classes dont la charge __init__/__new__[0] est du base64 à décoder
    // directement depuis le tampon de parse (0 -> bytes, 1 -> bytearray)
    std::unordered_map<std::string, int> b64PayloadClasses;

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
          fastStartObject(false),
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
                decoderObject = decoder;
                Py_INCREF(decoder);
            }
            sharedKeys = PyDict_New();
        }

    ~PyHandler() {
        while (!stack.empty()) {
            const HandlerContext& ctx = stack.back();
            if (ctx.copiedKey)
                PyMem_Free((void*) ctx.key);
            if (ctx.object != nullptr)
                Py_DECREF(ctx.object);
            stack.pop_back();
        }
        Py_CLEAR(decoderStartObject);
        Py_CLEAR(decoderEndObject);
        Py_CLEAR(decoderEndArray);
        Py_CLEAR(decoderString);
        Py_CLEAR(sharedKeys);
        Py_CLEAR(decoderObject);
        Py_CLEAR(decodeClassPlanFn);
        for (auto& entry : decodePlans)
            Py_DECREF(entry.second);
    }

    bool Handle(PyObject* value) {

        if (root) {
            const HandlerContext& current = stack.back();

            if (current.isObject) {
                PyObject* key = sj_unicode_from_utf8(current.key,
                                                            (size_t) current.keyLength);
                if (key == nullptr) {
                    Py_DECREF(value);
                    return false;
                }

                // internement des cles : rentable quand les memes cles
                // reviennent (objets, listes de dicts homogenes), pur surcout
                // quand elles sont toutes distinctes -> plafond au-dela duquel
                // on cesse d'interner (optimisation sans effet semantique)
                if (PyDict_GET_SIZE(sharedKeys) < 4096) {
                    PyObject* shared_key = PyDict_SetDefault(sharedKeys, key, key);
                    if (shared_key == nullptr) {
                        Py_DECREF(key);
                        Py_DECREF(value);
                        return false;
                    }
                    Py_INCREF(shared_key);
                    Py_DECREF(key);
                    key = shared_key;
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
            } else {
                PyList_Append(current.object, value);
                Py_DECREF(value);
            }
        } else {
            root = value;
        }
        return true;
    }

    bool Key(const char* str, SizeType length, bool copy) {
        HandlerContext& current = stack.back();

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
            mapping = PyDict_New();
            if (mapping == nullptr)
                return false;
            key_value_pairs = false;
            if (!rootAttrSet && stack.empty() && decoderObject != nullptr) {
                if (PyObject_SetAttr(decoderObject, root_attr_name, mapping) == -1) {
                    Py_DECREF(mapping);
                    return false;
                }
                rootAttrSet = true;
            }
        } else if (decoderStartObject != nullptr) {
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
        Py_INCREF(mapping);

        stack.push_back(ctx);

        return true;
    }

    bool EndObject(SizeType member_count) {
        const HandlerContext& ctx = stack.back();

        if (ctx.copiedKey)
            PyMem_Free((void*) ctx.key);

        PyObject* mapping = ctx.object;
        stack.pop_back();

        PyObject* replacement = nullptr;

        // ----- chemin rapide de décodage par classe : {"__class__": nom,
        // attributs...} sans clé spéciale -> instanciation directe en C++
        if (decodeClassPlanFn != nullptr && PyDict_CheckExact(mapping)) {
            PyObject* class_value = PyDict_GetItem(mapping, class_key_name);
            if (class_value != nullptr && PyUnicode_CheckExact(class_value)
                && PyDict_GetItem(mapping, init_key_name) == nullptr
                && PyDict_GetItem(mapping, new_key_name) == nullptr
                && PyDict_GetItem(mapping, state_key_name) == nullptr
                && PyDict_GetItem(mapping, items_key_name) == nullptr
                && PyDict_GetItem(mapping, dict_dunder_name) == nullptr) {
                Py_ssize_t class_length;
                const char* class_str =
                    PyUnicode_AsUTF8AndSize(class_value, &class_length);
                if (class_str == nullptr) {
                    Py_DECREF(mapping);
                    return false;
                }
                std::string plan_key(class_str, (size_t) class_length);
                PyObject* plan;
                auto plan_it = decodePlans.find(plan_key);
                if (plan_it != decodePlans.end()) {
                    plan = plan_it->second;
                } else {
                    plan = PyObject_CallFunctionObjArgs(decodeClassPlanFn,
                                                        class_value, nullptr);
                    if (plan == nullptr) {
                        Py_DECREF(mapping);
                        return false;
                    }
                    if (plan != Py_None && !PyType_Check(plan)) {
                        Py_DECREF(plan);
                        plan = Py_None;
                        Py_INCREF(Py_None);
                    }
                    decodePlans.emplace(std::move(plan_key), plan);
                }
                if (plan != Py_None) {
                    if (PyDict_DelItem(mapping, class_key_name) == -1) {
                        Py_DECREF(mapping);
                        return false;
                    }
                    PyTypeObject* cls = (PyTypeObject*) plan;
                    PyObject* inst = cls->tp_new(cls, empty_args_tuple, nullptr);
                    if (inst == nullptr) {
                        Py_DECREF(mapping);
                        return false;
                    }
                    // assignation directe du dict d'attributs (objet neuf au
                    // dict vide : équivalent du update() du chemin Python)
                    if (PyObject_SetAttr(inst, dict_dunder_name, mapping) == -1) {
                        Py_DECREF(inst);
                        Py_DECREF(mapping);
                        return false;
                    }
                    Py_DECREF(mapping);
                    replacement = inst;
                }
            }
        }

        if (replacement == nullptr) {
            if (objectHook == nullptr && decoderEndObject == nullptr) {
                Py_DECREF(mapping);
                return true;
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

        if (!stack.empty()) {
            HandlerContext& current = stack.back();

            if (current.isObject) {
                PyObject* key = sj_unicode_from_utf8(current.key,
                                                            (size_t) current.keyLength);
                if (key == nullptr) {
                    Py_DECREF(replacement);
                    return false;
                }

                PyObject* shared_key = PyDict_SetDefault(sharedKeys, key, key);
                if (shared_key == nullptr) {
                    Py_DECREF(key);
                    Py_DECREF(replacement);
                    return false;
                }
                Py_INCREF(shared_key);
                Py_DECREF(key);
                key = shared_key;

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
        Py_INCREF(list);

        stack.push_back(ctx);

        return true;
    }

    bool EndArray(SizeType elementCount) {
        const HandlerContext& ctx = stack.back();

        if (ctx.copiedKey)
            PyMem_Free((void*) ctx.key);

        PyObject* sequence = ctx.object;
        stack.pop_back();

        if (decoderEndArray == nullptr) {
            Py_DECREF(sequence);
            return true;
        }

        PyObject* replacement = PyObject_CallFunctionObjArgs(decoderEndArray, sequence,
                                                             nullptr);
        Py_DECREF(sequence);
        if (replacement == nullptr)
            return false;

        if (!stack.empty()) {
            const HandlerContext& current = stack.back();

            if (current.isObject) {
                PyObject* key = sj_unicode_from_utf8(current.key,
                                                            (size_t) current.keyLength);
                if (key == nullptr) {
                    Py_DECREF(replacement);
                    return false;
                }

                int rc;
                if (PyDict_Check(current.object))
                    // If it's a standard dictionary, this is +20% faster
                    rc = PyDict_SetItem(current.object, key, replacement);
                else
                    rc = PyObject_SetItem(current.object, key, replacement);

                Py_DECREF(key);
                Py_DECREF(replacement);

                if (rc == -1) {
                    return false;
                }
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

    bool String(const char* str, SizeType length, bool copy) {
        PyObject* value;

        // ----- charges binaires : décode le base64 directement depuis le
        // tampon de parse (sans matérialiser la chaîne Python intermédiaire)
        // quand cette chaîne est le premier élément de la liste __init__ ou
        // __new__ d'une classe enregistrée (bytes, bytearray, numpyB64...).
        // Si ce n'est pas du base64 propre, chemin normal.
        if (!b64PayloadClasses.empty() && length >= 8 && stack.size() >= 2) {
            const HandlerContext& top = stack.back();
            if (!top.isObject && PyList_CheckExact(top.object)
                && PyList_GET_SIZE(top.object) == 0) {
                const HandlerContext& parent = stack[stack.size() - 2];
                if (parent.isObject && parent.key != nullptr
                    && ((parent.keyLength == 8
                         && memcmp(parent.key, "__init__", 8) == 0)
                        || (parent.keyLength == 7
                            && memcmp(parent.key, "__new__", 7) == 0))
                    && PyDict_CheckExact(parent.object)) {
                    PyObject* class_value =
                        PyDict_GetItem(parent.object, class_key_name);
                    if (class_value != nullptr
                        && PyUnicode_CheckExact(class_value)) {
                        Py_ssize_t class_length;
                        const char* class_str = PyUnicode_AsUTF8AndSize(
                            class_value, &class_length);
                        if (class_str != nullptr) {
                            auto it = b64PayloadClasses.find(
                                std::string(class_str, (size_t) class_length));
                            if (it != b64PayloadClasses.end()) {
                                PyObject* decoded =
                                    serializejson_b64_decode_to_pyobject(
                                        str, (size_t) length, it->second);
                                if (decoded != nullptr)
                                    return Handle(decoded);
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

        value = sj_unicode_from_utf8(str, (size_t) length);
        if (value == nullptr)
            return false;

        if (decoderString != nullptr) {
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


typedef struct {
    PyObject_HEAD
    unsigned datetimeMode;
    unsigned uuidMode;
    unsigned numberMode;
    unsigned parseMode;
} DecoderObject;


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


static PyTypeObject Decoder_Type = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "rapidjson.Decoder",                      /* tp_name */
    sizeof(DecoderObject),                    /* tp_basicsize */
    0,                                        /* tp_itemsize */
    0,                                        /* tp_dealloc */
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
    0,                                        /* tp_methods */
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

    if (jsonStr != nullptr) {
        // insitu sur une COPIE de l'entrée : essayé sans copie (StringStream)
        // le 03/08/2026 — REGRESSION mesurée partout (nombres recopiés
        // caractère par caractère hors insitu, chaînes dés-échappées vers la
        // pile) : la copie unique de l'entrée est le bon échange
        char* jsonStrCopy = (char*) PyMem_Malloc(sizeof(char) * (jsonStrLen+1));

        if (jsonStrCopy == nullptr)
            return PyErr_NoMemory();

        memcpy(jsonStrCopy, jsonStr, jsonStrLen+1);

        InsituStringStream ss(jsonStrCopy);

        // pleine precision + grands entiers exacts : sans effet dans les branches
        // nombres-en-chaines, actifs dans les branches natives (NM_NATIVE)
        DECODE(reader, kParseInsituFlag | kParseFullPrecisionFlag | kParseBigIntsAsStringsFlag, ss, handler);

        PyMem_Free(jsonStrCopy);
    } else {
        PyReadStreamWrapper sw(jsonStream, chunkSize);

        DECODE(reader, kParseFullPrecisionFlag | kParseBigIntsAsStringsFlag, sw, handler);
    }

    if (reader.HasParseError()) {
        size_t offset = reader.GetErrorOffset();

        if (PyErr_Occurred()) {
            PyObject* etype;
            PyObject* evalue;
            PyObject* etraceback;
            PyErr_Fetch(&etype, &evalue, &etraceback);

            // Try to add the offset in the error message if the exception
            // value is a string.  Otherwise, use the original exception since
            // we can't be sure the exception type takes a single string.
            if (evalue != nullptr && PyUnicode_Check(evalue)) {
                PyErr_Format(etype, "Parse error at offset %zu: %S", offset, evalue);
                Py_DECREF(etype);
                Py_DECREF(evalue);
                Py_XDECREF(etraceback);
            }
            else
                PyErr_Restore(etype, evalue, etraceback);
        }
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
decoder_call(PyObject* self, PyObject* args, PyObject* kwargs)
{
    static char const* kwlist[] = {
        "json",
        "chunk_size",
        nullptr
    };
    PyObject* jsonObject;
    PyObject* chunkSizeObj = nullptr;
    size_t chunkSize = 65536;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|$O",
                                     (char**) kwlist,
                                     &jsonObject,
                                     &chunkSizeObj))
        return nullptr;

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
    } else if (PyBytes_Check(jsonObject) || PyByteArray_Check(jsonObject)) {
        asUnicode = PyUnicode_FromEncodedObject(jsonObject, "utf-8", nullptr);
        if (asUnicode == nullptr)
            return nullptr;
        jsonStr = PyUnicode_AsUTF8AndSize(asUnicode, &jsonStrLen);
        if (jsonStr == nullptr) {
            Py_DECREF(asUnicode);
            return nullptr;
        }
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
all_keys_are_string(PyObject* dict) {
    Py_ssize_t pos = 0;
    PyObject* key;

    while (PyDict_Next(dict, &pos, &key, nullptr))
        if (!PyUnicode_Check(key))
            return false;
    return true;
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
            // graphie EXACTE de repr() : Grisu3 en direct, repli sur le
            // moteur interne de CPython quand l'arrondi n'est pas garanti
            char repr_buf[40];
            int repr_len = sjdtoa::ReprDouble(value, repr_buf);
            if (repr_len > 0) {
                writer->RawValue(repr_buf, (size_t) repr_len);
            } else {
                char* repr_str = PyOS_double_to_string(value, 'r', 0,
                                                       Py_DTSF_ADD_DOT_0, nullptr);
                if (repr_str == nullptr)
                    return false;
                writer->RawValue(repr_str, strlen(repr_str));
                PyMem_Free(repr_str);
            }
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
            std::string ref_ = "{\"$ref\": \"";                         \
            ref_ += path_tracker_string(pathTracker, memo_slot->second);\
            ref_ += "\"}";                                              \
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
        writer->String(s, (SizeType) l);
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
            // Grisu3 en direct, repli sur le moteur interne de CPython
            // quand l'arrondi n'est pas garanti (~0,5 % des valeurs)
            char repr_buf[40];
            int repr_len = sjdtoa::ReprDouble(d, repr_buf);
            if (repr_len > 0) {
                writer->RawValue(repr_buf, (size_t) repr_len);
            } else {
                char* repr_str = PyOS_double_to_string(d, 'r', 0,
                                                       Py_DTSF_ADD_DOT_0, nullptr);
                if (repr_str == nullptr)
                    return false;
                writer->RawValue(repr_str, strlen(repr_str));
                PyMem_Free(repr_str);
            }
        }
    }
	
	// str unicode ---------------------------------------------------------------
	else if (PyUnicode_Check(object)) {
        Py_ssize_t l;
        const char* s = PyUnicode_AsUTF8AndSize(object, &l);
        if (!PyUnicode_IS_ASCII(object))
            writer->MarkMaybeNonAscii();
        writer->String(s, (SizeType) l);
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
                if (size >= SJ_NUM_MT_MIN) {
                    std::vector<long long> vals((size_t) size);
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
                        size_t nthreads = std::min<size_t>(
                            std::min<size_t>(8, std::thread::hardware_concurrency()),
                            (size_t) size / SJ_NUM_MT_CHUNK);
                        if (nthreads >= 2) {
                            size_t nchunks = ((size_t) size + SJ_NUM_MT_CHUNK - 1)
                                             / SJ_NUM_MT_CHUNK;
                            std::vector<sj_numchunk> chunks(nchunks);
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
                if (size >= SJ_NUM_MT_MIN) {
                    std::vector<double> vals((size_t) size);
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
                        size_t nthreads = std::min<size_t>(
                            std::min<size_t>(8, std::thread::hardware_concurrency()),
                            (size_t) size / SJ_NUM_MT_CHUNK);
                        if (nthreads >= 2) {
                            size_t nchunks = ((size_t) size + SJ_NUM_MT_CHUNK - 1)
                                             / SJ_NUM_MT_CHUNK;
                            std::vector<sj_numchunk> chunks(nchunks);
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
                        int repr_len = sjdtoa::ReprDouble(value, repr_buf);
                        if (repr_len > 0) {
                            writer->RawValue(repr_buf, (size_t) repr_len);
                        } else {
                            char* repr_str = PyOS_double_to_string(
                                value, 'r', 0, Py_DTSF_ADD_DOT_0, nullptr);
                            if (repr_str == nullptr) {
                                if (pushed_compact)
                                    writer->PopCompact();
                                return false;
                            }
                            writer->RawValue(repr_str, strlen(repr_str));
                            PyMem_Free(repr_str);
                        }
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
                    writer->String(inline_str, (SizeType) inline_length);
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
	
	// dictionnaires ---------------------------------------------------------
	else if (((!(mappingMode & MM_ONLY_DICTS) && PyDict_Check(object))
                ||
                PyDict_CheckExact(object))
               &&
               ((mappingMode & MM_SKIP_NON_STRING_KEYS)
                ||
                (mappingMode & MM_COERCE_KEYS_TO_STRINGS)
                ||
                all_keys_are_string(object))) {
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
                        if (PyUnicode_CheckExact(shape_item)) {
                            Py_ssize_t inline_length;
                            const char* inline_str = PyUnicode_AsUTF8AndSize(
                                shape_item, &inline_length);
                            if (inline_str == nullptr)
                                return false;
                            if (!PyUnicode_IS_ASCII(shape_item))
                                writer->MarkMaybeNonAscii();
                            writer->String(inline_str,
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
                        writer->String(inline_str, (SizeType) inline_length);
                        Py_CLEAR(coercedKey);
                        continue;
                    }
                    if (Py_EnterRecursiveCall(" while JSONifying dict object")) {
                        Py_XDECREF(coercedKey);
                        return false;
                    }
                    PATH_PUSH_KEY(key_str, l);
                    bool r = RECURSE(item);
                    PATH_POP();
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
                    writer->String(inline_str, (SizeType) inline_length);
                    continue;
                }
                if (Py_EnterRecursiveCall(" while JSONifying dict object"))
                    return false;
                PATH_PUSH_KEY(items[i].key_str, items[i].key_size);
                bool r = RECURSE(items[i].item);
                PATH_POP();
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
	else if (PyObject_TypeCheck(object, &RawBytesToBase64_Type)) {
        writer->RawBytesToBase64_(object);
    } 
	
	// all others ojects --------------------------------------------------------
	else if (defaultFn) {
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
                    && (!PyTuple_Check(plan) || PyTuple_GET_SIZE(plan) != 2)) {
                    Py_DECREF(plan);
                    plan = Py_None;
                    Py_INCREF(Py_None);
                }
                pathTracker->classPlans.emplace(object_type, plan);
            }
            if (plan != Py_None) {
                PyObject* class_name = PyTuple_GET_ITEM(plan, 0);
                bool filter_underscore =
                    PyObject_IsTrue(PyTuple_GET_ITEM(plan, 1)) == 1;

                // doublon ou cycle -> $ref
                auto memo_it = pathTracker->memo.find(object);
                if (memo_it != pathTracker->memo.end()) {
                    std::string ref_ = "{\"$ref\": \"";
                    ref_ += path_tracker_string(pathTracker, memo_it->second);
                    ref_ += "\"}";
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
                        std::string ref_ = "{\"$ref\": \"";
                        ref_ += path_tracker_string(pathTracker, shared_dict_node);
                        ref_ += "\"}";
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
                                writer->String(inline_str,
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
        bool r = RECURSE(retval);
        if (pathTracker)
            pathTracker->next_dict_is_attrs = false;
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
    // traqueur de chemin actif pendant un encodage (nullptr sinon),
    // consulté par la méthode json_path()
    PathTracker* activePathTracker;
    // tailles atteintes au dump précédent : pré-réservation du prochain
    // (évite les réallocations-copies mesurées ~8% sur les gros graphes)
    size_t pathNodesHighWater;
    size_t memoHighWater;
} EncoderObject;


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
    std::string out("root");
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


static PyMethodDef encoder_methods[] = {
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
                     iterableMode, mappingMode, returnBytes);
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
                     iterableMode, mappingMode, true);
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

static PyTypeObject Encoder_Type = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "rapidjson.Encoder",                      /* tp_name */
    sizeof(EncoderObject),                    /* tp_basicsize */
    0,                                        /* tp_itemsize */
    0,                                        /* tp_dealloc */
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
     ? (buf.Flush(), (returnBytes ? buf.getPyBytes()         : (buf.maybe_non_ascii            ? PyUnicode_FromEncodedObject(buf.getPyBytes(),"utf-8",errors)            : sj_unicode_from_ascii(buf.GetBuffer(), (Py_ssize_t) buf.GetSize())))): nullptr)


static PyObject*
do_encode(PyObject* value, PyObject* defaultFn,
          PyObject* defaultDictFn, PyObject* defaultListFn,
          PathTracker* pathTracker,
          bool ensureAscii, unsigned writeMode,
          char indentChar, unsigned indentCount, unsigned numberMode,
          unsigned datetimeMode, unsigned uuidMode, unsigned bytesMode,
          unsigned iterableMode, unsigned mappingMode, bool returnBytes)
{
    const char *errors;
    PyBytesBuffer buf;
    if (writeMode == WM_COMPACT) {
            Writer<PyBytesBuffer> writer(buf);
            return DUMPS_INTERNAL_CALL_WITH_PYBYTESBUFFER  ;
    } else {
        PrettyWriter<PyBytesBuffer> writer(buf);
        writer.SetIndent(indentChar, indentCount);
        if (writeMode & WM_SINGLE_LINE_ARRAY) {
            writer.SetFormatOptions(kFormatSingleLineArray);
        }
        return DUMPS_INTERNAL_CALL_WITH_PYBYTESBUFFER;
    }
}


#define DUMP_INTERNAL_CALL                      \
    (dumps_internal(&writer,                    \
                    value,                      \
                    defaultFn,                  \
                    defaultDictFn,              \
                    defaultListFn,              \
                    pathTracker,                \
                    numberMode,                 \
                    datetimeMode,               \
                    uuidMode,                   \
                    bytesMode,                  \
                    iterableMode,               \
                    mappingMode)                \
     ? (writer.Flush(), Py_INCREF(Py_None), Py_None) : nullptr)


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


static PyObject*
encoder_call(PyObject* self, PyObject* args, PyObject* kwargs)
{
    static char const* kwlist[] = {
        "obj",
        "stream",
        "chunk_size",
        nullptr
    };
    PyObject* value;
    PyObject* stream = nullptr;
    PyObject* chunkSizeObj = nullptr;
    size_t chunkSize = 65536;
    PyObject* defaultFn = nullptr;
    PyObject* defaultDictFn = nullptr;
    PyObject* defaultListFn = nullptr;
    PyObject* result;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O$O",
                                     (char**) kwlist,
                                     &value,
                                     &stream,
                                     &chunkSizeObj))
        return nullptr;

    EncoderObject* e = (EncoderObject*) self;

    if (PyObject_HasAttr(self, default_name)) {
        defaultFn = PyObject_GetAttr(self, default_name);
    }
    if (PyObject_HasAttr(self, default_dict_name)) {
        defaultDictFn = PyObject_GetAttr(self, default_dict_name);
    }
    if (PyObject_HasAttr(self, default_list_name)) {
        defaultListFn = PyObject_GetAttr(self, default_list_name);
    }
    PyObject* classPlanFn = nullptr;
    if (PyObject_HasAttr(self, class_plan_name)) {
        classPlanFn = PyObject_GetAttr(self, class_plan_name);
    }

    PathTracker pathTracker;
    if (e->pathNodesHighWater) {
        pathTracker.nodes.reserve(e->pathNodesHighWater);
        pathTracker.registered.reserve(64);
        pathTracker.segments.reserve(64);
    }
    if (e->memoHighWater)
        pathTracker.memo.reserve(e->memoHighWater);
    pathTracker.memoContainers = e->memoRefs;
    pathTracker.singleLineNumbers = e->singleLineNumbers;
    pathTracker.classPlanFn = classPlanFn;
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

        if (!accept_chunk_size_arg(chunkSizeObj, chunkSize)) {
            e->activePathTracker = nullptr;
            Py_XDECREF(defaultFn);
            Py_XDECREF(defaultDictFn);
            Py_XDECREF(defaultListFn);
            Py_XDECREF(classPlanFn);
            return nullptr;
        }

        result = do_stream_encode(value, stream, chunkSize, defaultFn,
                                  defaultDictFn, defaultListFn, &pathTracker,
                                  e->ensureAscii,
                                  e->writeMode, e->indentChar, e->indentCount,
                                  e->numberMode, e->datetimeMode, e->uuidMode,
                                  e->bytesMode, e->iterableMode, e->mappingMode);
    } else {
        result = do_encode(value, defaultFn, defaultDictFn, defaultListFn,
                           &pathTracker,
                           e->ensureAscii, e->writeMode, e->indentChar,
                           e->indentCount, e->numberMode, e->datetimeMode, e->uuidMode,
                           e->bytesMode, e->iterableMode, e->mappingMode, e->returnBytes);
    }

    e->activePathTracker = nullptr;
    if (pathTracker.nodes.size() > e->pathNodesHighWater)
        e->pathNodesHighWater = pathTracker.nodes.size();
    if (pathTracker.memo.size() > e->memoHighWater)
        e->memoHighWater = pathTracker.memo.size();
    Py_XDECREF(defaultFn);
    Py_XDECREF(defaultDictFn);
    Py_XDECREF(defaultListFn);
    Py_XDECREF(classPlanFn);

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
        nullptr
    };
    int skipInvalidKeys = false;
    int sortKeys = false;
    int memoRefs = false;
    int singleLineNumbers = false;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|ppOpOOOOOOOpppp:Encoder",
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
                                     &singleLineNumbers
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
    e->singleLineNumbers = singleLineNumbers? true : false;
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
// système) et résout les symboles de l'API de compatibilité blosc1 utilisés
// par BloscToBase64. Le handle n'est jamais refermé : la bibliothèque vit
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
    serializejson_blosc1_compress_t compress =
        (serializejson_blosc1_compress_t) dlsym(handle, "blosc1_compress");
    serializejson_blosc1_set_compressor_t set_compressor =
        (serializejson_blosc1_set_compressor_t) dlsym(handle, "blosc1_set_compressor");
    serializejson_blosc2_set_nthreads_t set_nthreads =
        (serializejson_blosc2_set_nthreads_t) dlsym(handle, "blosc2_set_nthreads");
    serializejson_blosc2_init_t init =
        (serializejson_blosc2_init_t) dlsym(handle, "blosc2_init");
    if (compress == nullptr || set_compressor == nullptr || init == nullptr) {
        dlclose(handle);
        PyErr_SetString(PyExc_OSError,
                        "blosc1 compatibility symbols not found in library");
        return nullptr;
    }
    init();
    serializejson_blosc1_compress = compress;
    serializejson_blosc1_set_compressor = set_compressor;
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

    Py_RETURN_TRUE;
}


PyDoc_STRVAR(blosc_decompress_chunks_docstring,
             "blosc_decompress_chunks(data, as_bytearray=0, nthreads=0)\n\n"
             "Décompresse une concaténation ordonnée de trames blosc"
             " (compression parallèle déterministe) — en parallèle aussi,"
             " chaque trame vers sa position finale. nthreads=0 : automatique.");

static PyObject*
blosc_decompress_chunks_fn(PyObject* Py_UNUSED(self), PyObject* args)
{
    Py_buffer view;
    int as_bytearray = 0;
    int nthreads = 0;
    if (!PyArg_ParseTuple(args, "y*|ii", &view, &as_bytearray, &nthreads))
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
    if (nthreads > (int) jobs.size())
        nthreads = (int) jobs.size();
    bool failed = false;
    Py_BEGIN_ALLOW_THREADS
    std::atomic<size_t> next(0);
    std::vector<std::thread> threads;
    for (int t = 1; t < nthreads; t++)
        threads.emplace_back(sj_decompress_worker, &jobs, &next);
    sj_decompress_worker(&jobs, &next);
    for (std::thread& worker : threads)
        worker.join();
    for (SjDecompressJob& job : jobs)
        if (job.result != job.destsize)
            failed = true;
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
    if (serializejson_blosc2_set_nthreads == nullptr)
        Py_RETURN_NONE;
    return PyLong_FromLong(
        serializejson_blosc2_set_nthreads((int16_t) nthreads));
}


static PyMethodDef functions[] = {
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
    {"blosc_set_nthreads", (PyCFunction) blosc_set_nthreads_fn, METH_O,
     "Nombre de threads de la libblosc2 chargée (None si non chargée)."},
    {"blosc_decompress_chunks", (PyCFunction) blosc_decompress_chunks_fn,
     METH_VARARGS, blosc_decompress_chunks_docstring},
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
    if (fast_start_object_name == nullptr)
        return -1;

    root_attr_name = PyUnicode_InternFromString("root");
    if (root_attr_name == nullptr)
        return -1;

    class_key_name = PyUnicode_InternFromString("__class__");
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
