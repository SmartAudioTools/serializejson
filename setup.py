import setuptools
import os 

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

def version():
    with open(os.path.join(__location__, 'CHANGELOG.md')) as changelog_file:
        for line in changelog_file.readlines():
            if line.startswith("##"):
                open_square = line.find("[")
                close_square = line.fined("]")
                if open_square != -1 and close_square != -1 : 
                    version = line[open_square+1:close_square]
                    if version.replace(".","").isdigit() : 
                        return version 
    raise Exception("no valid version in CHANGELOG.md")
                
def long_description():
    with open(os.path.join(__location__, "README.md")) as readme_file:
        readme_str = readme_file.read()
    with open(os.path.join(__location__, "README.md")) as changelog_file:
        changelog_str = changelog_file.read()
    return readme_str + '\n# History\n'  + changelog_str
        
if __name__ == '__main__':
    setuptools.setup(
        name="serializejson",
        version=version(),
        description="A python library for fast serialization (and deserialization) of complex Python objects into JSON.",
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
            "pybase64",
            "python-rapidjson",
            "apply",
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
        ],
        keywords="pickle json serialize dump dumps rapidjson base64",
        zip_safe = False,
        data_files = [("", ["LICENSE.txt"])]
        

    )
