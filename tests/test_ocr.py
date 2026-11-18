"""Pruebas de la detección de líneas y la limpieza de celdas (sin Tesseract)."""

import numpy as np
from PIL import Image

from rpa_dian.ocr import detectar_lineas, limpiar_bordes

BLANCO, NEGRO = 255, 0


def imagen_con_tabla_y_logo() -> Image.Image:
    """Lienzo blanco con un trazo vertical delgado arriba (como el logo DIAN) y una tabla abajo."""
    lienzo = np.full((1000, 800), BLANCO, dtype=np.uint8)
    lienzo[50:150, 316:319] = NEGRO  # trazo del logo: delgado y alto, fuera de la tabla
    for y in (500, 600, 700):  # bordes horizontales de la tabla
        lienzo[y : y + 3, 100:700] = NEGRO
    for x in (100, 250, 700):  # bordes verticales de la tabla
        lienzo[500:703, x : x + 3] = NEGRO
    return Image.fromarray(lienzo)


def test_con_zona_solo_cuenta_las_lineas_verticales_dentro_de_la_tabla():
    _, verticales = detectar_lineas(imagen_con_tabla_y_logo(), zona=(480, 720))
    assert [round(x) for x in verticales] == [101, 251, 701]


def test_sin_zona_tambien_cuenta_el_trazo_del_logo():
    _, verticales = detectar_lineas(imagen_con_tabla_y_logo())
    assert any(abs(x - 317) <= 2 for x in verticales)


def test_detecta_las_lineas_horizontales_de_la_tabla():
    horizontales, _ = detectar_lineas(imagen_con_tabla_y_logo(), zona=(480, 720))
    assert [round(y) for y in horizontales] == [501, 601, 701]


def test_limpiar_bordes_borra_las_lineas_del_borde_y_conserva_el_texto_pegado_a_ellas():
    celda = np.full((60, 100), BLANCO, dtype=np.uint8)
    celda[:, 0:3] = NEGRO  # borde izquierdo
    celda[:, 97:100] = NEGRO  # borde derecho
    celda[0:2, :] = NEGRO  # borde superior
    celda[20:40, 4:8] = NEGRO  # trazo de un dígito pegado al borde izquierdo
    celda[20:40, 90:96] = NEGRO  # trazo de un dígito pegado al borde derecho
    limpia = np.asarray(limpiar_bordes(Image.fromarray(celda)))
    assert (limpia[:, 0:3] == BLANCO).all()
    assert (limpia[:, 97:100] == BLANCO).all()
    assert (limpia[0:2, :] == BLANCO).all()
    assert (limpia[20:40, 4:8] == NEGRO).all()
    assert (limpia[20:40, 90:96] == NEGRO).all()
