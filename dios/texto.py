"""Utilidades para procesar texto en español: normalizar, separar oraciones y palabras."""

import re
import unicodedata

PALABRAS_VACIAS = set(
    """
    a al algo algun alguna algunas alguno algunos ante antes aqui asi aun
    bajo bien cada casi como con contra cual cuales cuando de del desde donde
    dos el ella ellas ello ellos en entre era eran es esa esas ese eso esos
    esta estaba estan estar estas este esto estos fue fueron ha haber habia
    hace hacia han hasta hay la las le les lo los mas me mi mis mucho muy
    nada ni no nos nosotros o os otra otras otro otros para pero poco por porque
    que quien quienes se sea ser si sido sin sobre son su sus tambien tan
    tanto te tener tiene tienen toda todas todo todos tu tus un una unas uno
    unos usted vos y ya yo cual cuales decime dime sabes sabe saber contame
    cuentame explicame explica queres quiero puedes podes
    the of and to in is it that for on with as are was be by this
    """.split()
)

_PALABRA = re.compile(r"[a-z0-9ñ]+")
_FIN_ORACION = re.compile(r"(?<=[.!?…])\s+|\n\s*\n|\n(?=\s*[-*•\d])")


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes (pero conservando la ñ)."""
    texto = texto.lower().replace("ñ", "\0")
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.replace("\0", "ñ")


def raiz(palabra: str) -> str:
    """Stemming muy liviano: junta singular/plural y algunas terminaciones."""
    for sufijo in ("mente", "ciones", "cion", "idades", "idad", "es", "s"):
        if palabra.endswith(sufijo) and len(palabra) - len(sufijo) >= 4:
            return palabra[: -len(sufijo)]
    return palabra


def claves(texto: str) -> list[str]:
    """Palabras significativas de un texto, listas para indexar o buscar."""
    return [
        raiz(p)
        for p in _PALABRA.findall(normalizar(texto))
        if p not in PALABRAS_VACIAS and len(p) > 1
    ]


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
