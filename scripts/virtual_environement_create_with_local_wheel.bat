cd ..
rmdir .\python_venv\ /s/q
IF EXIST "D:/Projets/Python/SmartPython/SmartPython-3.9.10.0-64bit/python-3.9.10.amd64/python.exe" (
  D:/Projets/Python/SmartPython/SmartPython-3.9.10.0-64bit/python-3.9.10.amd64/python.exe -m venv python_venv
) ELSE (
  python -m venv python_venv
)
.\python_venv\scripts\pip.exe install .\dist\serializejson-0.0.1-py3-none-any.whl
.\python_venv\scripts\pip.exe install pytest
.\python_venv\scripts\activate
