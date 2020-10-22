cd ..
.\python_venv\scripts\python.exe setup.py sdist
.\python_venv\scripts\activate
.\python_venv\scripts\python.exe setup.py bdist_wheel
.\python_venv\scripts\python.exe twine upload --repository-url https://test.pypi.org/legacy/ dist/*   