// Charge utile age v1 (https://age-encryption.org/v1) en C : segments de
// 64 Kio chiffrés ChaCha20-Poly1305, nonce = compteur 11 octets gros-boutiste
// + drapeau « dernier segment ». Les segments sont INDÉPENDANTS : répartis sur
// plusieurs fils, GIL rendu. L'en-tête (scrypt, HKDF, MAC) reste en python —
// quelques microsecondes par document, rien à gagner ici.
//
// libcrypto (OpenSSL ≥ 1.1) est chargée à l'exécution par dlopen, comme
// libblosc2 : ni en-tête ni lien à la construction, aucune dépendance du
// binaire. Absente, _encryption.py garde sa voie python (cryptography).

#ifndef SJ_CRYPTO_H_
#define SJ_CRYPTO_H_

#include <Python.h>
#include <dlfcn.h>
#include <atomic>
#include <cstring>
#include <thread>
#include <vector>

namespace sjcrypto {

struct Ctx;     // EVP_CIPHER_CTX
struct Cipher;  // EVP_CIPHER

static Ctx* (*ctxNew)(void) = nullptr;
static void (*ctxFree)(Ctx*) = nullptr;
static const Cipher* (*chacha)(void) = nullptr;
static int (*cipherInit)(Ctx*, const Cipher*, void*, const unsigned char*,
                         const unsigned char*, int) = nullptr;
static int (*cipherUpdate)(Ctx*, unsigned char*, int*, const unsigned char*,
                           int) = nullptr;
static int (*cipherFinal)(Ctx*, unsigned char*, int*) = nullptr;
static int (*ctxCtrl)(Ctx*, int, int, void*) = nullptr;

static const int CTRL_GET_TAG = 0x10;  // EVP_CTRL_AEAD_GET_TAG
static const int CTRL_SET_TAG = 0x11;  // EVP_CTRL_AEAD_SET_TAG
static const size_t SEG = 64 * 1024;
static const size_t TAG = 16;
// par fil : en deçà, le lancement d'un fil coûte plus que le travail (mesuré
// dans le bac à sable : 1 Mio sur un fil 0,40 ms, sur deux 0,50)
static const size_t SEG_PAR_FIL = 8;

// Segments [k0, k1) d'une charge de `clair` octets en clair et `nseg`
// segments. enc : src = clair, dst = chiffré ; sinon l'inverse.
static bool
tranche(const unsigned char* cle, const unsigned char* src, unsigned char* dst,
        size_t clair, size_t nseg, size_t k0, size_t k1, int enc)
{
    Ctx* ctx = ctxNew();
    if (ctx == nullptr)
        return false;
    bool ok = cipherInit(ctx, chacha(), nullptr, cle, nullptr, enc) == 1;
    unsigned char iv[12];
    for (size_t k = k0; ok && k < k1; k++) {
        const size_t n = k + 1 < nseg ? SEG : clair - k * SEG;
        const unsigned char* in = src + k * (enc ? SEG : SEG + TAG);
        unsigned char* out = dst + k * (enc ? SEG + TAG : SEG);
        memset(iv, 0, sizeof iv);
        for (size_t c = k, i = 10; c != 0; c >>= 8, i--)
            iv[i] = (unsigned char) c;
        iv[11] = k + 1 == nseg;
        int lu;
        ok = cipherInit(ctx, nullptr, nullptr, nullptr, iv, enc) == 1
             && (n == 0 || cipherUpdate(ctx, out, &lu, in, (int) n) == 1)
             && (enc || ctxCtrl(ctx, CTRL_SET_TAG, (int) TAG,
                                (void*) (in + n)) == 1)
             && cipherFinal(ctx, out + n, &lu) == 1
             && (!enc || ctxCtrl(ctx, CTRL_GET_TAG, (int) TAG, out + n) == 1);
    }
    ctxFree(ctx);
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


static PyObject*
load_crypto_library(PyObject* Py_UNUSED(self), PyObject* arg)
{
    using namespace sjcrypto;
    const char* path = PyUnicode_AsUTF8(arg);
    if (path == nullptr)
        return nullptr;
    void* h = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (h == nullptr) {
        PyErr_Format(PyExc_OSError, "dlopen(%s) : %s", path, dlerror());
        return nullptr;
    }
    // tout ou rien : aucun pointeur posé tant qu'un symbole manque
    void* s[] = {dlsym(h, "EVP_CIPHER_CTX_new"), dlsym(h, "EVP_CIPHER_CTX_free"),
                 dlsym(h, "EVP_chacha20_poly1305"), dlsym(h, "EVP_CipherInit_ex"),
                 dlsym(h, "EVP_CipherUpdate"), dlsym(h, "EVP_CipherFinal_ex"),
                 dlsym(h, "EVP_CIPHER_CTX_ctrl")};
    for (void* p : s)
        if (p == nullptr) {
            dlclose(h);
            PyErr_SetString(PyExc_OSError,
                            "ChaCha20-Poly1305 symbols not found in library");
            return nullptr;
        }
    ctxNew = (decltype(ctxNew)) s[0];
    ctxFree = (decltype(ctxFree)) s[1];
    chacha = (decltype(chacha)) s[2];
    cipherInit = (decltype(cipherInit)) s[3];
    cipherUpdate = (decltype(cipherUpdate)) s[4];
    cipherFinal = (decltype(cipherFinal)) s[5];
    ctxCtrl = (decltype(ctxCtrl)) s[6];
    Py_RETURN_TRUE;
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
    if (ctxNew == nullptr)
        PyErr_SetString(PyExc_RuntimeError, "crypto library not loaded");
    else if (cle.len != 32)
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
