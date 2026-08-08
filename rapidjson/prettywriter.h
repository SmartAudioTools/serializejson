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

#ifndef RAPIDJSON_PRETTYWRITER_H_
#define RAPIDJSON_PRETTYWRITER_H_
#include "serializejson.h"
#include "writer.h"

#ifdef __GNUC__
RAPIDJSON_DIAG_PUSH
RAPIDJSON_DIAG_OFF(effc++)
#endif

#if defined(__clang__)
RAPIDJSON_DIAG_PUSH
RAPIDJSON_DIAG_OFF(c++98-compat)
#endif

RAPIDJSON_NAMESPACE_BEGIN

//! Combination of PrettyWriter format flags.
/*! \see PrettyWriter::SetFormatOptions
 */
enum PrettyFormatOptions {
    kFormatDefault = 0,         //!< Default pretty formatting.
    kFormatSingleLineArray = 1  //!< Format arrays on a single line.
};

//! Writer with indentation and spacing.
/*!
    \tparam OutputStream Type of output os.
    \tparam SourceEncoding Encoding of source string.
    \tparam TargetEncoding Encoding of output stream.
    \tparam StackAllocator Type of allocator for allocating memory of stack.
*/



template<typename OutputStream, typename SourceEncoding = UTF8<>, typename TargetEncoding = UTF8<>, typename StackAllocator = CrtAllocator, unsigned writeFlags = kWriteDefaultFlags>
class PrettyWriter : public Writer<OutputStream, SourceEncoding, TargetEncoding, StackAllocator, writeFlags> {
public:
    typedef Writer<OutputStream, SourceEncoding, TargetEncoding, StackAllocator, writeFlags> Base;
    typedef typename Base::Ch Ch;

    //! Constructor
    /*! \param os Output stream.
        \param allocator User supplied allocator. If it is null, it will create a private one.
        \param levelDepth Initial capacity of stack.
    */
    explicit PrettyWriter(OutputStream& os, StackAllocator* allocator = 0, size_t levelDepth = Base::kDefaultLevelDepth) :
        Base(os, allocator, levelDepth), indentChar_(' '), indentCharCount_(4), formatOptions_(kFormatDefault),
        indentBase_(0), compactDepth_(0), compactPending_(false) {}


    explicit PrettyWriter(StackAllocator* allocator = 0, size_t levelDepth = Base::kDefaultLevelDepth) :
        Base(allocator, levelDepth), indentChar_(' '), indentCharCount_(4), formatOptions_(kFormatDefault),
        indentBase_(0), compactDepth_(0), compactPending_(false) {}

    //! Sous-arbre compact (pour rapidjson.SingleLine) : tout ce qui est écrit
    //! entre PushCompact() et PopCompact() l'est au format compact du Writer
    //! de base (virgules et deux-points sans espace, ni retour à la ligne, ni
    //! indentation). La bascule ne prend effet qu'APRÈS le préfixe du premier
    //! jeton du sous-arbre, qui appartient encore à la mise en page du parent
    //! (": " après la clé, ou virgule et indentation dans une liste).
    void PushCompact() {
        if (compactDepth_ == 0)
            compactPending_ = true;
        else
            compactDepth_++;
    }
    void PopCompact() {
        if (compactPending_)
            compactPending_ = false;  // sous-arbre sans aucun jeton (sécurité)
        else
            compactDepth_--;
    }
    // vrai si un sous-arbre compact est en cours (ou demandé) : une bascule
    // imbriquée serait alors redondante — et déséquilibrerait le compteur si
    // deux demandes étaient posées avant le premier jeton
    bool InCompact() const {
        return compactDepth_ > 0 || compactPending_;
    }
    void MarkMaybeNonAscii() { Base::os_->maybe_non_ascii = true; }

#if RAPIDJSON_HAS_CXX11_RVALUE_REFS
    PrettyWriter(PrettyWriter&& rhs) :
        Base(std::forward<PrettyWriter>(rhs)), indentChar_(rhs.indentChar_), indentCharCount_(rhs.indentCharCount_), formatOptions_(rhs.formatOptions_),
        indentBase_(rhs.indentBase_), compactDepth_(rhs.compactDepth_), compactPending_(rhs.compactPending_) {}
#endif

    //! Set custom indentation.
    /*! \param indentChar       Character for indentation. Must be whitespace character (' ', '\\t', '\\n', '\\r').
        \param indentCharCount  Number of indent characters for each indentation level.
        \note The default indentation is 4 spaces.
    */
    PrettyWriter& SetIndent(Ch indentChar, unsigned indentCharCount) {
        RAPIDJSON_ASSERT(indentChar == ' ' || indentChar == '\t' || indentChar == '\n' || indentChar == '\r');
        indentChar_ = indentChar;
        indentCharCount_ = indentCharCount;
        return *this;
    }

    //! Niveaux d'indentation AJOUTÉS à tous ceux du document, `append` n'en
    //! ayant qu'un usage : l'élément ajouté est un maillon d'une liste déjà
    //! ouverte, et le fichier doit rester identique, octet pour octet, à la
    //! sérialisation directe de la liste complète. Le décalage se faisait
    //! jusqu'ici côté python, par un remplacement des sauts de ligne dans
    //! chaque morceau écrit — ce qui interdisait l'écriture droit dans le
    //! descripteur, donc le thread d'écriture ET l'index relevé au vol.
    PrettyWriter& SetIndentBase(unsigned levels) {
        indentBase_ = levels;
        return *this;
    }

    //! Set pretty writer formatting options.
    /*! \param options Formatting options.
    */
    PrettyWriter& SetFormatOptions(PrettyFormatOptions options) {
        formatOptions_ = options;
        return *this;
    }

    /*! @name Implementation of Handler
        \see Handler
    */
    //@{

    bool Null(){ 
        PrettyPrefix();   
        Base::os_->RawValue("null",4);
        return true; 
    }
    
    bool Bool(bool b){
        PrettyPrefix(); 
        if (b) {
            Base::os_->RawValue("true",4);
        }
        else {
            Base::os_->RawValue("false",5);
        }
        return true; 
        }
        
    bool Int(int i){
        PrettyPrefix(); 
        Base::os_->bufferCursor = internal::i32toa(i, Base::os_->Reserve(11));
        return true;
    }    

    bool Uint(unsigned u){
        PrettyPrefix(); 
        Base::os_->bufferCursor = internal::u32toa(u, Base::os_->Reserve(10));
        return true;
    }
    
    bool Int64(int64_t i64)     { 
        PrettyPrefix(); 
        Base::os_->bufferCursor = internal::i64toa(i64, Base::os_->Reserve(21));
        return true;
    }
    
    bool Uint64(uint64_t u64)   { 
        PrettyPrefix(); 
        Base::os_->bufferCursor = internal::u64toa(u64, Base::os_->Reserve(20));
        return true;    
    }
    
    bool Double(double d)       { 
        PrettyPrefix(); 
        if (internal::Double(d).IsNanOrInf()) {
            if (!(writeFlags & kWriteNanAndInfFlag))
                return false;
            if (internal::Double(d).IsNan()) {
                Base::os_->RawValue("NaN",3);
                return true;
            }
            if (internal::Double(d).Sign()) {
                Base::os_->RawValue("-Infinity",9);
            }
            else {
                Base::os_->RawValue("Infinity",8);
            }
            return true;
        }
        Base::os_->bufferCursor = internal::dtoa(d,  Base::os_->Reserve(25), Base::maxDecimalPlaces_);
        return true;    
    }

    bool String(const Ch* str, SizeType length) {
        PrettyPrefix();
        Base::os_->Put('"');
        Base::Escape(str, length);
        Base::os_->Put('"');
		return true ;
    }

    bool StartObject() {
        PrettyPrefix();
        new (Base::level_stack_.template Push<typename Base::Level>()) typename Base::Level(false);
        return Base::WriteStartObject();
    }

    bool Key(const Ch* str, SizeType length, bool copy = false) { return String(str, length); }

#if RAPIDJSON_HAS_STDSTRING
    bool Key(const std::basic_string<Ch>& str) {
        return Key(str.data(), SizeType(str.size()));
    }
#endif
    
    bool EndObject() {
        bool empty = Base::level_stack_.template Pop<typename Base::Level>(1)->valueCount == 0;
        if (!empty && compactDepth_ == 0) {
            Base::os_->Put('\n');
            WriteIndent();
        }
        return Base::WriteEndObject();
    }

    bool StartArray() {
        PrettyPrefix();
        new (Base::level_stack_.template Push<typename Base::Level>()) typename Base::Level(true);
        return Base::WriteStartArray();
    }

    bool EndArray() {
        bool empty = Base::level_stack_.template Pop<typename Base::Level>(1)->valueCount == 0;
        if (!empty && compactDepth_ == 0 && !(formatOptions_ & kFormatSingleLineArray)) {
            Base::os_->Put('\n');
            WriteIndent();
        }
        return Base::WriteEndArray();
    }

    //@}

    /*! @name Convenience extensions */
    //@{

    //! Simpler but slower overload.
    bool String(const Ch* str) { return String(str, internal::StrLen(str)); }
    bool Key(const Ch* str) { return Key(str, internal::StrLen(str)); }

    //@}

    //! Write a raw JSON value.
    /*!
        For user to write a stringified JSON as a value.

        \param json A well-formed JSON value. It should not contain null character within [0, length - 1] range.
        \param length Length of the json.
        \param type Type of the root of json.
        \note When using PrettyWriter::RawValue(), the result json may not be indented correctly.
    */
    bool RawValue(const Ch* json, size_t length) {
        PrettyPrefix();
        Base::os_->RawValue(json,length);
        return true;
    }
    
    bool RawString_(PyObject* object) {
        PrettyPrefix();
        Base::os_->RawString(((RawString*) object)->value);
        return true;
    }
       
    bool RawBytes_(PyObject* object) {
        PrettyPrefix();
        Base::os_->RawBytes(((RawBytes*) object)->value);
        return true;
    }
    
    bool RawBytesToPutInQuotes_(PyObject* object) {
        PrettyPrefix();
        Base::os_->RawBytesToPutInQuotes(((RawBytesToPutInQuotes*) object)-> value);
        return true;
    }

    bool RawBytesToBase64_(PyObject* object) {
        PrettyPrefix();
        Base::os_->RawBytesToBase64(((RawBytesToBase64*) object)-> value);
        return true;
    }

    bool BloscToBase64_(PyObject* object) {
        PrettyPrefix();
        BloscToBase64* blosc = (BloscToBase64*) object;
        // voir Writer::BloscToBase64_ : le flux prend la trame, ou l'encode ici
        if (Base::os_->RawDataToBase64Owned(blosc->data, (size_t) blosc->size))
            blosc->data = nullptr;
        else
            Base::os_->RawDataToBase64((const unsigned char*) blosc->data,
                                       (size_t) blosc->size);
        return true;
    }


    // enveloppe complète d'un petit bytes/bytearray en UN passage, forme
    // indentée (la liste [base64,"b64"] reste compacte : single_line_init) —
    // mêmes octets que la suite StartObject/Key/.../EndObject
    //! tête d'enveloppe (voir Writer::EnvelopeHead) : forme indentée, ou
    //! compacte à l'identique du Writer dans un sous-arbre PushCompact
    bool EnvelopeHead(const char* cls, size_t cls_length,
                      const char* key, size_t key_length) {
        PrettyPrefix();
        bool compact = compactDepth_ > 0;
        new (Base::level_stack_.template Push<typename Base::Level>())
            typename Base::Level(false);
        Base::level_stack_.template Top<typename Base::Level>()->valueCount
            = 3;
        Base::OuvreIndex();   // l'accolade est écrite ici, pas par WriteStartObject
        Base::AttendIndex(key, key_length);   // et la clé nommera la charge
        Base::os_->Put('{');
        if (!compact) {
            Base::os_->Put('\n');
            WriteIndent();
        }
        Base::WriteRawSmall("\"__class__\":");
        if (!compact)
            Base::os_->Put(' ');
        Base::os_->Put('"');
        for (size_t i = 0; i < cls_length; i++)
            Base::os_->Put(cls[i]);
        Base::os_->Put('"');
        Base::os_->Put(',');
        if (!compact) {
            Base::os_->Put('\n');
            WriteIndent();
        }
        Base::os_->Put('"');
        for (size_t i = 0; i < key_length; i++)
            Base::os_->Put(key[i]);
        Base::os_->Put('"');
        return true;
    }

    bool BytesEnvelope(const unsigned char* data, size_t length,
                       bool printable, bool is_bytearray) {
        PrettyPrefix();
        const size_t debut = Base::PositionIndex();
        if (compactDepth_ > 0) {
            // sous-arbre compact : mêmes octets que le Writer
            Base::WriteRawSmall(is_bytearray
                                    ? "{\"__class__\":\"bytearray\",\"__init__\":"
                                    : "{\"__class__\":\"bytes\",\"__new__\":");
            const size_t debutCharge = Base::PositionIndex();
            Base::WriteBytesPayload(data, length, printable);
            const size_t finCharge = Base::PositionIndex();
            Base::os_->Put('}');
            Base::IndexEnveloppe(debut, debutCharge, finCharge, printable, is_bytearray);
            return true;
        }
        size_t profondeur =
            Base::level_stack_.GetSize() / sizeof(typename Base::Level);
        Base::os_->Put('{');
        Base::os_->Put('\n');
        Base::os_->PutN(static_cast<typename OutputStream::Ch>(indentChar_),
                        (profondeur + 1) * indentCharCount_);
        Base::WriteRawSmall(is_bytearray
                                ? "\"__class__\": \"bytearray\",\n"
                                : "\"__class__\": \"bytes\",\n");
        Base::os_->PutN(static_cast<typename OutputStream::Ch>(indentChar_),
                        (profondeur + 1) * indentCharCount_);
        Base::WriteRawSmall(is_bytearray ? "\"__init__\": "
                                         : "\"__new__\": ");
        const size_t debutCharge = Base::PositionIndex();
        Base::WriteBytesPayload(data, length, printable);
        const size_t finCharge = Base::PositionIndex();
        Base::os_->Put('\n');
        Base::os_->PutN(static_cast<typename OutputStream::Ch>(indentChar_),
                        profondeur * indentCharCount_);
        Base::os_->Put('}');
        Base::IndexEnveloppe(debut, debutCharge, finCharge, printable, is_bytearray);
        return true;
    }



protected:
    void PrettyPrefix() {
        if (compactDepth_ > 0) {
            // style du Writer compact : séparateurs seuls, sans espace,
            // retour à la ligne ni indentation
            if (Base::level_stack_.GetSize() != 0) {
                typename Base::Level* level = Base::level_stack_.template Top<typename Base::Level>();
                if (level->valueCount > 0) {
                    if (level->inArray)
                        Base::os_->Put(',');
                    else
                        Base::os_->Put((level->valueCount % 2 == 0) ? ',' : ':');
                }
                level->valueCount++;
            }
            else {
                RAPIDJSON_ASSERT(!Base::hasRoot_);
                Base::hasRoot_ = true;
            }
            return;
        }
        //void)type;
        if (Base::level_stack_.GetSize() != 0) { // this value is not at root
            typename Base::Level* level = Base::level_stack_.template Top<typename Base::Level>();

            if (level->inArray) {
                if (level->valueCount > 0) {
                    Base::os_->Put(','); // add comma if it is not the first element in array
                    if (formatOptions_ & kFormatSingleLineArray)
                        Base::os_->Put(' ');
                }

                if (!(formatOptions_ & kFormatSingleLineArray)) {
                    Base::os_->Put('\n');
                    WriteIndent();
                }
            }
            else {  // in object
                if (level->valueCount > 0) {
                    if (level->valueCount % 2 == 0) {
                        Base::os_->Put(',');
                        Base::os_->Put('\n');
                    }
                    else {
                        Base::os_->Put(':');
                        Base::os_->Put(' ');
                    }
                }
                else
                    Base::os_->Put('\n');

                if (level->valueCount % 2 == 0)
                    WriteIndent();
            }
            //if (!level->inArray && level->valueCount % 2 == 0)
            //   RAPIDJSON_ASSERT(type == kStringType);  // if it's in object, then even number should be a name
            level->valueCount++;
        }
        else {
            RAPIDJSON_ASSERT(!Base::hasRoot_);  // Should only has one and only one root.
            Base::hasRoot_ = true;
        }
        // le passage en compact demandé par PushCompact() prend effet
        // maintenant : après le préfixe du premier jeton du sous-arbre
        if (compactPending_) {
            compactPending_ = false;
            compactDepth_ = 1;
        }
    }

    void WriteIndent()  {
        size_t count = (Base::level_stack_.GetSize() / sizeof(typename Base::Level) + indentBase_) * indentCharCount_;
        // appel du PutN MEMBRE du flux (memset) : le PutN generique de
        // stream.h boucle un Put par caractere, mesure ~20%% du temps
        // d'encodage des conteneurs indentes
        Base::os_->PutN(static_cast<typename OutputStream::Ch>(indentChar_), count);
    }

    Ch indentChar_;
    unsigned indentCharCount_;
    PrettyFormatOptions formatOptions_;
    unsigned indentBase_;
    unsigned compactDepth_;
    bool compactPending_;

private:
    // Prohibit copy constructor & assignment operator.
    PrettyWriter(const PrettyWriter&);
    PrettyWriter& operator=(const PrettyWriter&);
};

RAPIDJSON_NAMESPACE_END

#if defined(__clang__)
RAPIDJSON_DIAG_POP
#endif

#ifdef __GNUC__
RAPIDJSON_DIAG_POP
#endif

#endif // RAPIDJSON_RAPIDJSON_H_
