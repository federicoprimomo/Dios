"""La red neuronal de Dios: un transformer chico, como los de los modelos de lenguaje.

Lee el texto en piezas (pedazos de palabra) que descubre el tokenizador a partir
de lo que lee. Al nacer sólo conoce los 256 bytes (letras sueltas) y tiene lugar
reservado para las piezas que vaya descubriendo. Empieza con pesos al azar y todo
lo demás lo aprende entrenándose con lo que le das.
"""

import math
from dataclasses import asdict, dataclass

import torch
import torch.nn as nn
from torch.nn import functional as F

@dataclass
class Config:
    tokens: int = 4096  # cuántas piezas distintas puede llegar a conocer
    contexto: int = 256  # cuántas piezas hacia atrás puede mirar
    capas: int = 4
    cabezas: int = 4
    dimension: int = 192
    abandono: float = 0.1  # "dropout": ayuda a no memorizar de más

    def como_dict(self) -> dict:
        return asdict(self)


TAMANOS = {
    "diminuto": Config(tokens=512, contexto=64, capas=2, cabezas=2, dimension=64, abandono=0.0),
    "chico": Config(tokens=1024, contexto=128, capas=3, cabezas=4, dimension=128, abandono=0.2),
    "mediano": Config(tokens=2048, abandono=0.2),
    "grande": Config(tokens=4096, contexto=512, capas=8, cabezas=8, dimension=384),
}


class Atencion(nn.Module):
    """Cada posición mira las anteriores y decide cuáles le importan."""

    def __init__(self, c: Config):
        super().__init__()
        self.cabezas = c.cabezas
        self.qkv = nn.Linear(c.dimension, 3 * c.dimension)
        self.salida = nn.Linear(c.dimension, c.dimension)
        self.abandono = c.abandono

    def forward(self, x):
        b, t, d = x.shape
        q, k, v = self.qkv(x).split(d, dim=2)
        q, k, v = (z.view(b, t, self.cabezas, d // self.cabezas).transpose(1, 2) for z in (q, k, v))
        y = F.scaled_dot_product_attention(
            q, k, v, is_causal=True, dropout_p=self.abandono if self.training else 0.0
        )
        return self.salida(y.transpose(1, 2).contiguous().view(b, t, d))


class Bloque(nn.Module):
    def __init__(self, c: Config):
        super().__init__()
        self.norma1 = nn.LayerNorm(c.dimension)
        self.atencion = Atencion(c)
        self.norma2 = nn.LayerNorm(c.dimension)
        self.mlp = nn.Sequential(
            nn.Linear(c.dimension, 4 * c.dimension),
            nn.GELU(),
            nn.Linear(4 * c.dimension, c.dimension),
            nn.Dropout(c.abandono),
        )

    def forward(self, x):
        x = x + self.atencion(self.norma1(x))
        return x + self.mlp(self.norma2(x))


class Red(nn.Module):
    """Predice cuál es la próxima pieza a partir de las anteriores."""

    def __init__(self, c: Config):
        super().__init__()
        self.config = c
        self.piezas = nn.Embedding(c.tokens, c.dimension)
        self.posiciones = nn.Embedding(c.contexto, c.dimension)
        self.abandono = nn.Dropout(c.abandono)
        self.bloques = nn.ModuleList(Bloque(c) for _ in range(c.capas))
        self.norma = nn.LayerNorm(c.dimension)
        self.cabeza = nn.Linear(c.dimension, c.tokens, bias=False)
        self.cabeza.weight = self.piezas.weight  # comparten pesos (menos parámetros)
        self.apply(self._iniciar_al_azar)

    @staticmethod
    def _iniciar_al_azar(modulo):
        if isinstance(modulo, (nn.Linear, nn.Embedding)):
            nn.init.normal_(modulo.weight, mean=0.0, std=0.02)
        if isinstance(modulo, nn.Linear) and modulo.bias is not None:
            nn.init.zeros_(modulo.bias)

    def parametros(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def forward(self, entrada, objetivo=None):
        _, t = entrada.shape
        pos = torch.arange(t, device=entrada.device)
        x = self.abandono(self.piezas(entrada) + self.posiciones(pos))
        for bloque in self.bloques:
            x = bloque(x)
        logits = self.cabeza(self.norma(x))
        perdida = None
        if objetivo is not None:
            perdida = F.cross_entropy(logits.reshape(-1, logits.size(-1)), objetivo.reshape(-1))
        return logits, perdida

    @torch.no_grad()
    def presentar_piezas(self, nuevas: list[int], partes: list[tuple[int, int]]) -> None:
        """Una pieza nueva arranca a mitad de camino entre las dos que la forman."""
        for nueva, (a, b) in zip(nuevas, partes):
            self.piezas.weight[nueva] = (self.piezas.weight[a] + self.piezas.weight[b]) / 2

    @torch.no_grad()
    def generar(self, inicio: list[int], activas: int, largo: int = 150, temperatura: float = 0.8,
                mejores: int = 40, parar=None) -> list[int]:
        """Escribe pieza por pieza, eligiendo cada una según lo que aprendió.

        activas: cuántas piezas conoce hasta ahora (las demás no las puede usar).
        mejores: sólo elige entre las piezas más probables (evita disparates).
        parar: función que recibe lo escrito y dice si ya terminó.
        """
        self.eval()
        dispositivo = next(self.parameters()).device
        x = torch.tensor([inicio or [10]], dtype=torch.long, device=dispositivo)
        nuevos: list[int] = []
        for _ in range(largo):
            logits, _ = self(x[:, -self.config.contexto:])
            logits = logits[0, -1, :activas] / max(temperatura, 1e-3)
            if mejores and mejores < activas:
                corte = torch.topk(logits, mejores).values[-1]
                logits = logits.masked_fill(logits < corte, float("-inf"))
            siguiente = torch.multinomial(F.softmax(logits, dim=-1), 1)
            nuevos.append(siguiente.item())
            if parar and parar(nuevos):
                break
            x = torch.cat([x, siguiente.view(1, 1)], dim=1)
        return nuevos


def perdida_a_texto(perdida: float | None) -> str:
    """Traduce la pérdida por letra (qué tan mal predice) a algo entendible."""
    if perdida is None:
        return "todavía no entrené nada"
    # la perplejidad es "entre cuántos bytes duda" en promedio al escribir
    duda = math.exp(perdida)
    if duda > 40:
        nivel = "estoy balbuceando: casi no reconozco patrones"
    elif duda > 12:
        nivel = "reconozco letras y sílabas frecuentes"
    elif duda > 5:
        nivel = "armo palabras, todavía sin mucho sentido"
    elif duda > 2.5:
        nivel = "escribo palabras y frases con forma"
    else:
        nivel = "conozco muy bien lo que leí (quizás de memoria)"
    return f"{nivel} (dudo entre ~{duda:.1f} opciones por letra)"
