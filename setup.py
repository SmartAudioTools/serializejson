import setuptools
import os 

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))


README = "README.rst"
CHANGELOG = "CHANGELOG.rst"
LICENSE = "LICENSE.txt"

def version():
    with open(os.path.join(__location__, CHANGELOG)) as changelog_file:
        for line in changelog_file.readlines():
            if line.startswith("Version "):
                return line[len("Version "):] 
    raise Exception("no valid version in "+CHANGELOG)
                
def long_description():
    with open(os.path.join(__location__, README)) as readme_file:
        readme_str = readme_file.read()
    with open(os.path.join(__location__, CHANGELOG)) as changelog_file:
        changelog_str = changelog_file.read()
    return readme_str + '\n# History\n'  + changelog_str
        
if __name__ == '__main__':
    setuptools.setup(
        name="serializejson",
        version=version(),
        description="A python library for fast serialization and deserialization of complex Python objects into JSON.",
        long_description=long_description(),  
        long_description_content_type="text/markdown",
        author="Baptiste de La Gorce",
        author_email="baptiste.delagorce@smartaudiotools.com",
        url="https://github.com/SmartAudioTools/serializejson",
        download_url = "https://github.com/SmartAudioTools/serializejson/tarball/master",
        license="MIT",
        keywords="pickle json serialize dump dumps rapidjson base64",
        packages=setuptools.find_packages(exclude=("tests",)),
        python_requires='>=3',
        install_requires=[
            'importlib_metadata; python_version < "3.8"',
            "pybase64",
            "python-rapidjson",
            "apply",
            "blosc"
        ],  
        extras_require={
            "dev": [
                "pytest",
                "numpy",
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
            'Documentation': 'https://serializejson.readthedocs.io',
            'Source': 'https://github.com/SmartAudioTools/serializejson',
            'Tracker': 'https://github.com/SmartAudioTools/serializejson/issues',
        },
        classifiers=[
            'Development Status :: 3 - Alpha',
            'Intended Audience :: Developers',
             'License :: OSI Approved :: MIT License',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.7',
            'Programming Language :: Python :: 3.8',
            'Programming Language :: Python :: 3.9',
        ],
        zip_safe = False,
        data_files = [("", [LICENSE,CHANGELOG,"pyproject.toml"])]
        

    )
