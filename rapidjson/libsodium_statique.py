# Construit libsodium.a depuis le clone épinglé libsodium/ (hors de l'arbre
# source), pour la lier dans le module rapidjson : scrypt et ChaCha20-Poly1305
# du chiffrement age, sans dépendance à l'exécution — même chaîne que la roue
# WebAssembly (scripts/construit_wasm.sh). Seules ces deux primitives restent
# au lien. Construite une fois, puis réutilisée tant que le fichier existe.
import os
import subprocess

DEPOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(DEPOT, "libsodium")
COMMIT = "77e1ce5d6dee871c49ef211222ba18ef0c486bda"  # 1.0.22-RELEASE


def construit(travail=os.path.join(DEPOT, "build", "sodium")):
    """Chemin de libsodium.a, construite dans `travail` si elle n'y est pas.

    Sources : le clone libsodium/ du dépôt, sinon (sdist, pip install git+…)
    un clone fait ici, au même commit.
    """
    source = SOURCE
    if not os.path.isdir(source):
        source = os.path.join(os.path.dirname(travail), "libsodium-src")
        if not os.path.isdir(source):
            subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", "1.0.22-RELEASE",
                            "https://github.com/jedisct1/libsodium.git", source], check=True)
    try:
        commit = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", source, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    if commit != COMMIT:
        raise SystemExit(
            f"{source} n'est pas au commit {COMMIT} :\n"
            f"git clone --branch 1.0.22-RELEASE https://github.com/jedisct1/libsodium.git {SOURCE}")
    lib = os.path.join(travail, "src", "libsodium", ".libs", "libsodium.a")
    if not os.path.exists(lib):
        os.makedirs(travail, exist_ok=True)
        # --with-pic : liée dans un module partagé ; asm et SIMD gardés, choisis
        # à l'exécution par sodium_init (appelé à l'import du module). CFLAGS
        # imposé : celui de l'environnement (-march=native ici) ferait un
        # binaire limité au processeur qui l'a construit
        env = dict(os.environ, CFLAGS="-O3")
        for commande in ([os.path.join(source, "configure"), "--disable-shared", "--with-pic"],
                         ["make", f"-j{os.cpu_count() or 1}"]):
            with open(os.path.join(travail, os.path.basename(commande[0]) + ".log"), "w") as journal:
                subprocess.run(commande, cwd=travail, env=env, stdout=journal, stderr=subprocess.STDOUT, check=True)
    return lib
