import importlib.util
import tempfile
import unittest
from pathlib import Path

from dios import Cerebro
from dios.chat import Chat, leer_pegado
from dios.lectores import ErrorDeLectura, _limpiar_pagina, extraer_texto

EJEMPLOS = Path(__file__).parent / "datos"
HAY_PYPDF = importlib.util.find_spec("pypdf") is not None


class TestLectores(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cerebro = Cerebro(Path(self.tmp.name) / "cerebro.pt", tamano="diminuto")

    def tearDown(self):
        self.tmp.cleanup()

    def test_une_lineas_cortadas_de_pdf(self):
        pagina = (
            "Título corto\n"
            "Esta es una oración larga que el PDF cortó en dos\n"
            "líneas y con una pala-\n"
            "bra partida al final de la línea que sigue acá.\n"
        )
        limpio = _limpiar_pagina(pagina)
        self.assertIn("cortó en dos líneas", limpio)
        self.assertIn("palabra partida", limpio)
        self.assertNotIn("Título corto Esta", limpio)

    def test_formato_desconocido(self):
        archivo = Path(self.tmp.name) / "foto.jpg"
        archivo.write_bytes(b"\xff\xd8")
        with self.assertRaises(ErrorDeLectura):
            extraer_texto(archivo)
        self.assertIn("No sé leer", Chat(self.cerebro).procesar(f"/leer {archivo}"))

    @unittest.skipUnless(HAY_PYPDF, "pypdf no está instalado")
    def test_lee_pdf(self):
        pasos = self.cerebro.leer_archivo(EJEMPLOS / "oceanos.pdf", progreso=None)
        self.assertGreater(pasos, 0)
        self.assertIn("fosa de las Marianas".encode(), self.cerebro.corpus)

    @unittest.skipUnless(HAY_PYPDF, "pypdf no está instalado")
    def test_lee_carpeta_con_txt_y_pdf(self):
        self.cerebro.leer_archivo(EJEMPLOS)
        self.assertEqual(
            self.cerebro.estado()["fuentes"], ["oceanos.pdf", "sistema_solar.txt"]
        )

    def test_pegar_texto(self):
        lineas = iter(["El mate se toma con yerba.", "Es muy popular.", "/fin"])
        texto = leer_pegado(lambda _: next(lineas))
        self.assertEqual(texto, "El mate se toma con yerba.\nEs muy popular.")


if __name__ == "__main__":
    unittest.main()
