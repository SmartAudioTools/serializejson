cd ..
rmdir .\python_venv\
IF EXIST "D:/Projets/Python/SmartPython/SmartPython-3.7.1.0-64bit/python-3.7.1.amd64/python.exe" (
  D:/Projets/Python/SmartPython/SmartPython-3.7.1.0-64bit/python-3.7.1.amd64/python.exe -m venv python_venv
) ELSE (
  python -m venv python_venv
)
.\python_venv\scripts\pip.exe install -r requirements_numpy.txt
.\python_venv\scripts\pip.exe install -e .
%~dp0/python_venv/Scripts/activate
