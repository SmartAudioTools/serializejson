"""Setup script for the DEODR project."""

from setuptools import setup, find_packages




libname = "SmartFramework"

setup(
    name=libname,
    version="0.0.1",
    author="Baptiste de La Gorce",
    author_email="baptiste.delagorce@smartaudiotools.com ",
    description="A python library for fast serialization (and deserialization) of complex Python objects into JSON.",
    url="https://github.com/SmartAudioTools/serializejson",
    license="MIT",
    packages=find_packages(),
    package_data={"SmartFramework": ["*.pyx", "*.pxd", "data/*.*", "data/**/*.*"]},
    data_files=[("serialized", ["serialized/*.json","serialized/*.txt"])],
    ext_modules=[],  # additional source file(s)),
    include_dirs=[],
    setup_requires=[],
    install_requires=[],
)
