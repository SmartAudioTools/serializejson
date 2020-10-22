cd ..
rmdir .\python_venv /s/q
rmdir .\dist /s/q
rmdir .\build /s/q
rmdir .pytest_cache  /s/q
IF EXIST "D:/Projets/Python/SmartPython/SmartPython-3.7.1.0-64bit/python-3.7.1.amd64/python.exe" (
  D:/Projets/Python/SmartPython/SmartPython-3.7.1.0-64bit/python-3.7.1.amd64/python.exe -m venv python_venv
) ELSE (
  python -m venv python_venv
)
.\python_venv\scripts\pip.exe install wheel
.\python_venv\scripts\pip.exe install twine
.\python_venv\scripts\python.exe setup.py sdist
.\python_venv\scripts\python.exe setup.py bdist_wheel
.\python_venv\scripts\python.exe .\python_venv\Lib\site-packages\twine\__main__.py upload --repository-url https://test.pypi.org/legacy/ dist/*  
cd scripts