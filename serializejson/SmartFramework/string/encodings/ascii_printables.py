import codecs
import encodings

name = __name__.split(".")[-1]

### Codec APIs


class Codec(codecs.Codec):
    def encode(self, input, errors="strict"):
        return codecs.charmap_encode(input, errors, encoding_table)

    def decode(self, input, errors="strict"):
        return codecs.charmap_decode(input, errors, decoding_table)


class IncrementalEncoder(codecs.IncrementalEncoder):
    def encode(self, input, final=False):
        return codecs.charmap_encode(input, self.errors, encoding_table)[0]


class IncrementalDecoder(codecs.IncrementalDecoder):
    def decode(self, input, final=False):
        return codecs.charmap_decode(input, self.errors, decoding_table)[0]


class StreamWriter(Codec, codecs.StreamWriter):
    pass


class StreamReader(Codec, codecs.StreamReader):
    pass


### encodings module API


def getregentry():
    return codecs.CodecInfo(
        name=name,
        encode=Codec().encode,
        decode=Codec().decode,
        incrementalencoder=IncrementalEncoder,
        incrementaldecoder=IncrementalDecoder,
        streamreader=StreamReader,
        streamwriter=StreamWriter,
    )


### Decoding Table

decoding_table = (
    "\ufffe"  #  0x00 -> NULL
    "\ufffe"  #  0x01 -> START OF HEADING
    "\ufffe"  #  0x02 -> START OF TEXT
    "\ufffe"  #  0x03 -> END OF TEXT
    "\ufffe"  #  0x04 -> END OF TRANSMISSION
    "\ufffe"  #  0x05 -> ENQUIRY
    "\ufffe"  #  0x06 -> ACKNOWLEDGE
    "\ufffe"  #  0x07 -> BELL
    "\ufffe"  #  0x08 -> BACKSPACE
    "\t"  #  0x09 -> HORIZONTAL TABULATION
    "\n"  #  0x0A -> LINE FEED
    "\ufffe"  #  0x0B -> VERTICAL TABULATION
    "\ufffe"  #  0x0C -> FORM FEED
    "\r"  #  0x0D -> CARRIAGE RETURN
    "\ufffe"  #  0x0E -> SHIFT OUT
    "\ufffe"  #  0x0F -> SHIFT IN
    "\ufffe"  #  0x10 -> DATA LINK ESCAPE
    "\ufffe"  #  0x11 -> DEVICE CONTROL ONE
    "\ufffe"  #  0x12 -> DEVICE CONTROL TWO
    "\ufffe"  #  0x13 -> DEVICE CONTROL THREE
    "\ufffe"  #  0x14 -> DEVICE CONTROL FOUR
    "\ufffe"  #  0x15 -> NEGATIVE ACKNOWLEDGE
    "\ufffe"  #  0x16 -> SYNCHRONOUS IDLE
    "\ufffe"  #  0x17 -> END OF TRANSMISSION BLOCK
    "\ufffe"  #  0x18 -> CANCEL
    "\ufffe"  #  0x19 -> END OF MEDIUM
    "\ufffe"  #  0x1A -> SUBSTITUTE
    "\ufffe"  #  0x1B -> ESCAPE
    "\ufffe"  #  0x1C -> FILE SEPARATOR
    "\ufffe"  #  0x1D -> GROUP SEPARATOR
    "\ufffe"  #  0x1E -> RECORD SEPARATOR
    "\ufffe"  #  0x1F -> UNIT SEPARATOR
    " "  #  0x20 -> SPACE
    "!"  #  0x21 -> EXCLAMATION MARK
    '"'  #  0x22 -> QUOTATION MARK
    "#"  #  0x23 -> NUMBER SIGN
    "$"  #  0x24 -> DOLLAR SIGN
    "%"  #  0x25 -> PERCENT SIGN
    "&"  #  0x26 -> AMPERSAND
    "'"  #  0x27 -> APOSTROPHE
    "("  #  0x28 -> LEFT PARENTHESIS
    ")"  #  0x29 -> RIGHT PARENTHESIS
    "*"  #  0x2A -> ASTERISK
    "+"  #  0x2B -> PLUS SIGN
    ","  #  0x2C -> COMMA
    "-"  #  0x2D -> HYPHEN-MINUS
    "."  #  0x2E -> FULL STOP
    "/"  #  0x2F -> SOLIDUS
    "0"  #  0x30 -> DIGIT ZERO
    "1"  #  0x31 -> DIGIT ONE
    "2"  #  0x32 -> DIGIT TWO
    "3"  #  0x33 -> DIGIT THREE
    "4"  #  0x34 -> DIGIT FOUR
    "5"  #  0x35 -> DIGIT FIVE
    "6"  #  0x36 -> DIGIT SIX
    "7"  #  0x37 -> DIGIT SEVEN
    "8"  #  0x38 -> DIGIT EIGHT
    "9"  #  0x39 -> DIGIT NINE
    ":"  #  0x3A -> COLON
    ";"  #  0x3B -> SEMICOLON
    "<"  #  0x3C -> LESS-THAN SIGN
    "="  #  0x3D -> EQUALS SIGN
    ">"  #  0x3E -> GREATER-THAN SIGN
    "?"  #  0x3F -> QUESTION MARK
    "@"  #  0x40 -> COMMERCIAL AT
    "A"  #  0x41 -> LATIN CAPITAL LETTER A
    "B"  #  0x42 -> LATIN CAPITAL LETTER B
    "C"  #  0x43 -> LATIN CAPITAL LETTER C
    "D"  #  0x44 -> LATIN CAPITAL LETTER D
    "E"  #  0x45 -> LATIN CAPITAL LETTER E
    "F"  #  0x46 -> LATIN CAPITAL LETTER F
    "G"  #  0x47 -> LATIN CAPITAL LETTER G
    "H"  #  0x48 -> LATIN CAPITAL LETTER H
    "I"  #  0x49 -> LATIN CAPITAL LETTER I
    "J"  #  0x4A -> LATIN CAPITAL LETTER J
    "K"  #  0x4B -> LATIN CAPITAL LETTER K
    "L"  #  0x4C -> LATIN CAPITAL LETTER L
    "M"  #  0x4D -> LATIN CAPITAL LETTER M
    "N"  #  0x4E -> LATIN CAPITAL LETTER N
    "O"  #  0x4F -> LATIN CAPITAL LETTER O
    "P"  #  0x50 -> LATIN CAPITAL LETTER P
    "Q"  #  0x51 -> LATIN CAPITAL LETTER Q
    "R"  #  0x52 -> LATIN CAPITAL LETTER R
    "S"  #  0x53 -> LATIN CAPITAL LETTER S
    "T"  #  0x54 -> LATIN CAPITAL LETTER T
    "U"  #  0x55 -> LATIN CAPITAL LETTER U
    "V"  #  0x56 -> LATIN CAPITAL LETTER V
    "W"  #  0x57 -> LATIN CAPITAL LETTER W
    "X"  #  0x58 -> LATIN CAPITAL LETTER X
    "Y"  #  0x59 -> LATIN CAPITAL LETTER Y
    "Z"  #  0x5A -> LATIN CAPITAL LETTER Z
    "["  #  0x5B -> LEFT SQUARE BRACKET
    "\\"  #  0x5C -> REVERSE SOLIDUS
    "]"  #  0x5D -> RIGHT SQUARE BRACKET
    "^"  #  0x5E -> CIRCUMFLEX ACCENT
    "_"  #  0x5F -> LOW LINE
    "`"  #  0x60 -> GRAVE ACCENT
    "a"  #  0x61 -> LATIN SMALL LETTER A
    "b"  #  0x62 -> LATIN SMALL LETTER B
    "c"  #  0x63 -> LATIN SMALL LETTER C
    "d"  #  0x64 -> LATIN SMALL LETTER D
    "e"  #  0x65 -> LATIN SMALL LETTER E
    "f"  #  0x66 -> LATIN SMALL LETTER F
    "g"  #  0x67 -> LATIN SMALL LETTER G
    "h"  #  0x68 -> LATIN SMALL LETTER H
    "i"  #  0x69 -> LATIN SMALL LETTER I
    "j"  #  0x6A -> LATIN SMALL LETTER J
    "k"  #  0x6B -> LATIN SMALL LETTER K
    "l"  #  0x6C -> LATIN SMALL LETTER L
    "m"  #  0x6D -> LATIN SMALL LETTER M
    "n"  #  0x6E -> LATIN SMALL LETTER N
    "o"  #  0x6F -> LATIN SMALL LETTER O
    "p"  #  0x70 -> LATIN SMALL LETTER P
    "q"  #  0x71 -> LATIN SMALL LETTER Q
    "r"  #  0x72 -> LATIN SMALL LETTER R
    "s"  #  0x73 -> LATIN SMALL LETTER S
    "t"  #  0x74 -> LATIN SMALL LETTER T
    "u"  #  0x75 -> LATIN SMALL LETTER U
    "v"  #  0x76 -> LATIN SMALL LETTER V
    "w"  #  0x77 -> LATIN SMALL LETTER W
    "x"  #  0x78 -> LATIN SMALL LETTER X
    "y"  #  0x79 -> LATIN SMALL LETTER Y
    "z"  #  0x7A -> LATIN SMALL LETTER Z
    "{"  #  0x7B -> LEFT CURLY BRACKET
    "|"  #  0x7C -> VERTICAL LINE
    "}"  #  0x7D -> RIGHT CURLY BRACKET
    "~"  #  0x7E -> TILDE
    "\ufffe"  #  0x7F -> DELETE
    "\ufffe"  #  0x80 -> EURO SIGN
    "\ufffe"  #  0x81 -> UNDEFINED
    "\ufffe"  #  0x82 -> SINGLE LOW-9 QUOTATION MARK
    "\ufffe"  #  0x83 -> LATIN SMALL LETTER F WITH HOOK
    "\ufffe"  #  0x84 -> DOUBLE LOW-9 QUOTATION MARK
    "\ufffe"  #  0x85 -> HORIZONTAL ELLIPSIS
    "\ufffe"  #  0x86 -> DAGGER
    "\ufffe"  #  0x87 -> DOUBLE DAGGER
    "\ufffe"  #  0x88 -> MODIFIER LETTER CIRCUMFLEX ACCENT
    "\ufffe"  #  0x89 -> PER MILLE SIGN
    "\ufffe"  #  0x8A -> LATIN CAPITAL LETTER S WITH CARON
    "\ufffe"  #  0x8B -> SINGLE LEFT-POINTING ANGLE QUOTATION MARK
    "\ufffe"  #  0x8C -> LATIN CAPITAL LIGATURE OE
    "\ufffe"  #  0x8D -> UNDEFINED
    "\ufffe"  #  0x8E -> LATIN CAPITAL LETTER Z WITH CARON
    "\ufffe"  #  0x8F -> UNDEFINED
    "\ufffe"  #  0x90 -> UNDEFINED
    "\ufffe"  #  0x91 -> LEFT SINGLE QUOTATION MARK
    "\ufffe"  #  0x92 -> RIGHT SINGLE QUOTATION MARK
    "\ufffe"  #  0x93 -> LEFT DOUBLE QUOTATION MARK
    "\ufffe"  #  0x94 -> RIGHT DOUBLE QUOTATION MARK
    "\ufffe"  #  0x95 -> BULLET
    "\ufffe"  #  0x96 -> EN DASH
    "\ufffe"  #  0x97 -> EM DASH
    "\ufffe"  #  0x98 -> SMALL TILDE
    "\ufffe"  #  0x99 -> TRADE MARK SIGN
    "\ufffe"  #  0x9A -> LATIN SMALL LETTER S WITH CARON
    "\ufffe"  #  0x9B -> SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
    "\ufffe"  #  0x9C -> LATIN SMALL LIGATURE OE
    "\ufffe"  #  0x9D -> UNDEFINED
    "\ufffe"  #  0x9E -> LATIN SMALL LETTER Z WITH CARON
    "\ufffe"  #  0x9F -> LATIN CAPITAL LETTER Y WITH DIAERESIS
    "\ufffe"  #  0xA0 -> NO-BREAK SPACE
    "\ufffe"  #  0xA1 -> INVERTED EXCLAMATION MARK
    "\ufffe"  #  0xA2 -> CENT SIGN
    "\ufffe"  #  0xA3 -> POUND SIGN
    "\ufffe"  #  0xA4 -> CURRENCY SIGN
    "\ufffe"  #  0xA5 -> YEN SIGN
    "\ufffe"  #  0xA6 -> BROKEN BAR
    "\ufffe"  #  0xA7 -> SECTION SIGN
    "\ufffe"  #  0xA8 -> DIAERESIS
    "\ufffe"  #  0xA9 -> COPYRIGHT SIGN
    "\ufffe"  #  0xAA -> FEMININE ORDINAL INDICATOR
    "\ufffe"  #  0xAB -> LEFT-POINTING DOUBLE ANGLE QUOTATION MARK
    "\ufffe"  #  0xAC -> NOT SIGN
    "\ufffe"  #  0xAD -> SOFT HYPHEN
    "\ufffe"  #  0xAE -> REGISTERED SIGN
    "\ufffe"  #  0xAF -> MACRON
    "\ufffe"  #  0xB0 -> DEGREE SIGN
    "\ufffe"  #  0xB1 -> PLUS-MINUS SIGN
    "\ufffe"  #  0xB2 -> SUPERSCRIPT TWO
    "\ufffe"  #  0xB3 -> SUPERSCRIPT THREE
    "\ufffe"  #  0xB4 -> ACUTE ACCENT
    "\ufffe"  #  0xB5 -> MICRO SIGN
    "\ufffe"  #  0xB6 -> PILCROW SIGN
    "\ufffe"  #  0xB7 -> MIDDLE DOT
    "\ufffe"  #  0xB8 -> CEDILLA
    "\ufffe"  #  0xB9 -> SUPERSCRIPT ONE
    "\ufffe"  #  0xBA -> MASCULINE ORDINAL INDICATOR
    "\ufffe"  #  0xBB -> RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK
    "\ufffe"  #  0xBC -> VULGAR FRACTION ONE QUARTER
    "\ufffe"  #  0xBD -> VULGAR FRACTION ONE HALF
    "\ufffe"  #  0xBE -> VULGAR FRACTION THREE QUARTERS
    "\ufffe"  #  0xBF -> INVERTED QUESTION MARK
    "\ufffe"  #  0xC0 -> LATIN CAPITAL LETTER A WITH GRAVE
    "\ufffe"  #  0xC1 -> LATIN CAPITAL LETTER A WITH ACUTE
    "\ufffe"  #  0xC2 -> LATIN CAPITAL LETTER A WITH CIRCUMFLEX
    "\ufffe"  #  0xC3 -> LATIN CAPITAL LETTER A WITH TILDE
    "\ufffe"  #  0xC4 -> LATIN CAPITAL LETTER A WITH DIAERESIS
    "\ufffe"  #  0xC5 -> LATIN CAPITAL LETTER A WITH RING ABOVE
    "\ufffe"  #  0xC6 -> LATIN CAPITAL LETTER AE
    "\ufffe"  #  0xC7 -> LATIN CAPITAL LETTER C WITH CEDILLA
    "\ufffe"  #  0xC8 -> LATIN CAPITAL LETTER E WITH GRAVE
    "\ufffe"  #  0xC9 -> LATIN CAPITAL LETTER E WITH ACUTE
    "\ufffe"  #  0xCA -> LATIN CAPITAL LETTER E WITH CIRCUMFLEX
    "\ufffe"  #  0xCB -> LATIN CAPITAL LETTER E WITH DIAERESIS
    "\ufffe"  #  0xCC -> LATIN CAPITAL LETTER I WITH GRAVE
    "\ufffe"  #  0xCD -> LATIN CAPITAL LETTER I WITH ACUTE
    "\ufffe"  #  0xCE -> LATIN CAPITAL LETTER I WITH CIRCUMFLEX
    "\ufffe"  #  0xCF -> LATIN CAPITAL LETTER I WITH DIAERESIS
    "\ufffe"  #  0xD0 -> LATIN CAPITAL LETTER ETH
    "\ufffe"  #  0xD1 -> LATIN CAPITAL LETTER N WITH TILDE
    "\ufffe"  #  0xD2 -> LATIN CAPITAL LETTER O WITH GRAVE
    "\ufffe"  #  0xD3 -> LATIN CAPITAL LETTER O WITH ACUTE
    "\ufffe"  #  0xD4 -> LATIN CAPITAL LETTER O WITH CIRCUMFLEX
    "\ufffe"  #  0xD5 -> LATIN CAPITAL LETTER O WITH TILDE
    "\ufffe"  #  0xD6 -> LATIN CAPITAL LETTER O WITH DIAERESIS
    "\ufffe"  #  0xD7 -> MULTIPLICATION SIGN
    "\ufffe"  #  0xD8 -> LATIN CAPITAL LETTER O WITH STROKE
    "\ufffe"  #  0xD9 -> LATIN CAPITAL LETTER U WITH GRAVE
    "\ufffe"  #  0xDA -> LATIN CAPITAL LETTER U WITH ACUTE
    "\ufffe"  #  0xDB -> LATIN CAPITAL LETTER U WITH CIRCUMFLEX
    "\ufffe"  #  0xDC -> LATIN CAPITAL LETTER U WITH DIAERESIS
    "\ufffe"  #  0xDD -> LATIN CAPITAL LETTER Y WITH ACUTE
    "\ufffe"  #  0xDE -> LATIN CAPITAL LETTER THORN
    "\ufffe"  #  0xDF -> LATIN SMALL LETTER SHARP S
    "\ufffe"  #  0xE0 -> LATIN SMALL LETTER A WITH GRAVE
    "\ufffe"  #  0xE1 -> LATIN SMALL LETTER A WITH ACUTE
    "\ufffe"  #  0xE2 -> LATIN SMALL LETTER A WITH CIRCUMFLEX
    "\ufffe"  #  0xE3 -> LATIN SMALL LETTER A WITH TILDE
    "\ufffe"  #  0xE4 -> LATIN SMALL LETTER A WITH DIAERESIS
    "\ufffe"  #  0xE5 -> LATIN SMALL LETTER A WITH RING ABOVE
    "\ufffe"  #  0xE6 -> LATIN SMALL LETTER AE
    "\ufffe"  #  0xE7 -> LATIN SMALL LETTER C WITH CEDILLA
    "\ufffe"  #  0xE8 -> LATIN SMALL LETTER E WITH GRAVE
    "\ufffe"  #  0xE9 -> LATIN SMALL LETTER E WITH ACUTE
    "\ufffe"  #  0xEA -> LATIN SMALL LETTER E WITH CIRCUMFLEX
    "\ufffe"  #  0xEB -> LATIN SMALL LETTER E WITH DIAERESIS
    "\ufffe"  #  0xEC -> LATIN SMALL LETTER I WITH GRAVE
    "\ufffe"  #  0xED -> LATIN SMALL LETTER I WITH ACUTE
    "\ufffe"  #  0xEE -> LATIN SMALL LETTER I WITH CIRCUMFLEX
    "\ufffe"  #  0xEF -> LATIN SMALL LETTER I WITH DIAERESIS
    "\ufffe"  #  0xF0 -> LATIN SMALL LETTER ETH
    "\ufffe"  #  0xF1 -> LATIN SMALL LETTER N WITH TILDE
    "\ufffe"  #  0xF2 -> LATIN SMALL LETTER O WITH GRAVE
    "\ufffe"  #  0xF3 -> LATIN SMALL LETTER O WITH ACUTE
    "\ufffe"  #  0xF4 -> LATIN SMALL LETTER O WITH CIRCUMFLEX
    "\ufffe"  #  0xF5 -> LATIN SMALL LETTER O WITH TILDE
    "\ufffe"  #  0xF6 -> LATIN SMALL LETTER O WITH DIAERESIS
    "\ufffe"  #  0xF7 -> DIVISION SIGN
    "\ufffe"  #  0xF8 -> LATIN SMALL LETTER O WITH STROKE
    "\ufffe"  #  0xF9 -> LATIN SMALL LETTER U WITH GRAVE
    "\ufffe"  #  0xFA -> LATIN SMALL LETTER U WITH ACUTE
    "\ufffe"  #  0xFB -> LATIN SMALL LETTER U WITH CIRCUMFLEX
    "\ufffe"  #  0xFC -> LATIN SMALL LETTER U WITH DIAERESIS
    "\ufffe"  #  0xFD -> LATIN SMALL LETTER Y WITH ACUTE
    "\ufffe"  #  0xFE -> LATIN SMALL LETTER THORN
    "\ufffe"  #  0xFF -> LATIN SMALL LETTER Y WITH DIAERESIS
)

### Encoding table
encoding_table = codecs.charmap_build(decoding_table)
encodings._cache[name] = getregentry()
