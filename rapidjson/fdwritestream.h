// Écriture d'un document json DROIT dans un descripteur de fichier.
//
// Pourquoi ce flux à côté de PyWriteStreamWrapper : celui-ci remet chaque
// tranche à `stream.write(bytes)`, ce qui fabrique un objet python par tranche
// et repasse par l'interpréteur. Mesuré sur ce dépôt, un document de 105 Mo,
// A/B interlacés dans le même processus et l'ordre alterné d'une ronde à
// l'autre (sans quoi la première paie la pression de cache de la précédente,
// et l'ordre décide du gagnant) :
//
//                              détour python      ici
//     vers /dev/null ........      302 ms       208 ms
//     sur le disque .........      316 ms       211 ms
//     idem, un thread python
//     qui calcule à côté ....     3529 ms       223 ms
//
// Les deux premières lignes sont le détour lui-même : un tiers du temps, pour
// des objets fabriqués puis détruits. La troisième est d'un autre ordre, et
// n'a rien à voir avec l'interpréteur : c'est l'ATTENTE DU DISQUE, que seul le
// thread d'écriture supprime (voir writerthread.h) — et il ne peut exister que
// parce que les octets d'ici n'appartiennent à aucun objet python.
//
// Ce n'est pas la reprise du verrou global : elle ne frappe qu'une BOUCLE
// écrite en python, dont chaque tour se fait préempter (36 ms contre 8546 ms
// avec un seul thread concurrent, mesuré) ; un appel venu du C++ ne la paie
// pas, et le détour python ne se dégrade pas non plus vers /dev/null.
//
// La cible doit avoir un descripteur : pour un tampon mémoire, un socket ou un
// flux compressé, l'appelant garde PyWriteStreamWrapper.

#ifndef RAPIDJSON_FdWriteStream_H_
#define RAPIDJSON_FdWriteStream_H_

#include "stream.h"
#include "writerthread.h"
#include <Python.h>
#include <cerrno>
#include <cstdlib>
#include <cstring>

RAPIDJSON_NAMESPACE_BEGIN

class FdWriteStream {
public:
    typedef char Ch;

    // Chaque tranche pleine est DÉPOSÉE chez l'écrivain, et la sérialisation
    // continue pendant qu'il l'écrit : ce flux n'écrit jamais lui-même.
    FdWriteStream(size_t chunkSize_, WriterThread* ecrivain_) {
        ecrivain = ecrivain_;
        chunkSize = chunkSize_ ? chunkSize_ : 65536;
        erreur = 0;
        bufferBegin = (char*) malloc(chunkSize);
        if (bufferBegin == nullptr) {
            chunkSize = 0;
            erreur = ENOMEM;
        }
        bufferCursor = bufferBegin;
        bufferEnd = bufferBegin + chunkSize;
    }

    ~FdWriteStream() {
        free(bufferBegin);
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

    void Flush() {
        size_t taille = (size_t) (bufferCursor - bufferBegin);
        if (taille == 0)
            return;
        // le tampon CHANGE DE MAIN : le thread le libérera après écriture, on
        // repart sur un neuf plutôt que d'attendre celui qu'on vient de donner
        ecrivain->pousse(bufferBegin, taille);
        bufferBegin = (char*) malloc(chunkSize);
        if (bufferBegin == nullptr) {
            chunkSize = 0;
            erreur = ENOMEM;
        }
        bufferCursor = bufferBegin;
        bufferEnd = bufferBegin + chunkSize;
        ecrivain->freineSiBesoin();
    }

    // Garantit `size` octets contigus dans le tampon. Le tampon ne grandit que
    // si une valeur unique dépasse la tranche (rare) : il reste alors grand
    // pour les suivantes, ce qui évite de refaire l'aller-retour.
    char* Reserve(size_t size) {
        if (bufferCursor + size > bufferEnd) {
            Flush();
            if (size > chunkSize)
                agrandit(size);
        }
        return bufferCursor;
    }

    void RawValue(const char* json, size_t size) {
        if (size < chunkSize) {
            Reserve(size);
            memcpy(bufferCursor, json, size);
            bufferCursor += size;
        } else {
            // gros bloc, qu'il faut COPIER : sa place appartient à un objet
            // python, que rien n'oblige à survivre jusqu'à l'écriture
            Flush();
            char* copie = (char*) malloc(size);
            if (copie == nullptr) {
                erreur = ENOMEM;
                return;
            }
            memcpy(copie, json, size);
            ecrivain->pousse(copie, size);
            ecrivain->freineSiBesoin();
        }
    }

    void RawString(PyObject* string) {
        Py_ssize_t taille = 0;
        // rend un pointeur INTERNE à l'objet : contrairement à
        // PyUnicode_AsUTF8String, aucun objet n'est créé donc aucun à libérer
        const char* utf8 = PyUnicode_AsUTF8AndSize(string, &taille);
        if (utf8 == nullptr)
            return;  // l'erreur python sera vue en fin d'encodage
        RawValue(utf8, (size_t) taille);
    }

    void RawBytes(PyObject* bytes) {
        RawValue(PyBytes_AS_STRING(bytes), (size_t) PyBytes_GET_SIZE(bytes));
    }

    void RawBytesToPutInQuotes(PyObject* bytes) {
        Put('\"');
        RawBytes(bytes);
        Put('\"');
    }

    void RawDataToBase64(const unsigned char* src, size_t remaining) {
        // encode le base64 par morceaux dans le tampon du flux, sans chaîne
        // intermédiaire (coupures sur des multiples de 3 octets source pour que
        // le padding ne tombe qu'à la toute fin)
        Put('\"');
        while (remaining) {
            Reserve(4);
            size_t triples = (size_t) (bufferEnd - bufferCursor) / 4;
            size_t take = triples * 3;
            if (take >= remaining)
                take = remaining;      // dernier morceau, avec padding
            bufferCursor = serializejson_b64_encode(src, take, bufferCursor);
            src += take;
            remaining -= take;
        }
        Put('\"');
    }

    // Même chose, mais on PREND le bloc, et son encodage avec : le thread
    // d'écriture fera le base64 pendant que la sérialisation continue. Réservé
    // aux trames compressées, seuls blocs dont nous soyons propriétaires — et
    // aux grandes, car pour une petite le Flush qui la précède coûterait plus
    // que l'encodage épargné. Rend false quand rien n'a été pris : l'appelant
    // encode alors lui-même, comme avant.
    //
    // Mesuré, 200 tableaux d'un mégaoctet compressés en blosc2_zstd, A/B
    // entrelacé et ordre alterné : dump rend la main en 200 ms au lieu de 258,
    // et tout est posé en 201 ms au lieu de 261.
    bool RawDataToBase64Owned(char* data, size_t taille) {
        if (taille < chunkSize)
            return false;
        Flush();
        ecrivain->pousse(data, taille, true);
        ecrivain->freineSiBesoin();
        return true;
    }

    void RawBytesToBase64(PyObject* obj) {
        Py_buffer view;
        if (PyObject_GetBuffer(obj, &view, PyBUF_CONTIG_RO) != 0)
            return;  // l'erreur python sera vue en fin d'encodage
        RawDataToBase64((const unsigned char*) view.buf, (size_t) view.len);
        PyBuffer_Release(&view);
    }

    // Position, DANS LE FICHIER, du prochain octet écrit : ce qui est déjà
    // parti chez l'écrivain, plus ce qui attend dans le tampon.
    size_t Tell() const {
        return ecrivain->depose() + (size_t) (bufferCursor - bufferBegin);
    }

    // errno de la première écriture qui a échoué, 0 sinon
    int Erreur() const {
        return erreur != 0 ? erreur : ecrivain->erreur();
    }

    Ch* bufferCursor;
    bool maybe_non_ascii = false;  // sans objet pour un flux (pas de conversion)

private:

    void agrandit(size_t size) {
        char* neuf = (char*) realloc(bufferBegin, size);
        if (neuf == nullptr) {
            if (erreur == 0)
                erreur = ENOMEM;
            return;            // Reserve rendra un tampon trop petit : l'erreur
        }                      // est relevée en fin d'encodage
        chunkSize = size;
        bufferBegin = neuf;
        bufferCursor = neuf;
        bufferEnd = neuf + size;
    }

    WriterThread* ecrivain;
    int erreur;
    Ch* bufferBegin;
    Ch* bufferEnd;
    size_t chunkSize;
};

RAPIDJSON_NAMESPACE_END

#endif // RAPIDJSON_FdWriteStream_H_
