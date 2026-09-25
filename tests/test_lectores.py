import importlib.util
import tempfile
import unittest
from pathlib import Path

from dios import Cerebro
from dios.chat import leer_pegado, procesar
from dios.lectores import ErrorDeLectura, _limpiar_pagina, extraer_texto

EJEMPLOS = Path(__file__).parent.parent / "ejemplos"
HAY_PYPDF = importlib.util.find_spec("pypdf") is not None


class TestLectores(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cerebro = Cerebro(Path(self.tmp.name) / "cerebro.json")

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
        self.assertIn("No sé leer", procesar(self.cerebro, f"/leer {archivo}"))

    @unittest.skipUnless(HAY_PYPDF, "pypdf no está instalado")
    def test_lee_pdf(self):
        n = self.cerebro.leer_archivo(EJEMPLOS / "oceanos.pdf")
        self.assertGreater(n, 5)
        self.assertIn("Marianas", self.cerebro.responder("¿Dónde está la fosa más profunda?"))
        self.assertIn("ballenas", self.cerebro.responder("¿Cuál es el animal más grande?"))

    @unittest.skipUnless(HAY_PYPDF, "pypdf no está instalado")
    def test_lee_carpeta_con_txt_y_pdf(self):
        self.cerebro.leer_archivo(EJEMPLOS)
        self.assertEqual(
            self.cerebro.estado()["fuentes"], ["oceanos.pdf", "sistema_solar.txt"]
        )
        # no mezcla temas: "grande" aparece también en los océanos
        respuesta = self.cerebro.responder("¿Cuál es el planeta más grande?")
        self.assertIn("Júpiter", respuesta)
        self.assertNotIn("océano", respuesta)

    def test_pegar_texto(self):
        lineas = iter(["El mate se toma con yerba.", "Es muy popular en Argentina.", "/fin"])
        texto = leer_pegado(lambda _: next(lineas))
        self.assertEqual(self.cerebro.aprender(texto, fuente="texto pegado"), 2)
        self.assertIn("yerba", self.cerebro.responder("¿con qué se toma el mate?"))

    def test_responde_con_la_oracion_siguiente(self):
        self.cerebro.aprender(
            "El dulce de leche es un postre típico. Se hace cocinando leche con azúcar."
        )
        self.assertIn("azúcar", self.cerebro.responder("¿Cómo se hace el dulce de leche?"))


if __name__ == "__main__":
    unittest.main()
