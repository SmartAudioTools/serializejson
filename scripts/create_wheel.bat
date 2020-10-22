cd ..
.\python_venv\scripts\pip.exe install wheel
.\python_venv\scripts\pip.exe install twine
.\python_venv\scripts\python.exe setup.py sdist
.\python_venv\scripts\python.exe setup.py bdist_wheel
cd scripts