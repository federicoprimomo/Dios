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
        self.assertEqual(c.estado(), {"oraciones": 0, "palabras_distintas": 0, "lecturas": 0, "fuentes": [], "desde": None})
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

    def test_acumula_en_muchas_sesiones(self):
        for dia in range(1, 6):
            Cerebro(self.archivo).aprender(f"El dato número {dia} es importante.")
        c = Cerebro(self.archivo)
        self.assertEqual(c.estado()["oraciones"], 5)
        self.assertEqual(c.estado()["lecturas"], 5)
        self.assertIn("número 1", c.responder("dato 1"))
        self.assertIn("número 5", c.responder("dato 5"))

    def test_se_reconstruye_si_la_memoria_se_dana(self):
        Cerebro(self.archivo).aprender("Toby es mi perro.")
        Cerebro(self.archivo).aprender("Michi es mi gato.")
        self.archivo.write_text("{basura", encoding="utf-8")
        c = Cerebro(self.archivo)
        self.assertTrue(c.reconstruido)
        self.assertIn("Toby", c.responder("Toby"))
        self.assertIn("Michi", c.responder("Michi"))
        # y quedó sano para la próxima
        self.assertFalse(Cerebro(self.archivo).reconstruido)

    def test_se_reconstruye_si_la_memoria_se_borra(self):
        Cerebro(self.archivo).aprender("Toby es mi perro.")
        self.archivo.unlink()
        self.assertIn("Toby", Cerebro(self.archivo).responder("Toby"))

    def test_olvidar_guarda_una_copia(self):
        c = Cerebro(self.archivo)
        c.aprender("Algo para olvidar.")
        copia = c.olvidar()
        self.assertEqual(Cerebro(self.archivo).estado()["oraciones"], 0)
        self.assertTrue((copia / "cerebro_diario.jsonl").exists())
        # después de olvidar vuelve a acumular desde cero
        c.aprender("Algo nuevo.")
        self.assertEqual(Cerebro(self.archivo).estado()["oraciones"], 1)

    def test_olvidar_pide_confirmacion(self):
        c = Cerebro(self.archivo)
        c.aprender("No me olvides.")
        self.assertIn("Seguro", procesar(c, "/olvidar"))
        self.assertEqual(Cerebro(self.archivo).estado()["oraciones"], 1)
        self.assertIn("Olvidé", procesar(c, "/olvidar si"))

    def test_chat_ensenar_con_frase(self):
        c = Cerebro(self.archivo)
        procesar(c, "recordá que mi color favorito es el verde")
        self.assertIn("verde", procesar(c, "¿cuál es mi color favorito?"))
        self.assertIsNone(procesar(c, "/salir"))


if __name__ == "__main__":
    unittest.main()
