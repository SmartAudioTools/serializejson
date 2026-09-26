// Chiffrement age v1 (https://age-encryption.org/v1) en C, par libsodium LIÉE
// dans le module (rapidjson/libsodium_statique.py, et pour WebAssembly
// scripts/construit_wasm.sh) : une seule chaîne cryptographique partout, sans
// dépendance à l'exécution ni divergence possible entre plateformes.
//   _scrypt, _chacha20poly1305 : primitives de l'en-tête, le reste de
//   l'en-tête (HKDF, MAC) restant en python ;
//   _age_payload : la charge utile, segments de 64 Kio chiffrés
//   ChaCha20-Poly1305, nonce = compteur 11 octets gros-boutiste + drapeau
//   « dernier segment ». Les segments sont INDÉPENDANTS : répartis sur
//   plusieurs fils, GIL rendu.

#ifndef SJ_CRYPTO_H_
#define SJ_CRYPTO_H_

#include <Python.h>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <thread>
#include <vector>

namespace sjcrypto {

extern "C" {
int sodium_init(void);
int crypto_pwhash_scryptsalsa208sha256_ll(const uint8_t*, size_t,
                                          const uint8_t*, size_t, uint64_t,
                                          uint32_t, uint32_t, uint8_t*, size_t);
int crypto_aead_chacha20poly1305_ietf_encrypt_detached(
    unsigned char*, unsigned char*, unsigned long long*, const unsigned char*,
    unsigned long long, const unsigned char*, unsigned long long,
    const unsigned char*, const unsigned char*, const unsigned char*);
int crypto_aead_chacha20poly1305_ietf_decrypt_detached(
    unsigned char*, unsigned char*, const unsigned char*, unsigned long long,
    const unsigned char*, const unsigned char*, unsigned long long,
    const unsigned char*, const unsigned char*);
}

static const size_t SEG = 64 * 1024;
static const size_t TAG = 16;
// par fil : en deçà, le lancement d'un fil coûte plus que le travail (mesuré
// dans le bac à sable : 1 Mio sur un fil 0,40 ms, sur deux 0,50)
static const size_t SEG_PAR_FIL = 8;

// Segments [k0, k1) d'une charge de `clair` octets en clair et `nseg`
// segments. enc : src = clair, dst = chiffré ; sinon l'inverse.
static void
nonce(unsigned char iv[12], size_t k, size_t nseg)
{
    memset(iv, 0, 12);
    for (size_t c = k, i = 10; c != 0; c >>= 8, i--)
        iv[i] = (unsigned char) c;
    iv[11] = k + 1 == nseg;
}

static bool
tranche(const unsigned char* cle, const unsigned char* src, unsigned char* dst,
        size_t clair, size_t nseg, size_t k0, size_t k1, int enc)
{
    unsigned char iv[12];
    bool ok = true;
    for (size_t k = k0; ok && k < k1; k++) {
        const size_t n = k + 1 < nseg ? SEG : clair - k * SEG;
        const unsigned char* in = src + k * (enc ? SEG : SEG + TAG);
        unsigned char* out = dst + k * (enc ? SEG + TAG : SEG);
        nonce(iv, k, nseg);
        ok = enc ? crypto_aead_chacha20poly1305_ietf_encrypt_detached(
                       out, out + n, nullptr, in, n, nullptr, 0, nullptr, iv,
                       cle) == 0
                 : crypto_aead_chacha20poly1305_ietf_decrypt_detached(
                       out, nullptr, in, n, in + n, nullptr, 0, iv, cle) == 0;
    }
    return ok;
}

// Tous les segments, répartis en tranches contiguës sur les fils.
static bool
segments(const unsigned char* cle, const unsigned char* src, unsigned char* dst,
         size_t clair, size_t nseg, int enc)
{
    // hardware_concurrency est un appel système coûteux dans le bac à sable.
    // Tous les cœurs : 25 Mo en 1,7 ms contre 3,4 plafonné à 8 fils (12700H,
    // 6 cœurs P + 8 E), le débit mémoire n'est pas encore le mur
    static const size_t maxFils = std::max<size_t>(
        1, std::thread::hardware_concurrency());
#ifdef __EMSCRIPTEN__
    // Pyodide n'a pas de pthreads : std::thread lèverait
    return tranche(cle, src, dst, clair, nseg, 0, nseg, enc);
#endif
    const size_t fils = nseg <= 2 * SEG_PAR_FIL
        ? 1 : std::min(maxFils, nseg / SEG_PAR_FIL);
    if (fils == 1)
        return tranche(cle, src, dst, clair, nseg, 0, nseg, enc);
    std::atomic<bool> ok(true);
    std::vector<std::thread> pool;
    pool.reserve(fils - 1);
    for (size_t f = 1; f < fils; f++)
        pool.emplace_back([&, f] {
            if (!tranche(cle, src, dst, clair, nseg, nseg * f / fils,
                         nseg * (f + 1) / fils, enc))
                ok = false;
        });
    if (!tranche(cle, src, dst, clair, nseg, 0, nseg / fils, enc))
        ok = false;
    for (auto& t : pool)
        t.join();
    return ok;
}

}  // namespace sjcrypto


// _scrypt(mot de passe, sel, n, r, p, longueur) -> bytes, GIL rendu
static PyObject*
sj_scrypt(PyObject* Py_UNUSED(self), PyObject* args)
{
    using namespace sjcrypto;
    Py_buffer mdp, sel;
    unsigned long long n;
    unsigned int r, p;
    Py_ssize_t lg;
    if (!PyArg_ParseTuple(args, "y*y*KIIn", &mdp, &sel, &n, &r, &p, &lg))
        return nullptr;
    PyObject* res = nullptr;
    if (lg <= 0)
        PyErr_SetString(PyExc_ValueError, "length must be positive");
    else if ((res = PyBytes_FromStringAndSize(nullptr, lg)) != nullptr) {
        int rc;
        Py_BEGIN_ALLOW_THREADS
        rc = crypto_pwhash_scryptsalsa208sha256_ll(
            (const uint8_t*) mdp.buf, (size_t) mdp.len,
            (const uint8_t*) sel.buf, (size_t) sel.len, n, r, p,
            (uint8_t*) PyBytes_AS_STRING(res), (size_t) lg);
        Py_END_ALLOW_THREADS
        if (rc != 0) {
            Py_CLEAR(res);
            PyErr_SetString(PyExc_MemoryError, "scrypt failed");
        }
    }
    PyBuffer_Release(&mdp);
    PyBuffer_Release(&sel);
    return res;
}


// _chacha20poly1305(clé, nonce, données, chiffre) -> bytes (chiffré + étiquette,
// ou clair), None si l'étiquette ne s'authentifie pas. Sans données associées.
static PyObject*
sj_chacha20poly1305(PyObject* Py_UNUSED(self), PyObject* args)
{
    using namespace sjcrypto;
    Py_buffer cle, iv, src;
    int enc;
    if (!PyArg_ParseTuple(args, "y*y*y*p", &cle, &iv, &src, &enc))
        return nullptr;
    PyObject* res = nullptr;
    const size_t n = (size_t) src.len;
    if (cle.len != 32 || iv.len != 12)
        PyErr_SetString(PyExc_ValueError,
                        "key must be 32 bytes and nonce 12 bytes");
    else if (!enc && n < TAG)
        res = Py_NewRef(Py_None);
    else if ((res = PyBytes_FromStringAndSize(
                  nullptr, (Py_ssize_t) (enc ? n + TAG : n - TAG)))
             != nullptr) {
        unsigned char* out = (unsigned char*) PyBytes_AS_STRING(res);
        const unsigned char* in = (const unsigned char*) src.buf;
        const unsigned char* k = (const unsigned char*) cle.buf;
        const unsigned char* v = (const unsigned char*) iv.buf;
        if (enc)
            crypto_aead_chacha20poly1305_ietf_encrypt_detached(
                out, out + n, nullptr, in, n, nullptr, 0, nullptr, v, k);
        else if (crypto_aead_chacha20poly1305_ietf_decrypt_detached(
                     out, nullptr, in, n - TAG, in + n - TAG, nullptr, 0, v, k)
                 != 0) {
            Py_DECREF(res);
            res = Py_NewRef(Py_None);
        }
    }
    PyBuffer_Release(&cle);
    PyBuffer_Release(&iv);
    PyBuffer_Release(&src);
    return res;
}


// _age_payload(clé de flux, données, chiffre[, préfixe])
//   chiffre : bytes = préfixe + segments chiffrés (une seule allocation) ;
//   sinon   : bytearray du clair, None si une étiquette ne s'authentifie pas.
static PyObject*
age_payload(PyObject* Py_UNUSED(self), PyObject* args)
{
    using namespace sjcrypto;
    Py_buffer cle, src, prefixe = {};
    int enc;
    if (!PyArg_ParseTuple(args, "y*y*p|y*", &cle, &src, &enc, &prefixe))
        return nullptr;
    PyObject* res = nullptr;
    const size_t n = (size_t) src.len;
    const size_t plein = enc ? SEG : SEG + TAG;
    const size_t nseg = std::max<size_t>(1, (n + plein - 1) / plein);
    // déchiffrement : un dernier segment plus court qu'une étiquette ne peut
    // pas s'authentifier (et rendrait la taille du clair négative)
    const bool court = !enc && n - (nseg - 1) * plein < TAG;
    const size_t clair = enc ? n : court ? 0 : n - TAG * nseg;
    if (cle.len != 32)
        PyErr_SetString(PyExc_ValueError, "stream key must be 32 bytes");
    else if (court)
        res = Py_NewRef(Py_None);
    else {
        unsigned char* dst;
        if (enc) {
            res = PyBytes_FromStringAndSize(
                nullptr, prefixe.len + (Py_ssize_t) (n + TAG * nseg));
            dst = res ? (unsigned char*) PyBytes_AS_STRING(res) : nullptr;
            if (dst && prefixe.len) {
                memcpy(dst, prefixe.buf, prefixe.len);
                dst += prefixe.len;
            }
        } else {
            res = PyByteArray_FromStringAndSize(nullptr, (Py_ssize_t) clair);
            dst = res ? (unsigned char*) PyByteArray_AS_STRING(res) : nullptr;
        }
        if (res != nullptr) {
            bool ok;
            Py_BEGIN_ALLOW_THREADS
            ok = segments((const unsigned char*) cle.buf,
                          (const unsigned char*) src.buf, dst, clair, nseg, enc);
            Py_END_ALLOW_THREADS
            if (!ok) {
                Py_CLEAR(res);
                if (enc)
                    PyErr_SetString(PyExc_RuntimeError, "encryption failed");
                else
                    res = Py_NewRef(Py_None);
            }
        }
    }
    PyBuffer_Release(&cle);
    PyBuffer_Release(&src);
    if (prefixe.obj != nullptr)
        PyBuffer_Release(&prefixe);
    return res;
}

#endif  // SJ_CRYPTO_H_
