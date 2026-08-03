// Eisel-Lemire : conversion décimal -> double correctement arrondie par un
// produit 128 bits avec une puissance de 5 précalculée (Daniel Lemire,
// « Number Parsing at a Gigabyte per Second », 2021). Rend false au moindre
// doute (l'appelant garde son chemin exact : StrtodDiyFp puis BigInteger) —
// jamais un résultat approché. Validé contre float() de Python sur des
// dizaines de millions de valeurs, mi-chemins exacts compris (voir
// tests/test_eisel_lemire.py et le validateur de campagne).
#ifndef SJ_EISEL_LEMIRE_H_
#define SJ_EISEL_LEMIRE_H_

#include <stdint.h>
#include <string.h>
#include "eisel_lemire_table.h"

#if defined(_MSC_VER) && !defined(__clang__)
#include <intrin.h>
#endif

static inline void sj_el_mul128(uint64_t a, uint64_t b,
                                uint64_t* hi, uint64_t* lo)
{
#if defined(__SIZEOF_INT128__)
    unsigned __int128 p = (unsigned __int128) a * b;
    *hi = (uint64_t)(p >> 64);
    *lo = (uint64_t) p;
#else
    *lo = _umul128(a, b, hi);
#endif
}

static inline int sj_el_clz64(uint64_t x)
{
#if defined(_MSC_VER) && !defined(__clang__)
    unsigned long index;
    _BitScanReverse64(&index, x);
    return 63 - (int) index;
#else
    return __builtin_clzll(x);
#endif
}

// w : mantisse décimale (les 19 premiers chiffres significatifs, w != 0) ;
// q : exposant tel que la valeur vaut w * 10^q ;
// rend true et écrit le double correctement arrondi, ou false (doute).
static inline bool sj_eisel_lemire(uint64_t w, int q, double* out)
{
    if (q < SJ_EL_SMALLEST_POWER || q > SJ_EL_LARGEST_POWER)
        return false;               // hors table : zéro ou infini, l'appelant
                                    // a déjà tranché ces cas

    int lz = sj_el_clz64(w);
    w <<= lz;

    const uint64_t* power = sj_el_powers[q - SJ_EL_SMALLEST_POWER];
    uint64_t upper, lower;
    sj_el_mul128(w, power[0], &upper, &lower);

    // les 9 bits de garde : si tous levés, le produit tronqué pourrait
    // cacher une retenue — on affine avec les 64 bits suivants de la
    // puissance, et si l'ambiguïté persiste, on renonce
    if ((upper & UINT64_C(0x1FF)) == UINT64_C(0x1FF)) {
        uint64_t upper2, lower2;
        sj_el_mul128(w, power[1], &upper2, &lower2);
        lower += upper2;
        if (lower < upper2)
            upper++;
        if ((upper & UINT64_C(0x1FF)) == UINT64_C(0x1FF)
            && lower + w < lower)
            return false;
    }

    // mantisse de 55 bits (54 utiles + bit d'arrondi), exposant binaire
    uint64_t upperbit = upper >> 63;
    uint64_t mantissa = upper >> (upperbit + 9);
    // floor(log2(10^q)) approché par (217706*q)>>16, exact sur la plage
    int power2 = (int) ((217706 * (int64_t) q) >> 16) + 63 - lz
        + (int) upperbit + 1024 + 62 - 63;

    if (power2 <= 0) {
        // sous-normal ou zéro
        if (power2 + 54 < 0)
            return false;           // arrondi vers zéro : cas rare, chemin sûr
        mantissa >>= -power2 + 1;
        mantissa += (mantissa & 1);
        mantissa >>= 1;
        uint64_t bits = mantissa;   // exposant 0 (sous-normal), sauf si
        if (mantissa >= (UINT64_C(1) << 52))
            bits = (UINT64_C(1) << 52) | (mantissa & ((UINT64_C(1) << 52) - 1));
        double d;
        memcpy(&d, &bits, 8);
        *out = d;
        return true;
    }

    // arrondi au plus proche, cas d'égalité exclu : si la traîne est
    // exactement .5 (mantisse en ...1, reste nul possible), la règle
    // pair-impair peut basculer — on écarte le motif ambigu connu
    if (lower == 0 && (upper & UINT64_C(0x1FF)) == 0
        && (mantissa & 3) == 1)
        return false;

    mantissa += mantissa & 1;       // arrondi au plus proche (demi -> haut,
    mantissa >>= 1;                 // le cas d'égalité vrai a été écarté)

    if (mantissa >= (UINT64_C(2) << 52)) {
        mantissa = UINT64_C(1) << 52;
        power2++;
    }
    mantissa &= ~(UINT64_C(1) << 52);
    if (power2 >= 0x7FF)
        return false;               // infini : l'appelant a sa borne exacte

    uint64_t bits = mantissa | ((uint64_t) power2 << 52);
    double d;
    memcpy(&d, &bits, 8);
    *out = d;
    return true;
}

#endif  // SJ_EISEL_LEMIRE_H_
