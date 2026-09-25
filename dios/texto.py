"""Utilidades mecánicas para partir texto en oraciones y palabras.

A propósito no hay acá ningún conocimiento del idioma (ni listas de palabras,
ni reglas de gramática): todo lo que Dios sabe lo aprende de lo que lee.
"""

import re
import unicodedata

_PALABRA = re.compile(r"\w+")
_FIN_ORACION = re.compile(r"(?<=[.!?…])\s+|\n\s*\n|\n(?=\s*[-*•\d])")


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes (pero conservando la ñ)."""
    texto = texto.lower().replace("ñ", "\0")
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.replace("\0", "ñ")


def claves(texto: str) -> list[str]:
    """Todas las palabras de un texto, normalizadas, para indexar o buscar."""
    return _PALABRA.findall(normalizar(texto))


def oraciones(texto: str) -> list[str]:
    """Parte un texto en oraciones limpias."""
    partes = _FIN_ORACION.split(texto.replace("\r", ""))
    resultado = []
    for parte in partes:
        parte = " ".join(parte.split())
        if len(parte) >= 3:
            resultado.append(parte)
    return resultado


def palabras_originales(texto: str) -> list[str]:
    """Palabras tal cual aparecen (con signos pegados), para generar texto."""
    return texto.split()
