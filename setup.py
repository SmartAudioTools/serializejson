import sys
import os
import setuptools
from distutils import sysconfig

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))


README = "README.rst"
CHANGELOG = "CHANGELOG.rst"
LICENSE = "LICENSE.rst"


def version():
    with open(os.path.join(__location__, CHANGELOG), encoding="utf_8") as changelog_file:
        for line in changelog_file.readlines():
            if line.startswith("Version "):
                return line[len("Version "):]
    raise Exception("no valid version in " + CHANGELOG)


def long_description():
    with open(os.path.join(__location__, README), encoding="utf_8") as readme_file:
        readme_str = readme_file.read()
    with open(os.path.join(__location__, CHANGELOG), encoding="utf_8") as changelog_file:
        changelog_str = changelog_file.read()
    return readme_str + "\nHistory\n=======\n\n" + changelog_str


with open('./rapidjson/version.txt', encoding='utf-8') as f:
    RAPIDJSON_VERSION = f.read()


cxx = sysconfig.get_config_var('CXX')
if cxx and 'g++' in cxx:
    # Avoid warning about invalid flag for C++
    for varname in ('CFLAGS', 'OPT'):
        value = sysconfig.get_config_var(varname)
        if value and '-Wstrict-prototypes' in value:
            value = value.replace('-Wstrict-prototypes', '')
            sysconfig.get_config_vars()[varname] = value


if __name__ == "__main__":
    setuptools.setup(
        name="serializejson",
        version=version(),
        description="A python library for fast serialization and deserialization of complex Python objects into JSON.",
        long_description=long_description(),
        # "text/markdown " si la long_description est au format markdown et pas restructuredText
        long_description_content_type="text/x-rst",
        author="Baptiste de La Gorce",
        author_email="baptiste.delagorce@smartaudiotools.com",
        url="https://github.com/SmartAudioTools/serializejson",
        download_url="https://github.com/SmartAudioTools/serializejson/tarball/master",
        license="Prosperity Public License 3.0.0 and Patron License 1.0.0",
        keywords="pickle json serialize dump dumps rapidjson base64",
        packages=setuptools.find_packages(exclude=("tests",)),
        python_requires=">=3",
        install_requires=[
            'importlib_metadata; python_version < "3.8"',
            "pybase64>=1.1.1",
            "apply",
            "blosc",
        ],
        extras_require={
            "dev": [
                "pytest",
                "numpy",
                "qtpy",
                "PyQt5",
            ],
            "test": [
                "pytest",
                "numpy",
            ],
        },
        include_package_data=True,
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
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            'Programming Language :: Python :: 3.10',
            'Programming Language :: Python :: 3.11',
        ],
        zip_safe=False,
        data_files=[("", [LICENSE, CHANGELOG, "pyproject.toml"])],
        ext_modules=[
            setuptools.Extension(
                'serializejson.rapidjson',
                sources=['./rapidjson/rapidjson.cpp'],
                include_dirs=['./rapidjson'],
                define_macros=[('PYTHON_RAPIDJSON_VERSION', RAPIDJSON_VERSION)],
                extra_compile_args=['-pedantic', '-std=c++11']
            )
        ],
    )
