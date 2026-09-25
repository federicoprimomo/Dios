"""El cerebro de Dios: una red neuronal que nace vacía y aprende de lo que lee.

Es acumulativo:
  * cerebro.pt: los pesos de la red (lo que aprendió) y cuánto se entrenó.
  * cerebro_diario.jsonl: todo lo que leyó, en orden y nunca borrado.

Cuando le das algo nuevo, se entrena con eso pero también repasa lo que ya había
leído, para no olvidarlo (a las redes neuronales les pasa: si sólo estudian lo
nuevo, pisan lo viejo). Si cerebro.pt se pierde o se daña, se vuelve a entrenar
desde cero con el diario.
"""

import json
import random
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

import torch

from . import lectores
from .red import TAMANOS, Config, Red

SEPARADOR = b"\n\n"
Progreso = Callable[[int, int, float], None]  # (paso, total, pérdida)


def _dispositivo() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class Cerebro:
    def __init__(self, archivo: str | Path | None = None, tamano: str = "chico",
                 progreso: Progreso | None = None):
        self.archivo = Path(archivo) if archivo else None
        self.diario = (
            self.archivo.with_name(self.archivo.stem + "_diario.jsonl") if self.archivo else None
        )
        self.dispositivo = _dispositivo()
        self.tamano = tamano
        self.reconstruido = False
        self._nacer(TAMANOS[tamano])
        if self.archivo and self.archivo.exists():
            try:
                self.cargar()
            except Exception:  # archivo dañado: lo rehacemos desde el diario
                self._reconstruir_desde_diario(progreso)
        elif self.diario and self.diario.exists():
            self._reconstruir_desde_diario(progreso)

    def _nacer(self, config: Config) -> None:
        """Una red nueva, con pesos al azar: no sabe absolutamente nada."""
        self.red = Red(config).to(self.dispositivo)
        self.optimizador = torch.optim.AdamW(self.red.parameters(), lr=1e-3, weight_decay=0.01)
        self.corpus = bytearray()  # todo lo leído, en bytes
        self.lecturas: list[dict] = []
        self.pasos = 0
        self.perdida: float | None = None

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
        nuevos = len(self.corpus) - desde
        return self.entrenar(pasos or self.pasos_sugeridos(nuevos), desde=desde,
                             progreso=progreso)

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

    def _incorporar(self, contenido: str, fuente: str, fecha: str) -> int:
        """Agrega el texto al corpus. Devuelve dónde empieza lo nuevo."""
        desde = len(self.corpus)
        self.corpus += contenido.encode("utf-8") + SEPARADOR
        self.lecturas.append({"fuente": fuente, "fecha": fecha, "bytes": len(self.corpus) - desde})
        return desde

    # ------------------------------------------------------------ entrenar
    def _lote(self, tamano: int, desde: int | None):
        largo = min(self.red.config.contexto, len(self.corpus) - 1)
        datos = self.corpus
        inicios = []
        hay_nuevo = desde is not None and len(datos) - desde > largo + 1
        hay_viejo = desde is not None and desde > largo + 1
        for j in range(tamano):
            # mitad del lote estudia lo nuevo, la otra mitad repasa lo anterior
            if hay_nuevo and (j % 2 == 0 or not hay_viejo):
                inicios.append(random.randint(desde, len(datos) - largo - 1))
            elif hay_viejo:
                inicios.append(random.randint(0, desde - largo - 1))
            else:
                inicios.append(random.randint(0, len(datos) - largo - 1))
        x = torch.tensor([list(datos[i:i + largo]) for i in inicios], dtype=torch.long)
        y = torch.tensor([list(datos[i + 1:i + largo + 1]) for i in inicios], dtype=torch.long)
        return x.to(self.dispositivo), y.to(self.dispositivo)

    def entrenar(self, pasos: int, desde: int | None = None, tamano_lote: int = 32,
                 progreso: Progreso | None = None) -> int:
        """Entrena la red. Se puede cortar con Ctrl+C: lo aprendido hasta ahí queda."""
        if len(self.corpus) < 3:
            return 0
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
                    progreso(paso, pasos, self.perdida)
        except KeyboardInterrupt:
            pass
        self.guardar()
        return hechos

    # ------------------------------------------------------------ hablar
    def responder(self, mensaje: str, largo: int = 300, temperatura: float = 0.8) -> str:
        """La red continúa escribiendo a partir de tu mensaje."""
        if not self.pasos:
            return (
                "(Estoy vacío: nunca me entrené con nada. Dame algo para leer con "
                "/leer <archivo> o /aprender <texto>.)"
            )
        inicio = (mensaje.strip() + "\n").encode("utf-8")
        texto = self.red.generar(inicio, largo=largo, temperatura=temperatura, parar_en=SEPARADOR)
        return texto.decode("utf-8", errors="ignore").strip()

    def imaginar(self, inicio: str = "", largo: int = 400, temperatura: float = 0.8) -> str:
        """Escribe libremente, empezando (o no) por las palabras que le des."""
        if not self.pasos:
            return "(Estoy vacío: todavía no sé escribir nada.)"
        texto = self.red.generar(inicio.encode("utf-8"), largo=largo, temperatura=temperatura)
        return (inicio + texto.decode("utf-8", errors="ignore")).strip()

    # ------------------------------------------------------------ estado
    def estado(self) -> dict:
        return {
            "parametros": self.red.parametros(),
            "tamano": self.tamano,
            "bytes_leidos": len(self.corpus),
            "lecturas": len(self.lecturas),
            "fuentes": sorted({l["fuente"] for l in self.lecturas}),
            "pasos": self.pasos,
            "perdida": self.perdida,
            "desde": self.lecturas[0]["fecha"] if self.lecturas else None,
            "dispositivo": self.dispositivo,
        }

    def olvidar(self) -> Path | None:
        """Vuelve a nacer vacío. Guarda una copia de lo anterior en memoria/olvidados/."""
        copia = None
        if self.archivo and any(p.exists() for p in (self.archivo, self.diario)):
            marca = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            copia = self.archivo.parent / "olvidados" / marca
            copia.mkdir(parents=True, exist_ok=True)
            for p in (self.archivo, self.diario):
                if p.exists():
                    shutil.move(p, copia / p.name)
        self._nacer(self.red.config)
        return copia

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

    def _reconstruir_desde_diario(self, progreso: Progreso | None = None) -> None:
        """Nace de nuevo y vuelve a estudiar, en orden, todo lo del diario."""
        self._nacer(TAMANOS[self.tamano])
        for e in self._leer_diario():
            self._incorporar(e["texto"], e["fuente"], e["fecha"])
        self.reconstruido = True
        if self.corpus:
            self.entrenar(self.pasos_sugeridos(len(self.corpus)), progreso=progreso)

    def guardar(self) -> None:
        if not self.archivo:
            return
        self.archivo.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.archivo.with_suffix(".tmp")
        torch.save(
            {
                "version": 2,
                "config": self.red.config.como_dict(),
                "tamano": self.tamano,
                "red": self.red.state_dict(),
                "optimizador": self.optimizador.state_dict(),
                "pasos": self.pasos,
                "perdida": self.perdida,
            },
            temporal,
        )
        temporal.replace(self.archivo)

    def cargar(self) -> None:
        datos = torch.load(self.archivo, map_location=self.dispositivo, weights_only=True)
        self.tamano = datos.get("tamano", self.tamano)
        self._nacer(Config(**datos["config"]))
        self.red.load_state_dict(datos["red"])
        self.optimizador.load_state_dict(datos["optimizador"])
        self.pasos, self.perdida = datos["pasos"], datos["perdida"]
        # el texto leído vive en el diario (la red lo necesita para repasar)
        for e in self._leer_diario():
            self._incorporar(e["texto"], e["fuente"], e["fecha"])
