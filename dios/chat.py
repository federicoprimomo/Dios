"""Chat por consola con Dios."""

import argparse
import re
from pathlib import Path

from .cerebro import Cerebro

AYUDA = """\
Comandos:
  /leer <archivo o carpeta>   Leo un .txt/.md (o todos los de una carpeta) y lo aprendo
  /aprender <texto>           Aprendo el texto que escribas
  /imaginar [palabras]        Invento texto con el estilo de lo que leí
  /estado                     Te cuento cuánto sé
  /olvidar                    Borro todo lo aprendido (vuelvo a estar vacío)
  /ayuda                      Muestra esta ayuda
  /salir                      Termina el chat

También podés enseñarme escribiendo "recordá que ..." o "aprendé que ...".
Cualquier otra cosa que escribas es una pregunta: te respondo con lo que aprendí."""

_ENSENAR = re.compile(r"^\s*(record[aá]|aprend[eé]|anot[aá]|sab[eé])\s+(que\s+)?", re.I)


def procesar(cerebro: Cerebro, entrada: str) -> str | None:
    """Procesa una línea del usuario y devuelve la respuesta (None = salir)."""
    entrada = entrada.strip()
    if not entrada:
        return ""
    if entrada.startswith("/"):
        comando, _, argumento = entrada.partition(" ")
        comando, argumento = comando.lower(), argumento.strip()
        if comando in ("/salir", "/chau", "/exit"):
            return None
        if comando == "/ayuda":
            return AYUDA
        if comando == "/leer":
            if not argumento:
                return "Decime qué leer: /leer mi_archivo.txt"
            ruta = Path(argumento.strip("\"'")).expanduser()
            if not ruta.exists():
                return f"No encuentro '{ruta}'."
            n = cerebro.leer_archivo(ruta)
            return f"Listo, leí {ruta.name} y aprendí {n} oraciones nuevas."
        if comando in ("/aprender", "/enseñar", "/ensenar"):
            if not argumento:
                return "Escribí lo que querés que aprenda: /aprender El cielo es azul."
            n = cerebro.aprender(argumento)
            return f"Aprendido ({n} oraciones nuevas)." if n else "Eso ya lo sabía."
        if comando == "/imaginar":
            return cerebro.imaginar(argumento)
        if comando == "/estado":
            e = cerebro.estado()
            fuentes = ", ".join(e["fuentes"]) or "nada todavía"
            return (
                f"Sé {e['oraciones']} oraciones y {e['palabras_distintas']} palabras distintas.\n"
                f"Aprendí de: {fuentes}"
            )
        if comando == "/olvidar":
            cerebro.olvidar()
            return "Olvidé todo. Vuelvo a estar vacío."
        return f"No conozco el comando {comando}. Probá /ayuda."

    ensenanza = _ENSENAR.match(entrada)
    if ensenanza:
        contenido = entrada[ensenanza.end():].strip()
        contenido = contenido[0].upper() + contenido[1:] if contenido else contenido
        n = cerebro.aprender(contenido)
        return "Anotado, ya lo sé." if n else "Eso ya lo sabía."
    return cerebro.responder(entrada)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chateá con Dios, una IA que empieza vacía.")
    parser.add_argument(
        "--memoria",
        default=str(Path(__file__).resolve().parent.parent / "memoria" / "cerebro.json"),
        help="Archivo donde se guarda lo aprendido (por defecto memoria/cerebro.json)",
    )
    args = parser.parse_args()

    cerebro = Cerebro(args.memoria)
    e = cerebro.estado()
    print("=== Dios ===")
    if e["oraciones"]:
        print(f"Me acuerdo de {e['oraciones']} oraciones. Preguntame algo.")
    else:
        print("Estoy vacío. Enseñame algo.")
    print("Escribí /ayuda para ver los comandos.\n")

    while True:
        try:
            entrada = input("vos > ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        respuesta = procesar(cerebro, entrada)
        if respuesta is None:
            break
        if respuesta:
            print(f"dios > {respuesta}\n")
    print("Chau. Todo lo que aprendí queda guardado.")


if __name__ == "__main__":
    main()
