// Tencent is pleased to support the open source community by making RapidJSON available.
// 
// Copyright (C) 2015 THL A29 Limited, a Tencent company, and Milo Yip.
//
// Licensed under the MIT License (the "License"); you may not use this file except
// in compliance with the License. You may obtain a copy of the License at
//
// http://opensource.org/licenses/MIT
//
// Unless required by applicable law or agreed to in writing, software distributed 
// under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR 
// CONDITIONS OF ANY KIND, either express or implied. See the License for the 
// specific language governing permissions and limitations under the License.

#ifndef RAPIDJSON_PyBytesBuffer_H_
#define RAPIDJSON_PyBytesBuffer_H_

#include "stream.h"
#include <Python.h>
#include <algorithm>
#include <new>

RAPIDJSON_NAMESPACE_BEGIN

//! Represents an in-memory output byte stream.
/*!
    This class is mainly for being wrapped by EncodedOutputStream or AutoUTFOutputStream.

    It is similar to FileWriteBuffer but the destination is an in-memory buffer instead of a file.

    Differences between PyBytesBuffer and StringBuffer:
    1. StringBuffer has Encoding but PyBytesBuffer is only a byte buffer. 
    2. StringBuffer::GetString() returns a null-terminated string. PyBytesBuffer::GetBuffer() returns a buffer without terminator.

    \tparam Allocator type for allocating memory buffer.
    \note implements Stream concept
*/
struct PyBytesBuffer { // a revoir c'est quoi la différence entre struc et class
    typedef char Ch; // byte
    
    // strBacking : le tampon est adossé à un str ASCII compact plutôt qu'à
    // un bytes — même octets, même croissance (PyUnicode_Resize realloque
    // comme _PyBytes_Resize), mais la sortie str du cas courant (document
    // resté ascii) se PREND au lieu de se recopier : la conversion finale
    // était une copie du document entier
    PyBytesBuffer(size_t capacity = kDefaultCapacity, bool strBacking_ = false){
        if (capacity == 0) capacity = kDefaultCapacity;
        initialCapacity_ = capacity;
        strBacking = strBacking_;
        bufferBegin = 0;
        bufferCursor = 0;
        bufferEnd = 0;
        pybytes = nullptr;
    }

    // propriétaire de pybytes tant que stealPyBytes() n'a pas transféré la
    // référence : les chemins str et TOUS les chemins d'erreur libèrent ici
    // (avant, chaque dumps vers str fuyait son tampon entier — mesuré
    // +205 Mo en 200 dumps de 1 Mo)
    ~PyBytesBuffer() {
        Py_XDECREF(pybytes);
    }

    void Put(char c) { 
        Reserve(1);
        *bufferCursor++ = c;
    }
    void PutUnsafe(char c) { 
        *bufferCursor++ = c;
    }
    void PutN(char c, size_t n) {
        Reserve(n);
        memset(bufferCursor, c, n);
        bufferCursor+=n;
    }
    void RawValue(const char* json, size_t length) {
        Reserve(length);
        memcpy(bufferCursor, json,length);
        bufferCursor += length;
    }
    void RawValueUnsafe(const char* json, size_t length) {
        memcpy(bufferCursor, json,length);
        bufferCursor += length;
    }
    
    void RawString(PyObject* string){
        // A REVOIR 
        Py_ssize_t length;
        const char* json = PyUnicode_AsUTF8AndSize(string, &length); // 1er copy si characteres speciaux et qu'il ne l'a jamais transformé en utf_8
        Reserve(length);
        memcpy(bufferCursor, json,length); // 2eme copy 
        bufferCursor += length;
    }
    
    void RawBytes(PyObject* bytes){
        Py_ssize_t length;
        char* json;
        PyBytes_AsStringAndSize(bytes,&json, &length); 
        Reserve(length);
        memcpy(bufferCursor, json,length);
        bufferCursor += length;
    }
    
    void RawBytesToPutInQuotes(PyObject* bytes){
        Py_ssize_t length;
        char* json;
        PyBytes_AsStringAndSize(bytes,&json, &length);
        Reserve(length+2);
        *bufferCursor++ = '\"';
        memcpy(bufferCursor, json,length);
        bufferCursor += length;
        *bufferCursor++ = '\"';
    }

    // Rien à prendre : ici l'encodage va droit dans le tampon de sortie, il
    // n'y a personne à qui le déléguer (voir FdWriteStream).
    bool RawDataToBase64Owned(char*, size_t) { return false; }
    bool RawPyStrPropre(PyObject*, const char*, size_t) { return false; }
    bool CompresseDiffere(PyObject*, char*, size_t, int, int) { return false; }

    void RawDataToBase64(const unsigned char* data, size_t length){
        // encode le base64 directement dans le buffer de sortie,
        // sans chaîne intermédiaire, précédé du préfixe « <n>: » (n = nombre
        // de caractères base64) : le parseur, qui sait par sa pile qu'une
        // charge arrive, saute alors le scan de la chaîne entière — ':' est
        // hors de l'alphabet base64, la détection est sans ambiguïté, et les
        // fichiers sans préfixe restent lus par le scan normal ;
        // en parallèle (découpage fixe sur des multiples de 3 octets, octets
        // identiques au séquentiel) au-delà du seuil, GIL relâché
        size_t nchars = 4 * ((length + 2) / 3);
        char prefix[24];
        int prefix_length = snprintf(prefix, sizeof(prefix), "%zu:", nchars);
        Reserve(nchars + (size_t) prefix_length + 2);
        *bufferCursor++ = '\"';
        memcpy(bufferCursor, prefix, (size_t) prefix_length);
        bufferCursor += prefix_length;
        if (length >= SERIALIZEJSON_B64_PARALLEL_THRESHOLD) {
            char* out = bufferCursor;
            Py_BEGIN_ALLOW_THREADS
            sj_b64_encode_maybe_parallel(data, length, out);
            Py_END_ALLOW_THREADS
            bufferCursor += nchars;
        } else {
            bufferCursor = serializejson_b64_encode(data, length, bufferCursor);
        }
        *bufferCursor++ = '\"';
    }

    void RawBytesToBase64(PyObject* obj){
        Py_buffer view;
        if (PyObject_GetBuffer(obj, &view, PyBUF_CONTIG_RO) != 0)
            return;  // l'erreur Python sera vue en fin d'encodage
        RawDataToBase64((const unsigned char*) view.buf, (size_t) view.len);
        PyBuffer_Release(&view);
    }
    

    void Flush() {
        Resize(GetSize());
    }
    void Clear() { bufferCursor = bufferBegin;}    
    
    char* Push(size_t count = 1) {
        Reserve(count);
        char* ret = bufferCursor;
        bufferCursor += count;
        return ret;
    }
    char* PushUnsafe(size_t count = 1) {
        char* ret = bufferCursor;
        bufferCursor += count;
        return ret;
    }
    void Pop(size_t count) {bufferCursor -= count ;}
    const char* GetBuffer(){return bufferBegin;}
    size_t GetSize() const { return bufferCursor - bufferBegin; }
    // tampon mémoire : la position du prochain octet écrit est sa taille
    size_t Tell() const { return GetSize(); }
    size_t GetCapacity() const { return bufferEnd - bufferBegin; }
    bool Empty() const { return bufferCursor == bufferBegin; }    
    char* Reserve(size_t count) {
        if ( bufferCursor + count > bufferEnd ){
            // croissance par facteur 4 (choix mesuré : moitié moins de
            // reallocs et trois fois moins de recopies qu'un doublement,
            // pour une sur-allocation transitoire rendue au Flush final) ;
            // une grosse réservation (blob base64...) saute directement à
            // la puissance de deux couvrante
            size_t needed = GetSize() + count;
            size_t desiredCapacity = GetCapacity() * 4;
            if (desiredCapacity < needed)
                desiredCapacity = static_cast<size_t>(std::pow(2, std::ceil(std::log((double) needed)/std::log(2))));
            if (desiredCapacity < initialCapacity_)
                desiredCapacity  = initialCapacity_;
            Resize(desiredCapacity);
        }
        return bufferCursor;
    }
    
    // référence EMPRUNTÉE (le buffer reste propriétaire) : pour lire ou
    // convertir sans transfert
    PyObject* getPyBytes(){
        return pybytes;
    }

    // TRANSFÈRE la référence à l'appelant (sortie bytes) : le destructeur
    // ne libérera pas
    PyObject* stealPyBytes(){
        PyObject* transferred = pybytes;
        pybytes = nullptr;
        return transferred;
    }

    // TRANSFÈRE le str ascii compact (strBacking, document resté ascii,
    // APRÈS Flush qui l'a retaillé à la taille exacte) : zéro copie
    PyObject* stealPyStrAscii(){
        PyObject* transferred = pybytes;
        pybytes = nullptr;
        return transferred;
    }

    void Resize(size_t newCapacity) {
        const size_t size = GetSize();  // Backup the current size
        if (strBacking) {
            // le str compact se realloque comme le bytes ; exigences de
            // PyUnicode_Resize tenues par construction (refcount 1, jamais
            // haché ni interné). Sa longueur vaut la CAPACITÉ pendant la
            // construction — le Flush final la ramène à la taille du
            // document (et à 0, CPython substitue le singleton vide : cas
            // du document vide, rien n'y est écrit)
            if (pybytes==nullptr){
                pybytes = PyUnicode_New((Py_ssize_t) newCapacity, 127);
                if (pybytes == nullptr)
                    throw std::bad_alloc();
            } else if (PyUnicode_Resize(&pybytes, (Py_ssize_t) newCapacity) != 0) {
                // contrairement à _PyBytes_Resize, l'objet reste valide :
                // le destructeur le libérera
                throw std::bad_alloc();
            }
            bufferBegin = (char*) PyUnicode_1BYTE_DATA(pybytes);
            bufferCursor = bufferBegin + size;
            bufferEnd = bufferBegin + newCapacity;
            return;
        }
        if (pybytes==nullptr){
            pybytes = PyBytes_FromStringAndSize(nullptr,newCapacity);
            if (pybytes == nullptr)
                // MemoryError déjà levée ; interrompt l'encodage (rattrapé
                // dans do_encode) au lieu de déréférencer NULL plus bas
                throw std::bad_alloc();
        } else {
            if (_PyBytes_Resize(&pybytes, newCapacity) != 0) {
                // _PyBytes_Resize a LIBÉRÉ l'objet et mis pybytes à NULL :
                // remet les curseurs dans un état sûr avant d'interrompre
                bufferBegin = bufferCursor = bufferEnd = nullptr;
                throw std::bad_alloc();
            }
        }
        bufferBegin = PyBytes_AS_STRING(pybytes);
        bufferCursor = bufferBegin + size;
        bufferEnd = bufferBegin + newCapacity;
    }
    static const size_t kDefaultCapacity = 1024; // 10 Mo
    PyObject* pybytes;      // bytes, ou str ascii compact si strBacking
    bool strBacking;
    // vrai si une chaîne potentiellement non-ascii a été écrite : sinon la
    // conversion finale en str peut être une copie brute (_PyUnicode_FromASCII)
    bool maybe_non_ascii = false;
    char* bufferBegin ;
    char* bufferCursor;
    char* bufferEnd;
    size_t initialCapacity_;
};



RAPIDJSON_NAMESPACE_END

#endif // RAPIDJSON_PyBytesBuffer_H_
