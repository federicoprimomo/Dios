"""El cerebro de Dios: empieza vacío y acumula todo lo que lee.

Tiene dos partes:
  * Memoria: guarda cada oración leída y la indexa (BM25) para poder
    encontrar lo relevante cuando le hacés una pregunta.
  * Lenguaje: una cadena de Markov que aprende cómo se encadenan las
    palabras, para "imaginar" texto nuevo con el estilo de lo que leyó.

Todo se guarda en un archivo JSON, así lo aprendido se suma sesión tras sesión.
"""

import json
import math
import random
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from . import lectores
from . import texto as tx

FIN = "\x03"  # marca de fin de oración en la cadena de Markov


class Cerebro:
    def __init__(self, archivo: str | Path | None = None):
        self.archivo = Path(archivo) if archivo else None
        self.lecturas: list[dict] = []  # historial de lo que leyó
        self.recuerdos: list[dict] = []  # oraciones: {"texto", "fuente"}
        self.cadena: dict[str, Counter] = defaultdict(Counter)
        self.inicios: Counter = Counter()
        self._reiniciar_indice()
        if self.archivo and self.archivo.exists():
            self.cargar()

    # ------------------------------------------------------------ aprender
    def aprender(self, contenido: str, fuente: str = "chat") -> int:
        """Incorpora un texto. Devuelve cuántas oraciones nuevas aprendió."""
        vistas = {r["texto"] for r in self.recuerdos}
        nuevas = 0
        for oracion in tx.oraciones(contenido):
            self._aprender_lenguaje(oracion)
            if oracion in vistas:
                continue
            vistas.add(oracion)
            self.recuerdos.append({"texto": oracion, "fuente": fuente})
            self._indexar(len(self.recuerdos) - 1)
            nuevas += 1
        if nuevas:
            self.lecturas.append(
                {
                    "fuente": fuente,
                    "oraciones": nuevas,
                    "fecha": datetime.now().isoformat(timespec="seconds"),
                }
            )
            self.guardar()
        return nuevas

    def leer_archivo(self, ruta: str | Path) -> int:
        """Lee un archivo de texto o PDF (o todos los de una carpeta)."""
        ruta = Path(ruta).expanduser()
        if ruta.is_dir():
            return sum(
                self.leer_archivo(p)
                for p in sorted(ruta.rglob("*"))
                if p.suffix.lower() in lectores.EXTENSIONES
            )
        return self.aprender(lectores.extraer_texto(ruta), fuente=ruta.name)

    def _aprender_lenguaje(self, oracion: str) -> None:
        palabras = tx.palabras_originales(oracion)
        if not palabras:
            return
        self.inicios[palabras[0]] += 1
        secuencia = palabras + [FIN]
        for i in range(len(palabras)):
            anterior = secuencia[i - 1] if i > 0 else ""
            clave = f"{anterior} {secuencia[i]}"
            self.cadena[clave][secuencia[i + 1]] += 1

    # ------------------------------------------------------------ índice BM25
    def _reiniciar_indice(self) -> None:
        self._indice: dict[str, dict[int, int]] = defaultdict(dict)
        self._largos: list[int] = []

    def _indexar(self, i: int) -> None:
        palabras = tx.claves(self.recuerdos[i]["texto"])
        self._largos.append(len(palabras))
        for palabra, veces in Counter(palabras).items():
            self._indice[palabra][i] = veces

    def _comunes(self) -> set[str]:
        """Palabras que aparecen en casi todas partes ("el", "de", "que"...).

        No vienen de ninguna lista: las descubre solo, mirando lo que leyó.
        Con poca lectura todavía no sabe cuáles son, y no ignora ninguna.
        """
        n = len(self.recuerdos)
        if n < 8:
            return set()
        return {p for p, apariciones in self._indice.items() if len(apariciones) > n * 0.5}

    def _variantes(self, palabra: str) -> dict[str, float]:
        """Palabras que conoce y se parecen a esta (perro/perros, planeta/planetas).

        Se basa sólo en que compartan el comienzo, sin reglas del idioma.
        """
        variantes = {palabra: 1.0} if palabra in self._indice else {}
        if len(palabra) >= 4:
            for conocida in self._indice:
                if conocida != palabra and len(conocida) >= 4 and abs(len(conocida) - len(palabra)) <= 3:
                    if conocida.startswith(palabra) or palabra.startswith(conocida):
                        variantes[conocida] = 0.7
        return variantes

    def buscar(self, consulta: str, cuantos: int = 3) -> list[tuple[float, int, float, bool]]:
        """Devuelve (puntaje, índice, cobertura, relevante) de los mejores recuerdos.

        cobertura: cuánto de la consulta tiene la oración (las palabras raras pesan más).
        relevante: si comparte con la consulta alguna palabra que no sea de las comunes.
        """
        n = len(self.recuerdos)
        if not n:
            return []
        promedio = sum(self._largos) / n or 1
        k1, b = 1.5, 0.75
        comunes = self._comunes()
        puntajes: Counter = Counter()
        cobertura: dict[int, dict[str, float]] = defaultdict(dict)
        relevante: set[int] = set()
        for buscada in set(tx.claves(consulta)):
            for palabra, peso in self._variantes(buscada).items():
                apariciones = self._indice[palabra]
                idf = math.log(1 + (n - len(apariciones) + 0.5) / (len(apariciones) + 0.5))
                for i, veces in apariciones.items():
                    norma = k1 * (1 - b + b * self._largos[i] / promedio)
                    puntajes[i] += peso * idf * veces * (k1 + 1) / (veces + norma)
                    cobertura[i][buscada] = max(cobertura[i].get(buscada, 0), peso * idf)
                    if palabra not in comunes:
                        relevante.add(i)
        return [
            (p, i, sum(cobertura[i].values()), i in relevante)
            for i, p in puntajes.most_common(cuantos)
        ]

    # ------------------------------------------------------------ hablar
    def responder(self, pregunta: str) -> str:
        if not self.recuerdos:
            return (
                "Todavía no sé nada. Estoy vacío. "
                "Dame algo para leer con /leer <archivo> o enseñame con /aprender <texto>."
            )
        encontrados = self.buscar(pregunta, cuantos=5)
        encontrados = [e for e in encontrados if e[3]]
        desconocidas = [
            p for p in dict.fromkeys(re.findall(r"\w+", pregunta.lower()))
            if not self._variantes(tx.normalizar(p))
        ]
        aviso = f"(Nunca leí: {', '.join(desconocidas)}.) " if desconocidas else ""
        if not encontrados:
            return (
                aviso + "No aprendí nada sobre eso todavía. "
                "Si me lo enseñás (/aprender ...), la próxima te sé responder."
            )
        # Nos quedamos con las oraciones que cubren más palabras de la pregunta
        # y que tienen un puntaje parecido al de la mejor.
        maxima = max(c for _, _, c, _ in encontrados)
        mejor = encontrados[0][0]
        elegidos = [
            i for p, i, c, _ in encontrados if p >= mejor * 0.6 and c >= maxima * 0.85
        ][:3]
        # Sumamos la oración que sigue en el mismo texto si también habla del tema:
        # muchas veces la respuesta continúa ahí ("Se hace cocinando...").
        relacionadas = {
            i for _, i, _, r in self.buscar(pregunta, cuantos=len(self.recuerdos)) if r
        }
        con_contexto = []
        for i in elegidos:
            if i not in con_contexto:
                con_contexto.append(i)
            siguiente = i + 1
            if (
                siguiente in relacionadas
                and siguiente not in con_contexto
                and self.recuerdos[siguiente]["fuente"] == self.recuerdos[i]["fuente"]
            ):
                con_contexto.append(siguiente)
        return aviso + " ".join(self.recuerdos[i]["texto"] for i in con_contexto[:4])

    def imaginar(self, semilla: str = "", largo_max: int = 40) -> str:
        """Genera texto nuevo con lo que aprendió del lenguaje."""
        if not self.inicios:
            return "No tengo palabras todavía: necesito leer algo primero."
        anterior, actual, prefijo = "", None, []
        if semilla:
            ultima = tx.normalizar(semilla.split()[-1])
            candidatas = [
                c.split(" ", 1)[1]
                for c in self.cadena
                if tx.normalizar(c.split(" ", 1)[1]).strip(".,;:!?¿¡\"'()") == ultima
            ]
            if candidatas:
                actual = random.choice(candidatas)
                prefijo = semilla.split()[:-1]
                anterior = prefijo[-1] if prefijo else ""
        if actual is None:
            actual = random.choices(list(self.inicios), weights=self.inicios.values())[0]
        salida = [actual]
        while len(salida) < largo_max:
            opciones = self.cadena.get(f"{anterior} {actual}")
            if not opciones:
                # probamos con cualquier contexto que termine en la palabra actual
                opciones = Counter()
                for clave, siguientes in self.cadena.items():
                    if clave.endswith(" " + actual):
                        opciones.update(siguientes)
            if not opciones:
                break
            siguiente = random.choices(list(opciones), weights=opciones.values())[0]
            if siguiente == FIN:
                break
            salida.append(siguiente)
            anterior, actual = actual, siguiente
        return " ".join(prefijo + salida)

    # ------------------------------------------------------------ estado
    def estado(self) -> dict:
        return {
            "oraciones": len(self.recuerdos),
            "palabras_distintas": len(self._indice),
            "lecturas": len(self.lecturas),
            "fuentes": sorted({l["fuente"] for l in self.lecturas}),
        }

    def olvidar(self) -> None:
        """Vuelve a dejar el cerebro vacío."""
        self.lecturas, self.recuerdos = [], []
        self.cadena, self.inicios = defaultdict(Counter), Counter()
        self._reiniciar_indice()
        self.guardar()

    # ------------------------------------------------------------ persistencia
    def guardar(self) -> None:
        if not self.archivo:
            return
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        datos = {
            "version": 1,
            "lecturas": self.lecturas,
            "recuerdos": self.recuerdos,
            "cadena": {k: dict(v) for k, v in self.cadena.items()},
            "inicios": dict(self.inicios),
        }
        temporal = self.archivo.with_suffix(".tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        temporal.replace(self.archivo)

    def cargar(self) -> None:
        datos = json.loads(self.archivo.read_text(encoding="utf-8"))
        self.lecturas = datos.get("lecturas", [])
        self.recuerdos = datos.get("recuerdos", [])
        self.cadena = defaultdict(
            Counter, {k: Counter(v) for k, v in datos.get("cadena", {}).items()}
        )
        self.inicios = Counter(datos.get("inicios", {}))
        self._reiniciar_indice()
        for i in range(len(self.recuerdos)):
            self._indexar(i)
