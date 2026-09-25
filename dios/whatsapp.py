"""Limpia chats exportados de WhatsApp (Android y iPhone).

Convierte esto:
    12/06/26, 22:14 - Federico: llegaste?
    [12/06/26, 22:15:03] Ana: sii recién
en esto:
    Federico: llegaste?
    Ana: sii recién

Saca fechas, horas, avisos automáticos y archivos omitidos, une los mensajes de
varios renglones y deja una línea en blanco entre charlas separadas por horas.
"""

import re
from datetime import datetime, timedelta

# Separación entre charlas: si pasan más de estas horas sin mensajes, es otra charla.
PAUSA_ENTRE_CHARLAS = timedelta(hours=3)

_INVISIBLES = re.compile("[‎‏‪-‮⁦-⁩﻿]")
_HORA = r"(\d{1,2}:\d{2}(?::\d{2})?)\s*([ap]\.?\s?m\.?)?"
_FECHA = r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})"
# Android: "12/06/26, 22:14 - Ana: hola"   iPhone: "[12/06/26, 22:14:05] Ana: hola"
_LINEA = re.compile(
    rf"^\[?{_FECHA},?\s+{_HORA}\]?\s*(?:-\s+)?(?P<resto>.*)$", re.IGNORECASE
)
_AUTOR = re.compile(r"^(?P<autor>[^:]{1,40}):\s(?P<mensaje>.*)$")

# Mensajes automáticos que no son de las personas (en español e inglés).
_DESCARTAR = re.compile(
    r"^<?("
    r"multimedia omitid[oa]|media omitted|archivo omitido|"
    r"(imagen|audio|video|sticker|gif|documento|contacto) omitid[oa]|"
    r"(image|audio|video|sticker|gif|document|contact card) omitted|"
    r"se eliminó este mensaje\.?|eliminaste este mensaje\.?|"
    r"this message was deleted\.?|you deleted this message\.?|"
    r"llamada (de voz|de video|perdida)[^>]*|(missed )?(voice|video) call[^>]*|"
    r"null|ubicación: .*|location: .*"
    r")>?$",
    re.IGNORECASE,
)
_EDITADO = re.compile(r"\s*<(se editó este mensaje|this message was edited)\.?>\s*$", re.I)
_ADJUNTO = re.compile(r"^\S+\.\w{2,4} \((archivo adjunto|file attached)\)", re.I)


def es_whatsapp(texto: str) -> bool:
    """¿Parece una exportación de WhatsApp? Mira los primeros renglones."""
    lineas = [l for l in texto.splitlines()[:40] if l.strip()]
    if not lineas:
        return False
    coinciden = sum(1 for l in lineas if _LINEA.match(_INVISIBLES.sub("", l).strip()))
    return coinciden >= max(2, len(lineas) // 2)


def _momento(dia, mes, anio, hora, ampm) -> datetime | None:
    anio = int(anio) + (2000 if len(anio) == 2 else 0)
    try:
        h, m, *s = (int(x) for x in hora.split(":"))
        if ampm:
            pm = ampm.lower().startswith("p")
            h = (h % 12) + (12 if pm else 0)
        try:
            return datetime(anio, int(mes), int(dia), h, m)
        except ValueError:  # formato mes/día (algunos teléfonos en inglés)
            return datetime(anio, int(dia), int(mes), h, m)
    except ValueError:
        return None


def limpiar(texto: str) -> str:
    mensajes: list[list] = []  # [momento, autor, texto]
    for linea in texto.splitlines():
        linea = _INVISIBLES.sub("", linea).rstrip()
        encabezado = _LINEA.match(linea.strip())
        if encabezado:
            autor = _AUTOR.match(encabezado["resto"])
            if not autor:  # aviso del sistema ("cifrado de extremo a extremo", etc.)
                mensajes.append([None, None, None])
                continue
            momento = _momento(*encabezado.groups()[:5])
            mensajes.append([momento, autor["autor"].strip(), autor["mensaje"]])
        elif mensajes and mensajes[-1][1] and linea.strip():
            mensajes[-1][2] += " " + linea.strip()  # continuación de un mensaje largo

    salida = []
    anterior = None
    for momento, autor, mensaje in mensajes:
        if not autor:
            continue
        mensaje = _EDITADO.sub("", mensaje).strip()
        if not mensaje or _DESCARTAR.match(mensaje) or _ADJUNTO.match(mensaje):
            continue
        if salida and momento and anterior and momento - anterior > PAUSA_ENTRE_CHARLAS:
            salida.append("")
        salida.append(f"{autor}: {mensaje}")
        anterior = momento or anterior
    return "\n".join(salida)
