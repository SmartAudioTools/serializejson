// -*- coding: utf-8 -*-
// :Project:   python-rapidjson -- Python extension module
// :Author:    Ken Robbins <ken@kenrobbins.com>
// :License:   MIT License
// :Copyright: © 2015 Ken Robbins
// :Copyright: © 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022 Lele Gaifax
//

#include <locale.h>
#include <Python.h>
#include <datetime.h>
#include <structmember.h>
#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

#include "serializejson.h"
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


static PyObject* do_encode(PyObject* value, PyObject* defaultFn, bool ensureAscii,
                           unsigned writeMode, char indentChar, unsigned indentCount,
                           unsigned numberMode, unsigned datetimeMode,
                           unsigned uuidMode, unsigned bytesMode,
                           unsigned iterableMode, unsigned mappingMode, bool returnBytes);
static PyObject* do_stream_encode(PyObject* value, PyObject* stream, size_t chunkSize,
                                  PyObject* defaultFn, bool ensureAscii,
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
          numberMode(nm)
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
    }

    bool Handle(PyObject* value) {
        if (root) {
            const HandlerContext& current = stack.back();

            if (current.isObject) {
                PyObject* key = PyUnicode_FromStringAndSize(current.key,
                                                            current.keyLength);
                if (key == nullptr) {
                    Py_DECREF(value);
                    return false;
                }

                PyObject* shared_key = PyDict_SetDefault(sharedKeys, key, key);
                if (shared_key == nullptr) {
                    Py_DECREF(key);
                    Py_DECREF(value);
                    return false;
                }
                Py_INCREF(shared_key);
                Py_DECREF(key);
                key = shared_key;

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

        if (decoderStartObject != nullptr) {
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

        if (objectHook == nullptr && decoderEndObject == nullptr) {
            Py_DECREF(mapping);
            return true;
        }

        PyObject* replacement;
        if (decoderEndObject != nullptr) {
            replacement = PyObject_CallFunctionObjArgs(decoderEndObject, mapping, nullptr);
        } else /* if (objectHook != nullptr) */ {
            replacement = PyObject_CallFunctionObjArgs(objectHook, mapping, nullptr);
        }

        Py_DECREF(mapping);
        if (replacement == nullptr)
            return false;

        if (!stack.empty()) {
            HandlerContext& current = stack.back();

            if (current.isObject) {
                PyObject* key = PyUnicode_FromStringAndSize(current.key,
                                                            current.keyLength);
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
                PyObject* key = PyUnicode_FromStringAndSize(current.key,
                                                            current.keyLength);
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
            std::string zstr(str, length);

            value = PyLong_FromString(zstr.c_str(), nullptr, 10);
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

        if (datetimeMode != DM_NONE) {
            int year, month, day, hours, mins, secs, usecs, tzoff;

            if (IsIso8601(str, length, year, month, day,
                          hours, mins, secs, usecs, tzoff))
                return HandleIso8601(str, length, year, month, day,
                                     hours, mins, secs, usecs, tzoff);
        }

        if (uuidMode != UM_NONE && IsUuid(str, length))
            return HandleUuid(str, length);

        value = PyUnicode_FromStringAndSize(str, length);
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

    if (jsonStr != nullptr) {
        char* jsonStrCopy = (char*) PyMem_Malloc(sizeof(char) * (jsonStrLen+1));

        if (jsonStrCopy == nullptr)
            return PyErr_NoMemory();

        memcpy(jsonStrCopy, jsonStr, jsonStrLen+1);

        InsituStringStream ss(jsonStrCopy);

        DECODE(reader, kParseInsituFlag, ss, handler);

        PyMem_Free(jsonStrCopy);
    } else {
        PyReadStreamWrapper sw(jsonStream, chunkSize);

        DECODE(reader, kParseNoFlags, sw, handler);
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


template<typename WriterT>
static bool
dumps_internal(
    WriterT* writer,
    PyObject* object,
    PyObject* defaultFn,
    unsigned numberMode,
    unsigned datetimeMode,
    unsigned uuidMode,
    unsigned bytesMode,
    unsigned iterableMode,
    unsigned mappingMode)
{
    int is_decimal;

#define RECURSE(v) dumps_internal(writer, v, defaultFn,                 \
                                  numberMode, datetimeMode, uuidMode,   \
                                  bytesMode, iterableMode, mappingMode)

#define ASSERT_VALID_SIZE(l) do {                                       \
    if (l < 0 || l > UINT_MAX) {                                        \
        PyErr_SetString(PyExc_ValueError, "Out of range string size");  \
        return false;                                                   \
    } } while(0)

    // None -------------------------------------
    if (object == Py_None) {
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
        writer->Flush();
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
            // The RJ dtoa() produces "strange" results for particular values, see #101:
            // use Python's repr() to emit a raw value instead of writer->Double(d)

            PyObject* dr = PyObject_Repr(object);

            if (dr == nullptr)
                return false;

            Py_ssize_t l;
            const char* rs = PyUnicode_AsUTF8AndSize(dr, &l);
            if (rs == nullptr) {
                Py_DECREF(dr);
                return false;
            }

            writer->RawValue(rs, l);
            Py_DECREF(dr);
        }
    } 
	
	// str unicode ---------------------------------------------------------------
	else if (PyUnicode_Check(object)) {
        Py_ssize_t l;
        const char* s = PyUnicode_AsUTF8AndSize(object, &l);
        //if (s == nullptr)
        //    return false;
        //ASSERT_VALID_SIZE(l);
        writer->String(s, (SizeType) l);
    } 
	
	// liste  ---------------------------------------------------------------
	else if ((!(iterableMode & IM_ONLY_LISTS) && PyList_Check(object))
               ||
               PyList_CheckExact(object)) {
        writer->StartArray();

        Py_ssize_t size = PyList_GET_SIZE(object);

        for (Py_ssize_t i = 0; i < size; i++) {
            if (Py_EnterRecursiveCall(" while JSONifying list object"))
                return false;
            PyObject* item = PyList_GET_ITEM(object, i);
            bool r = RECURSE(item);
            Py_LeaveRecursiveCall();
            if (!r)
                return false;
        }

        writer->EndArray();
    } 
	else if (!(iterableMode & IM_ONLY_LISTS) && PyTuple_Check(object)) {
        writer->StartArray();

        Py_ssize_t size = PyTuple_GET_SIZE(object);

        for (Py_ssize_t i = 0; i < size; i++) {
            if (Py_EnterRecursiveCall(" while JSONifying tuple object"))
                return false;
            PyObject* item = PyTuple_GET_ITEM(object, i);
            bool r = RECURSE(item);
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
        while ((item = PyIter_Next(iterator))) {
            if (Py_EnterRecursiveCall(" while JSONifying iterable object")) {
                Py_DECREF(item);
                Py_DECREF(iterator);
                return false;
            }
            bool r = RECURSE(item);
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
        writer->StartObject();

        Py_ssize_t pos = 0;
        PyObject* key;
        PyObject* item;
        PyObject* coercedKey = nullptr;

            if (!(mappingMode & MM_SORT_KEYS)) {
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
                    writer->Key(key_str, (SizeType) l);
                    if (Py_EnterRecursiveCall(" while JSONifying dict object")) {
                        Py_XDECREF(coercedKey);
                        return false;
                    }
                    bool r = RECURSE(item);
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
                if (Py_EnterRecursiveCall(" while JSONifying dict object"))
                    return false;
                bool r = RECURSE(items[i].item);
                Py_LeaveRecursiveCall();
                if (!r)
                    return false;
            }
        }

        writer->EndObject();
    } 

	// RawString, RawBytes , RawBytesToPutInQuotes----------------------------------
	else if (PyObject_TypeCheck(object, &RawString_Type)) {
        writer->RawString_(object);
    } 
	else if (PyObject_TypeCheck(object, &RawBytes_Type)) {
        writer->RawBytes_(object);
    } 
	else if (PyObject_TypeCheck(object, &RawBytesToPutInQuotes_Type)) {
        writer->RawBytesToPutInQuotes_(object);
    } 
	
	// all others ojects --------------------------------------------------------
	else if (defaultFn) {
        PyObject* retval = PyObject_CallFunctionObjArgs(defaultFn, object, nullptr);
        if (retval == nullptr)
            return false;
        if (Py_EnterRecursiveCall(" while JSONifying default function result")) {
            Py_DECREF(retval);
            return false;
        }
        bool r = RECURSE(retval);
        Py_LeaveRecursiveCall();
        Py_DECREF(retval);
        if (!r)
            return false;
    } 
	else {
        PyErr_Format(PyExc_TypeError, "%R is not JSON serializable", object);
        return false;
    }

    // Catch possible error raised in associated stream operations
    
    writer->Flush();
    return PyErr_Occurred() ? false : true;

#undef RECURSE
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
} EncoderObject;

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

    return do_encode(value, defaultFn, ensureAscii ? true : false, writeMode, indentChar,
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

    return do_encode(value, defaultFn, ensureAscii ? true : false, writeMode, indentChar,
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

    return do_stream_encode(value, stream, chunkSize, defaultFn,
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
    0,                                        /* tp_methods */
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
                    numberMode,                         \
                    datetimeMode,                       \
                    uuidMode,                           \
                    bytesMode,                          \
                    iterableMode,                       \
                    mappingMode)                        \
     ? (returnBytes ? buf.getPyBytes() : PyUnicode_FromEncodedObject(buf.getPyBytes(),"utf-8",errors)): nullptr)


static PyObject*
do_encode(PyObject* value, PyObject* defaultFn, bool ensureAscii, unsigned writeMode,
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
                    numberMode,                 \
                    datetimeMode,               \
                    uuidMode,                   \
                    bytesMode,                  \
                    iterableMode,               \
                    mappingMode)                \
     ? Py_INCREF(Py_None), Py_None : nullptr)


static PyObject*
do_stream_encode(PyObject* value, PyObject* stream, size_t chunkSize, PyObject* defaultFn,
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
    PyObject* result;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O$O",
                                     (char**) kwlist,
                                     &value,
                                     &stream,
                                     &chunkSizeObj))
        return nullptr;

    EncoderObject* e = (EncoderObject*) self;

    if (stream != nullptr && stream != Py_None) {
        if (!PyObject_HasAttr(stream, write_name)) {
            PyErr_SetString(PyExc_TypeError, "Expected a writable stream");
            return nullptr;
        }

        if (!accept_chunk_size_arg(chunkSizeObj, chunkSize))
            return nullptr;

        if (PyObject_HasAttr(self, default_name)) {
            defaultFn = PyObject_GetAttr(self, default_name);
        }

        result = do_stream_encode(value, stream, chunkSize, defaultFn, e->ensureAscii,
                                  e->writeMode, e->indentChar, e->indentCount,
                                  e->numberMode, e->datetimeMode, e->uuidMode,
                                  e->bytesMode, e->iterableMode, e->mappingMode);
    } else {
        if (PyObject_HasAttr(self, default_name)) {
            defaultFn = PyObject_GetAttr(self, default_name);
        }

        result = do_encode(value, defaultFn, e->ensureAscii, e->writeMode, e->indentChar,
                           e->indentCount, e->numberMode, e->datetimeMode, e->uuidMode,
                           e->bytesMode, e->iterableMode, e->mappingMode, e->returnBytes);
    }

    if (defaultFn != nullptr)
        Py_DECREF(defaultFn);

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
        nullptr
    };
    int skipInvalidKeys = false;
    int sortKeys = false;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|ppOpOOOOOOOpp:Encoder",
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
                                     &returnBytes
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
