"""Setup script for the DEODR project."""

from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="serializejson",
    version="0.0.1",
    description="A python library for fast serialization (and deserialization) of complex Python objects into JSON.",
    long_description=long_description,  # le contenu de notre fichier README.md s’affichera sur la future page de notre bibliothèque sur PyPI.
    long_description_content_type="text/markdown",
    author="Baptiste de La Gorce",
    author_email="baptiste.delagorce@smartaudiotools.com",
    url="https://github.com/SmartAudioTools/serializejson",
    license="MIT",
    packages=find_packages(),
    install_requires=[
        "pybase64",
        "python-rapidjson",
    ],  # libraries qui seront automatiquement installées lorsque nous installerons notre librairie depuis l’extérieur.  contrairement à ce qu’il y avait dans le fichier requirements.txt,  on ne fixe pas précisement les versions des dépendances, pour éviter un éventuel conflit de versions si une application qui utilisait la librairie dépendait elle-même d’une version précise d'un librairie. Si la librairie n'est pas compatible avec n’importe quelle version des dépendances, restreindre les versions compatibles, par exemple : requests>=2.0.0,<3.
    extras_require={
        "dev": [
            "apply",
            "numpy",
        ],  # dépendances nécessaires lorsque l’on développe la librairie, notamment les dépendances utilisées dans les tests unitaires. Mais elles ne sont pas nécessaires pour le bon usage de la librairie dans le cas nominal.
    },
    # package_data={"SmartFramework": ["*.pyx", "*.pxd", "data/*.*", "data/**/*.*"]},
    # data_files=[("serialized", ["serialized/*.json", "serialized/*.txt"])],
    # ext_modules=[],  # additional source file(s)),
    # include_dirs=[],
    # setup_requires=[],
)
