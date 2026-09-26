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
        self.assertFalse(torch.equal(c.red.piezas.weight, otra.red.piezas.weight))

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
        pesos = c.red.piezas.weight.detach().clone()
        c = self.nuevo()  # otra sesión
        self.assertEqual(c.pasos, 10)
        self.assertTrue(torch.equal(c.red.piezas.weight, pesos))
        c.aprender("Segundo texto.", pasos=10)
        c = self.nuevo()
        self.assertEqual(c.pasos, 20)
        self.assertEqual(c.estado()["lecturas"], 2)
        self.assertIn(b"Primer texto.", c.corpus)
        self.assertIn(b"Segundo texto.", c.corpus)

    def test_repasa_lo_viejo_al_aprender_lo_nuevo(self):
        c = self.nuevo()
        viejo = " ".join("".join(random.choices("aeiou", k=3)) for _ in range(300))
        nuevo = " ".join("".join(random.choices("bcdfg", k=3)) for _ in range(300))
        c.aprender(viejo, pasos=1)
        desde = c._incorporar(nuevo, "x", "f")
        x, _ = c._lote(32, desde)
        filas = [c.tokenizador.decodificar(fila) for fila in x.tolist()]
        vocales, consonantes = set(b"aeiou"), set(b"bcdfg")
        viejas = sum(1 for f in filas if set(f) & vocales and not set(f) & consonantes)
        nuevas = sum(1 for f in filas if set(f) & consonantes and not set(f) & vocales)
        self.assertGreaterEqual(viejas, 8)  # repasa lo anterior
        self.assertGreaterEqual(nuevas, 8)  # y estudia lo nuevo

    def test_descubre_piezas_de_palabra(self):
        c = self.nuevo()
        self.assertEqual(c.estado()["piezas"], 256)  # al nacer: sólo letras sueltas
        c.aprender(REPETIDO, pasos=1)
        self.assertLess(c.estado()["piezas"], 270)  # con poco texto, pocas piezas
        c.aprender(REPETIDO * 20, pasos=1)
        piezas = {p.decode("utf-8", "replace") for p in c.tokenizador.piezas}
        self.assertIn(" gato", piezas)
        self.assertGreater(c.estado()["piezas"], 256)
        # vuelven iguales al abrirlo de nuevo
        self.assertEqual(self.nuevo().tokenizador.uniones, c.tokenizador.uniones)

    def test_mide_con_texto_apartado(self):
        c = self.nuevo()
        texto = " ".join(f"El número {i} viene después del {i - 1}." for i in range(1, 300))
        c.aprender(texto, pasos=30)
        e = c.estado()
        self.assertIsNotNone(e["perdida_aparte"])
        self.assertGreater(len(c._aparte), 0)
        # lo apartado nunca aparece en lo que estudia
        final = c.tokenizador.decodificar(c._aparte.tolist())
        self.assertNotIn(final, c.tokenizador.decodificar(c._estudio.tolist()))

    def test_freno_automatico_si_memoriza(self):
        import dios.cerebro as modulo
        viejo, modulo.REVISAR_CADA = modulo.REVISAR_CADA, 25
        try:
            c = self.nuevo()
            palabras = ["".join(random.choices("abcdefghij", k=5)) for _ in range(900)]
            c.aprender(" ".join(palabras), pasos=1)  # texto al azar: sólo se puede memorizar
            c.entrenar(3000)
            self.assertIsNotNone(c.frenado_en)
            self.assertLess(c.frenado_en, 3000)
            self.assertIn("Frené", Chat(c, progreso=None).aprendido(c.frenado_en))
        finally:
            modulo.REVISAR_CADA = viejo

    def test_se_actualiza_desde_una_version_vieja(self):
        self.nuevo().aprender("Toby es mi perro.", pasos=5)
        datos = torch.load(self.archivo, weights_only=True)
        datos["version"] = 2
        torch.save(datos, self.archivo)
        avisos = []
        c = Cerebro(self.archivo, tamano="diminuto", avisar=avisos.append)
        self.assertTrue(c.actualizado)
        self.assertIn("versión nueva", avisos[0])
        self.assertIn(b"Toby", c.corpus)
        self.assertGreater(c.pasos, 0)
        guardados = list((Path(self.tmp.name) / "olvidados").glob("*/cerebro.pt"))
        self.assertEqual(len(guardados), 1)
        self.assertFalse(self.nuevo().actualizado)

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
        self.assertIn("/olvidar si", chat.procesar("/olvidar"))
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
