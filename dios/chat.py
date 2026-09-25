"""Chat por consola con Dios."""

import argparse
import re
import sys
from pathlib import Path

from .cerebro import Cerebro
from .lectores import ErrorDeLectura
from .red import TAMANOS, perdida_a_texto

AYUDA = """\
Comandos:
  /leer <archivo o carpeta>   Leo un .txt, .md o .pdf (o todos los de una carpeta) y me entreno con eso
  /aprender <texto>           Me entreno con el texto que escribas
  /pegar                      Pegás un texto largo (varias líneas) y me entreno; terminás con /fin
  /entrenar [pasos]           Estudio más todo lo que ya leí (por defecto 500 pasos)
  /imaginar [inicio]          Escribo libremente, empezando por lo que me des
  /temperatura <número>       Qué tan arriesgado escribo: 0.3 prudente, 1.0 creativo (ahora {temp})
  /estado                     Te cuento cuánto sé
  /olvidar si                 Vuelvo a nacer vacío (guardo una copia de lo anterior)
  /ayuda                      Muestra esta ayuda
  /salir                      Termina el chat

También podés enseñarme escribiendo "recordá que ..." o "aprendé que ...".
Cualquier otra cosa que escribas la continúo con lo que aprendí.
El entrenamiento se puede cortar con Ctrl+C: lo aprendido hasta ahí queda guardado."""

_ENSENAR = re.compile(r"^\s*(record[aá]|aprend[eé]|anot[aá])\s+(que\s+)?", re.I)


def barra(paso: int, total: int, perdida: float) -> None:
    """Muestra el avance del entrenamiento en la terminal."""
    lleno = int(30 * paso / total)
    sys.stderr.write(
        f"\r  entrenando [{'#' * lleno}{'.' * (30 - lleno)}] {paso}/{total}  pérdida {perdida:.2f} "
    )
    if paso == total:
        sys.stderr.write("\n")
    sys.stderr.flush()


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


class Chat:
    def __init__(self, cerebro: Cerebro, progreso=barra):
        self.cerebro = cerebro
        self.progreso = progreso
        self.temperatura = 0.8

    def aprendido(self, pasos: int) -> str:
        return f"Me entrené {pasos} pasos. Ahora {perdida_a_texto(self.cerebro.perdida)}."

    def procesar(self, entrada: str) -> str | None:
        """Procesa una línea del usuario y devuelve la respuesta (None = salir)."""
        entrada = entrada.strip()
        if not entrada:
            return ""
        c = self.cerebro
        if entrada.startswith("/"):
            comando, _, argumento = entrada.partition(" ")
            comando, argumento = comando.lower(), argumento.strip()
            if comando in ("/salir", "/chau", "/exit"):
                return None
            if comando == "/ayuda":
                return AYUDA.format(temp=self.temperatura)
            if comando == "/leer":
                if not argumento:
                    return "Decime qué leer: /leer mi_archivo.pdf"
                ruta = Path(argumento.strip("\"'")).expanduser()
                if not ruta.exists():
                    return f"No encuentro '{ruta}'."
                try:
                    pasos = c.leer_archivo(ruta, progreso=self.progreso)
                except ErrorDeLectura as error:
                    return str(error)
                return f"Leí {ruta.name}. " + self.aprendido(pasos)
            if comando in ("/aprender", "/enseñar", "/ensenar"):
                if not argumento:
                    return "Escribí lo que querés que aprenda: /aprender El cielo es azul."
                return self.aprendido(c.aprender(argumento, progreso=self.progreso))
            if comando == "/entrenar":
                if not c.corpus:
                    return "No tengo nada para estudiar: primero dame algo para leer."
                pasos = int(argumento) if argumento.isdigit() else 500
                return self.aprendido(c.entrenar(pasos, progreso=self.progreso))
            if comando == "/imaginar":
                return c.imaginar(argumento, temperatura=self.temperatura)
            if comando == "/temperatura":
                try:
                    self.temperatura = min(2.0, max(0.05, float(argumento.replace(",", "."))))
                except ValueError:
                    return "Decime un número, por ejemplo: /temperatura 0.5"
                return f"Temperatura en {self.temperatura}."
            if comando == "/estado":
                e = c.estado()
                fuentes = ", ".join(e["fuentes"]) or "nada todavía"
                desde = (
                    f"\nVengo aprendiendo desde {e['desde'].replace('T', ' ')}." if e["desde"] else ""
                )
                return (
                    f"Soy una red neuronal de {_miles(e['parametros'])} parámetros, tamaño {e['tamano']} "
                    f"(corriendo en {e['dispositivo']}).\n"
                    f"Leí {_miles(e['bytes_leidos'])} bytes de: {fuentes}.\n"
                    f"Me entrené {_miles(e['pasos'])} pasos. Ahora {perdida_a_texto(e['perdida'])}."
                    f"{desde}"
                )
            if comando == "/olvidar":
                if argumento.lower() not in ("si", "sí"):
                    return "¿Seguro? Voy a volver a nacer vacío. Si estás seguro escribí: /olvidar si"
                copia = c.olvidar()
                donde = f" Guardé una copia de lo anterior en {copia}." if copia else ""
                return "Volví a nacer: no sé nada." + donde
            return f"No conozco el comando {comando}. Probá /ayuda."

        ensenanza = _ENSENAR.match(entrada)
        if ensenanza:
            contenido = entrada[ensenanza.end():].strip()
            contenido = contenido[:1].upper() + contenido[1:]
            return self.aprendido(c.aprender(contenido, progreso=self.progreso))
        return c.responder(entrada, temperatura=self.temperatura)


def leer_pegado(leer_linea=input) -> str:
    """Junta líneas hasta que el usuario escribe /fin."""
    lineas = []
    while True:
        try:
            linea = leer_linea("... ")
        except (EOFError, KeyboardInterrupt):
            break
        if linea.strip().lower() == "/fin":
            break
        lineas.append(linea)
    return "\n".join(lineas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chateá con Dios, una red neuronal que nace vacía.")
    parser.add_argument(
        "--memoria",
        default=str(Path(__file__).resolve().parent.parent / "memoria" / "cerebro.pt"),
        help="Archivo donde se guarda lo aprendido (por defecto memoria/cerebro.pt)",
    )
    parser.add_argument(
        "--tamano", choices=list(TAMANOS), default="chico",
        help="Tamaño de la red al nacer (después no se puede cambiar). "
             "Más grande aprende mejor pero entrena más lento.",
    )
    args = parser.parse_args()

    cerebro = Cerebro(args.memoria, tamano=args.tamano, progreso=barra)
    chat = Chat(cerebro)
    e = cerebro.estado()
    print("=== Dios ===")
    if cerebro.reconstruido:
        print("(Mi memoria estaba dañada: me volví a entrenar con el diario.)")
    if e["pasos"]:
        print(f"Me entrené {_miles(e['pasos'])} pasos. {perdida_a_texto(e['perdida']).capitalize()}.")
    else:
        print(f"Acabo de nacer: soy una red de {_miles(e['parametros'])} parámetros al azar. No sé nada.")
    print("Escribí /ayuda para ver los comandos.\n")

    while True:
        try:
            entrada = input("vos > ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if entrada.strip().lower() == "/pegar":
            print("Pegá el texto. Cuando termines escribí /fin en una línea sola.")
            pasos = cerebro.aprender(leer_pegado(), fuente="texto pegado", progreso=barra)
            print(f"dios > {chat.aprendido(pasos)}\n")
            continue
        respuesta = chat.procesar(entrada)
        if respuesta is None:
            break
        if respuesta:
            print(f"dios > {respuesta}\n")
    print("Chau. Todo lo que aprendí queda guardado.")


if __name__ == "__main__":
    main()
