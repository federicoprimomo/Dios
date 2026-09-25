"""Abre el chat con Dios. Funciona desde cualquier carpeta:

    python chatear.py
    python C:\\ruta\\a\\dios\\chatear.py

En Windows también podés hacerle doble clic.
"""

import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA))

try:
    from dios.chat import main
except ModuleNotFoundError as error:
    print(f"Falta instalar algo ({error.name}). Abrí una terminal y ejecutá:\n")
    print(f'    pip install -r "{CARPETA / "requirements.txt"}"\n')
    input("Apretá Enter para cerrar.")
    sys.exit(1)

main()
