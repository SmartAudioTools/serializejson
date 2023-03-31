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

#ifndef RAPIDJSON_WRITER_H_
#define RAPIDJSON_WRITER_H_

#include "stream.h"
#include "internal/clzll.h"
#include "internal/meta.h"
#include "internal/stack.h"
#include "internal/strfunc.h"
#include "internal/dtoa.h"
#include "internal/itoa.h"
//#include "stringbuffer.h"
#include <new>      // placement new

#if defined(RAPIDJSON_SIMD) && defined(_MSC_VER)
#include <intrin.h>
#pragma intrinsic(_BitScanForward)
#endif
#ifdef RAPIDJSON_SSE42
#include <nmmintrin.h>
#elif defined(RAPIDJSON_SSE2)
#include <emmintrin.h>
#elif defined(RAPIDJSON_NEON)
#include <arm_neon.h>
#endif

#ifdef __clang__
RAPIDJSON_DIAG_PUSH
RAPIDJSON_DIAG_OFF(padded)
RAPIDJSON_DIAG_OFF(unreachable-code)
RAPIDJSON_DIAG_OFF(c++98-compat)
#elif defined(_MSC_VER)
RAPIDJSON_DIAG_PUSH
RAPIDJSON_DIAG_OFF(4127) // conditional expression is constant
#endif

RAPIDJSON_NAMESPACE_BEGIN

///////////////////////////////////////////////////////////////////////////////
// WriteFlag

/*! \def RAPIDJSON_WRITE_DEFAULT_FLAGS 
    \ingroup RAPIDJSON_CONFIG
    \brief User-defined kWriteDefaultFlags definition.

    User can define this as any \c WriteFlag combinations.
*/
#ifndef RAPIDJSON_WRITE_DEFAULT_FLAGS
#define RAPIDJSON_WRITE_DEFAULT_FLAGS kWriteNoFlags
#endif

//! Combination of writeFlags
enum WriteFlag {
    kWriteNoFlags = 0,              //!< No flags are set.
    kWriteValidateEncodingFlag = 1, //!< Validate encoding of JSON strings.
    kWriteNanAndInfFlag = 2,        //!< Allow writing of Infinity, -Infinity and NaN.
    kWriteDefaultFlags = RAPIDJSON_WRITE_DEFAULT_FLAGS  //!< Default write flags. Can be customized by defining RAPIDJSON_WRITE_DEFAULT_FLAGS
};

//! JSON writer
/*! Writer implements the concept Handler.
    It generates JSON text by events to an output os.

    User may programmatically calls the functions of a writer to generate JSON text.

    On the other side, a writer can also be passed to objects that generates events, 

    for example Reader::Parse() and Document::Accept().

    \tparam OutputStream Type of output stream.
    \tparam SourceEncoding Encoding of source string.
    \tparam TargetEncoding Encoding of output stream.
    \tparam StackAllocator Type of allocator for allocating memory of stack.
    \note implements Handler concept
*/
template<typename OutputStream, typename SourceEncoding = UTF8<>, typename TargetEncoding = UTF8<>, typename StackAllocator = CrtAllocator, unsigned writeFlags = kWriteDefaultFlags>
class Writer {
public:
    typedef typename SourceEncoding::Ch Ch;

    static const int kDefaultMaxDecimalPlaces = 324;

    //! Constructor
    /*! \param os Output stream.
        \param stackAllocator User supplied allocator. If it is null, it will create a private one.
        \param levelDepth Initial capacity of stack.
    */
    explicit
    Writer(OutputStream& os, StackAllocator* stackAllocator = 0, size_t levelDepth = kDefaultLevelDepth) : 
        os_(&os), level_stack_(stackAllocator, levelDepth * sizeof(Level)), maxDecimalPlaces_(kDefaultMaxDecimalPlaces), hasRoot_(false) {}

    explicit
    Writer(StackAllocator* allocator = 0, size_t levelDepth = kDefaultLevelDepth) :
        os_(0), level_stack_(allocator, levelDepth * sizeof(Level)), maxDecimalPlaces_(kDefaultMaxDecimalPlaces), hasRoot_(false) {}

#if RAPIDJSON_HAS_CXX11_RVALUE_REFS
    Writer(Writer&& rhs) :
        os_(rhs.os_), level_stack_(std::move(rhs.level_stack_)), maxDecimalPlaces_(rhs.maxDecimalPlaces_), hasRoot_(rhs.hasRoot_) {
        rhs.os_ = 0;
    }
#endif

    //! Reset the writer with a new stream.
    /*!
        This function reset the writer with a new stream and default settings,
        in order to make a Writer object reusable for output multiple JSONs.

        \param os New output stream.
        \code
        Writer<OutputStream> writer(os1);
        writer.StartObject();
        // ...
        writer.EndObject();

        writer.Reset(os2);
        writer.StartObject();
        // ...
        writer.EndObject();
        \endcode
    */
    void Reset(OutputStream& os) {
        os_ = &os;
        hasRoot_ = false;
        level_stack_.Clear();
    }

    //! Checks whether the output is a complete JSON.
    /*!
        A complete JSON has a complete root object or array.
    */
    bool IsComplete() const {
        return hasRoot_ && level_stack_.Empty();
    }

    int GetMaxDecimalPlaces() const {
        return maxDecimalPlaces_;
    }

    //! Sets the maximum number of decimal places for double output.
    /*!
        This setting truncates the output with specified number of decimal places.

        For example, 

        \code
        writer.SetMaxDecimalPlaces(3);
        writer.StartArray();
        writer.Double(0.12345);                 // "0.123"
        writer.Double(0.0001);                  // "0.0"
        writer.Double(1.234567890123456e30);    // "1.234567890123456e30" (do not truncate significand for positive exponent)
        writer.Double(1.23e-4);                 // "0.0"                  (do truncate significand for negative exponent)
        writer.EndArray();
        \endcode

        The default setting does not truncate any decimal places. You can restore to this setting by calling
        \code
        writer.SetMaxDecimalPlaces(Writer::kDefaultMaxDecimalPlaces);
        \endcode
    */
    void SetMaxDecimalPlaces(int maxDecimalPlaces) {
        maxDecimalPlaces_ = maxDecimalPlaces;
    }

    /*!@name Implementation of Handler
        \see Handler
    */
    //@{

    bool Null(){ 
        Prefix();   
        os_->RawValue("null",4);
        return true; 
    }
    
    bool Bool(bool b){
        Prefix(); 
        if (b) {
            os_->RawValue("true",4);
        }
        else {
            os_->RawValue("false",5);
        }
        return true;
    }
        
    bool Int(int i){
        Prefix(); 
        os_->bufferCursor = internal::i32toa(i, os_->Reserve(11));
        return true;
    }    

    bool Uint(unsigned u){
        Prefix(); 
        os_->bufferCursor = internal::u32toa(u, os_->Reserve(10));
        return true;
    }
    
    bool Int64(int64_t i64)     { 
        Prefix(); 
        os_->bufferCursor = internal::i64toa(i64, os_->Reserve(21));
        return true;
    }
    
    bool Uint64(uint64_t u64)   { 
        Prefix(); 
        os_->bufferCursor = internal::u64toa(u64, os_->Reserve(20));
        return true;    
    }
    
    bool Double(double d)       { 
        Prefix(); 
        if (internal::Double(d).IsNanOrInf()) {
            if (!(writeFlags & kWriteNanAndInfFlag))
                return false;
            if (internal::Double(d).IsNan()) {
                os_->RawValue("NaN",3);
                return true;
            }
            if (internal::Double(d).Sign()) {
                os_->RawValue("-Infinity",9);
            }
            else {
                os_->RawValue("Infinity",8);
            }
            return true;
        }
        os_->bufferCursor = internal::dtoa(d,  os_->Reserve(25), maxDecimalPlaces_);
        return true;    
    }
	
    bool String(const Ch* str, SizeType length) {
        Prefix();
		os_->Put('"');
        Escape(str, length);
		os_->Put('"');
		return true ;
    }

    bool StartObject() {
        Prefix();
        new (level_stack_.template Push<Level>()) Level(false);
        return WriteStartObject();
    }

    bool Key(const Ch* str, SizeType length) { return String(str, length); }

    bool EndObject() {
        level_stack_.template Pop<Level>(1);
        return WriteEndObject();
    }

    bool StartArray() {
        Prefix();
        new (level_stack_.template Push<Level>()) Level(true);
        return WriteStartArray();
    }

    bool EndArray() {
        level_stack_.template Pop<Level>(1);
        return WriteEndArray();
    }
    //@}

    /*! @name Convenience extensions */
    //@{

    //! Simpler but slower overload.
    bool String(const Ch* const& str) { return String(str, internal::StrLen(str)); }
    bool Key(const Ch* const& str) { return Key(str, internal::StrLen(str)); }
    
    //@}

    //! Write a raw JSON value.
    /*!
        For user to write a stringified JSON as a value.

        \param json A well-formed JSON value. It should not contain null character within [0, length - 1] range.
        \param length Length of the json.
        \param type Type of the root of json.
    */
    bool RawValue(const Ch* json, size_t length) {
        Prefix();
        os_->RawValue(json,length);
        return true;
    }
    
    bool RawString_(PyObject* object) {
        Prefix();
        os_->RawString(((RawString*) object)->value);
        return true;
    }
       
    bool RawBytes_(PyObject* object) {
        Prefix();
        os_->RawBytes(((RawBytes*) object)->value);
        return true;
    }
    
    bool RawBytesToPutInQuotes_(PyObject* object) {
        Prefix();
        os_->RawBytesToPutInQuotes(((RawBytesToPutInQuotes*) object)-> value);
        return true;
    }

    //! Flush the output stream.
    /*!
        Allows the user to flush the output stream immediately.
     */
    void Flush() {
        os_->Flush();
    }

    static const size_t kDefaultLevelDepth = 32;

protected:
    //! Information for each nested level
    struct Level {
        Level(bool inArray_) : valueCount(0), inArray(inArray_) {}
        size_t valueCount;  //!< number of values in this level
        bool inArray;       //!< true if in array, otherwise in object
    };

    bool Escape(const Ch* str, SizeType length)  {  
		// check for escape need 
		size_t copy_length = length;
		char c;
		const char* stop = str + length;
		//std::cout << "length "<<length;
		const char* cursor = str;
		c = *cursor++;
		while ((cursor <=  stop) && (c != '\\') && (c != '"') && (c != '\t') && (c != '\n') && (c != '\r')) // super long !!!!
			c = *cursor++;
			
		copy_length = cursor-str-1;
		//std::cout << "copy_length "<<copy_length;
		if (copy_length>0)
			os_->RawValue(str,copy_length);
		if (copy_length < length){
			//std::cout << "escape " << c;
			os_->Reserve(2);
			*(os_->bufferCursor)++ = '\\';
			if ((c == '\\')||(c == '"'))
				*(os_->bufferCursor)++ = c;
			else if (c == '\t')
				*(os_->bufferCursor)++ = 't';
			else if (c == '\r')
				*(os_->bufferCursor)++ = 'r';
			else if (c == '\n')
				*(os_->bufferCursor)++ = 'n';
			Escape(str+copy_length+1 , length-(copy_length+1));
		}
        return true;
		
		/*
			
			//{ // bouffe  70  msec avec juste std::cout<<'!' ou break,  et 100 msec avec juste bufferCursor++;	
				break;
				//std::cout<<'!';
				//bufferCursor++;	
				/*
				// faudrait checker qu'on est pas dans du utf-8
				if (c == '\t'){
					//if ((bufferCursor - memcpy_src ) > 0 )
					//	memcpy(memcpy_dst, memcpy_src,bufferCursor - memcpy_src); 
					//memcpy_src = cursor + 1 ; 
					//memcpy_dst = bufferCursor + 2;
					*bufferCursor++ = '\\';
					*bufferCursor++ = 't';
					
				}
				
				else if (c == '\n'){
					//if ((bufferCursor - memcpy_src ) > 0 )
					//	memcpy(memcpy_dst, memcpy_src,bufferCursor - memcpy_src); 
					//memcpy_src = cursor + 1 ; 
					//memcpy_dst = bufferCursor + 2;
					*bufferCursor++ = '\\';
					*bufferCursor++ = 'n';
				}
				else if (c == '\r'){
					//if ((bufferCursor - memcpy_src ) > 0 )
					//	memcpy(memcpy_dst, memcpy_src,bufferCursor - memcpy_src);  
					//memcpy_src = cursor + 1 ; 
					//memcpy_dst = bufferCursor + 2;
					*bufferCursor++ = '\\';
					*bufferCursor++ = 'r';
				}
				else if (c == '\f'){
					//if ((bufferCursor - memcpy_src ) > 0 )
					//	memcpy(memcpy_dst, memcpy_src,bufferCursor - memcpy_src);  
					//memcpy_src = cursor + 1 ; 
					//memcpy_dst = bufferCursor + 2;
					*bufferCursor++ = '\\';
					*bufferCursor++ = 'f';
				}
				else {
					//*bufferCursor++ = c;
					//bufferCursor++;
					//
                    //*bufferCursor++ = '0';
                    //*bufferCursor++ = '0';
                    //*bufferCursor++ = hexDigits[static_cast<unsigned char>(c) >> 4];
                    //*bufferCursor++ = hexDigits[static_cast<unsigned char>(c) & 0xF];
                
			}
		
			else if (c == '\\'){
				//if ((bufferCursor - memcpy_src ) > 0 )
				//	memcpy(memcpy_dst, memcpy_src,bufferCursor - memcpy_src); 
				//memcpy_src = cursor + 1 ; 
				//memcpy_dst = bufferCursor + 2;
				*bufferCursor++ = '\\';
				*bufferCursor++ = '\\';
			}

			else if (c == '"'){
				//if ((bufferCursor - memcpy_src ) > 0 )
				//	memcpy(memcpy_dst, memcpy_src,bufferCursor - memcpy_src); 
				//memcpy_src = cursor + 1 ; 
				//memcpy_dst = bufferCursor + 2;
				*bufferCursor++ = '\\';
				*bufferCursor++ = '"';
			}
			else 
				//bufferCursor++;
				*bufferCursor++ = c;
		
        }	
		//if ((bufferCursor - memcpy_src ) > 0 )
		//	memcpy(memcpy_dst, memcpy_src,bufferCursor - memcpy_src); 		
		//memcpy(bufferCursor, str,length); 	
		bufferCursor+=length;
        *bufferCursor++ = '\"';
		os_-> bufferCursor = bufferCursor;
		*/
    }


    bool WriteStartObject() { os_->Put('{'); return true; }
    bool WriteEndObject()   { os_->Put('}'); return true; }
    bool WriteStartArray()  { os_->Put('['); return true; }
    bool WriteEndArray()    { os_->Put(']'); return true; }

    void Prefix() {
        //(void)type;
        if (RAPIDJSON_LIKELY(level_stack_.GetSize() != 0)) { // this value is not at root
            Level* level = level_stack_.template Top<Level>();
            if (level->valueCount > 0) {
                if (level->inArray) 
                    os_->Put(','); // add comma if it is not the first element in array
                else  // in object
                    os_->Put((level->valueCount % 2 == 0) ? ',' : ':');
            }
            //if (!level->inArray && level->valueCount % 2 == 0)
            //    RAPIDJSON_ASSERT(type == kStringType);  // if it's in object, then even number should be a name
            level->valueCount++;
        }
        else {
            RAPIDJSON_ASSERT(!hasRoot_);    // Should only has one and only one root.
            hasRoot_ = true;
        }
    }

    // Flush the value if it is the top level one.
    /*bool EndValue(bool ret) {
        if (RAPIDJSON_UNLIKELY(level_stack_.Empty()))   // end of json text
            Flush();
        return ret;
    }*/

    OutputStream* os_;
    internal::Stack<StackAllocator> level_stack_;
    int maxDecimalPlaces_;
    bool hasRoot_;
	Ch hexDigits[16] = { '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F' };

private:
    // Prohibit copy constructor & assignment operator.
    Writer(const Writer&);
    Writer& operator=(const Writer&);
};

RAPIDJSON_NAMESPACE_END

#if defined(_MSC_VER) || defined(__clang__)
RAPIDJSON_DIAG_POP
#endif

#endif // RAPIDJSON_RAPIDJSON_H_
