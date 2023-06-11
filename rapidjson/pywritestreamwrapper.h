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
        if (currentBytes != nullptr){
            size_t currentSize = bufferCursor - bufferBegin;
            if (currentSize){
                _PyBytes_Resize(&currentBytes, currentSize);
                sendBytes(currentBytes);
                //Py_DECREF(currentBytes);
                currentBytes = nullptr;
            }
        }
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
			sendBytes(PyMemoryView_FromMemory((char*)json,size,PyBUF_READ));
		}
    }
    
    void RawString(PyObject* string){
        Flush();
        sendBytes(PyUnicode_AsUTF8String(string));
    }
    
    void RawBytes(PyObject* bytes){
        Flush();
        sendBytes(bytes);
    }
    
    void RawBytesToPutInQuotes(PyObject* bytes){
        Put('\"');
        Flush();
        sendBytes(bytes);
        Put('\"');
    }
    
    ~PyWriteStreamWrapper() {
        Py_CLEAR(stream);
        if (currentBytes != nullptr)
            Py_DECREF(currentBytes);
    }
    
    
    Ch* bufferCursor;
    PyObject* currentBytes;

    

private:

    void createBytes(size_t size){
        currentBytes = PyBytes_FromStringAndSize(nullptr,size);
        bufferBegin = bufferCursor = PyBytes_AS_STRING(currentBytes);
        bufferEnd = bufferBegin + size;
    }

    void sendBytes(PyObject* bytes){
        PyObject_CallMethodObjArgs(stream, write_name, bytes, nullptr); // copy inside ? 
        //Py_DECREF(bytes);
    }

    PyObject* write_name;
    PyObject* stream;
    Ch* bufferBegin;
    Ch* bufferEnd;
    size_t chunkSize;
};


RAPIDJSON_NAMESPACE_END

#endif // RAPIDJSON_PyBytesBuffer_H_
