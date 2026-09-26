"""Descubre los pedazos de palabra más frecuentes en lo que Dios lee.

Arranca sabiendo sólo los 256 bytes posibles (letras sueltas). Cada vez que lee
algo, busca qué par de pedazos aparece junto más seguido y lo une en un pedazo
nuevo ("c"+"a" -> "ca", "ca"+"sa" -> "casa"...), una y otra vez. Así va armando
su propio vocabulario a partir de sus textos, sin ningún diccionario previo.
Es la misma técnica (BPE) que usan los modelos de lenguaje grandes.

Cualquier texto se puede escribir siempre, aunque tenga palabras que nunca vio:
en el peor caso, se escribe letra por letra.
"""

import heapq
import re
from collections import Counter, defaultdict

BYTES = 256
# Corta el texto en palabras (con su espacio adelante), signos y espacios, para
# que los pedazos nunca crucen de una palabra a otra.
_TROZOS = re.compile(r" ?\w+| ?[^\s\w]+|\s+(?!\S)|\s+")


class Tokenizador:
    def __init__(self, uniones: list[tuple[int, int]] | None = None):
        self.uniones: list[tuple[int, int]] = []
        self._rango: dict[tuple[int, int], int] = {}
        self.piezas: list[bytes] = [bytes([b]) for b in range(BYTES)]
        self._cache: dict[str, tuple[int, ...]] = {}
        for a, b in uniones or []:
            self._unir(a, b)

    def __len__(self) -> int:
        return len(self.piezas)

    def _unir(self, a: int, b: int) -> int:
        nuevo = len(self.piezas)
        self.uniones.append((a, b))
        self._rango[(a, b)] = nuevo
        self.piezas.append(self.piezas[a] + self.piezas[b])
        return nuevo

    # ------------------------------------------------------------ usar
    def _codificar_trozo(self, trozo: str) -> tuple[int, ...]:
        guardado = self._cache.get(trozo)
        if guardado is not None:
            return guardado
        ids = list(trozo.encode("utf-8"))
        while len(ids) > 1:
            # une primero el par que aprendió antes (el más frecuente)
            par = min(zip(ids, ids[1:]), key=lambda p: self._rango.get(p, 1 << 30))
            nuevo = self._rango.get(par)
            if nuevo is None:
                break
            i, unidos = 0, []
            while i < len(ids):
                if i < len(ids) - 1 and (ids[i], ids[i + 1]) == par:
                    unidos.append(nuevo)
                    i += 2
                else:
                    unidos.append(ids[i])
                    i += 1
            ids = unidos
        resultado = tuple(ids)
        self._cache[trozo] = resultado
        return resultado

    def codificar(self, texto: str) -> list[int]:
        ids: list[int] = []
        for trozo in _TROZOS.findall(texto):
            ids.extend(self._codificar_trozo(trozo))
        return ids

    def decodificar(self, ids) -> bytes:
        return b"".join(self.piezas[i] for i in ids)

    # ------------------------------------------------------------ aprender
    def aprender(self, texto: str, maximo: int, minimo_repeticiones: int = 2) -> list[int]:
        """Suma al vocabulario los pedazos más frecuentes de este texto.

        No pasa de `maximo` piezas en total. Devuelve los ids de las piezas nuevas.
        """
        if len(self) >= maximo:
            return []
        frecuencia = Counter(_TROZOS.findall(texto))
        palabras = [list(self._codificar_trozo(t)) for t in frecuencia]
        veces = list(frecuencia.values())

        pares: Counter = Counter()
        donde: dict[tuple[int, int], set[int]] = defaultdict(set)
        for i, palabra in enumerate(palabras):
            for par in zip(palabra, palabra[1:]):
                pares[par] += veces[i]
                donde[par].add(i)
        monticulo = [(-n, par) for par, n in pares.items()]
        heapq.heapify(monticulo)

        nuevos = []
        while len(self) < maximo and monticulo:
            negativo, par = heapq.heappop(monticulo)
            if -negativo != pares.get(par, 0):
                continue  # dato viejo del montículo: ese par cambió
            if -negativo < minimo_repeticiones:
                break
            nuevo = self._unir(*par)
            nuevos.append(nuevo)
            cambiados = set()
            for i in list(donde[par]):
                palabra = palabras[i]
                for viejo in zip(palabra, palabra[1:]):
                    pares[viejo] -= veces[i]
                    donde[viejo].discard(i)
                    cambiados.add(viejo)
                j, unida = 0, []
                while j < len(palabra):
                    if j < len(palabra) - 1 and (palabra[j], palabra[j + 1]) == par:
                        unida.append(nuevo)
                        j += 2
                    else:
                        unida.append(palabra[j])
                        j += 1
                palabras[i] = unida
                for otro in zip(unida, unida[1:]):
                    pares[otro] += veces[i]
                    donde[otro].add(i)
                    cambiados.add(otro)
            for c in cambiados:
                if pares.get(c, 0) > 0:
                    heapq.heappush(monticulo, (-pares[c], c))
                else:
                    pares.pop(c, None)
        if nuevos:
            self._cache.clear()
        return nuevos
