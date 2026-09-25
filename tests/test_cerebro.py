import tempfile
import unittest
from pathlib import Path

from dios import Cerebro
from dios.chat import procesar


class TestCerebro(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.archivo = Path(self.tmp.name) / "cerebro.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_empieza_vacio(self):
        c = Cerebro(self.archivo)
        self.assertEqual(c.estado()["oraciones"], 0)
        self.assertIn("vacío", c.responder("¿Qué es el Sol?"))

    def test_aprende_y_responde(self):
        c = Cerebro(self.archivo)
        c.aprender("Los gatos duermen mucho. Los perros ladran a los carteros.")
        self.assertIn("gatos", c.responder("¿Qué hacen los gatos?"))
        self.assertIn("perros", c.responder("perro"))

    def test_no_viene_preentrenado(self):
        c = Cerebro(self.archivo)
        self.assertEqual(c.estado(), {"oraciones": 0, "palabras_distintas": 0, "lecturas": 0, "fuentes": []})
        self.assertIn("No tengo palabras", c.imaginar())

    def test_aprende_un_idioma_inventado(self):
        # No trae conocimiento de ningún idioma: aprende igual uno que no existe.
        c = Cerebro(self.archivo)
        c.aprender("Blorg zintapo fe kramu. Quarnel mip dolo sefa.")
        self.assertIn("Blorg", c.responder("zintapo"))
        self.assertIn("Quarnel", c.responder("dolo mip"))
        self.assertIn("Nunca leí: gato", c.responder("gato"))

    def test_no_sabe_lo_que_no_aprendio(self):
        c = Cerebro(self.archivo)
        c.aprender("Los gatos duermen mucho.")
        self.assertIn("No aprendí", c.responder("¿Qué es un volcán?"))

    def test_acumula_entre_sesiones(self):
        Cerebro(self.archivo).aprender("Buenos Aires es la capital de Argentina.")
        c = Cerebro(self.archivo)
        c.aprender("Montevideo es la capital de Uruguay.")
        c = Cerebro(self.archivo)
        self.assertEqual(c.estado()["oraciones"], 2)
        self.assertIn("Uruguay", c.responder("capital de uruguay"))
        self.assertIn("Argentina", c.responder("capital de argentina"))

    def test_no_duplica(self):
        c = Cerebro(self.archivo)
        self.assertEqual(c.aprender("El agua moja."), 1)
        self.assertEqual(c.aprender("El agua moja."), 0)

    def test_leer_archivo_e_imaginar(self):
        c = Cerebro(self.archivo)
        ejemplo = Path(__file__).parent / "datos" / "sistema_solar.txt"
        self.assertGreater(c.leer_archivo(ejemplo), 5)
        self.assertIn("Júpiter", c.responder("¿Cuál es el planeta más grande?"))
        self.assertTrue(c.imaginar())

    def test_olvidar(self):
        c = Cerebro(self.archivo)
        c.aprender("Algo para olvidar.")
        c.olvidar()
        self.assertEqual(Cerebro(self.archivo).estado()["oraciones"], 0)

    def test_chat_ensenar_con_frase(self):
        c = Cerebro(self.archivo)
        procesar(c, "recordá que mi color favorito es el verde")
        self.assertIn("verde", procesar(c, "¿cuál es mi color favorito?"))
        self.assertIsNone(procesar(c, "/salir"))


if __name__ == "__main__":
    unittest.main()
