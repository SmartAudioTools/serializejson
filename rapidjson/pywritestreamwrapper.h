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


#ifndef RAPIDJSON_PyWriteStreamWrapper_H_
#define RAPIDJSON_PyWriteStreamWrapper_H_

#include "stream.h"
#include <Python.h>
#include <algorithm>   
#include <string>
#include <iostream>

RAPIDJSON_NAMESPACE_BEGIN
class PyWriteStreamWrapper {
public:
    typedef char Ch;    

    PyWriteStreamWrapper(PyObject* stream_, size_t chunkSize_){
        currentBytes = nullptr;
        bufferBegin = bufferCursor = bufferEnd = nullptr;
        stream = stream_;
        Py_INCREF(stream);
        chunkSize = chunkSize_ ;
        write_name = PyUnicode_InternFromString("write");
    }

    void Put(Ch c) {
        Reserve(1);
        *bufferCursor++ = c;
    }
    
    void PutUnsafe(Ch c) {
        *bufferCursor++ = c;
    }
    
    void PutN(Ch c, size_t n) {
        if (n > 0) {
            Reserve(n);    
            memset(bufferCursor, c, n);
            bufferCursor += n;
        }
    }
    
    void Flush(){
        if (currentBytes == nullptr)
            return;
        size_t currentSize = bufferCursor - bufferBegin;
        if (currentSize){
            _PyBytes_Resize(&currentBytes, currentSize);
            sendBytesEtLache(currentBytes, currentSize);
        } else {
            Py_DECREF(currentBytes);   // rien dedans : rien à envoyer, mais
        }                              // le prochain Reserve en crée un autre
        currentBytes = nullptr;
        // la tranche est partie : le curseur ne doit plus rien mesurer, sans
        // quoi Tell() recompterait ce qui vient d'être envoyé
        bufferBegin = bufferCursor = bufferEnd = nullptr;
    }
    
    char* Reserve(size_t size) {
        if (currentBytes == nullptr){
            if(size < chunkSize)
                size = chunkSize;
            createBytes(size);
        } else if (bufferCursor + size > bufferEnd) {
            Flush();
            if(size < chunkSize)
                size = chunkSize;
            createBytes(size);
        }
        return bufferCursor;
    }
        
    void RawValue(const char* json , size_t size) {
		if (size < chunkSize){
			Reserve(size);
			memcpy(bufferCursor,json,size);
			bufferCursor += size;
		}
		else {
			Flush();
			sendBytesEtLache(PyMemoryView_FromMemory((char*)json,size,PyBUF_READ), size);
		}
    }
    
    void RawString(PyObject* string){
        Flush();
        PyObject* utf8 = PyUnicode_AsUTF8String(string);
        sendBytesEtLache(utf8, utf8 == nullptr ? 0 : (size_t) PyBytes_GET_SIZE(utf8));
    }
    
    void RawBytes(PyObject* bytes){
        Flush();
        sendBytes(bytes, (size_t) PyBytes_GET_SIZE(bytes));
    }
    
    void RawBytesToPutInQuotes(PyObject* bytes){
        Put('\"');
        Flush();
        sendBytes(bytes, (size_t) PyBytes_GET_SIZE(bytes));
        Put('\"');
    }

    // Position du prochain octet écrit, comptée DEPUIS LE DÉBUT DU DOCUMENT :
    // ce qui est déjà parti dans le flux python, plus ce qui attend en tranche.
    // Ce n'est une position de FICHIER que si le flux en est un, ouvert à zéro
    // et sans transformation — d'où l'index réservé au flux à descripteur.
    size_t Tell() const {
        return envoyes + (size_t)(bufferCursor - bufferBegin);
    }

    // Rien à prendre : sans thread d'écriture, il n'y a personne à qui
    // déléguer l'encodage (voir FdWriteStream).
    bool RawDataToBase64Owned(char*, size_t) { return false; }

    void RawDataToBase64(const unsigned char* src, size_t remaining){
        // encode le base64 par morceaux dans les chunks du flux,
        // sans chaîne intermédiaire (coupures sur des multiples de 3 octets
        // source pour que le padding ne tombe qu'à la toute fin)
        Put('\"');
        while (remaining) {
            Reserve(4);
            size_t triples = (size_t)(bufferEnd - bufferCursor) / 4;
            size_t take = triples * 3;
            if (take >= remaining)
                take = remaining;      // dernier morceau, avec padding
            bufferCursor = serializejson_b64_encode(src, take, bufferCursor);
            src += take;
            remaining -= take;
        }
        Put('\"');
    }

    void RawBytesToBase64(PyObject* obj){
        Py_buffer view;
        if (PyObject_GetBuffer(obj, &view, PyBUF_CONTIG_RO) != 0)
            return;  // l'erreur Python sera vue en fin d'encodage
        RawDataToBase64((const unsigned char*) view.buf, (size_t) view.len);
        PyBuffer_Release(&view);
    }
    
    ~PyWriteStreamWrapper() {
        Py_CLEAR(stream);
        if (currentBytes != nullptr)
            Py_DECREF(currentBytes);
    }
    
    
    Ch* bufferCursor;
    PyObject* currentBytes;
    bool maybe_non_ascii = false;  // sans objet pour un flux (pas de conversion)

    

private:

    void createBytes(size_t size){
        currentBytes = PyBytes_FromStringAndSize(nullptr,size);
        bufferBegin = bufferCursor = PyBytes_AS_STRING(currentBytes);
        bufferEnd = bufferBegin + size;
    }

    // Envoi d'un objet EMPRUNTÉ : celui qui l'a passé le garde (RawBytes).
    void sendBytes(PyObject* bytes, size_t taille){
        envoyes += taille;
        // ce que rend write() — None le plus souvent — est un objet neuf :
        // sans ce relâchement, il en fuit un par tranche écrite
        PyObject* rendu = PyObject_CallMethodObjArgs(stream, write_name, bytes, nullptr);
        Py_XDECREF(rendu);
    }

    // Envoi d'un objet dont on est PROPRIÉTAIRE : tranche fraîchement
    // découpée, mémoire vue, chaîne encodée en utf-8. Sans ce relâchement,
    // c'est tout le document qui reste en mémoire après un dump (mesuré :
    // 14 Mo retenus par dump de 14 Mo dans un BytesIO).
    void sendBytesEtLache(PyObject* bytes, size_t taille){
        if (bytes == nullptr)
            return;            // l'erreur python sera vue en fin d'encodage
        sendBytes(bytes, taille);
        Py_DECREF(bytes);
    }

    PyObject* write_name;
    PyObject* stream;
    Ch* bufferBegin;
    Ch* bufferEnd;
    size_t chunkSize;
    size_t envoyes = 0;      // octets déjà remis au flux python
};


RAPIDJSON_NAMESPACE_END

#endif // RAPIDJSON_PyBytesBuffer_H_
