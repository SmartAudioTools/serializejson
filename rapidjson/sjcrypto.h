// Charge utile age v1 (https://age-encryption.org/v1) en C : segments de
// 64 Kio chiffrés ChaCha20-Poly1305, nonce = compteur 11 octets gros-boutiste
// + drapeau « dernier segment ». Les segments sont INDÉPENDANTS : répartis sur
// plusieurs fils, GIL rendu. L'en-tête (scrypt, HKDF, MAC) reste en python —
// quelques microsecondes par document, rien à gagner ici.
//
// libcrypto (OpenSSL ≥ 1.1) est chargée à l'exécution par dlopen, comme
// libblosc2 : ni en-tête ni lien à la construction, aucune dépendance du
// binaire. Absente, _encryption.py garde sa voie python (cryptography).
//
// libsodium prend le relais de libcrypto pour la charge, et fournit aussi
// scrypt et l'AEAD de l'en-tête (_scrypt, _chacha20poly1305) quand le paquet
// cryptography manque. Chargée par dlopen en natif ; LIÉE dans le module pour
// WebAssembly (SJ_SODIUM_STATIQUE, scripts/construit_wasm.sh), où le lecteur
// web ne doit rien télécharger d'ailleurs que de ses propres fichiers.

#ifndef SJ_CRYPTO_H_
#define SJ_CRYPTO_H_

#include <Python.h>
#include <dlfcn.h>
#include <atomic>
#include <cstdint>
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

#ifdef SJ_SODIUM_STATIQUE
extern "C" {
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
#define SJ_SOD(f) f
#else
#define SJ_SOD(f) nullptr
#endif

// libsodium : scrypt (mot de passe, sel, N, r, p, sortie) et AEAD détaché
static int (*sodScrypt)(const uint8_t*, size_t, const uint8_t*, size_t,
                        uint64_t, uint32_t, uint32_t, uint8_t*, size_t)
    = SJ_SOD(crypto_pwhash_scryptsalsa208sha256_ll);
static int (*sodEnc)(unsigned char*, unsigned char*, unsigned long long*,
                     const unsigned char*, unsigned long long,
                     const unsigned char*, unsigned long long,
                     const unsigned char*, const unsigned char*,
                     const unsigned char*)
    = SJ_SOD(crypto_aead_chacha20poly1305_ietf_encrypt_detached);
static int (*sodDec)(unsigned char*, unsigned char*, const unsigned char*,
                     unsigned long long, const unsigned char*,
                     const unsigned char*, unsigned long long,
                     const unsigned char*, const unsigned char*)
    = SJ_SOD(crypto_aead_chacha20poly1305_ietf_decrypt_detached);

static const int CTRL_GET_TAG = 0x10;  // EVP_CTRL_AEAD_GET_TAG
static const int CTRL_SET_TAG = 0x11;  // EVP_CTRL_AEAD_SET_TAG
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
    if (ctxNew == nullptr) {  // libsodium
        bool ok = true;
        for (size_t k = k0; ok && k < k1; k++) {
            const size_t n = k + 1 < nseg ? SEG : clair - k * SEG;
            const unsigned char* in = src + k * (enc ? SEG : SEG + TAG);
            unsigned char* out = dst + k * (enc ? SEG + TAG : SEG);
            nonce(iv, k, nseg);
            ok = enc ? sodEnc(out, out + n, nullptr, in, n, nullptr, 0,
                              nullptr, iv, cle) == 0
                     : sodDec(out, nullptr, in, n, in + n, nullptr, 0, iv,
                              cle) == 0;
        }
        return ok;
    }
    Ctx* ctx = ctxNew();
    if (ctx == nullptr)
        return false;
    bool ok = cipherInit(ctx, chacha(), nullptr, cle, nullptr, enc) == 1;
    for (size_t k = k0; ok && k < k1; k++) {
        const size_t n = k + 1 < nseg ? SEG : clair - k * SEG;
        const unsigned char* in = src + k * (enc ? SEG : SEG + TAG);
        unsigned char* out = dst + k * (enc ? SEG + TAG : SEG);
        nonce(iv, k, nseg);
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


static PyObject*
load_sodium_library(PyObject* Py_UNUSED(self), PyObject* arg)
{
    using namespace sjcrypto;
    // déjà là (chargée, ou liée dans le module) : le chemin est ignoré
    if (sodScrypt != nullptr)
        Py_RETURN_TRUE;
    const char* path = PyUnicode_AsUTF8(arg);
    if (path == nullptr)
        return nullptr;
    void* h = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (h == nullptr) {
        PyErr_Format(PyExc_OSError, "dlopen(%s) : %s", path, dlerror());
        return nullptr;
    }
    void* s[] = {dlsym(h, "crypto_pwhash_scryptsalsa208sha256_ll"),
                 dlsym(h, "crypto_aead_chacha20poly1305_ietf_encrypt_detached"),
                 dlsym(h, "crypto_aead_chacha20poly1305_ietf_decrypt_detached")};
    for (void* p : s)
        if (p == nullptr) {
            dlclose(h);
            PyErr_SetString(PyExc_OSError,
                            "scrypt/ChaCha20-Poly1305 symbols not found in"
                            " library");
            return nullptr;
        }
    // choisit les variantes SIMD ; sans lui, les versions de référence
    if (void* init = dlsym(h, "sodium_init"))
        ((int (*)(void)) init)();
    sodScrypt = (decltype(sodScrypt)) s[0];
    sodEnc = (decltype(sodEnc)) s[1];
    sodDec = (decltype(sodDec)) s[2];
    Py_RETURN_TRUE;
}


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
    if (sodScrypt == nullptr)
        PyErr_SetString(PyExc_RuntimeError, "sodium library not loaded");
    else if (lg <= 0)
        PyErr_SetString(PyExc_ValueError, "length must be positive");
    else if ((res = PyBytes_FromStringAndSize(nullptr, lg)) != nullptr) {
        int rc;
        Py_BEGIN_ALLOW_THREADS
        rc = sodScrypt((const uint8_t*) mdp.buf, (size_t) mdp.len,
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
    if (sodEnc == nullptr)
        PyErr_SetString(PyExc_RuntimeError, "sodium library not loaded");
    else if (cle.len != 32 || iv.len != 12)
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
            sodEnc(out, out + n, nullptr, in, n, nullptr, 0, nullptr, v, k);
        else if (sodDec(out, nullptr, in, n - TAG, in + n - TAG, nullptr, 0, v,
                        k) != 0) {
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
    if (ctxNew == nullptr && sodEnc == nullptr)
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
