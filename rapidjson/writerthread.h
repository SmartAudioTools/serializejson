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
#include <mutex>
#include <sys/types.h>
#include <thread>

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

struct Bloc {
    char* data;
    size_t taille;
    bool base64;     // à encoder en écrivant, guillemets compris
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
};

inline EnVol& enVol() {
    static EnVol e;
    return e;
}

class WriterThread {
public:

    // Le descripteur devient celui de l'écrivain dès qu'il est lâché : c'est
    // lui qui le refermera, l'appelant ayant depuis longtemps refermé le sien.
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
        // zéro (append rouvre et se replace avant le crochet fermant)
        off_t ou = lseek(fd, 0, SEEK_CUR);
        debut = ou < 0 ? 0 : ou;
#endif
        fini = false;
        pose = false;
        tue = false;
        th = std::thread(&WriterThread::boucle, this);
    }

    // Écrit ce qui reste, puis rend la main.
    ~WriterThread() {
        {
            std::unique_lock<std::mutex> verrou(m);
            fini = true;
        }
        aBloc.notify_one();
        th.join();
    }

    // Prend possession du bloc : il sera libéré par le thread, une fois écrit.
    // `base64` le fait ENCODER par le thread au moment de l'écrire, plutôt que
    // par la sérialisation qui le dépose — et c'est alors la trame compressée,
    // plus petite d'un quart, qui attend en mémoire.
    void pousse(char* data, size_t taille, bool base64 = false) {
        {
            std::unique_lock<std::mutex> verrou(m);
            file.push_back(Bloc{data, taille, base64});
            octets += taille;
        }
        aBloc.notify_one();
        depuisControle += taille;
        pousses += base64 ? tailleBase64(taille) : taille;
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
        std::unique_lock<std::mutex> verrou(m);
        while (octets != 0 && err == 0)
            aVide.wait(verrou);
        Py_END_ALLOW_THREADS
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
        return err;
    }

    // errno de la première écriture ratée, 0 sinon
    int erreur() const {
        std::unique_lock<std::mutex> verrou(m);
        return err;
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
            int rate = bloc.base64 ? ecritBase64(bloc.data, bloc.taille)
                                   : ecrit(bloc.data, bloc.taille);
            free(bloc.data);
            {
                std::unique_lock<std::mutex> verrou(m);
                octets -= bloc.taille;
                if (rate && err == 0)
                    err = rate;
            }
            aVide.notify_all();          // le frein attend cette descente
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
#ifdef _WIN32
            _close(fd);
#else
            close(fd);
#endif
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
    mutable std::mutex m;
    std::condition_variable aBloc;       // un bloc à écrire
    std::condition_variable aVide;       // la file s'est allégée
    std::thread th;
};

RAPIDJSON_NAMESPACE_END

#endif // RAPIDJSON_WriterThread_H_
