// Thread d'écriture : la sérialisation dépose des blocs, celui-ci les écrit,
// et l'appelant s'en va sans attendre le disque.
//
// Ce qui coûte, de loin, c'est l'ATTENTE du disque : sérialiser 105 Mo prend
// 210 ms, les écrire en prend 3500 dès qu'un cœur travaille à côté. Recouvrir
// les deux ne gagnerait donc presque rien — c'est de ne PLUS LES ATTENDRE que
// vient le gain, et dump rend la main en 223 ms au lieu de 3529.
//
// Les blocs déposés sont des malloc bruts, sans le moindre objet python : le
// thread écrit et libère sans jamais toucher au verrou global. C'est ce que
// permet l'écriture droit dans un descripteur, et c'est sa seule raison d'être.
//
// Rien n'est réservé d'avance. La file grandit au fil de la sérialisation et
// se vide au fil de l'écriture ; ce qui la borne n'est pas une part fixe de la
// mémoire mais un PLANCHER de disponibilité relu pendant le remplissage — tant
// qu'il reste au système plus que ce plancher, on prend.
//
// Le DISQUE, lui, est réservé d'un coup : la sérialisation finie, sa taille
// exacte est connue, et c'est le dernier instant où un manque de place peut
// encore être relevé comme une erreur de dump.
//
// PROPRIÉTÉ, et c'est ce qui commande tout le reste : un écrivain n'est JAMAIS
// détruit par son propre thread. Il le serait pendant que celui qui l'a lâché
// relâche encore son verrou, et le processus s'arrête net (constaté). Le
// thread ne fait que se signaler terminé ; la destruction a lieu plus tard, et
// toujours depuis le thread python — au prochain dump, ou dans l'attente.

// (inclus depuis fdwritestream.h, après serializejson.h dont il emprunte
// l'encodeur base64 : serializejson_b64_encode)

#ifndef RAPIDJSON_WriterThread_H_
#define RAPIDJSON_WriterThread_H_

#include <Python.h>
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <condition_variable>
#include <deque>
#include <functional>
#include <mutex>
#include <sys/types.h>
#include <thread>
#if defined(__SSE2__)
#include <emmintrin.h>
#endif

#ifdef _WIN32
#include <io.h>
#else
#include <fcntl.h>
#include <sys/statvfs.h>
#include <unistd.h>
#endif

RAPIDJSON_NAMESPACE_BEGIN

// Ce qu'on laisse au système, jamais moins : 5 % de la mémoire totale, et au
// moins 2 Go dans l'absolu (sur une petite machine, 5 % ne protègent rien).
#define RAPIDJSON_PLANCHER_ABSOLU (size_t(2) << 30)
// La disponibilité est relue tous les 64 Mo déposés : 4,5 µs de lecture pour
// 64 Mo produits, c'est-à-dire rien, et assez serré pour ne pas dépasser le
// plancher entre deux contrôles.
#define RAPIDJSON_PAS_DE_CONTROLE (size_t(64) << 20)

// Ce qu'on laisse libre sur le DISQUE : 2 % de ce qui y reste, au plus 1 Go
// (au-delà on refuserait d'écrire alors qu'il y a la place) et au moins 16 Mo
// (en deçà la marge ne protège plus de rien).
#define RAPIDJSON_MARGE_DISQUE_MAX (size_t(1) << 30)
#define RAPIDJSON_MARGE_DISQUE_MIN (size_t(16) << 20)

// Un nombre de /proc/meminfo, en octets ; 0 si on ne sait pas le lire (autre
// système) — le frein est alors sans objet et la file n'est pas bornée.
inline size_t meminfo(const char* cle) {
    FILE* f = fopen("/proc/meminfo", "r");
    if (f == nullptr)
        return 0;
    // ligne à ligne : toutes les entrées ne finissent pas par « kB », un
    // format unique appliqué au fichier entier se décalerait sur les autres
    size_t longueur = strlen(cle);
    char ligne[256];
    unsigned long ko;
    size_t trouve = 0;
    while (fgets(ligne, sizeof ligne, f) != nullptr) {
        if (strncmp(ligne, cle, longueur) == 0
                && sscanf(ligne + longueur, "%lu", &ko) == 1) {
            trouve = (size_t) ko << 10;
            break;
        }
    }
    fclose(f);
    return trouve;
}

// Position du premier caractère à échapper en json (taille s'il n'y en a
// pas) : même prédicat que Writer::EscapeTranche (« " », « \ », <= 0x1F
// non signé), en lecture seule — c'est ce qui autorise le zéro-copie des
// blocs Echappe, dont ecritEchappe saute ainsi les plages propres.
inline size_t sjPremierEchappement(const char* str, size_t taille) {
    size_t k = 0;
#if defined(__SSE2__)
    const __m128i quote = _mm_set1_epi8('"');
    const __m128i backslash = _mm_set1_epi8('\\');
    const __m128i commande = _mm_set1_epi8(0x1F);
    while (k + 16 <= taille) {
        __m128i chunk = _mm_loadu_si128((const __m128i*) (str + k));
        __m128i hits = _mm_or_si128(
            _mm_or_si128(_mm_cmpeq_epi8(chunk, quote),
                         _mm_cmpeq_epi8(chunk, backslash)),
            _mm_cmpeq_epi8(_mm_min_epu8(chunk, commande), chunk));
        int masque = _mm_movemask_epi8(hits);
        if (masque)
            return k + (size_t) __builtin_ctz((unsigned) masque);
        k += 16;
    }
#endif
    for (; k < taille; k++) {
        const char c = str[k];
        if (c == '\\' || c == '"' || (unsigned char) c <= 0x1F)
            return k;
    }
    return taille;
}

// Forme échappée de l'octet — MÊME GRAPHIE que Writer::EchappeUn et
// sj_ref_append_escape (formes courtes \\ \" \t \n \r, le reste des
// commandes C0 en « \u00xx » minuscule) : l'identité à l'octet du document
// entre les deux voies est verrouillée par test. Rend le curseur avancé.
inline char* sjEchappeUn(char c, char* d) {
    static const char HEXA[] = "0123456789abcdef";
    const unsigned char u = (unsigned char) c;
    *d++ = '\\';
    switch (c) {
    case '\\': case '"': *d++ = c;   break;
    case '\t':           *d++ = 't'; break;
    case '\n':           *d++ = 'n'; break;
    case '\r':           *d++ = 'r'; break;
    default:
        *d++ = 'u';
        *d++ = '0';
        *d++ = '0';
        *d++ = HEXA[u >> 4];
        *d++ = HEXA[u & 0xF];
    }
    return d;
}

struct Bloc {
    char* data;
    size_t taille;
    // Brut : écrit tel quel. Base64 : encodé en écrivant, guillemets
    // compris. Echappe : échappé json en écrivant, guillemets EXCLUS —
    // l'appelant les pose autour du bloc. Compresse : compressé blosc2 en
    // écrivant, puis émis « "<base64>","<étiquette>" » — l'étiquette se
    // CHOISIT là, selon que la trame gagne ou non ; l'appelant pose les
    // crochets de la liste autour.
    enum Mode : char { Brut, Base64, Echappe, Compresse };
    Mode mode;
    // référence FORTE à l'objet python dont data est le tampon interne
    // (grand str remis en zéro-copie) : le thread, qui n'a pas le
    // verrou global, ne la relâche pas lui-même — il la range dans
    // enVol().aLiberer, vidée par le prochain point qui tient le GIL
    PyObject* ref;
    // où le bloc commence dans le fichier, en compte BRUT (Echappe compté
    // tel quel, Compresse compté ZÉRO) : l'ancre des expansions relevées
    // à l'écriture
    size_t posBrut;
    // Compresse seulement : la recette, figée au dépôt sous GIL — le
    // réglage global de threads peut changer derrière
    int clevel;
    int compcode;
    int16_t nthreads;
};

// Ce que taille octets deviennent en base64, guillemets compris.
inline size_t tailleBase64(size_t taille) {
    return 4 * ((taille + 2) / 3) + 2;
}

class WriterThread;

// Les écrivains lâchés, ceux dont l'écriture continue après le retour de dump.
// Tout ce qui est partagé entre le thread d'écriture et le thread python passe
// par ce verrou-ci, qui ne meurt jamais — celui de l'écrivain, lui, disparaît
// avec lui.
struct EnVol {
    std::mutex m;
    std::condition_variable vide;
    std::deque<WriterThread*> liste;
    size_t nombre = 0;                   // pas encore posés sur le disque
    int err = 0;                         // errno du premier qui a raté
    // références rendues par les threads d'écriture (blocs zéro-copie
    // écrits), à relâcher sous GIL — voir WriterThread::libereRefs
    std::vector<PyObject*> aLiberer;
};

inline EnVol& enVol() {
    static EnVol e;
    return e;
}

class WriterThread {
public:

    // Le descripteur devient celui de l'écrivain dès qu'il est lâché : c'est
    // lui qui le refermera, l'appelant ayant depuis longtemps refermé le sien.
    // `fd_` vaut -1 pour un écrivain qui n'écrit RIEN : il ne porte alors
    // qu'une tâche de fin (rangeApres), et c'est ce qui permet de ranger
    // l'index d'un fichier rempli par appends hors du thread appelant, sans
    // avoir à rouvrir le document pour la forme.
    WriterThread(int fd_) {
        fd = fd_;
        err = 0;
        octets = 0;
        pousses = 0;
        depuisControle = 0;
#ifdef _WIN32
        debut = 0;
#else
        // là où le document commence dans le fichier : ce n'est pas toujours
        // zéro (append se replace derrière le dernier maillon de la liste)
        off_t ou = fd < 0 ? -1 : lseek(fd, 0, SEEK_CUR);
        debut = ou < 0 ? 0 : ou;
#endif
        fini = false;
        pose = false;
        tue = false;
        th = std::thread(&WriterThread::boucle, this);
    }

    // Écrit ce qui reste, puis rend la main.
    ~WriterThread() { termine(); }

    // Ferme l'écrivain et rend son errno. À préférer au destructeur quand
    // l'erreur intéresse : la tâche de fin ne s'exécute qu'ici, si bien qu'un
    // `erreur()` lu avant la destruction ne verrait que les écritures.
    int termine() {
        {
            std::unique_lock<std::mutex> verrou(m);
            fini = true;
        }
        aBloc.notify_one();
        if (th.joinable())
            th.join();
        return erreur();
    }

    // Ce qu'il reste à faire une fois le DERNIER octet posé, exécuté par le
    // thread d'écriture avant qu'il ne se signale terminé — ranger l'index du
    // document, aujourd'hui, et c'est tout son coût qui sort du retour de
    // dump. La tâche rend un errno, 0 si tout va bien, et n'est pas appelée si
    // l'écriture a déjà raté : un index sur un document tronqué vaut moins que
    // pas d'index. Elle ne doit toucher aucun objet python — comme les blocs,
    // et pour la même raison, elle tourne quand plus personne n'attend.
    void rangeApres(std::function<int()> tache) {
        std::unique_lock<std::mutex> verrou(m);
        apres = std::move(tache);
    }

    // Prend possession du bloc : il sera libéré par le thread, une fois écrit.
    // `Base64` le fait ENCODER par le thread au moment de l'écrire, plutôt que
    // par la sérialisation qui le dépose — et c'est alors la trame compressée,
    // plus petite d'un quart, qui attend en mémoire. `Echappe` lui fait faire
    // le scan ET l'échappement json : le déposant n'a même pas lu le bloc.
    // `ref` non nul : data est le tampon INTERNE de cet objet python (grand
    // str), pris en zéro-copie — le bloc n'est pas libéré après
    // écriture, la référence est rangée pour le prochain point sous GIL.
    void pousse(char* data, size_t taille, Bloc::Mode mode = Bloc::Brut,
                PyObject* ref = nullptr) {
        {
            std::unique_lock<std::mutex> verrou(m);
            file.push_back(Bloc{data, taille, mode, ref,
                                (size_t) debut + pousses});
            octets += taille;
        }
        aBloc.notify_one();
        depuisControle += taille;
        // Echappe est compté BRUT : la taille écrite (chaque échappement
        // grossit de 1 ou 5 octets) n'est pas connue d'avance, depose()
        // devient un PLANCHER. L'index de positions, seul consommateur
        // exact, se rattrape au rangement : le fil d'écriture relève chaque
        // expansion (voir boucle), et la tâche rangeApres — qui tourne dans
        // ce même fil, après le dernier bloc — corrige les entrées.
        // reservePlace peut sous-réserver d'autant, le contrôle d'espace
        // garde sa marge.
        pousses += mode == Bloc::Base64 ? tailleBase64(taille) : taille;
    }

    // Dépose un bytes/bytearray à COMPRESSER par le thread (Bloc::Compresse).
    // Compté ZÉRO dans `pousses` : la taille émise (trame en base64 si elle
    // gagne, source sinon, étiquette comprise) n'est connue qu'à l'écriture —
    // le fil la relève ENTIÈRE en delta, comme les expansions des blocs
    // Echappe, et l'index de positions s'en corrige au rangement.
    void pousseCompresse(char* data, size_t taille, PyObject* ref,
                         int clevel, int compcode) {
        {
            std::unique_lock<std::mutex> verrou(m);
            file.push_back(Bloc{data, taille, Bloc::Compresse, ref,
                                (size_t) debut + pousses, clevel, compcode,
                                (int16_t) serializejson_blosc2_nthreads_global});
            octets += taille;
        }
        aBloc.notify_one();
        depuisControle += taille;
    }

    // Position dans le FICHIER juste après le dernier octet déposé. `debut` est
    // lu du descripteur à la construction et `pousses` compte les octets une
    // fois ENCODÉS (base64 compris) : c'est ce qui permet à l'écrivain d'indexer
    // ce qu'il écrit sans jamais supposer où il écrit.
    size_t depose() const { return (size_t) debut + pousses; }

    // Ce que les blocs Echappe ont ajouté au compte brut : (posBrut du bloc,
    // octets d'expansion), dans l'ordre du flux. Une position d'index p en
    // compte brut se corrige en ajoutant les expansions des blocs dont
    // posBrut < p — une borne d'entrée ne tombe jamais DANS un str, le
    // guillemet ouvrant la précède et le fermant vient derrière le bloc.
    // À lire depuis la tâche rangeApres ou après termine() SEULEMENT : le
    // vecteur n'appartient qu'au thread d'écriture.
    const std::vector<std::pair<size_t, size_t>>& expansions() const {
        return deltas;
    }

    // Réserve sur le disque la place du document. Appelé une fois, la
    // sérialisation FINIE : sa taille exacte est alors connue, si bien que le
    // manque de place devient une erreur de dump, relevée avant son retour, au
    // lieu d'une écriture qui rate quand plus personne n'est là pour
    // l'entendre.
    void reservePlace() {
#ifndef _WIN32
        size_t restant;
        {
            std::unique_lock<std::mutex> verrou(m);
            if (err != 0)
                return;              // déjà raté : la place n'y changera rien
            restant = octets;        // ce qui n'est pas encore sur le disque
        }
        struct statvfs fs;
        if (fstatvfs(fd, &fs) == 0) {
            size_t libre = (size_t) fs.f_bavail * (size_t) fs.f_frsize;
            size_t marge = libre / 50;
            if (marge > RAPIDJSON_MARGE_DISQUE_MAX)
                marge = RAPIDJSON_MARGE_DISQUE_MAX;
            else if (marge < RAPIDJSON_MARGE_DISQUE_MIN)
                marge = RAPIDJSON_MARGE_DISQUE_MIN;
            if (restant + marge > libre) {
                manque(ENOSPC);
                return;
            }
        }
#ifdef __linux__
        // fallocate(2), et NON posix_fallocate : quand le système de fichiers
        // ne sait pas réserver, celui-ci se rabat sur une réécriture des
        // octets du fichier — c'est-à-dire, ici, sur une course avec le thread
        // qui est en train de les écrire. Celui-là rend EOPNOTSUPP, et le
        // contrôle ci-dessus reste alors la seule garantie.
        if (pousses != 0 && fallocate(fd, 0, debut, (off_t) pousses) != 0
                && errno != EOPNOTSUPP && errno != ENOSYS
                && errno != EINVAL && errno != ESPIPE)
            // « ne sait pas réserver » n'est pas un refus : seul un vrai refus
            // (plus de place, quota, taille maximale de fichier) en est un
            manque(errno);
#endif
#endif
    }

    // Freine la sérialisation quand la mémoire vive se raréfie. On attend que
    // la file soit retombée à la MOITIÉ de son poids, pas qu'un bloc parte :
    // sinon on repartirait pour se rebloquer au bloc suivant, et le frein
    // deviendrait une oscillation. Le verrou global est rendu pendant
    // l'attente, sans quoi une sérialisation qui freine gèlerait tous les
    // autres threads python.
    void freineSiBesoin() {
        if (depuisControle < RAPIDJSON_PAS_DE_CONTROLE)
            return;
        depuisControle = 0;
        size_t dispo = meminfo("MemAvailable:");
        if (dispo == 0 || dispo > plancher())
            return;
        Py_BEGIN_ALLOW_THREADS
        std::unique_lock<std::mutex> verrou(m);
        size_t cible = octets / 2;
        while (octets > cible && err == 0)
            aVide.wait(verrou);
        Py_END_ALLOW_THREADS
    }

    // L'appelant s'en va : l'écrivain finit seul. Il n'est plus touché ensuite
    // — sa destruction viendra d'un balayage ultérieur, jamais de son thread.
    // `dejaVue` quand l'appelant a déjà relevé l'erreur en exception : sans
    // quoi la même serait relevée une seconde fois par la prochaine attente.
    void laisseFiler(bool dejaVue = false) {
        libereRefs();                    // appelé sous GIL : point de vidage
        {
            std::unique_lock<std::mutex> verrou(m);
            tue = dejaVue;
        }
        balaye();                        // avant de s'ajouter, pas après
        {
            std::unique_lock<std::mutex> verrou(enVol().m);
            enVol().liste.push_back(this);
            enVol().nombre += 1;
        }
        {
            std::unique_lock<std::mutex> verrou(m);
            fini = true;
        }
        aBloc.notify_one();
    }

    // Attend que CET écrivain ait tout posé — l'écriture bloquante, celle que
    // demande qui veut savoir en sortant de dump que tout est sur le disque.
    void attends() {
        Py_BEGIN_ALLOW_THREADS
        {
            std::unique_lock<std::mutex> verrou(m);
            while (octets != 0 && err == 0)
                aVide.wait(verrou);
        }
        Py_END_ALLOW_THREADS
        libereRefs();
    }

    // Attend que toutes les écritures en vol soient posées sur le disque, et
    // rend l'errno de la première qui a raté (une seule fois : il est
    // consommé). Détruit au passage tout ce qui traînait.
    static int attendsToutes() {
        int err;
        Py_BEGIN_ALLOW_THREADS
        {
            std::unique_lock<std::mutex> verrou(enVol().m);
            while (enVol().nombre != 0)
                enVol().vide.wait(verrou);
            err = enVol().err;
            enVol().err = 0;
        }
        balaye();
        Py_END_ALLOW_THREADS
        libereRefs();
        return err;
    }

    // errno de la première écriture ratée, 0 sinon
    int erreur() const {
        std::unique_lock<std::mutex> verrou(m);
        return err;
    }

    // Relâche les références des blocs zéro-copie déjà écrits. EXIGE le GIL.
    // Appelé partout où l'on repasse de toute façon sous GIL près des
    // écrivains : nouveau dump, écrivain lâché, attentes. Le DECREF se fait
    // hors du verrou partagé — il peut détruire l'objet.
    static void libereRefs() {
        std::vector<PyObject*> refs;
        {
            std::unique_lock<std::mutex> verrou(enVol().m);
            refs.swap(enVol().aLiberer);
        }
        for (size_t i = 0; i < refs.size(); ++i)
            Py_DECREF(refs[i]);
    }

private:

    // Détruit les écrivains dont le thread est sorti. La destruction joint le
    // thread, ce qui est immédiat puisqu'il a fini ; et elle a lieu hors du
    // verrou partagé, que le destructeur n'a pas à reprendre.
    static void balaye() {
        std::deque<WriterThread*> finis;
        {
            std::unique_lock<std::mutex> verrou(enVol().m);
            std::deque<WriterThread*>& liste = enVol().liste;
            for (size_t i = liste.size(); i > 0; --i) {
                WriterThread* e = liste[i - 1];
                if (e->pose) {
                    finis.push_back(e);
                    liste.erase(liste.begin() + (i - 1));
                }
            }
        }
        for (size_t i = 0; i < finis.size(); ++i)
            delete finis[i];
    }

    // Le disque a dit non : les blocs encore en file ne seront pas écrits,
    // `ecrit` les laissera passer sans s'acharner.
    void manque(int raison) {
        std::unique_lock<std::mutex> verrou(m);
        if (err == 0)
            err = raison;
    }

    // Calculé une fois : la mémoire totale ne bouge pas.
    static size_t plancher() {
        static const size_t valeur = std::max(meminfo("MemTotal:") / 20,
                                              RAPIDJSON_PLANCHER_ABSOLU);
        return valeur;
    }

    void boucle() {
        for (;;) {
            Bloc bloc;
            {
                std::unique_lock<std::mutex> verrou(m);
                while (file.empty() && !fini)
                    aBloc.wait(verrou);
                if (file.empty())        // plus rien à écrire, et c'est fini
                    break;
                bloc = file.front();
                file.pop_front();
            }
            int rate;
            if (bloc.mode == Bloc::Base64) {
                rate = ecritBase64(bloc.data, bloc.taille);
            } else if (bloc.mode == Bloc::Echappe) {
                size_t expansion = 0;
                rate = ecritEchappe(bloc.data, bloc.taille, expansion);
                // relevé pour le rangement de l'index (voir expansions()) ;
                // blocs écrits dans l'ordre du flux → posBrut croît, la
                // recherche binaire du rangement s'en sert
                if (expansion != 0)
                    deltas.push_back({bloc.posBrut, expansion});
            } else if (bloc.mode == Bloc::Compresse) {
                size_t emis = 0;
                rate = ecritCompresse(bloc, emis);
                // compté ZÉRO au dépôt : la taille émise entière est le delta
                deltas.push_back({bloc.posBrut, emis});
            } else {
                rate = ecrit(bloc.data, bloc.taille);
            }
            if (bloc.ref != nullptr) {
                // tampon interne d'un objet python : rien à libérer ici, la
                // référence part vers le prochain point qui tient le GIL
                std::unique_lock<std::mutex> verrou(enVol().m);
                enVol().aLiberer.push_back(bloc.ref);
            } else {
                free(bloc.data);
            }
            {
                std::unique_lock<std::mutex> verrou(m);
                octets -= bloc.taille;
                if (rate && err == 0)
                    err = rate;
            }
            aVide.notify_all();          // le frein attend cette descente
        }
        std::function<int()> tache;
        {
            std::unique_lock<std::mutex> verrou(m);
            tache.swap(apres);
        }
        if (tache && erreur() == 0) {
            const int rate = tache();
            if (rate)
                manque(rate);
        }
        if (cctx != nullptr) {
            sj_blosc2_free_ctx(cctx);
            cctx = nullptr;
        }
        signalePose();
    }

    // Tout est sur le disque. Ni destruction ni verrou propre au-delà d'ici :
    // seul le verrou partagé, qui survit à l'objet.
    void signalePose() {
        int mien;
        bool lache;
        {
            std::unique_lock<std::mutex> verrou(m);
            mien = tue ? 0 : err;
        }
        {
            std::unique_lock<std::mutex> verrou(enVol().m);
            lache = !enVol().liste.empty()
                    && std::find(enVol().liste.begin(), enVol().liste.end(),
                                 this) != enVol().liste.end();
            if (!lache)
                return;                  // l'appelant attend : il fera le reste
            if (mien && enVol().err == 0)
                enVol().err = mien;
            enVol().nombre -= 1;
            pose = true;
            if (fd >= 0) {
#ifdef _WIN32
                _close(fd);
#else
                close(fd);
#endif
            }
        }
        enVol().vide.notify_all();
    }

    // Encode et écrit d'un même mouvement, par morceaux : un seul tampon de
    // 64 Ko, quelle que soit la taille de la trame. Les coupures tombent sur
    // des multiples de 3 octets source pour que le padding ne vienne qu'à la
    // toute fin, et les guillemets voyagent dans le tampon plutôt que dans
    // deux écritures d'un octet.
    int ecritBase64(const char* data, size_t taille) {
        const unsigned char* src = (const unsigned char*) data;
        char tampon[65536];
        const size_t parPasse = (sizeof tampon / 4 - 1) * 3;   // -1 : le guillemet
        char* curseur = tampon;
        *curseur++ = '\"';
        for (;;) {
            size_t prend = taille < parPasse ? taille : parPasse;
            curseur = serializejson_b64_encode(src, prend, curseur);
            src += prend;
            taille -= prend;
            if (taille == 0)
                *curseur++ = '\"';
            int rate = ecrit(tampon, (size_t) (curseur - tampon));
            if (rate || taille == 0)
                return rate;
            curseur = tampon;
        }
    }

    // Compresse et écrit d'un même mouvement — et c'est ICI que l'étiquette
    // se choisit : la trame ne part que si elle est PLUS PETITE que la
    // source (le critère strict du greffon), sinon la source part en base64
    // sous « b64 » ; un échec de compression se replie de même, en silence —
    // le document reste valide, seulement moins compact. Le contexte blosc2
    // est propre au thread, recréé quand la recette change (memcmp de clé,
    // comme le cache global de la voie synchrone) et libéré en fin de
    // boucle. `emis` rend la taille réellement écrite, étiquette comprise.
    int ecritCompresse(const Bloc& bloc, size_t& emis) {
        char* trame = nullptr;
        int csize = -1;
        const size_t destsize = bloc.taille + BLOSC2_MAX_OVERHEAD;
        if ((trame = (char*) malloc(destsize)) != nullptr) {
            blosc2_cparams cparams = sj_bytes_cparams(bloc.compcode,
                                                      bloc.clevel,
                                                      bloc.nthreads);
            SjCctxKey cle = sj_cctx_key(cparams, (int32_t) bloc.taille);
            if (cctx != nullptr && memcmp(&cle, &cctxCle, sizeof cle) != 0) {
                sj_blosc2_free_ctx(cctx);
                cctx = nullptr;
            }
            if (cctx == nullptr) {
                cctx = sj_blosc2_create_cctx(cparams);
                cctxCle = cle;
            }
            if (cctx != nullptr)
                csize = sj_blosc2_compress_ctx(cctx, bloc.data,
                                               (int32_t) bloc.taille, trame,
                                               (int32_t) destsize);
        }
        int rate;
        if (csize > 0 && (size_t) csize < bloc.taille) {
            emis = tailleBase64((size_t) csize) + 13;
            rate = ecritBase64(trame, (size_t) csize);
            if (rate == 0)
                rate = ecrit(",\"b64_blosc2\"", 13);
        } else {
            emis = tailleBase64(bloc.taille) + 6;
            rate = ecritBase64(bloc.data, bloc.taille);
            if (rate == 0)
                rate = ecrit(",\"b64\"", 6);
        }
        free(trame);
        return rate;
    }

    // Échappe et écrit d'un même mouvement : le str n'a même pas été LU par
    // la sérialisation (voir FdWriteStream::RawPyStrPropre, voie entière) —
    // son immuabilité et la référence forte du bloc figent le tampon, le fil
    // d'écriture peut donc faire le scan à sa place. Les plages propres qui
    // rempliraient le tampon partent DROIT du tampon source (zéro-copie) ;
    // le reste — plages courtes, échappements — s'y regroupe pour ne pas
    // dégénérer en write() de quelques octets. `expansion` s'accroît de ce
    // que les échappements ajoutent au compte brut (1 ou 5 octets chacun) :
    // c'est la matière du rangement d'index (voir expansions()).
    int ecritEchappe(const char* data, size_t taille, size_t& expansion) {
        char tampon[65536];
        char* curseur = tampon;
        char* const fin = tampon + sizeof tampon;
        size_t k = 0;
        int rate;
        while (k < taille) {
            size_t propre = sjPremierEchappement(data + k, taille - k);
            if (propre >= sizeof tampon) {
                if (curseur != tampon) {
                    if ((rate = ecrit(tampon, (size_t) (curseur - tampon))))
                        return rate;
                    curseur = tampon;
                }
                if ((rate = ecrit(data + k, propre)))
                    return rate;
                k += propre;
            } else {
                while (propre != 0) {
                    size_t prend = propre < (size_t) (fin - curseur)
                                       ? propre
                                       : (size_t) (fin - curseur);
                    memcpy(curseur, data + k, prend);
                    curseur += prend;
                    k += prend;
                    propre -= prend;
                    if (curseur == fin) {
                        if ((rate = ecrit(tampon, sizeof tampon)))
                            return rate;
                        curseur = tampon;
                    }
                }
            }
            if (k < taille) {            // data[k] est à échapper
                if (fin - curseur < 6) {
                    if ((rate = ecrit(tampon, (size_t) (curseur - tampon))))
                        return rate;
                    curseur = tampon;
                }
                char* avant = curseur;
                curseur = sjEchappeUn(data[k], curseur);
                expansion += (size_t) (curseur - avant) - 1;
                k++;
            }
        }
        if (curseur != tampon)
            return ecrit(tampon, (size_t) (curseur - tampon));
        return 0;
    }

    // write() peut n'en prendre qu'une partie, et être interrompu par un signal
    int ecrit(const char* data, size_t taille) {
        if (erreur())
            return 0;                    // déjà raté : on ne s'acharne pas
        while (taille) {
#ifdef _WIN32
            int ecrits = _write(fd, data, (unsigned int) taille);
#else
            ssize_t ecrits = write(fd, data, taille);
#endif
            if (ecrits < 0) {
                if (errno == EINTR)
                    continue;
                return errno;
            }
            data += ecrits;
            taille -= (size_t) ecrits;
        }
        return 0;
    }

    int fd;
    int err;                             // sous m
    off_t debut;                         // où le document commence
    size_t octets;                       // poids de la file, sous m
    size_t pousses;                      // tout ce qui a été déposé
    size_t depuisControle;               // au déposant seul : pas de verrou
    bool fini;                           // sous m
    bool pose;                           // sous enVol().m
    bool tue;                            // erreur déjà relevée, sous m
    std::deque<Bloc> file;               // sous m
    // expansions des blocs Echappe et Compresse écrits — au thread seul
    std::vector<std::pair<size_t, size_t>> deltas;
    // contexte blosc2 des blocs Compresse — au thread seul, libéré en fin
    // de boucle ; cctxCle dit la recette qu'il incarne
    blosc2_context* cctx = nullptr;
    SjCctxKey cctxCle;
    std::function<int()> apres;          // à faire le dernier octet posé, sous m
    mutable std::mutex m;
    std::condition_variable aBloc;       // un bloc à écrire
    std::condition_variable aVide;       // la file s'est allégée
    std::thread th;
};

RAPIDJSON_NAMESPACE_END

#endif // RAPIDJSON_WriterThread_H_
