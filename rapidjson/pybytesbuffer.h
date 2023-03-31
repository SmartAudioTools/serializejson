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
    
    PyBytesBuffer(size_t capacity = kDefaultCapacity){        
        initialCapacity_ = capacity;
        bufferBegin = 0;
        bufferCursor = 0;
        bufferEnd = 0;
        pybytes = NULL;
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
    size_t GetCapacity() const { return bufferEnd - bufferBegin; }
    bool Empty() const { return bufferCursor == bufferBegin; }    
    char* Reserve(size_t count) {
        if ( bufferCursor + count > bufferEnd ){
            size_t desiredCapacity = static_cast<size_t>(std::pow(2, std::ceil(std::log((bufferCursor - bufferBegin) + count)/std::log(2))));
            if (desiredCapacity < initialCapacity_)
                desiredCapacity  = initialCapacity_;
            Resize(desiredCapacity);
        }
        return bufferCursor;
    }
    
    PyObject* getPyBytes(){
        return pybytes;
    }
    
    int Resize(size_t newCapacity) {
        int success;
        const size_t size = GetSize();  // Backup the current size
        if (pybytes==NULL){
            pybytes = PyBytes_FromStringAndSize(NULL,newCapacity);
            success = (pybytes!=NULL);
        } else { 
            success= _PyBytes_Resize(&pybytes, newCapacity);
        }
        bufferBegin = PyBytes_AS_STRING(pybytes);
        bufferCursor = bufferBegin + size;
        bufferEnd = bufferBegin + newCapacity;
        return success;
    }
    static const size_t kDefaultCapacity = 1024; // 10 Mo 
    PyObject* pybytes;
    char* bufferBegin ;
    char* bufferCursor;
    char* bufferEnd;
    size_t initialCapacity_;
};



RAPIDJSON_NAMESPACE_END

#endif // RAPIDJSON_PyBytesBuffer_H_
