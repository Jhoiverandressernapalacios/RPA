"""OCR con Tesseract y detección de la cuadrícula de la tabla en la imagen."""

import os
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image, ImageOps

from rpa_dian import config
from rpa_dian.extraccion import Caja, Palabra, votar_numero

if Path(config.TESSERACT_CMD).is_file():
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
if Path(config.TESSDATA_DIR).is_dir():
    os.environ.setdefault("TESSDATA_PREFIX", config.TESSDATA_DIR)

UMBRAL_TINTA = 235  # gris por debajo de esto es tinta (incluye las líneas verde claro)
UMBRAL_FONDO = 200  # gris por encima de esto se vuelve blanco antes del OCR


def preprocesar(imagen: Image.Image) -> Image.Image:
    """Escala de grises y fondo de color (encabezados verde claro) a blanco."""
    return imagen.convert("L").point(lambda v: 255 if v > UMBRAL_FONDO else v)


def leer_texto(imagen: Image.Image) -> str:
    """Texto completo de la página.

    psm 4 (una columna de texto de tamaño variable) deja cada etiqueta en la misma línea que
    su valor ("Fecha de Emisión: 05/11/2025"); la segmentación automática los separaba.
    """
    return pytesseract.image_to_string(
        preprocesar(imagen), lang=config.IDIOMA_OCR, config="--psm 4"
    )


def leer_palabras(imagen: Image.Image) -> list[Palabra]:
    """Cada palabra con su caja. El modo de texto disperso (psm 11) separa bien las celdas."""
    datos = pytesseract.image_to_data(
        preprocesar(imagen),
        lang=config.IDIOMA_OCR,
        config="--psm 11",
        output_type=pytesseract.Output.DICT,
    )
    palabras = []
    for texto, x, y, ancho, alto, confianza in zip(
        datos["text"],
        datos["left"],
        datos["top"],
        datos["width"],
        datos["height"],
        datos["conf"],
        strict=True,
    ):
        if texto.strip() and float(confianza) >= 0:
            palabras.append(Palabra(texto.strip(), x, y, x + ancho, y + alto))
    return palabras


_SOLO_NUMEROS = "-c tessedit_char_whitelist=0123456789.,$"


def leer_celda(imagen: Image.Image, caja: Caja, solo_numeros: bool = False, escala: int = 2) -> str:
    """Lee una celda de tabla: recortada, sin las líneas del borde, ampliada y con margen.

    Leer cada celda por separado (bloque de texto, psm 6) recupera caracteres sueltos y el
    orden de las líneas que el OCR de página completa pierde en celdas angostas. Se borran
    las líneas del borde en vez de recortar un margen, porque hay códigos que llegan al borde.
    Con `solo_numeros` el OCR solo puede devolver dígitos, puntos, comas y "$".
    """
    x0, y0, x1, y1 = (int(round(c)) for c in caja)
    recorte = preprocesar(limpiar_bordes(imagen.crop((x0, y0, x1 + 1, y1 + 1))))
    recorte = recorte.resize(
        (recorte.width * escala, recorte.height * escala), Image.Resampling.LANCZOS
    )
    recorte = ImageOps.expand(recorte, border=20, fill=255)
    opciones = "--psm 6" + (f" {_SOLO_NUMEROS}" if solo_numeros else "")
    return pytesseract.image_to_string(recorte, lang=config.IDIOMA_OCR, config=opciones)


ESCALAS_NUMERO = (3, 2, 4)


def leer_numero(imagen: Image.Image, caja: Caja) -> str:
    """Lee un valor numérico a varias escalas y vota el resultado carácter por carácter.

    Medido en una factura real: cada escala confundía un dígito distinto (4/9, 6/0), pero
    nunca la mayoría el mismo. El orden de ESCALAS_NUMERO decide los empates. Si las dos
    primeras lecturas coinciden, la tercera no cambiaría el voto y se omite.
    """
    lecturas = [leer_celda(imagen, caja, True, e) for e in ESCALAS_NUMERO[:2]]
    if votar_numero(lecturas[:1]) != votar_numero(lecturas[1:]):
        lecturas.append(leer_celda(imagen, caja, True, ESCALAS_NUMERO[2]))
    return votar_numero(lecturas)


def limpiar_bordes(celda: Image.Image, franja: int = 8) -> Image.Image:
    """Pone en blanco las filas y columnas de las orillas que son casi todo tinta (bordes).

    El texto pegado al borde se conserva porque no ocupa más del 60 % de la columna o fila.
    """
    gris = np.asarray(celda.convert("L")).copy()
    tinta = gris < UMBRAL_TINTA
    alto, ancho = gris.shape
    for x in [*range(min(franja, ancho)), *range(max(ancho - franja, 0), ancho)]:
        if tinta[:, x].mean() > 0.6:
            gris[:, x] = 255
    for y in [*range(min(franja, alto)), *range(max(alto - franja, 0), alto)]:
        if tinta[y, :].mean() > 0.6:
            gris[y, :] = 255
    return Image.fromarray(gris)


def detectar_lineas(
    imagen: Image.Image,
    dpi: int = config.DPI_IMAGEN,
    zona: tuple[float, float] | None = None,
) -> tuple[list[float], list[float]]:
    """Posiciones (en píxeles) de las líneas horizontales y verticales de las tablas.

    - Horizontal: fila de píxeles con un tramo continuo de tinta de al menos 40 % del ancho.
      Una franja gruesa (encabezado relleno) aporta su borde superior e inferior.
    - Vertical: columna con un tramo de tinta "delgada" (blanco a ambos lados) de al menos
      0,15 pulgadas; así no cuentan las letras ni los rellenos.
    - `zona` (y0, y1) limita la búsqueda a la franja de la tabla, para no confundir trazos
      delgados de logos con bordes de columnas.
    """
    tinta = np.asarray(imagen.convert("L")) < UMBRAL_TINTA
    desde = 0
    if zona is not None:
        desde = max(int(zona[0]), 0)
        tinta = tinta[desde : int(min(zona[1], tinta.shape[0]))]
    alto, ancho = tinta.shape

    filas = [y for y in range(alto) if _corrida_maxima(tinta[y]) >= 0.4 * ancho]
    horizontales: list[float] = []
    for inicio, fin in _grupos(filas):
        if fin - inicio <= 10:
            horizontales.append(desde + (inicio + fin) / 2)
        else:
            horizontales.extend([float(desde + inicio), float(desde + fin)])

    d = 4
    delgada = tinta.copy()
    delgada[:, d:] &= ~tinta[:, :-d]
    delgada[:, :-d] &= ~tinta[:, d:]
    delgada[:, :d] = False
    delgada[:, -d:] = False
    minimo = 0.15 * dpi
    columnas = [x for x in range(ancho) if _corrida_maxima(delgada[:, x]) >= minimo]
    verticales = [(inicio + fin) / 2 for inicio, fin in _grupos(columnas)]
    return horizontales, verticales


def _corrida_maxima(vector: np.ndarray) -> int:
    """Longitud del tramo más largo de valores True consecutivos."""
    if not vector.any():
        return 0
    bordes = np.diff(np.concatenate(([0], vector.astype(np.int8), [0])))
    inicios, fines = np.flatnonzero(bordes == 1), np.flatnonzero(bordes == -1)
    return int((fines - inicios).max())


def _grupos(indices: list[int]) -> list[tuple[int, int]]:
    """Agrupa índices consecutivos: [3, 4, 5, 9] -> [(3, 5), (9, 9)]."""
    grupos: list[tuple[int, int]] = []
    for i in indices:
        if grupos and i - grupos[-1][1] <= 1:
            grupos[-1] = (grupos[-1][0], i)
        else:
            grupos.append((i, i))
    return grupos
