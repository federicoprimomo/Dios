"""Sacan el texto de los distintos tipos de archivo que Dios sabe leer."""

import re
from pathlib import Path

EXTENSIONES_TEXTO = {".txt", ".md", ".text"}
EXTENSIONES = EXTENSIONES_TEXTO | {".pdf"}


class ErrorDeLectura(Exception):
    """El archivo no se pudo leer (formato no soportado, PDF escaneado, etc.)."""


def extraer_texto(ruta: str | Path) -> str:
    ruta = Path(ruta)
    extension = ruta.suffix.lower()
    if extension == ".pdf":
        return _leer_pdf(ruta)
    if extension in EXTENSIONES_TEXTO or not extension:
        return ruta.read_text(encoding="utf-8", errors="replace")
    raise ErrorDeLectura(
        f"No sé leer archivos {extension}. Por ahora leo: {', '.join(sorted(EXTENSIONES))}"
    )


def _leer_pdf(ruta: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ErrorDeLectura(
            "Para leer PDFs necesito la librería pypdf. Instalala con: pip install pypdf"
        ) from None
    try:
        lector = PdfReader(ruta)
        paginas = [pagina.extract_text() or "" for pagina in lector.pages]
    except Exception as error:
        raise ErrorDeLectura(f"No pude abrir el PDF: {error}") from None
    texto = "\n\n".join(_limpiar_pagina(p) for p in paginas)
    if not texto.strip():
        raise ErrorDeLectura(
            "El PDF no tiene texto que pueda leer (quizás es una imagen escaneada)."
        )
    return texto


def _limpiar_pagina(texto: str) -> str:
    """Une las líneas cortadas por el ancho de página del PDF.

    Una línea que termina en signo de puntuación, o que es mucho más corta
    que las demás (un título, el final de un párrafo), se deja como corte.
    """
    texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)  # pala-\nbra -> palabra
    lineas = [l.strip() for l in texto.splitlines()]
    ancho = max((len(l) for l in lineas), default=0)
    resultado = ""
    for linea in lineas:
        if not linea:
            resultado += "\n\n"
            continue
        resultado += linea
        corta = len(linea) < ancho * 0.6
        resultado += "\n\n" if corta or linea[-1] in ".!?:" else " "
    return resultado
