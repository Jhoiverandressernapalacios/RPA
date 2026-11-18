"""Une las piezas para una factura: PDF cifrado -> imágenes -> OCR -> encabezado y productos."""

import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from rpa_dian.conversion import pdf_a_imagenes
from rpa_dian.extraccion import (
    Encabezado,
    Producto,
    extraer_encabezado,
    extraer_productos,
    producto_desde_textos,
    ubicar_celdas,
    zona_tabla,
)
from rpa_dian.ocr import detectar_lineas, leer_celda, leer_numero, leer_palabras, leer_texto


@dataclass
class Factura:
    cufe: str
    encabezado: Encabezado
    productos: list[Producto]
    imagenes: list[Path] = field(default_factory=list)
    texto_ocr: str = ""
    tiempos: dict[str, float] = field(default_factory=dict)  # segundos por etapa


def procesar_pdf(ruta: Path, nit: str, carpeta_imagenes: Path) -> Factura:
    inicio = time.monotonic()
    imagenes = pdf_a_imagenes(ruta, nit, carpeta_imagenes)
    conversion = time.monotonic() - inicio
    textos, productos = [], []
    for ruta_imagen in imagenes:
        with Image.open(ruta_imagen) as imagen:
            textos.append(leer_texto(imagen))
            productos.extend(_productos_de_la_pagina(imagen))
    texto = "\n".join(textos)
    total = time.monotonic() - inicio
    return Factura(
        cufe=ruta.stem,
        encabezado=extraer_encabezado(texto),
        productos=productos,
        imagenes=imagenes,
        texto_ocr=texto,
        tiempos={"conversion": conversion, "ocr": total - conversion, "total": total},
    )


def _productos_de_la_pagina(imagen: Image.Image) -> list[Producto]:
    """Con cuadrícula se lee cada celda por separado; sin ella, se usan las palabras sueltas."""
    palabras = leer_palabras(imagen)
    zona = zona_tabla(palabras)
    if zona is None:
        return []
    horizontales, verticales = detectar_lineas(imagen, zona=zona)
    filas = ubicar_celdas(palabras, horizontales, verticales)
    if not filas:
        return extraer_productos(palabras, horizontales, verticales)
    return [
        producto_desde_textos(
            codigo=leer_celda(imagen, fila["codigo"]),
            descripcion=leer_celda(imagen, fila["descripcion"]),
            cantidad=leer_numero(imagen, fila["cantidad"]),
            precio=leer_numero(imagen, fila["precio"]),
        )
        for fila in filas
    ]
