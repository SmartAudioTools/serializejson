// fork serializejson : graphie la plus courte d'un double, identique octet à
// octet à float.__repr__ de CPython, sans passer par PyOS_double_to_string
// (malloc + moteur David Gay + format + free, ~110 ns/valeur).
//
// Moteur de chiffres : Ryu (Ulf Adams, PLDI 2018) — le plus court
// correctement arrondi, sans échec possible (Grisu3, qui devait renoncer
// sur ~0,5 % des valeurs, a été retiré après validation bit-exacte de Ryu
// sur 25 M de valeurs contre repr()). Tables 128 bits générées en
// arithmétique exacte par gen_ryu_table.py.
//
// La mise en forme reproduit format_float_short de CPython (pystrtod.c)
// pour le code 'r' + Py_DTSF_ADD_DOT_0 : notation fixe pour un point
// décimal dans ]-4, 16], scientifique sinon, exposant signé sur au moins
// deux chiffres, ".0" ajouté aux valeurs entières en notation fixe.

#ifndef SERIALIZEJSON_DTOA_REPR_H_
#define SERIALIZEJSON_DTOA_REPR_H_

#include "internal/itoa.h"
#include "ryu_d2d_table.h"
#include <string.h>
#if defined(_MSC_VER) && defined(_M_X64)
#include <intrin.h>
#endif

namespace sjdtoa {

// --- Ryu (Ulf Adams, PLDI 2018) : chiffres décimaux les plus courts
// correctement arrondis, sans échec possible — remplace Grisu3 comme
// moteur de chiffres (tables 128 bits générées par gen_ryu_table.py,
// validation bit-exacte contre float.__repr__ avant adoption)

inline uint32_t RyuPow5Bits(int32_t e) {
    return (uint32_t) (((e * 1217359) >> 19) + 1);
}

inline uint32_t RyuPow5Factor(uint64_t value) {
    uint32_t count = 0;
    for (;;) {
        if (value % 5 != 0)
            return count;
        value /= 5;
        count++;
    }
}

inline bool RyuMultipleOfPowerOf5(uint64_t value, uint32_t p) {
    return RyuPow5Factor(value) >= p;
}

inline bool RyuMultipleOfPowerOf2(uint64_t value, uint32_t p) {
    return (value & ((UINT64_C(1) << p) - 1)) == 0;
}

inline uint64_t RyuMulShift64(uint64_t m, const uint64_t* mul, int32_t j) {
#if defined(_MSC_VER) && defined(_M_X64)
    uint64_t high0;
    uint64_t high2;
    _umul128(m, mul[0], &high0);
    uint64_t low2 = _umul128(m, mul[1], &high2);
    uint64_t sum_low = high0 + low2;
    uint64_t sum_high = high2 + (sum_low < high0);
    return __shiftright128(sum_low, sum_high, (unsigned char) (j - 64));
#else
    unsigned __int128 b0 = (unsigned __int128) m * mul[0];
    unsigned __int128 b2 = (unsigned __int128) m * mul[1];
    return (uint64_t) (((b0 >> 64) + b2) >> (j - 64));
#endif
}

// chiffres (sans zéros de tête) et exposant : value = chiffres × 10^K
inline void RyuDigits(double value, char* digits, int* len, int* K) {
    uint64_t bits;
    memcpy(&bits, &value, 8);
    const uint64_t ieeeMantissa = bits & ((UINT64_C(1) << 52) - 1);
    const uint32_t ieeeExponent = (uint32_t) ((bits >> 52) & 0x7FF);
    int32_t e2;
    uint64_t m2;
    if (ieeeExponent == 0) {
        e2 = 1 - 1023 - 52 - 2;
        m2 = ieeeMantissa;
    } else {
        e2 = (int32_t) ieeeExponent - 1023 - 52 - 2;
        m2 = (UINT64_C(1) << 52) | ieeeMantissa;
    }
    const bool acceptBounds = (m2 & 1) == 0;
    const uint64_t mv = 4 * m2;
    const uint32_t mmShift = (ieeeMantissa != 0 || ieeeExponent <= 1) ? 1 : 0;
    uint64_t vr;
    uint64_t vp;
    uint64_t vm;
    int32_t e10;
    bool vmIsTrailingZeros = false;
    bool vrIsTrailingZeros = false;
    if (e2 >= 0) {
        const uint32_t q =
            (uint32_t) ((e2 * 78913) >> 18) - (e2 > 3);   // log10(2^e2)
        e10 = (int32_t) q;
        const int32_t k = SJ_DOUBLE_POW5_INV_BITCOUNT
            + (int32_t) RyuPow5Bits((int32_t) q) - 1;
        const int32_t i = -e2 + (int32_t) q + k;
        vr = RyuMulShift64(mv, SJ_DOUBLE_POW5_INV_SPLIT[q], i);
        vp = RyuMulShift64(mv + 2, SJ_DOUBLE_POW5_INV_SPLIT[q], i);
        vm = RyuMulShift64(mv - 1 - mmShift, SJ_DOUBLE_POW5_INV_SPLIT[q], i);
        if (q <= 21) {
            if (mv % 5 == 0)
                vrIsTrailingZeros = RyuMultipleOfPowerOf5(mv, q);
            else if (acceptBounds)
                vmIsTrailingZeros =
                    RyuMultipleOfPowerOf5(mv - 1 - mmShift, q);
            else
                vp -= RyuMultipleOfPowerOf5(mv + 2, q);
        }
    } else {
        const uint32_t q =
            (uint32_t) (((-e2) * 732923) >> 20) - (-e2 > 1);  // log10(5^-e2)
        e10 = (int32_t) q + e2;
        const int32_t i = -e2 - (int32_t) q;
        const int32_t k = (int32_t) RyuPow5Bits(i) - SJ_DOUBLE_POW5_BITCOUNT;
        const int32_t j = (int32_t) q - k;
        vr = RyuMulShift64(mv, SJ_DOUBLE_POW5_SPLIT[i], j);
        vp = RyuMulShift64(mv + 2, SJ_DOUBLE_POW5_SPLIT[i], j);
        vm = RyuMulShift64(mv - 1 - mmShift, SJ_DOUBLE_POW5_SPLIT[i], j);
        if (q <= 1) {
            vrIsTrailingZeros = true;
            if (acceptBounds)
                vmIsTrailingZeros = mmShift == 1;
            else
                --vp;
        } else if (q < 63) {
            vrIsTrailingZeros = RyuMultipleOfPowerOf2(mv, q - 1);
        }
    }
    int32_t removed = 0;
    uint8_t lastRemovedDigit = 0;
    uint64_t output;
    if (vmIsTrailingZeros || vrIsTrailingZeros) {
        for (;;) {
            const uint64_t vpDiv10 = vp / 10;
            const uint64_t vmDiv10 = vm / 10;
            if (vpDiv10 <= vmDiv10)
                break;
            const uint32_t vmMod10 = (uint32_t) (vm - 10 * vmDiv10);
            const uint64_t vrDiv10 = vr / 10;
            const uint32_t vrMod10 = (uint32_t) (vr - 10 * vrDiv10);
            vmIsTrailingZeros &= vmMod10 == 0;
            vrIsTrailingZeros &= lastRemovedDigit == 0;
            lastRemovedDigit = (uint8_t) vrMod10;
            vr = vrDiv10;
            vp = vpDiv10;
            vm = vmDiv10;
            ++removed;
        }
        if (vmIsTrailingZeros) {
            for (;;) {
                const uint64_t vmDiv10 = vm / 10;
                const uint32_t vmMod10 = (uint32_t) (vm - 10 * vmDiv10);
                if (vmMod10 != 0)
                    break;
                const uint64_t vpDiv10 = vp / 10;
                const uint64_t vrDiv10 = vr / 10;
                const uint32_t vrMod10 = (uint32_t) (vr - 10 * vrDiv10);
                vrIsTrailingZeros &= lastRemovedDigit == 0;
                lastRemovedDigit = (uint8_t) vrMod10;
                vr = vrDiv10;
                vp = vpDiv10;
                vm = vmDiv10;
                ++removed;
            }
        }
        if (vrIsTrailingZeros && lastRemovedDigit == 5 && vr % 2 == 0)
            lastRemovedDigit = 4;   // arrondi pair
        output = vr
            + ((vr == vm && (!acceptBounds || !vmIsTrailingZeros))
               || lastRemovedDigit >= 5);
    } else {
        bool roundUp = false;
        const uint64_t vpDiv100 = vp / 100;
        const uint64_t vmDiv100 = vm / 100;
        if (vpDiv100 > vmDiv100) {
            const uint64_t vrDiv100 = vr / 100;
            const uint32_t vrMod100 = (uint32_t) (vr - 100 * vrDiv100);
            roundUp = vrMod100 >= 50;
            vr = vrDiv100;
            vp = vpDiv100;
            vm = vmDiv100;
            removed += 2;
        }
        for (;;) {
            const uint64_t vpDiv10 = vp / 10;
            const uint64_t vmDiv10 = vm / 10;
            if (vpDiv10 <= vmDiv10)
                break;
            const uint64_t vrDiv10 = vr / 10;
            const uint32_t vrMod10 = (uint32_t) (vr - 10 * vrDiv10);
            roundUp = vrMod10 >= 5;
            vr = vrDiv10;
            vp = vpDiv10;
            vm = vmDiv10;
            ++removed;
        }
        output = vr + (vr == vm || roundUp);
    }
    char* end = rapidjson::internal::u64toa(output, digits);
    *len = (int) (end - digits);
    *K = e10 + removed;
}

// écrit dans out (>= 40 octets) la graphie repr() d'un double FINI ;
// rend la longueur écrite (Ryu est total : jamais d'échec)
inline int ReprDouble(double value, char* out) {
    char* p = out;
    if (value < 0 || (value == 0.0 && 1.0 / value < 0)) {  // signe, -0.0 compris
        *p++ = '-';
        value = -value;
    }
    if (value == 0.0) {
        *p++ = '0'; *p++ = '.'; *p++ = '0';
        return static_cast<int>(p - out);
    }
    char digits[24];
    int len, K = 0;
    RyuDigits(value, digits, &len, &K);
    // filet : des zéros de queue éventuels sont repliés dans l'exposant
    // (la valeur est inchangée, le point décimal aussi)
    while (len > 1 && digits[len - 1] == '0') {
        len--;
        K++;
    }
    const int decpt = len + K;  // value = 0.chiffres × 10^decpt
    if (decpt < -3 || decpt > 16) {
        // scientifique : d1[.d2..dn]e±EE (exposant sur 2 chiffres minimum)
        *p++ = digits[0];
        if (len > 1) {
            *p++ = '.';
            memcpy(p, digits + 1, static_cast<size_t>(len - 1));
            p += len - 1;
        }
        *p++ = 'e';
        int e = decpt - 1;
        if (e < 0) { *p++ = '-'; e = -e; }
        else       { *p++ = '+'; }
        if (e >= 100) {
            *p++ = static_cast<char>('0' + e / 100);
            e %= 100;
        }
        *p++ = static_cast<char>('0' + e / 10);
        *p++ = static_cast<char>('0' + e % 10);
    } else if (decpt <= 0) {
        *p++ = '0'; *p++ = '.';
        for (int i = 0; i < -decpt; i++)
            *p++ = '0';
        memcpy(p, digits, static_cast<size_t>(len));
        p += len;
    } else if (decpt >= len) {
        memcpy(p, digits, static_cast<size_t>(len));
        p += len;
        for (int i = len; i < decpt; i++)
            *p++ = '0';
        *p++ = '.'; *p++ = '0';
    } else {
        memcpy(p, digits, static_cast<size_t>(decpt));
        p += decpt;
        *p++ = '.';
        memcpy(p, digits + decpt, static_cast<size_t>(len - decpt));
        p += len - decpt;
    }
    return static_cast<int>(p - out);
}

}  // namespace sjdtoa

#endif  // SERIALIZEJSON_DTOA_REPR_H_
