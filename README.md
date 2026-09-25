# Dios

Una **red neuronal** que nace vacía y aprende de todo lo que le das para leer.
Es del mismo tipo que los modelos de lenguaje como Claude o ChatGPT (un *transformer*),
pero en miniatura, y con una diferencia clave: **no viene preentrenada**.

- Nace con pesos al azar: no sabe ni una letra, ni una palabra, ni un idioma.
- Lee de a bytes, así que ni siquiera trae un vocabulario armado.
- Todo lo que sabe lo aprende entrenándose con los textos y PDFs que vos le das.
- Es **acumulativa**: cada cosa nueva se suma a lo que ya sabía, sesión tras sesión.

## Instalación

```bash
pip install -r requirements.txt
```

Anda en cualquier compu. Si tenés placa de video NVIDIA (o una Mac con chip M), la usa sola y entrena mucho más rápido.

## Cómo usarla

```bash
python chatear.py
```

Funciona desde cualquier carpeta (`python C:\ruta\a\dios\chatear.py`), y en Windows
también con doble clic en `chatear.py`. Si estás parado en la carpeta del proyecto,
`python -m dios` hace lo mismo.

```
=== Dios ===
Acabo de nacer: soy una red de 644.224 parámetros al azar. No sé nada.

vos > /leer quijote.txt
  entrenando [##############################] 2000/2000  pérdida 1.45
dios > Leí quijote.txt. Me entrené 2000 pasos. Ahora escribo palabras y frases con forma.

vos > /entrenar 3000
  entrenando [##############################] 3000/3000  pérdida 1.30
dios > Me entrené 3000 pasos. Ahora escribo palabras y frases con forma.

vos > Don Quijote
dios > (continúa el texto con el estilo de lo que leyó)
```

## Comandos

| Comando | Qué hace |
|---|---|
| `/leer <archivo o carpeta>` | Lee un `.txt`, `.md`, `.pdf` o `.zip` (o todos los de una carpeta) y se entrena con eso |
| `/aprender <texto>` | Se entrena con el texto que escribas |
| `recordá que ...` | Otra forma de enseñarle algo mientras chateás |
| `/pegar` | Pegás un texto largo (varias líneas) y terminás con `/fin` |
| `/entrenar [pasos]` | Estudia más todo lo que ya leyó (por defecto 500 pasos) |
| `/imaginar [inicio]` | Escribe libremente, empezando por lo que le des |
| `/temperatura <n>` | 0.3 = prudente y repetitivo, 1.0 = creativo y caótico (por defecto 0.8) |
| `/estado` | Tamaño de la red, cuánto leyó, cuánto se entrenó y qué tan bien escribe |
| `/olvidar <archivo>` | Olvida sólo ese texto y se reentrena con el resto (ej: `/olvidar chat.txt`) |
| `/olvidar si` | Olvida todo y vuelve a nacer vacía (guarda una copia en `memoria/olvidados/`) |
| `/salir` | Termina (lo aprendido queda guardado) |

Cualquier otra cosa que escribas, la red la **continúa**: escribe lo que, según lo que
aprendió, vendría después. El entrenamiento se puede cortar con **Ctrl+C** y lo
aprendido hasta ahí queda guardado.

## Qué esperar

Una red que arranca de cero necesita **mucho** texto y mucho entrenamiento. Más o menos:

| Lo que le diste | Lo que escribe |
|---|---|
| Nada | Bytes al azar (basura) |
| Unas páginas | Letras y sílabas frecuentes, repite trozos de memoria |
| Un libro | Palabras reales, frases con forma, poco sentido |
| Muchos libros + horas de entrenamiento | Frases con el estilo de lo que leyó |

Claude y ChatGPT leyeron millones de veces más y se entrenaron en miles de computadoras
especiales. Esta es la misma idea, a escala de tu compu.

**Para que aprenda a conversar**, dale textos con forma de conversación: por ejemplo,
diálogos, o un archivo con preguntas y respuestas separadas por una línea en blanco.
La red aprende a responder de la manera en que están escritos los textos que lee.

## Chats de WhatsApp

Exportá el chat desde WhatsApp (chat → ⋮ → Más → Exportar chat → **Sin archivos**) y dáselo
con `/leer`. Dios se da cuenta solo de que es un WhatsApp (Android o iPhone, `.txt` o `.zip`) y lo limpia:

- saca fechas, horas, avisos automáticos, `<Multimedia omitido>`, mensajes eliminados y adjuntos,
- une los mensajes de varios renglones,
- deja una línea en blanco entre charlas separadas por más de 3 horas.

Queda así, que es lo que la red estudia:

```
Federico: llegaste?
Ana: sii recién, estoy muerta jaja
```

Para chatear, escribí igual que en el chat. Dios contesta como la otra persona y corta
cuando te vuelve a tocar a vos:

```
vos > Federico: hola amor, cómo estuvo tu día?
dios > Ana: bien, cansada jaja. vos?
```

## Tamaños

Se elige al nacer (después no se puede cambiar sin `/olvidar`):

```bash
python -m dios --tamano chico      # 0,6 M parámetros (por defecto)
python -m dios --tamano mediano    # 1,9 M: aprende mejor, ~4 veces más lenta
python -m dios --tamano grande     # 14 M: necesita placa de video
python -m dios --tamano diminuto   # para compus muy lentas o para probar
```

## Cómo funciona por dentro

- **La red** (`dios/red.py`): un transformer que mira los últimos bytes y predice el próximo.
  Entrenar es ajustar sus pesos para que prediga cada vez mejor el texto que leyó.
  Escribir es predecir un byte, agregarlo, y repetir.
- **Aprendizaje acumulativo** (`dios/cerebro.py`): cuando le das algo nuevo, la mitad de
  cada tanda de estudio es con lo nuevo y la otra mitad repasa lo que ya había leído.
  Así no se olvida de lo anterior (a las redes neuronales les pasa si sólo estudian lo nuevo).
- **Memoria** en la carpeta `memoria/`:
  - `cerebro.pt`: los pesos de la red, o sea, lo que aprendió.
  - `cerebro_diario.jsonl`: todo lo que leyó, en orden y con fecha. Nunca se borra.
    Si `cerebro.pt` se daña o se pierde, Dios se vuelve a entrenar solo desde el diario.

  La carpeta `memoria/` no se sube a git (es tuya y privada). Para llevarte el cerebro a
  otra compu, copiá esa carpeta.

## Tests

```bash
python -m unittest
```
