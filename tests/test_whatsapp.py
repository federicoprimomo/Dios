import tempfile
import unittest
import zipfile
from pathlib import Path

from dios import Cerebro
from dios.chat import Chat
from dios.lectores import extraer_texto
from dios.whatsapp import es_whatsapp, limpiar

ANDROID = """\
12/06/26, 22:10 - Los mensajes y las llamadas están cifrados de extremo a extremo. Nadie fuera de este chat puede leerlos.
12/06/26, 22:14 - Federico: llegaste?
12/06/26, 22:15 - Ana: sii recién, estoy muerta jaja
12/06/26, 22:15 - Ana: <Multimedia omitido>
12/06/26, 22:16 - Ana: mañana te cuento
todo lo que pasó
12/06/26, 22:16 - Federico: Se eliminó este mensaje.
12/06/26, 22:17 - Federico: IMG-20260612-WA0003.jpg (archivo adjunto)
12/06/26, 22:18 - Federico: dale, descansá <Se editó este mensaje.>
13/06/26, 08:03 - Ana: buen díaa ☀️
"""

IPHONE = (
    "‎[12/6/26, 10:14:05 p. m.] Ana: hola: todo bien?\n"
    "[12/6/26, 10:15:40 p. m.] Federico: sí!\n"
    "‎[12/6/26, 10:15:41 p. m.] Federico: ‎imagen omitida\n"
    "[13/6/26, 9:01:00 a. m.] Ana: buen día\n"
)


class TestWhatsApp(unittest.TestCase):
    def test_limpia_android(self):
        self.assertEqual(
            limpiar(ANDROID),
            "Federico: llegaste?\n"
            "Ana: sii recién, estoy muerta jaja\n"
            "Ana: mañana te cuento todo lo que pasó\n"
            "Federico: dale, descansá\n"
            "\n"
            "Ana: buen díaa ☀️",
        )

    def test_limpia_iphone(self):
        self.assertEqual(
            limpiar(IPHONE),
            "Ana: hola: todo bien?\nFederico: sí!\n\nAna: buen día",
        )

    def test_detecta_solo_whatsapp(self):
        self.assertTrue(es_whatsapp(ANDROID))
        self.assertTrue(es_whatsapp(IPHONE))
        self.assertFalse(es_whatsapp("Había una vez un gato.\nEl gato dormía: mucho."))

    def test_lee_txt_y_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            txt = Path(tmp) / "Chat de WhatsApp con Ana.txt"
            txt.write_text(ANDROID, encoding="utf-8")
            self.assertTrue(extraer_texto(txt).startswith("Federico: llegaste?"))
            zipeado = Path(tmp) / "chat.zip"
            with zipfile.ZipFile(zipeado, "w") as z:
                z.writestr("_chat.txt", IPHONE)
                z.writestr("foto.jpg", b"\xff\xd8")
            self.assertTrue(extraer_texto(zipeado).startswith("Ana: hola"))


class TestOlvidarUnTexto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.archivo = Path(self.tmp.name) / "cerebro.pt"

    def tearDown(self):
        self.tmp.cleanup()

    def test_olvida_solo_ese_texto(self):
        c = Cerebro(self.archivo, tamano="diminuto")
        c.aprender("El libro que quiero conservar.", fuente="libro.txt", pasos=5)
        c.aprender("12/06/26 chat sucio", fuente="chat.txt", pasos=5)
        chat = Chat(c, progreso=None)
        self.assertIn("chat.txt", chat.procesar("/olvidar"))
        self.assertIn("No leí nada llamado", chat.procesar("/olvidar otro.txt"))
        self.assertIn("Olvidé chat.txt", chat.procesar("/olvidar chat.txt"))
        for cerebro in (c, Cerebro(self.archivo, tamano="diminuto")):
            self.assertEqual(cerebro.estado()["fuentes"], ["libro.txt"])
            self.assertNotIn(b"chat sucio", cerebro.corpus)
            self.assertGreater(cerebro.pasos, 0)
        self.assertTrue(list((Path(self.tmp.name) / "olvidados").glob("*/cerebro_diario.jsonl")))

    def test_responde_hasta_que_te_toca(self):
        c = Cerebro(tamano="diminuto")
        c.aprender("Fede: hola\nAna: hola amor\nFede: todo bien?\nAna: sii\n" * 30, pasos=300)
        respuesta = c.responder("Fede: hola", temperatura=0.1)
        self.assertNotIn("Fede:", respuesta)


if __name__ == "__main__":
    unittest.main()
