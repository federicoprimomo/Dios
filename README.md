# Dios

Una inteligencia artificial que **empieza vacía** y aprende de todo lo que le das para leer.
Todo lo que aprende se guarda, así que sesión tras sesión va sumando conocimiento.

**No viene preentrenada.** No trae datos, ni textos, ni listas de palabras, ni reglas de
gramática: ni siquiera sabe español. Todo lo que sabe (incluso qué palabras son
"de relleno", como *el*, *de* o *que*) lo descubre leyendo lo que vos le das.

Hecho en Python puro: no necesita internet ni GPU. Para leer PDFs hace falta una sola librería:

```bash
pip install -r requirements.txt
```

## Cómo usarlo

```bash
python -m dios
```

```
=== Dios ===
Estoy vacío. Enseñame algo.

vos > ¿qué es el sol?
dios > Todavía no sé nada. Estoy vacío. Dame algo para leer...

vos > /leer sistema_solar.txt
dios > Listo, leí sistema_solar.txt y aprendí 9 oraciones nuevas.

vos > /leer oceanos.pdf
dios > Listo, leí oceanos.pdf y aprendí 8 oraciones nuevas.

vos > ¿cuál es el planeta más grande?
dios > (Nunca leí: cuál.) Júpiter es el planeta más grande del sistema solar.

vos > recordá que Plutón fue degradado a planeta enano en 2006
dios > Anotado, ya lo sé.

vos > ¿qué pasó con plutón?
dios > Plutón fue degradado a planeta enano en 2006
```

## Comandos

| Comando | Qué hace |
|---|---|
| `/leer <archivo o carpeta>` | Lee un `.txt`, `.md` o `.pdf` (o todos los de una carpeta) y lo aprende |
| `/pegar` | Pegás un texto largo (varias líneas) y termina con `/fin` |
| `/aprender <texto>` | Aprende el texto que escribas |
| `recordá que ...` / `aprendé que ...` | Otra forma de enseñarle algo mientras chateás |
| `/imaginar [palabras]` | Inventa texto nuevo con el estilo de lo que leyó |
| `/estado` | Cuánto sabe y de dónde lo aprendió |
| `/olvidar` | Borra todo y vuelve a estar vacío |
| `/salir` | Termina (lo aprendido queda guardado) |

Cualquier otra cosa que escribas es una pregunta.

## Cómo funciona por dentro

Como no sabe nada de antemano, al principio es torpe: te avisa qué palabras de tu
pregunta nunca leyó (`(Nunca leí: cuál.)`) y puede confundirse con palabras muy
comunes. Cuanto más le das para leer, mejor distingue lo importante.

- **Memoria** (`dios/cerebro.py`): cada texto se parte en oraciones y se indexa con
  [BM25](https://es.wikipedia.org/wiki/Okapi_BM25), el mismo tipo de algoritmo que usan los buscadores.
  Cuando preguntás, busca las oraciones más relevantes y te responde con ellas.
  Las palabras raras pesan más que las que aparecen en todos lados; eso lo calcula
  con lo que leyó, no con una lista hecha a mano.
- **Palabras parecidas**: une *planeta* con *planetas* o *perro* con *perros* sólo porque
  empiezan igual, sin reglas del idioma.
- **Lenguaje**: una cadena de Markov aprende qué palabra suele venir después de cada par de palabras.
  Con eso `/imaginar` escribe frases nuevas con el estilo de lo que leyó (pueden mezclar datos: es imaginación, no memoria).
- **Persistencia**: todo se guarda en `memoria/cerebro.json`. Podés usar otro archivo con
  `python -m dios --memoria otro_cerebro.json` para tener varios cerebros distintos.

## Tests

```bash
python -m unittest
```

## Ideas para seguir

- Leer páginas web y documentos de Word.
- Leer PDFs escaneados (necesita OCR).
- Que descubra sinónimos solo ("auto" ≈ "coche") viendo qué palabras aparecen en contextos parecidos.
- Una pequeña red neuronal entrenada desde cero, sólo con lo que le diste, para que redacte mejor.
