// Balayage d'un document json : début et fin de chaque conteneur assez gros,
// nommé sous la grammaire de chemins des $ref (root['clé'].attribut[0]).
//
// Portage de serializejson.indexation.balaye, dont il doit rendre EXACTEMENT
// le même résultat — c'est ce que vérifie le test, en comparant les deux sur
// tout le catalogue. La version python est une expression régulière qui relit
// le document produit à 18 Mo/s, quand le PARSEUR complet, qui en fait
// pourtant bien davantage, tourne à 350 Mo/s : indexer coûtait vingt fois
// désérialiser.
//
// Le balayage ne regarde que la STRUCTURE : il saute les chaînes d'un bloc et
// ignore tout le reste (nombres, true, false, null ne contiennent aucun des
// caractères qui l'intéressent). Aucune valeur n'est décodée, aucun objet
// python fabriqué — sauf les chemins des conteneurs RETENUS.

#ifndef RAPIDJSON_IndexScan_H_
#define RAPIDJSON_IndexScan_H_

#include "rapidjson.h"
#include "serializejson.h"     // base 64 et pointeurs blosc2 du rangement
#include <Python.h>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#ifdef _WIN32
#include <io.h>
#define SJ_INDEX_FSEEK _fseeki64
#define SJ_INDEX_FTELL _ftelli64
#else
#include <unistd.h>
#define SJ_INDEX_FSEEK fseeko
#define SJ_INDEX_FTELL ftello
#endif

RAPIDJSON_NAMESPACE_BEGIN

// Un segment de chemin : « [3] », « ['clé'] », « .attribut ». Défini ICI parce
// que deux producteurs de chemins s'en servent — le suivi de chemin de
// l'encodeur (rapidjson.cpp, pour les $ref) et l'index construit à l'écriture
// (plus bas), qui vit dans l'écrivain et n'inclut que ce fichier.
struct SjSegment {
    enum Kind { INDEX, KEY, ATTR } kind;
    const char* str;   // clé utf-8 empruntée, valide pendant la récursion sous cette clé
    size_t len;
    Py_ssize_t index;
};

// `chemin` ajouté à `out` échappé pour une chaîne json : une clé de dict peut
// contenir guillemets, antislashs ou contrôles — insérée brute, elle rendait
// le document invalide (constaté sur {'a"b': ...} partagé)
inline void sj_json_echappe(const char* s, size_t len, std::string& out)
{
    for (size_t i = 0; i < len; i++) {
        const char c = s[i];
        switch (c) {
        case '"':  out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\t': out += "\\t"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        default:
            if ((unsigned char) c < 0x20) {
                char buffer[8];
                snprintf(buffer, sizeof(buffer), "\\u%04x", (unsigned char) c);
                out += buffer;
            } else {
                out += c;
            }
        }
    }
}

// un conteneur ouvert : sa position, ce que son parent l'a nommé, et l'état
// de lecture de ses propres enfants
struct SjNiveau {
    size_t debut;
    int parent;                  // niveau du parent, -1 pour la racine
    // segment nommant CE conteneur, capturé à l'ouverture (le parent aura
    // changé de clé et de rang bien avant qu'on referme)
    unsigned char genre;         // 0 rang, 1 clé, 2 attribut
    long long rang;
    const char* cle;             // pointe DANS le tampon balayé, échappements
    size_t cleLen;               // compris : rien n'est copié avant de retenir
    // lecture des enfants
    bool liste;
    bool attrs;                  // clés à écrire en « .nom » plutôt que ['nom']
    bool renvoi;                 // marqueur {"$ref": …} : pas un conteneur
    bool attendClasse;           // le nom de classe est la chaîne qui suit
    bool premiere;
    bool attendCle;
    long long n;
    const char* cleCourante;
    size_t cleCouranteLen;
    // chemin matérialisé, une seule fois, partagé par toute la descendance
    std::string chemin;
    bool fait;
};

// « \n », « é »… d'une clé json vers l'utf-8 du chemin. Le chemin porte
// la clé RÉELLE : c'est le parseur qui défera l'échappement du $ref quand il
// le relira.
inline void sj_index_desechappe(const char* s, size_t len, std::string& out)
{
    for (size_t i = 0; i < len; i++) {
        if (s[i] != '\\') {
            out += s[i];
            continue;
        }
        if (++i >= len)
            return;
        switch (s[i]) {
        case 'n': out += '\n'; break;
        case 't': out += '\t'; break;
        case 'r': out += '\r'; break;
        case 'b': out += '\b'; break;
        case 'f': out += '\f'; break;
        case 'u': {
            if (i + 4 >= len) return;
            unsigned code = 0;
            for (int k = 1; k <= 4; k++) {
                unsigned char c = (unsigned char) s[i + k];
                code = (code << 4) | (unsigned) (c <= '9' ? c - '0'
                                                : (c | 0x20) - 'a' + 10);
            }
            i += 4;
            // paire de substitution : le couple porte UN caractère
            if (code >= 0xD800 && code < 0xDC00 && i + 6 < len
                    && s[i + 1] == '\\' && s[i + 2] == 'u') {
                unsigned bas = 0;
                for (int k = 3; k <= 6; k++) {
                    unsigned char c = (unsigned char) s[i + k];
                    bas = (bas << 4) | (unsigned) (c <= '9' ? c - '0'
                                                  : (c | 0x20) - 'a' + 10);
                }
                if (bas >= 0xDC00 && bas < 0xE000) {
                    code = 0x10000 + ((code - 0xD800) << 10) + (bas - 0xDC00);
                    i += 6;
                }
            }
            if (code < 0x80) {
                out += (char) code;
            } else if (code < 0x800) {
                out += (char) (0xC0 | (code >> 6));
                out += (char) (0x80 | (code & 0x3F));
            } else if (code < 0x10000) {
                out += (char) (0xE0 | (code >> 12));
                out += (char) (0x80 | ((code >> 6) & 0x3F));
                out += (char) (0x80 | (code & 0x3F));
            } else {
                out += (char) (0xF0 | (code >> 18));
                out += (char) (0x80 | ((code >> 12) & 0x3F));
                out += (char) (0x80 | ((code >> 6) & 0x3F));
                out += (char) (0x80 | (code & 0x3F));
            }
            break;
        }
        default: out += s[i]; break;   // \" \\ \/ : le caractère lui-même
        }
    }
}

// chemin du niveau k, composé une seule fois puis resservi à ses enfants
inline const std::string& sj_index_chemin(std::vector<SjNiveau>& pile, int k)
{
    if (pile[(size_t) k].fait)
        return pile[(size_t) k].chemin;
    std::string compose;
    if (pile[(size_t) k].parent < 0) {
        compose = "root";
    } else {
        compose = sj_index_chemin(pile, pile[(size_t) k].parent);
        SjNiveau& niv = pile[(size_t) k];
        if (niv.genre == 0) {
            compose += '[';
            compose += std::to_string(niv.rang);
            compose += ']';
        } else if (niv.genre == 2) {
            compose += '.';
            sj_index_desechappe(niv.cle, niv.cleLen, compose);
        } else {
            compose += "['";
            sj_index_desechappe(niv.cle, niv.cleLen, compose);
            compose += "']";
        }
    }
    pile[(size_t) k].chemin = std::move(compose);
    pile[(size_t) k].fait = true;
    return pile[(size_t) k].chemin;
}

// Une entrée, au format où l'index se range : « "chemin":[début,fin] », les
// entrées séparées par des virgules. Les DEUX producteurs passent par là, et
// c'est ce qui garantit qu'ils composent le même texte.
inline void sj_index_retient(const char* chemin, size_t len, size_t debut,
                             size_t fin, std::string& texte)
{
    if (!texte.empty())
        texte += ',';
    texte += '"';
    sj_json_echappe(chemin, len, texte);
    texte += "\":[";
    texte += std::to_string((unsigned long long) debut);
    texte += ',';
    texte += std::to_string((unsigned long long) fin);
    texte += ']';
}

// Remplit `entrees` ({chemin: [début, fin]}) pour les conteneurs de `seuil`
// octets au moins, ou `texte` quand `entrees` est nul — l'index qui part sur
// le disque n'a pas à passer par un objet python par entrée.
// Rend false avec une erreur python posée.
inline bool sj_index_balaye(const char* data, size_t fin, size_t seuil,
                            PyObject* entrees, std::string* texte = nullptr)
{
    std::vector<SjNiveau> pile;
    pile.reserve(32);
    for (size_t i = 0; i < fin; i++) {
        const char c = data[i];
        if (c == '"') {
            size_t j = i + 1;
            while (j < fin) {
                if (data[j] == '\\') { j += 2; continue; }
                if (data[j] == '"') break;
                j++;
            }
            if (!pile.empty()) {
                SjNiveau& niv = pile.back();
                if (niv.attendCle) {
                    niv.cleCourante = data + i + 1;
                    niv.cleCouranteLen = j - i - 1;
                    if (niv.premiere) {
                        // une enveloppe d'objet commence par "__class__" : ses
                        // autres clés sont des ATTRIBUTS (chemins en « .nom »),
                        // exactement la règle attrsDict de l'écrivain — sauf
                        // l'enveloppe de dict à clés non-str, dont la classe
                        // est lue ci-dessous
                        niv.attendClasse = niv.cleCouranteLen == 9
                            && memcmp(niv.cleCourante, "__class__", 9) == 0;
                        niv.attrs = niv.attendClasse;
                        // un marqueur {"$ref": "chemin"} RENVOIE à un objet, il
                        // n'en porte pas les octets : l'indexer donnerait une
                        // tranche qu'il faudrait résoudre à nouveau. L'écrivain,
                        // qui l'écrit d'un bloc, ne l'indexe pas davantage
                        niv.renvoi = niv.cleCouranteLen == 4
                            && memcmp(niv.cleCourante, "$ref", 4) == 0;
                        niv.premiere = false;
                    }
                } else if (niv.attendClasse) {
                    // {"__class__": "dict", "2": …} : les clés d'un dict à clés
                    // non-str s'écrivent ['2'], jamais .2 — le texte encodé
                    // d'une clé tuple ou frozenset ne serait pas relisible en
                    // segment d'attribut (voir test_references)
                    niv.attrs = !(j - i - 1 == 4
                                  && memcmp(data + i + 1, "dict", 4) == 0);
                    niv.attendClasse = false;
                }
            }
            i = j;                       // sur le guillemet fermant
        } else if (c == '{' || c == '[') {
            const int parent = (int) pile.size() - 1;
            pile.resize(pile.size() + 1);
            SjNiveau& niv = pile.back();
            niv.debut = i;
            niv.parent = parent;
            niv.fait = false;
            // la racine n'a pas de segment : son chemin est « root »
            if (parent >= 0) {
                SjNiveau& pere = pile[(size_t) parent];
                if (pere.liste) {
                    niv.genre = 0;
                    niv.rang = pere.n;
                } else {
                    niv.genre = pere.attrs ? 2 : 1;
                    niv.cle = pere.cleCourante;
                    niv.cleLen = pere.cleCouranteLen;
                }
            }
            niv.liste = c == '[';
            niv.attrs = false;
            niv.renvoi = false;
            niv.attendClasse = false;
            niv.premiere = true;
            niv.attendCle = !niv.liste;
            niv.n = 0;
            niv.cleCourante = nullptr;
            niv.cleCouranteLen = 0;
        } else if (pile.empty()) {
            // hors de tout conteneur : un document réduit à un scalaire, ou
            // un fermant de trop dans un fichier abîmé — que le balayage
            // ignore plutôt que de dépiler dans le vide
            continue;
        } else if (c == '}' || c == ']') {
            SjNiveau& niv = pile.back();
            if (!niv.renvoi && i + 1 - niv.debut >= seuil) {
                const std::string& chemin_ =
                    sj_index_chemin(pile, (int) pile.size() - 1);
                if (entrees == nullptr) {
                    sj_index_retient(chemin_.data(), chemin_.size(),
                                     niv.debut, i + 1, *texte);
                } else {
                    PyObject* chemin = PyUnicode_FromStringAndSize(
                        chemin_.data(), (Py_ssize_t) chemin_.size());
                    PyObject* bornes = Py_BuildValue(
                        "[nn]", (Py_ssize_t) niv.debut, (Py_ssize_t) (i + 1));
                    if (chemin == nullptr || bornes == nullptr
                            || PyDict_SetItem(entrees, chemin, bornes) != 0) {
                        Py_XDECREF(chemin);
                        Py_XDECREF(bornes);
                        return false;
                    }
                    Py_DECREF(chemin);
                    Py_DECREF(bornes);
                }
            }
            pile.pop_back();
        } else if (c == ':') {
            pile.back().attendCle = false;
        } else if (c == ',') {
            SjNiveau& niv = pile.back();
            if (niv.liste)
                niv.n++;
            else
                niv.attendCle = true;
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// Le même index, mais construit PENDANT l'écriture : l'écrivain annonce
// l'ouverture et la fermeture de chaque conteneur, et le chemin vient des
// segments que le suivi de chemin tient DÉJÀ pour les $ref. Aucun octet n'est
// relu, aucune structure n'est redécouverte.
//
// Ce que l'écrivain croit avoir écrit peut diverger de ce que le fichier
// contient — c'est le danger propre à cette voie, et il est MUET. Trois
// réponses, dans l'ordre où elles agissent :
//   - le décalage du document dans le fichier se LIT (lseek, voir
//     WriterThread::debut), il ne se suppose pas ;
//   - les positions viennent du flux lui-même, expansion base64 comprise, et
//     ce chemin n'est branché QUE là où les octets tombent tels quels dans un
//     descripteur (un GzipFile a un fileno, et ses positions ne voudraient
//     rien dire — il garde le balayage) ;
//   - le test exige l'ÉGALITÉ STRICTE avec le balayage sur tout le catalogue,
//     et le balayage, lui, lit le fichier.
//
// Le rendu est le TEXTE json des entrées, composé au vol : pas un objet python
// par entrée, qui était le second coût du balayage après le balayage même.
struct SjIndexEcriture {
    const std::vector<SjSegment>* segments = nullptr;
    size_t seuil = 0;
    std::string texte;      // « "chemin":[début,fin],… », sans les accolades

    // un conteneur ouvert, en attente de sa fermeture
    struct Niveau {
        size_t debut;
        size_t prof;         // nombre de segments de chemin à l'ouverture
        const char* attr;    // clé d'enveloppe reprise (voir attente), ou nul
        size_t attrLen;
        std::string chemin;  // composé à la demande, resservi à la descendance
        bool fait;
    };
    std::vector<Niveau> pile;

    // Clé d'enveloppe EN ATTENTE d'un conteneur à nommer. Une tête d'enveloppe
    // écrite d'un bloc ne pousse aucun segment de chemin pour sa charge, que le
    // balayage nomme pourtant « .__new__ » ou « .__init__ » : le conteneur
    // ouvert juste après, SANS qu'un segment soit venu entretemps, est cette
    // charge. Le test sur la profondeur laisse donc la main aux voies qui
    // poussent le segment elles-mêmes (tuple, set, recette).
    const char* attente = nullptr;
    size_t attenteLen = 0;

    void ouvre(size_t position) {
        const size_t prof = segments->size();
        const char* attr = nullptr;
        if (attente != nullptr && !pile.empty() && pile.back().prof == prof)
            attr = attente;
        attente = nullptr;
        pile.resize(pile.size() + 1);
        Niveau& niv = pile.back();
        niv.debut = position;
        niv.prof = prof;
        niv.attr = attr;
        niv.attrLen = attenteLen;
        niv.fait = false;
    }

    void ferme(size_t position) {
        attente = nullptr;   // charge scalaire : la clé n'a pas servi
        Niveau& niv = pile.back();
        // la racine est écartée : le python la pose en [0, taille], exactement
        // comme le balayage, dont l'entrée « root » écrase la sienne
        if (pile.size() > 1 && position - niv.debut >= seuil)
            retient(chemin(pile.size() - 1), niv.debut, position);
        pile.pop_back();
    }

    // conteneur écrit d'un bloc, sans enfant
    void plat(size_t debut, size_t position) {
        ouvre(debut);
        ferme(position);
    }

private:
    // chemin du niveau k, composé une seule fois puis resservi à ses enfants :
    // celui du parent, plus les segments poussés depuis (une clé d'enveloppe
    // s'intercale entre un objet et sa liste d'arguments)
    const std::string& chemin(size_t k) {
        Niveau& niv = pile[k];
        if (niv.fait)
            return niv.chemin;
        size_t depuis = 0;
        if (k == 0) {
            niv.chemin = "root";
        } else {
            niv.chemin = chemin(k - 1);
            depuis = pile[k - 1].prof;
        }
        for (size_t i = depuis; i < niv.prof; i++) {
            const SjSegment& segment = (*segments)[i];
            switch (segment.kind) {
            case SjSegment::INDEX:
                niv.chemin += '[';
                niv.chemin += std::to_string((long long) segment.index);
                niv.chemin += ']';
                break;
            case SjSegment::ATTR:
                niv.chemin += '.';
                niv.chemin.append(segment.str, segment.len);
                break;
            default:
                niv.chemin += "['";
                niv.chemin.append(segment.str, segment.len);
                niv.chemin += "']";
                break;
            }
        }
        if (niv.attr) {
            niv.chemin += '.';
            niv.chemin.append(niv.attr, niv.attrLen);
        }
        niv.fait = true;
        return niv.chemin;
    }

    void retient(const std::string& chemin_, size_t debut, size_t fin) {
        sj_index_retient(chemin_.data(), chemin_.size(), debut, fin, texte);
    }
};

// ---------------------------------------------------------------------------
// RANGEMENT de l'index : composition du bloc json, dégonflage zstd, base 64,
// queue de la forme "comment" et la lecture qui les défait. Tout est ici —
// python appelle, il ne met plus rien en forme lui-même.
//
// Ce que la forme "comment" ajoute en fin de json, sans un octet de rembourrage :
//
//   //  <index dégonflé, en base 64>  <date>  <longueur>  <1 caractère>
//
// Tout est en base 64, donc la queue reste du TEXTE : un octet binaire y
// couperait la ligne, et le fichier cesserait d'être lisible par un parseur
// tolérant aux commentaires. Elle se lit à l'ENVERS depuis la fin — le dernier
// caractère porte les DEUX largeurs, sur trois bits chacune (la longueur dans
// les bits bas), ces deux champs donnent la date de composition et la taille
// du bloc, et le bloc est juste avant : rien à remonter à l'aveugle, et aucun
// champ de largeur fixe à surdimensionner. Les deux caractères d'en-tête sont
// relus À la position calculée : c'est ce contrôle, et non la rareté d'un
// préfixe bavard, qui interdit de prendre pour un index la fin d'un json
// ordinaire — qui s'achève sur « } », « ] » ou « " », hors alphabet.
//
// La DATE est là pour trancher SANS lire le bloc : elle dit, en une lecture de
// seize octets en fin de fichier, si cet index-ci est plus récent que le
// sidecar posé à côté — donc lequel des deux mérite le seek, la base 64 à
// l'envers et le dégonflage. Elle est en millisecondes depuis l'époque, sur
// sept chiffres de base 64 (42 bits, jusqu'en 2109), la même échelle que le
// mtime dont le sidecar est daté.
static const char sj_index_entete[] = "//";
const size_t sj_index_entete_len = 2;
const size_t sj_index_largeur_max = 7;   // 3 bits par largeur, et jamais nulle
// de quoi tenir la date, la longueur et le caractère de largeurs dans tous les
// cas : une seule lecture en fin de fichier suffit à décider
const size_t sj_index_queue_max = 2 * sj_index_largeur_max + 1;

struct SjIndexQueue {
    bool present;        // la fin du fichier a la FORME d'une queue d'index
    size_t taille;       // taille du fichier
    size_t fin;          // fin du document json (sa taille s'il n'y a pas de queue)
    size_t debut;        // début du bloc base 64
    size_t longueur;     // sa longueur en caractères
    uint64_t date;       // composition de l'index, en ms depuis l'époque
};

inline int sj_index_b64_valeur(char c)
{
    const unsigned char v =
        serializejson_b64_decode_table()[(unsigned char) c];
    return v < 64 ? (int) v : -1;
}

// `n` en base 64, sur le minimum de chiffres
inline void sj_index_chiffres(uint64_t n, std::string& out)
{
    char tampon[16];
    size_t k = 0;
    do {
        tampon[k++] = serializejson_b64_table[n & 63];
        n >>= 6;
    } while (n);
    while (k)
        out += tampon[--k];
}

// Lit la queue d'un fichier de `taille` octets dont les `n` derniers sont dans
// `tail`. Ne vérifie PAS l'en-tête « // », qui est hors du tampon dès que le
// bloc est long : c'est à l'appelant, qui seul sait comment atteindre la
// position calculée.
inline SjIndexQueue sj_index_queue(const char* tail, size_t n, size_t taille)
{
    SjIndexQueue q = {false, taille, taille, 0, 0, 0};
    if (n == 0)
        return q;
    const int largeurs = sj_index_b64_valeur(tail[n - 1]);
    if (largeurs < 0)
        return q;
    const size_t wl = (size_t) (largeurs & 7);
    const size_t wd = (size_t) (largeurs >> 3);
    if (wl == 0 || wd == 0 || wl + wd + 1 > n)
        return q;
    uint64_t longueur = 0, date = 0;
    const char* champ = tail + n - 1 - wl;
    for (size_t i = 0; i < wl; i++) {
        const int v = sj_index_b64_valeur(champ[i]);
        if (v < 0)
            return q;
        longueur = (longueur << 6) | (uint64_t) v;
    }
    champ -= wd;
    for (size_t i = 0; i < wd; i++) {
        const int v = sj_index_b64_valeur(champ[i]);
        if (v < 0)
            return q;
        date = (date << 6) | (uint64_t) v;
    }
    const size_t queue = sj_index_entete_len + (size_t) longueur + wd + wl + 1;
    if (queue > taille)
        return q;
    q.present = true;
    q.fin = taille - queue;
    q.debut = q.fin + sj_index_entete_len;
    q.longueur = (size_t) longueur;
    q.date = date;
    return q;
}

// Fin du document json dans un tampon qui porte peut-être sa queue d'index :
// la taille du tampon quand il n'y en a pas.
inline size_t sj_index_fin(const char* data, size_t taille)
{
    const size_t n = taille < sj_index_queue_max ? taille : sj_index_queue_max;
    const SjIndexQueue q = sj_index_queue(data + taille - n, n, taille);
    if (!q.present || memcmp(data + q.fin, sj_index_entete,
                             sj_index_entete_len) != 0)
        return taille;
    return q.fin;
}

// Dégonflage zstd par la bibliothèque déjà chargée pour les tableaux
// (libblosc2_serializejson.so). Rend false quand elle manque, ou quand le
// dégonflage ne gagne rien : le bloc part alors en clair, et le PREMIER OCTET
// tranche à la lecture — un json commence par « { », jamais une trame blosc2.
inline bool sj_index_tasse(const std::string& texte, std::string& out)
{
    if (!serializejson_blosc2_ctx_ok || texte.empty()
            || texte.size() >= (size_t) BLOSC2_MAX_BUFFERSIZE)
        return false;
    const int compcode = sj_blosc2_compname_to_compcode("zstd");
    if (compcode < 0)
        return false;
    blosc2_cparams cparams = BLOSC2_CPARAMS_DEFAULTS;
    cparams.compcode = (uint8_t) compcode;
    // 5, le même niveau que les tableaux — soit zstd 9 (blosc2 double le
    // sien moins un, blosc2.c:571). Le 9 de blosc2, lui, demande
    // ZSTD_maxCLevel(), le MAXIMUM : sur 1,2 Mo de texte d'index il coûtait
    // 2,0 s là où le 5 met 2,1 ms, pour onze pour cent d'octets sur un bloc
    // qui pèse déjà moins d'un vingtième du document. C'est ce seul chiffre
    // qui rendait l'indexation fine inabordable à l'écriture.
    cparams.clevel = 5;
    cparams.typesize = 1;     // du texte : ni colonnes ni mots à transposer
    cparams.nthreads = 1;
    for (int f = 0; f < BLOSC2_MAX_FILTERS; f++) {
        cparams.filters[f] = BLOSC_NOFILTER;
        cparams.filters_meta[f] = 0;
    }
    blosc2_context* ctx = sj_blosc2_create_cctx(cparams);
    if (ctx == nullptr)
        return false;
    out.resize(texte.size() + BLOSC2_MAX_OVERHEAD);
    const int n = sj_blosc2_compress_ctx(ctx, texte.data(),
                                         (int32_t) texte.size(),
                                         &out[0], (int32_t) out.size());
    sj_blosc2_free_ctx(ctx);
    if (n <= 0 || (size_t) n >= texte.size()) {
        out.clear();
        return false;
    }
    out.resize((size_t) n);
    return true;
}

inline bool sj_index_degonfle(const char* data, size_t n, std::string& out)
{
    if (!serializejson_blosc2_ctx_ok || n < (size_t) BLOSC_MIN_HEADER_LENGTH)
        return false;
    size_t nbytes = 0, cbytes = 0, blocksize = 0;
    sj_blosc1_cbuffer_sizes(data, &nbytes, &cbytes, &blocksize);
    if (nbytes == 0 || cbytes != n || nbytes >= (size_t) BLOSC2_MAX_BUFFERSIZE)
        return false;
    blosc2_dparams dparams = BLOSC2_DPARAMS_DEFAULTS;
    dparams.nthreads = 1;
    blosc2_context* ctx = sj_blosc2_create_dctx(dparams);
    if (ctx == nullptr)
        return false;
    out.resize(nbytes);
    const int ecrits = sj_blosc2_decompress_ctx(ctx, data, (int32_t) n,
                                                &out[0], (int32_t) nbytes);
    sj_blosc2_free_ctx(ctx);
    if (ecrits != (int) nbytes) {
        out.clear();
        return false;
    }
    return true;
}

// Le bloc tel qu'il se range : dégonflé s'il y gagne, puis en base 64 pour la
// forme "comment" — dont le rembourrage « = » se retire, puisqu'il se retrouve
// de la longueur et tomberait entre le bloc et le champ qui le mesure.
inline void sj_index_bloc(const std::string& texte, bool base64,
                          std::string& out)
{
    std::string tasse;
    const std::string& brut = sj_index_tasse(texte, tasse) ? tasse : texte;
    if (!base64) {
        out.assign(brut);
        return;
    }
    out.resize((brut.size() + 2) / 3 * 4);
    serializejson_b64_encode((const unsigned char*) brut.data(), brut.size(),
                             &out[0]);
    while (!out.empty() && out.back() == '=')
        out.pop_back();
}

inline bool sj_index_debloc(const char* data, size_t n, bool base64,
                            std::string& out)
{
    std::string brut;
    if (base64) {
        if (n == 0 || n % 4 == 1)
            return false;
        std::string rembourre(data, n);
        rembourre.resize((n + 3) / 4 * 4, '=');
        brut.resize(rembourre.size() / 4 * 3);
        if (!sj_b64_decode_into(rembourre.data(), rembourre.size(),
                                (unsigned char*) &brut[0],
                                serializejson_b64_decode_table()))
            return false;
        brut.resize(brut.size() - (rembourre.size() - n));
    } else {
        brut.assign(data, n);
    }
    if (!brut.empty() && brut[0] == '{') {
        out.swap(brut);
        return true;
    }
    return sj_index_degonfle(brut.data(), brut.size(), out);
}

// L'index complet, tel qu'il se range : le texte des entrées relevées par l'un
// ou l'autre producteur, plus `root`, qui vaut le document entier et donne du
// même coup le contrôle de fraîcheur.
inline void sj_index_compose(size_t seuil, const char* chemins, size_t len,
                             size_t fin, std::string& out)
{
    out = "{\"threshold\":";
    out += std::to_string((unsigned long long) seuil);
    out += ",\"paths\":{";
    if (len) {
        out.append(chemins, len);
        out += ',';
    }
    out += "\"root\":[0,";
    out += std::to_string((unsigned long long) fin);
    out += "]}}";
}

// La queue de la forme "comment", prête à coller derrière le document. Rend
// false si le bloc dépasse ce que trois bits de largeur peuvent mesurer
// (2**42 caractères) : mieux vaut pas d'index qu'une queue illisible.
inline bool sj_index_queue_compose(const std::string& bloc, std::string& out)
{
    const uint64_t maintenant = (uint64_t)
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
    std::string date, longueur;
    // au-delà de sept chiffres (2109), les bits de poids fort tombent : la
    // date resterait comparable entre index d'une même époque, qui est tout ce
    // qu'on lui demande
    sj_index_chiffres(maintenant & (((uint64_t) 1 << 42) - 1), date);
    sj_index_chiffres((uint64_t) bloc.size(), longueur);
    if (longueur.size() > sj_index_largeur_max)
        return false;
    out.assign(sj_index_entete, sj_index_entete_len);
    out += bloc;
    out += date;
    out += longueur;
    out += serializejson_b64_table[(date.size() << 3) | longueur.size()];
    return true;
}

// --- le disque -------------------------------------------------------------
// Aucune de ces trois fonctions ne pose d'erreur python : un index absent,
// illisible ou périmé n'est pas une panne — l'appelant relit simplement le
// document en entier, ce qui donne le même résultat.

inline bool sj_index_tronque(FILE* f, size_t taille)
{
#ifdef _WIN32
    return _chsize_s(_fileno(f), (__int64) taille) == 0;
#else
    return ftruncate(fileno(f), (off_t) taille) == 0;
#endif
}

inline bool sj_index_fichier_lit(const char* chemin, size_t debut, size_t n,
                                 std::string& out)
{
    FILE* f = fopen(chemin, "rb");
    if (f == nullptr)
        return false;
    out.resize(n);
    const bool ok = SJ_INDEX_FSEEK(f, (int64_t) debut, SEEK_SET) == 0
        && (n == 0 || fread(&out[0], 1, n, f) == n);
    fclose(f);
    if (!ok)
        out.clear();
    return ok;
}

// Tout le contenu d'un fichier : le sidecar n'est QUE le bloc d'index, sa
// taille n'a donc pas à être demandée avant de le lire.
inline bool sj_index_fichier_tout(const char* chemin, std::string& out)
{
    FILE* f = fopen(chemin, "rb");
    if (f == nullptr)
        return false;
    out.clear();
    char tampon[65536];
    size_t lus;
    while ((lus = fread(tampon, 1, sizeof(tampon), f)) != 0)
        out.append(tampon, lus);
    const bool ok = ferror(f) == 0;
    fclose(f);
    if (!ok)
        out.clear();
    return ok;
}

// La queue d'index d'un fichier, en UNE lecture en fin de fichier — plus la
// relecture des deux caractères d'en-tête à la position calculée, qui est le
// contrôle. `q->present` dit s'il y en a une ; `q->fin` vaut de toute façon la
// fin du document, donc la taille du fichier quand il n'y en a pas.
inline bool sj_index_fichier_queue(const char* chemin, SjIndexQueue* q)
{
    *q = SjIndexQueue{false, 0, 0, 0, 0, 0};
    FILE* f = fopen(chemin, "rb");
    if (f == nullptr)
        return false;
    bool ok = SJ_INDEX_FSEEK(f, 0, SEEK_END) == 0;
    const int64_t taille = ok ? (int64_t) SJ_INDEX_FTELL(f) : -1;
    if (taille < 0)
        ok = false;
    if (ok) {
        q->taille = q->fin = (size_t) taille;
        const size_t n = q->taille < sj_index_queue_max ? q->taille
                                                        : sj_index_queue_max;
        char tampon[sj_index_queue_max];
        char entete[sj_index_entete_len];
        if (n != 0
                && SJ_INDEX_FSEEK(f, (int64_t) (q->taille - n), SEEK_SET) == 0
                && fread(tampon, 1, n, f) == n) {
            const SjIndexQueue candidat = sj_index_queue(tampon, n, q->taille);
            if (candidat.present
                    && SJ_INDEX_FSEEK(f, (int64_t) candidat.fin, SEEK_SET) == 0
                    && fread(entete, 1, sj_index_entete_len, f)
                       == sj_index_entete_len
                    && memcmp(entete, sj_index_entete,
                              sj_index_entete_len) == 0)
                *q = candidat;
        }
    }
    fclose(f);
    return ok;
}

// Range l'index composé `texte` : dans `sidecar` si `en_sidecar`, en queue de
// `chemin` derrière ses `fin` premiers octets sinon. Un `texte` vide veut dire
// qu'il n'y a rien à indexer : l'index qui traînait est alors retiré, et un
// fichier qui n'en portait pas n'est même pas rouvert.
//
// L'AUTRE forme est retirée dans tous les cas : un document ne porte qu'un
// index, sans quoi les deux subsistent et c'est leur date qui déciderait
// lequel suivre — à la milliseconde près, donc au hasard quand `dump` puis
// `index()` se suivent.
inline bool sj_index_fichier_range(const char* chemin, const char* sidecar,
                                   bool en_sidecar, size_t taille, size_t fin,
                                   const std::string& texte)
{
    std::string bloc, queue;
    if (en_sidecar) {
        if (texte.empty()) {
            if (remove(sidecar) != 0 && errno != ENOENT)
                return false;
        } else {
            sj_index_bloc(texte, false, bloc);
            FILE* fs = fopen(sidecar, "wb");
            if (fs == nullptr)
                return false;
            const bool ok = fwrite(bloc.data(), 1, bloc.size(), fs)
                            == bloc.size();
            if (fclose(fs) != 0 || !ok)
                return false;
        }
    } else {
        if (remove(sidecar) != 0 && errno != ENOENT)    // l'autre forme
            return false;
        if (!texte.empty()) {
            sj_index_bloc(texte, true, bloc);
            if (!sj_index_queue_compose(bloc, queue))
                return false;
        }
    }
    // le document ne se rouvre que pour poser la queue, ou pour retirer celle
    // qui traînait — sa taille le dit sans avoir à le relire
    if (queue.empty() && taille == fin)
        return true;
    FILE* f = fopen(chemin, "r+b");
    if (f == nullptr)
        return false;
    bool ok = SJ_INDEX_FSEEK(f, (int64_t) fin, SEEK_SET) == 0
        && (queue.empty()
            || fwrite(queue.data(), 1, queue.size(), f) == queue.size())
        && fflush(f) == 0
        && sj_index_tronque(f, fin + queue.size());
    return fclose(f) == 0 && ok;
}

RAPIDJSON_NAMESPACE_END

#endif // RAPIDJSON_IndexScan_H_
