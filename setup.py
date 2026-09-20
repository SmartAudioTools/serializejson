import os
import platform
import shutil
import subprocess
import sys
import sysconfig

import setuptools
from setuptools.command.build_ext import build_ext

__location__ = os.path.dirname(os.path.realpath(__file__))


README = "README.rst"
CHANGELOG = "CHANGELOG.rst"
# bibliothèque blosc2 patchée (rapidjson/blosc2_determinisme.patch), chargée
# par dlopen depuis le dossier du module compilé (tools.py)
BLOSC2_LIB = os.path.join("rapidjson", "libblosc2_serializejson.so")


def version():
    with open(os.path.join(__location__, CHANGELOG), encoding="utf_8") as changelog_file:
        for line in changelog_file.readlines():
            if line.startswith("Version "):
                return line[len("Version ") :].strip()
    raise Exception("no valid version in " + CHANGELOG)


def long_description():
    with open(os.path.join(__location__, README), encoding="utf_8") as readme_file:
        readme_str = readme_file.read()
    with open(os.path.join(__location__, CHANGELOG), encoding="utf_8") as changelog_file:
        changelog_str = changelog_file.read()
    return readme_str + "\nHistory\n=======\n\n" + changelog_str


with open(os.path.join(__location__, "rapidjson", "version.txt"), encoding="utf-8") as f:
    RAPIDJSON_VERSION = f.read().strip()


# mêmes options que rapidjson/setup.py (construction de développement)
define_macros = [("PYTHON_RAPIDJSON_VERSION", RAPIDJSON_VERSION)]
compile_args = []
link_args = []
cxx = sysconfig.get_config_var("CXX")
if cxx and "g++" in cxx:
    # Avoid warning about invalid flag for C++
    for varname in ("CFLAGS", "OPT"):
        value = sysconfig.get_config_var(varname)
        if value and "-Wstrict-prototypes" in value:
            sysconfig.get_config_vars()[varname] = value.replace("-Wstrict-prototypes", "")
    compile_args = [
        "-pedantic", "-Wno-long-long", "-std=c++11",
        "-O3", "-fno-semantic-interposition",
        "-pthread",  # thread d'écriture (writerthread.h)
    ]
    link_args = ["-pthread"]
    if platform.machine() in ("x86_64", "AMD64"):
        # rapidjson.cpp pose RAPIDJSON_SSE42 : sans ce drapeau, un python aux
        # CFLAGS génériques (manylinux) refuse les intrinsèques SSE4.2
        compile_args.append("-msse4.2")


class build_ext_pgo(build_ext):
    """build_ext + copie de la libblosc2 patchée à côté du module compilé.

    SERIALIZEJSON_PGO=auto : optimisation guidée par profil en deux passes,
    à objets identiques (les .gcda sont retrouvés par leur chemin) —
    compilation instrumentée, exécution de rapidjson/pgo_workload.py sur le
    paquet construit, recompilation guidée.
    """

    def build_extensions(self):
        if os.environ.get("SERIALIZEJSON_PGO") != "auto":
            super().build_extensions()
            self._copie_blosc2()
            return
        self.force = True
        for passe, drapeaux, liens in (
            ("generate", ["-fprofile-generate"], ["-fprofile-generate"]),
            ("use", ["-fprofile-use", "-fprofile-correction"], []),
        ):
            for ext in self.extensions:
                ext.extra_compile_args = compile_args + drapeaux
                ext.extra_link_args = link_args + liens
            super().build_extensions()
            self._copie_blosc2()
            if passe == "generate":
                racine = os.path.dirname(os.path.dirname(self.get_ext_fullpath("serializejson.rapidjson")))
                # sans .pyc : ils finiraient dans la roue
                env = dict(os.environ, SERIALIZEJSON_PGO_LIB=os.path.abspath(racine), PYTHONDONTWRITEBYTECODE="1")
                subprocess.check_call(
                    [sys.executable, os.path.join(__location__, "rapidjson", "pgo_workload.py")], env=env
                )

    def _copie_blosc2(self):
        source = os.path.join(__location__, BLOSC2_LIB)
        if not os.path.exists(source):
            return
        destinations = {os.path.dirname(self.get_ext_fullpath("serializejson.rapidjson"))}
        # pip install -e : setuptools recopie le module compilé dans les sources
        # (serializejson/), mais pas cette lib, que tools.py cherche à côté de lui ;
        # sans elle, repli silencieux sur une compression non déterministe
        if self.editable_mode:
            destinations.add(os.path.join(__location__, "serializejson"))
        for destination in destinations:
            shutil.copy2(source, os.path.join(destination, os.path.basename(BLOSC2_LIB)))


if __name__ == "__main__":
    setuptools.setup(
        name="serializejson",
        version=version(),
        description="A python library for fast serialization and deserialization of complex Python objects into JSON.",
        long_description=long_description(),
        long_description_content_type="text/x-rst",
        author="Baptiste de La Gorce",
        author_email="baptiste.delagorce@smartaudiotools.com",
        url="https://github.com/SmartAudioTools/serializejson",
        license="Prosperity Public License 3.0.0 and Patron License 1.0.0",
        keywords="pickle json serialize dump dumps rapidjson base64",
        packages=setuptools.find_packages(include=("serializejson", "serializejson.*")),
        python_requires=">=3.10",
        install_requires=["apply"],
        extras_require={
            "dev": ["pytest", "numpy", "qtpy6", "PySide6"],
            "test": ["pytest", "numpy"],
            "crypto": ["cryptography>=47"],
        },
        project_urls={
            "Documentation": "https://smartaudiotools.github.io/serializejson",
            "Funding": "https://github.com/sponsors/SmartAudioTools",
            "Source": "https://github.com/SmartAudioTools/serializejson",
            "Tracker": "https://github.com/SmartAudioTools/serializejson/issues",
        },
        classifiers=[
            "Development Status :: 3 - Alpha",
            "Intended Audience :: Developers",
            "License :: Free for non-commercial use",
            "Operating System :: POSIX :: Linux",
            "Programming Language :: C++",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "Programming Language :: Python :: 3.12",
            "Programming Language :: Python :: 3.13",
            "Programming Language :: Python :: 3.14",
        ],
        zip_safe=False,
        ext_modules=[
            setuptools.Extension(
                "serializejson.rapidjson",
                sources=["rapidjson/rapidjson.cpp"],
                include_dirs=["rapidjson"],
                define_macros=define_macros,
                extra_compile_args=compile_args,
                extra_link_args=link_args,
            )
        ],
        cmdclass={"build_ext": build_ext_pgo},
    )
