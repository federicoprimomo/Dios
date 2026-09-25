import random
import tempfile
import unittest
from pathlib import Path

import torch

from dios import Cerebro
from dios.chat import Chat

REPETIDO = "El gato duerme en la cama. " * 40


def sin_barra(*_):
    pass


class TestCerebro(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(0)
        random.seed(0)
        self.tmp = tempfile.TemporaryDirectory()
        self.archivo = Path(self.tmp.name) / "cerebro.pt"

    def tearDown(self):
        self.tmp.cleanup()

    def nuevo(self):
        return Cerebro(self.archivo, tamano="diminuto")

    def test_nace_vacio_y_al_azar(self):
        c = self.nuevo()
        e = c.estado()
        self.assertEqual((e["pasos"], e["bytes_leidos"], e["perdida"]), (0, 0, None))
        self.assertIn("vacío", c.responder("hola"))
        # dos redes recién nacidas son distintas: pesos al azar, nada preentrenado
        otra = Cerebro(tamano="diminuto")
        self.assertFalse(torch.equal(c.red.letras.weight, otra.red.letras.weight))

    def test_aprende_de_lo_que_lee(self):
        c = self.nuevo()
        c.aprender(REPETIDO, pasos=5)
        perdida_inicial = c.perdida
        c.entrenar(300)
        self.assertLess(c.perdida, perdida_inicial / 2)
        self.assertIn("duerme", c.imaginar("El gato", temperatura=0.1, largo=40))

    def test_acumula_entre_sesiones(self):
        c = self.nuevo()
        c.aprender("Primer texto.", pasos=10)
        pesos = c.red.letras.weight.detach().clone()
        c = self.nuevo()  # otra sesión
        self.assertEqual(c.pasos, 10)
        self.assertTrue(torch.equal(c.red.letras.weight, pesos))
        c.aprender("Segundo texto.", pasos=10)
        c = self.nuevo()
        self.assertEqual(c.pasos, 20)
        self.assertEqual(c.estado()["lecturas"], 2)
        self.assertIn(b"Primer texto.", c.corpus)
        self.assertIn(b"Segundo texto.", c.corpus)

    def test_repasa_lo_viejo_al_aprender_lo_nuevo(self):
        c = self.nuevo()
        c.aprender("a" * 500, pasos=1)
        desde = c._incorporar("b" * 500, "x", "f")
        x, _ = c._lote(32, desde)
        filas_viejas = sum(1 for fila in x.tolist() if ord("a") in fila)
        self.assertGreaterEqual(filas_viejas, 8)  # repasa lo anterior
        self.assertGreaterEqual(32 - filas_viejas, 8)  # y estudia lo nuevo

    def test_se_reconstruye_si_la_memoria_se_dana(self):
        self.nuevo().aprender("Toby es mi perro.", pasos=5)
        self.archivo.write_bytes(b"basura")
        c = self.nuevo()
        self.assertTrue(c.reconstruido)
        self.assertGreater(c.pasos, 0)
        self.assertIn(b"Toby", c.corpus)
        self.assertFalse(self.nuevo().reconstruido)

    def test_olvidar(self):
        c = self.nuevo()
        chat = Chat(c, progreso=sin_barra)
        c.aprender("No me olvides.", pasos=5)
        self.assertIn("Seguro", chat.procesar("/olvidar"))
        self.assertEqual(self.nuevo().pasos, 5)
        self.assertIn("nacer", chat.procesar("/olvidar si"))
        self.assertEqual(self.nuevo().pasos, 0)
        self.assertTrue(list((Path(self.tmp.name) / "olvidados").glob("*/cerebro_diario.jsonl")))

    def test_chat(self):
        c = self.nuevo()
        chat = Chat(c, progreso=sin_barra)
        self.assertIn("Me entrené", chat.procesar("recordá que el cielo es azul"))
        self.assertIn(b"El cielo es azul", c.corpus)
        self.assertIn("Me entrené 20 pasos", chat.procesar("/entrenar 20"))
        self.assertIn("parámetros", chat.procesar("/estado"))
        self.assertIsInstance(chat.procesar("hola"), str)
        self.assertIsNone(chat.procesar("/salir"))


if __name__ == "__main__":
    unittest.main()
