// fork serializejson : graphie la plus courte d'un double, identique octet à
// octet à float.__repr__ de CPython, sans passer par PyOS_double_to_string
// (mesuré ~110 ns/valeur : malloc + moteur David Gay + format + free).
//
// Algorithme : Grisu3 — le DigitGen de rapidjson (internal/dtoa.h, Grisu2)
// complété par la détection d'incertitude de la bibliothèque double-conversion
// (fast-dtoa.cc, licence BSD) : quand l'arrondi ne peut pas être GARANTI
// optimal, on retourne faux et l'appelant retombe sur PyOS_double_to_string
// (~0,5 % des valeurs). Quand il réussit, le résultat est la représentation
// décimale la plus courte correctement arrondie — celle de repr().
//
// La mise en forme reproduit format_float_short de CPython (pystrtod.c) pour
// le code 'r' + Py_DTSF_ADD_DOT_0 : notation fixe pour un point décimal dans
// ]-4, 16], scientifique sinon, exposant signé sur au moins deux chiffres,
// ".0" ajouté aux valeurs entières en notation fixe.

#ifndef SERIALIZEJSON_DTOA_REPR_H_
#define SERIALIZEJSON_DTOA_REPR_H_

#include "internal/diyfp.h"
#include <string.h>

namespace sjdtoa {

using rapidjson::internal::DiyFp;
using rapidjson::internal::GetCachedPower;

// ajuste le dernier chiffre vers w et vérifie que l'arrondi est certain :
// faux si un autre chiffre aurait pu être aussi proche (double-conversion)
inline bool RoundWeed(char* last_digit, uint64_t distance_too_high_w,
                      uint64_t unsafe_interval, uint64_t rest,
                      uint64_t ten_kappa, uint64_t unit) {
    const uint64_t small_distance = distance_too_high_w - unit;
    const uint64_t big_distance = distance_too_high_w + unit;
    while (rest < small_distance &&
           unsafe_interval - rest >= ten_kappa &&
           (rest + ten_kappa < small_distance ||
            small_distance - rest >= rest + ten_kappa - small_distance)) {
        (*last_digit)--;
        rest += ten_kappa;
    }
    if (rest < big_distance &&
        unsafe_interval - rest >= ten_kappa &&
        (rest + ten_kappa < big_distance ||
         big_distance - rest > rest + ten_kappa - big_distance))
        return false;
    return (2 * unit <= rest) && (rest <= unsafe_interval - 4 * unit);
}

inline int CountDecimalDigit32(uint32_t n) {
    if (n < 10) return 1;
    if (n < 100) return 2;
    if (n < 1000) return 3;
    if (n < 10000) return 4;
    if (n < 100000) return 5;
    if (n < 1000000) return 6;
    if (n < 10000000) return 7;
    if (n < 100000000) return 8;
    return 9;
}

// génère les chiffres depuis la borne haute élargie (too_high), comme
// double-conversion — et non depuis la borne rétrécie comme le Grisu2 de
// rapidjson, qui ne peut pas détecter ses échecs
inline bool DigitGen(const DiyFp& W, const DiyFp& too_high,
                     uint64_t unsafe_interval_f,
                     char* buffer, int* len, int* K) {
    static const uint64_t kPow10[] = {
        1U, 10U, 100U, 1000U, 10000U, 100000U, 1000000U, 10000000U,
        100000000U, 1000000000U };
    uint64_t unit = 1;
    const DiyFp one(uint64_t(1) << -too_high.e, too_high.e);
    const uint64_t wp_w = (too_high - W).f;
    uint32_t p1 = static_cast<uint32_t>(too_high.f >> -one.e);
    uint64_t p2 = too_high.f & (one.f - 1);
    int kappa = CountDecimalDigit32(p1);
    *len = 0;

    while (kappa > 0) {
        const uint32_t divisor = static_cast<uint32_t>(kPow10[kappa - 1]);
        const uint32_t d = p1 / divisor;
        p1 %= divisor;
        if (d || *len)
            buffer[(*len)++] = static_cast<char>('0' + d);
        kappa--;
        const uint64_t rest = (static_cast<uint64_t>(p1) << -one.e) + p2;
        if (rest < unsafe_interval_f) {
            *K += kappa;
            return RoundWeed(&buffer[*len - 1], wp_w, unsafe_interval_f, rest,
                             kPow10[kappa] << -one.e, unit);
        }
    }

    for (;;) {
        p2 *= 10;
        unit *= 10;
        unsafe_interval_f *= 10;
        const char d = static_cast<char>(p2 >> -one.e);
        if (d || *len)
            buffer[(*len)++] = static_cast<char>('0' + d);
        p2 &= one.f - 1;
        kappa--;
        if (p2 < unsafe_interval_f) {
            *K += kappa;
            // wp_w × 10^n : dépasserait 64 bits au-delà de quelques tours ;
            // unit a suivi exactement le même facteur, on multiplie donc la
            // distance déjà mise à l'échelle
            return RoundWeed(&buffer[*len - 1], wp_w * unit,
                             unsafe_interval_f, p2, one.f, unit);
        }
    }
}

// vrai si buffer/len/decimal_exponent contiennent la représentation la plus
// courte correctement arrondie (value = chiffres × 10^decimal_exponent)
inline bool Grisu3(double value, char* buffer, int* len, int* K) {
    const DiyFp v(value);
    DiyFp w_m, w_p;
    v.NormalizedBoundaries(&w_m, &w_p);
    const DiyFp c_mk = GetCachedPower(w_p.e, K);
    const DiyFp W = v.Normalize() * c_mk;
    DiyFp Wp = w_p * c_mk;
    DiyFp Wm = w_m * c_mk;
    // borne élargie d'une unité d'erreur de chaque côté (l'inverse du
    // rétrécissement de Grisu2) : l'intervalle « non sûr » dont RoundWeed
    // vérifie les marges
    Wm.f -= 1;
    Wp.f += 1;
    return DigitGen(W, Wp, Wp.f - Wm.f, buffer, len, K);
}

// écrit dans out (>= 40 octets) la graphie repr() d'un double FINI :
// longueur écrite, ou -1 si Grisu3 ne peut pas garantir l'optimalité
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
    if (!Grisu3(value, digits, &len, &K))
        return -1;
    // Grisu peut laisser des zéros de queue après l'ajustement ; repr()
    // n'en produit jamais (la valeur est inchangée, le point décimal aussi)
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
