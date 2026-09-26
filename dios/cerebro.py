"""El cerebro de Dios: una red neuronal que nace vacía y aprende de lo que lee.

Es acumulativo:
  * cerebro.pt: los pesos de la red, las piezas de palabra que descubrió y cuánto
    se entrenó.
  * cerebro_diario.jsonl: todo lo que leyó, en orden y nunca borrado.

Cuando le das algo nuevo, primero descubre las piezas de palabra nuevas que trae
y después se entrena con eso, pero también repasa lo que ya había leído para no
olvidarlo (a las redes neuronales les pasa: si sólo estudian lo nuevo, pisan lo
viejo). Si cerebro.pt se pierde o se daña, se vuelve a entrenar desde cero con
el diario.

De cada texto aparta un pedacito (el 5% final) que nunca estudia: sirve para
medir si de verdad aprende o si sólo está memorizando.
"""

import copy
import json
import random
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

import torch

from . import lectores
from .red import TAMANOS, Config, Red
from .tokenizador import BYTES, Tokenizador

VERSION = 3
SEPARADOR = "\n\n"
APARTE = 0.05  # parte de cada texto que se usa para medir y no para estudiar
REVISAR_CADA = 250  # cada cuántos pasos se mide con lo apartado mientras entrena
Progreso = Callable[[int, int, float], None]  # (paso, total, pérdida)


class VersionVieja(Exception):
    """El cerebro guardado es de una versión de Dios que no es compatible."""


def _dispositivo() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class Cerebro:
    def __init__(self, archivo: str | Path | None = None, tamano: str = "chico",
                 progreso: Progreso | None = None, avisar: Callable[[str], None] | None = None):
        avisar = avisar or (lambda _: None)
        self.archivo = Path(archivo) if archivo else None
        self.diario = (
            self.archivo.with_name(self.archivo.stem + "_diario.jsonl") if self.archivo else None
        )
        self.dispositivo = _dispositivo()
        self.tamano = tamano
        self.reconstruido = False
        self.actualizado = False
        self._nacer(TAMANOS[tamano])
        if self.archivo and self.archivo.exists():
            try:
                self.cargar()
            except VersionVieja:
                copia = self._archivar(mover=[self.archivo])
                self.actualizado = True
                avisar(
                    "Me actualicé a una versión nueva: vuelvo a leer y estudiar todo lo del "
                    f"diario (el cerebro viejo quedó guardado en {copia})."
                )
                self._reconstruir_desde_diario(progreso)
            except Exception:  # archivo dañado: lo rehacemos desde el diario
                avisar("Mi memoria estaba dañada: me vuelvo a entrenar con el diario.")
                self._reconstruir_desde_diario(progreso)
        elif self.diario and self.diario.exists():
            avisar("No encuentro mi cerebro pero sí el diario: me vuelvo a entrenar con él.")
            self._reconstruir_desde_diario(progreso)

    def _nacer(self, config: Config) -> None:
        """Una red nueva, con pesos al azar: no sabe absolutamente nada."""
        self.red = Red(config).to(self.dispositivo)
        self.optimizador = torch.optim.AdamW(self.red.parameters(), lr=1e-3, weight_decay=0.01)
        self.tokenizador = Tokenizador()
        self.textos: list[dict] = []  # {"texto", "fuente", "fecha"}
        self.corpus = bytearray()  # todo lo leído, en bytes
        self.lecturas: list[dict] = []
        self._estudio = torch.zeros(0, dtype=torch.long)  # piezas para entrenar
        self._aparte = torch.zeros(0, dtype=torch.long)  # piezas para medir
        self._inicios: list[int] = []  # dónde empieza cada texto dentro de _estudio
        self._piezas_por_byte = 1.0
        self.pasos = 0
        self.perdida: float | None = None  # por pieza, en lo que estudia
        self.perdida_aparte: float | None = None  # por pieza, en lo apartado
        self.frenado_en: int | None = None  # paso en el que el freno cortó el último entrenamiento

    # ------------------------------------------------------------ aprender
    def aprender(self, contenido: str, fuente: str = "chat", pasos: int | None = None,
                 progreso: Progreso | None = None) -> int:
        """Suma un texto a lo que sabe y entrena la red con él.

        Devuelve cuántos pasos de entrenamiento hizo.
        """
        contenido = contenido.strip()
        if not contenido:
            return 0
        fecha = datetime.now().isoformat(timespec="seconds")
        self._anotar_en_diario({"fecha": fecha, "fuente": fuente, "texto": contenido})
        desde = self._incorporar(contenido, fuente, fecha)
        return self.entrenar(pasos or self.pasos_sugeridos(len(contenido.encode())),
                             desde=desde, progreso=progreso)

    def leer_archivo(self, ruta: str | Path, progreso: Progreso | None = None) -> int:
        """Lee un archivo de texto o PDF (o todos los de una carpeta)."""
        ruta = Path(ruta).expanduser()
        if ruta.is_dir():
            return sum(
                self.leer_archivo(p, progreso)
                for p in sorted(ruta.rglob("*"))
                if p.suffix.lower() in lectores.EXTENSIONES
            )
        return self.aprender(lectores.extraer_texto(ruta), fuente=ruta.name, progreso=progreso)

    @staticmethod
    def pasos_sugeridos(bytes_nuevos: int) -> int:
        """Cuánto estudiar un texto nuevo según su largo."""
        return max(60, min(2000, bytes_nuevos // 8))

    def _incorporar(self, contenido: str, fuente: str, fecha: str,
                    descubrir: bool = True, preparar: bool = True) -> int:
        """Agrega un texto. Devuelve dónde empieza lo nuevo (en piezas de estudio).

        descubrir: buscar piezas de palabra nuevas en este texto.
        preparar: volver a pasar todo lo leído a piezas (hace falta si hay piezas nuevas).
        """
        self.textos.append({"texto": contenido, "fuente": fuente, "fecha": fecha})
        bytes_texto = len(contenido.encode("utf-8")) + len(SEPARADOR)
        self.corpus += contenido.encode("utf-8") + SEPARADOR.encode()
        self.lecturas.append({"fuente": fuente, "fecha": fecha, "bytes": bytes_texto})
        if descubrir:
            nuevas = self.tokenizador.aprender(contenido, maximo=self.maximo_piezas())
            if nuevas:
                partes = [self.tokenizador.uniones[n - BYTES] for n in nuevas]
                self.red.presentar_piezas(nuevas, partes)
        if preparar:
            self._preparar()
            return self._inicios[-1]
        return 0

    def maximo_piezas(self) -> int:
        """Cuántas piezas puede tener según cuánto leyó: con poco texto, pocas piezas
        (si no, inventa piezas que casi nunca ve y termina memorizando)."""
        return min(self.red.config.tokens, BYTES + len(self.corpus) // 300)

    def _preparar(self) -> None:
        """Pasa todo lo leído a piezas y separa lo que estudia de lo que aparta."""
        estudio, aparte, self._inicios = [], [], []
        total = 0
        for t in self.textos:
            ids = self.tokenizador.codificar(t["texto"] + SEPARADOR)
            corte = len(ids) - int(len(ids) * APARTE) if len(ids) >= 400 else len(ids)
            self._inicios.append(total)
            estudio.extend(ids[:corte])
            aparte.extend(ids[corte:])
            total += corte
        self._estudio = torch.tensor(estudio, dtype=torch.long)
        self._aparte = torch.tensor(aparte, dtype=torch.long)
        if self.corpus:
            self._piezas_por_byte = (len(estudio) + len(aparte)) / len(self.corpus)

    # ------------------------------------------------------------ entrenar
    def _lote(self, tamano: int, desde: int | None):
        datos = self._estudio
        largo = min(self.red.config.contexto, len(datos) - 1)
        hay_nuevo = desde is not None and len(datos) - desde > largo + 1
        hay_viejo = desde is not None and desde > largo + 1
        inicios = []
        for j in range(tamano):
            # mitad del lote estudia lo nuevo, la otra mitad repasa lo anterior
            if hay_nuevo and (j % 2 == 0 or not hay_viejo):
                inicios.append(random.randint(desde, len(datos) - largo - 1))
            elif hay_viejo:
                inicios.append(random.randint(0, desde - largo - 1))
            else:
                inicios.append(random.randint(0, len(datos) - largo - 1))
        indices = torch.tensor(inicios).unsqueeze(1) + torch.arange(largo + 1)
        ventanas = datos[indices]
        return ventanas[:, :-1].to(self.dispositivo), ventanas[:, 1:].to(self.dispositivo)

    def entrenar(self, pasos: int, desde: int | None = None, tamano_lote: int = 32,
                 progreso: Progreso | None = None, frenar: bool = True) -> int:
        """Entrena la red. Se puede cortar con Ctrl+C: lo aprendido hasta ahí queda.

        Freno automático: cada tanto se mide con el texto apartado. Si empeora dos
        veces seguidas es que está memorizando en vez de aprender: deja de entrenar
        y vuelve al mejor momento.
        """
        self.frenado_en = None
        if len(self._estudio) < 3:
            return 0
        mejor = self.medir() if frenar else None
        mejor_estado = self._foto() if mejor is not None else None
        empeoro = 0
        self.red.train()
        hechos = 0
        try:
            for paso in range(1, pasos + 1):
                x, y = self._lote(tamano_lote, desde)
                _, perdida = self.red(x, y)
                self.optimizador.zero_grad(set_to_none=True)
                perdida.backward()
                torch.nn.utils.clip_grad_norm_(self.red.parameters(), 1.0)
                self.optimizador.step()
                valor = perdida.item()
                self.perdida = valor if self.perdida is None else 0.95 * self.perdida + 0.05 * valor
                self.pasos += 1
                hechos = paso
                if progreso and (paso % 10 == 0 or paso == pasos):
                    progreso(paso, pasos, self._por_letra(self.perdida))
                if mejor is not None and paso % REVISAR_CADA == 0:
                    ahora = self.medir()
                    self.red.train()
                    if ahora < mejor:
                        mejor, mejor_estado, empeoro = ahora, self._foto(), 0
                    else:
                        empeoro += 1
                        if empeoro >= 2:
                            self.frenado_en = paso
                            break
        except KeyboardInterrupt:
            pass
        if self.frenado_en:
            self.red.load_state_dict(mejor_estado[0])
            self.optimizador.load_state_dict(mejor_estado[1])
        self.perdida_aparte = self.medir()
        self.guardar()
        return hechos

    def _foto(self):
        """Copia de los pesos y del optimizador, para poder volver a este momento."""
        return copy.deepcopy(self.red.state_dict()), copy.deepcopy(self.optimizador.state_dict())

    @torch.no_grad()
    def medir(self, ventanas: int = 16) -> float | None:
        """Pérdida en el texto apartado (que nunca estudió)."""
        datos = self._aparte
        if len(datos) < 8:
            return None
        largo = min(self.red.config.contexto, len(datos) - 1)
        paso = max(1, (len(datos) - largo - 1) // ventanas)
        inicios = torch.arange(0, len(datos) - largo, paso)[:ventanas]
        indices = inicios.unsqueeze(1) + torch.arange(largo + 1)
        muestra = datos[indices].to(self.dispositivo)
        self.red.eval()
        _, perdida = self.red(muestra[:, :-1], muestra[:, 1:])
        return perdida.item()

    def _por_letra(self, perdida: float | None) -> float | None:
        """Pasa la pérdida por pieza a pérdida por letra (comparable entre versiones)."""
        return None if perdida is None else perdida * self._piezas_por_byte

    # ------------------------------------------------------------ hablar
    def _escribir(self, inicio: str, largo: int, temperatura: float, parar_en_separador: bool) -> str:
        separador = SEPARADOR.encode()

        def parar(ids):
            return parar_en_separador and separador in self.tokenizador.decodificar(ids[-4:])

        ids = self.red.generar(
            self.tokenizador.codificar(inicio), activas=len(self.tokenizador),
            largo=largo, temperatura=temperatura, parar=parar,
        )
        return self.tokenizador.decodificar(ids).decode("utf-8", errors="ignore")

    def responder(self, mensaje: str, largo: int = 150, temperatura: float = 0.8) -> str:
        """La red continúa escribiendo a partir de tu mensaje."""
        if not self.pasos:
            return (
                "(Estoy vacío: nunca me entrené con nada. Dame algo para leer con "
                "/leer <archivo> o /aprender <texto>.)"
            )
        texto = self._escribir(mensaje.strip() + "\n", largo, temperatura, parar_en_separador=True)
        respuesta = texto.split(SEPARADOR)[0].strip()
        # Si escribiste como en un chat ("Federico: hola"), corta cuando te toca a vos otra vez.
        quien = re.match(r"^([^:\n]{1,40}):\s", mensaje.strip())
        if quien:
            lineas = respuesta.splitlines()
            for i, linea in enumerate(lineas):
                if i > 0 and linea.startswith(quien.group(1) + ":"):
                    respuesta = "\n".join(lineas[:i])
                    break
        return respuesta

    def imaginar(self, inicio: str = "", largo: int = 150, temperatura: float = 0.8) -> str:
        """Escribe libremente, empezando (o no) por las palabras que le des."""
        if not self.pasos:
            return "(Estoy vacío: todavía no sé escribir nada.)"
        texto = self._escribir(inicio, largo, temperatura, parar_en_separador=False)
        return (inicio + texto).strip()

    # ------------------------------------------------------------ estado
    def estado(self) -> dict:
        perdida = self._por_letra(self.perdida)
        aparte = self._por_letra(self.perdida_aparte)
        return {
            "parametros": self.red.parametros(),
            "tamano": self.tamano,
            "piezas": len(self.tokenizador),
            "bytes_leidos": len(self.corpus),
            "lecturas": len(self.lecturas),
            "fuentes": sorted({l["fuente"] for l in self.lecturas}),
            "pasos": self.pasos,
            "perdida": perdida,
            "perdida_aparte": aparte,
            "memorizando": bool(perdida and aparte and aparte - perdida > 0.25),
            "desde": self.lecturas[0]["fecha"] if self.lecturas else None,
            "dispositivo": self.dispositivo,
        }

    def _archivar(self, mover=(), copiar=()) -> Path | None:
        """Guarda archivos en memoria/olvidados/<fecha>/. Devuelve esa carpeta."""
        archivos = [(p, shutil.move) for p in mover] + [(p, shutil.copy2) for p in copiar]
        archivos = [(p, f) for p, f in archivos if p and p.exists()]
        if not self.archivo or not archivos:
            return None
        marca = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        copia = self.archivo.parent / "olvidados" / marca
        copia.mkdir(parents=True, exist_ok=True)
        for p, f in archivos:
            f(p, copia / p.name)
        return copia

    def olvidar(self) -> Path | None:
        """Vuelve a nacer vacío. Guarda una copia de lo anterior en memoria/olvidados/."""
        copia = self._archivar(mover=[self.archivo, self.diario] if self.archivo else [])
        self._nacer(self.red.config)
        return copia

    def olvidar_fuente(self, fuente: str, progreso: Progreso | None = None) -> int:
        """Olvida un solo texto (por ejemplo "chat.txt") y conserva todo lo demás.

        Una red no puede "desaprender" una parte, así que vuelve a nacer y se
        entrena de nuevo con todo lo del diario menos ese texto. Guarda una copia
        de cómo estaba antes en memoria/olvidados/. Devuelve cuántas lecturas sacó.
        """
        entradas = self._leer_diario() if self.diario else list(self.textos)
        quedan = [e for e in entradas if e["fuente"].lower() != fuente.lower()]
        sacadas = len(entradas) - len(quedan)
        if not sacadas:
            return 0
        if self.archivo:
            self._archivar(copiar=[self.archivo, self.diario])
            temporal = self.diario.with_suffix(".tmp")
            temporal.write_text(
                "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in quedan),
                encoding="utf-8",
            )
            temporal.replace(self.diario)
        self._reconstruir(quedan, progreso)
        self.reconstruido = False
        return sacadas

    # ------------------------------------------------------------ persistencia
    def _anotar_en_diario(self, entrada: dict) -> None:
        if not self.diario:
            return
        self.diario.parent.mkdir(parents=True, exist_ok=True)
        with self.diario.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")

    def _leer_diario(self) -> list[dict]:
        entradas = []
        if self.diario and self.diario.exists():
            for linea in self.diario.read_text(encoding="utf-8").splitlines():
                try:
                    entradas.append(json.loads(linea))
                except ValueError:
                    continue  # una línea dañada no arruina el resto
        return entradas

    def _reconstruir(self, entradas: list[dict], progreso: Progreso | None = None) -> None:
        """Nace de nuevo y vuelve a leer y estudiar, en orden, estos textos."""
        self._nacer(TAMANOS.get(self.tamano, self.red.config))
        for e in entradas:
            self._incorporar(e["texto"], e["fuente"], e["fecha"], preparar=False)
        self._preparar()
        if self.corpus:
            self.entrenar(self.pasos_sugeridos(len(self.corpus)), progreso=progreso)
        else:
            self.guardar()

    def _reconstruir_desde_diario(self, progreso: Progreso | None = None) -> None:
        self._reconstruir(self._leer_diario(), progreso)
        self.reconstruido = True

    def guardar(self) -> None:
        if not self.archivo:
            return
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.archivo.with_suffix(".tmp")
        torch.save(
            {
                "version": VERSION,
                "config": self.red.config.como_dict(),
                "tamano": self.tamano,
                "uniones": [list(u) for u in self.tokenizador.uniones],
                "red": self.red.state_dict(),
                "optimizador": self.optimizador.state_dict(),
                "pasos": self.pasos,
                "perdida": self.perdida,
                "perdida_aparte": self.perdida_aparte,
            },
            temporal,
        )
        temporal.replace(self.archivo)

    def cargar(self) -> None:
        datos = torch.load(self.archivo, map_location=self.dispositivo, weights_only=True)
        if datos.get("version") != VERSION:
            raise VersionVieja
        self.tamano = datos.get("tamano", self.tamano)
        self._nacer(Config(**datos["config"]))
        self.tokenizador = Tokenizador([tuple(u) for u in datos["uniones"]])
        self.red.load_state_dict(datos["red"])
        self.optimizador.load_state_dict(datos["optimizador"])
        self.pasos, self.perdida = datos["pasos"], datos["perdida"]
        self.perdida_aparte = datos.get("perdida_aparte")
        # el texto leído vive en el diario (la red lo necesita para repasar)
        for e in self._leer_diario():
            self._incorporar(e["texto"], e["fuente"], e["fecha"], descubrir=False, preparar=False)
        self._preparar()
