"""Pruebas de integración: PDF cifrado -> imagen -> OCR -> campos, con Tesseract real.

Usan las facturas de EJEMPLO de tests/fixtures/pdf (datos ficticios) y su JSON esperado.
"""

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from rpa_dian import config
from rpa_dian.conversion import PdfProtegidoError, pdf_a_imagenes
from rpa_dian.ocr import detectar_lineas, leer_texto
from rpa_dian.proceso import procesar_pdf

FIXTURES = Path(__file__).parent / "fixtures" / "pdf"
ESPERADOS = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURES.glob("*.json"))]

hay_tesseract = Path(config.TESSERACT_CMD).is_file() or shutil.which("tesseract") is not None
requiere_tesseract = pytest.mark.skipif(not hay_tesseract, reason="Tesseract no está instalado")


def pdf_de(esperado: dict) -> Path:
    return FIXTURES / f"{esperado['cufe']}.pdf"


def sin_espacios(texto: str) -> str:
    return "".join(texto.split())


# --- Conversión -------------------------------------------------------------


def test_un_pdf_cifrado_con_un_nit_equivocado_da_un_error_claro(tmp_path):
    with pytest.raises(PdfProtegidoError, match="NIT"):
        pdf_a_imagenes(pdf_de(ESPERADOS[0]), "123", tmp_path)


def test_convierte_cada_pagina_en_un_png_a_300_dpi(tmp_path):
    esperado = ESPERADOS[0]
    imagenes = pdf_a_imagenes(pdf_de(esperado), esperado["nit_clave"], tmp_path)
    assert len(imagenes) == 1
    assert imagenes[0].name == f"{esperado['cufe']}_p1.png"
    with Image.open(imagenes[0]) as imagen:
        assert imagen.width == pytest.approx(595 * 300 / 72, abs=2)


def test_detecta_las_lineas_de_la_cuadricula_de_la_tabla(tmp_path):
    esperado = ESPERADOS[0]
    [ruta] = pdf_a_imagenes(pdf_de(esperado), esperado["nit_clave"], tmp_path)
    with Image.open(ruta) as imagen:
        horizontales, verticales = detectar_lineas(imagen)
    escala = 300 / 72
    # Bordes de las columnas Nro | Código | Descripción del generador (puntos -> píxeles)
    for x_pt in (30, 51, 82, 156):
        assert any(abs(x - x_pt * escala) <= 4 for x in verticales), x_pt
    assert len(horizontales) >= 3


# --- OCR ----------------------------------------------------------------------


@requiere_tesseract
def test_el_ocr_lee_los_titulos_de_las_tres_secciones(tmp_path):
    esperado = ESPERADOS[0]
    [ruta] = pdf_a_imagenes(pdf_de(esperado), esperado["nit_clave"], tmp_path)
    with Image.open(ruta) as imagen:
        texto = leer_texto(imagen)
    for titulo in ("Datos del Documento", "Datos del Emisor", "Detalles de Productos"):
        assert titulo in texto


@pytest.fixture(scope="module")
def facturas(tmp_path_factory):
    """Procesa cada PDF de ejemplo una sola vez (el OCR tarda unos segundos por factura)."""
    if not hay_tesseract:
        pytest.skip("Tesseract no está instalado")
    carpeta = tmp_path_factory.mktemp("img")
    return {e["cufe"]: procesar_pdf(pdf_de(e), e["nit_clave"], carpeta) for e in ESPERADOS}


@requiere_tesseract
@pytest.mark.parametrize("esperado", ESPERADOS, ids=[e["numero_factura"] for e in ESPERADOS])
def test_extrae_el_encabezado_de_la_factura_de_ejemplo(facturas, esperado):
    factura = facturas[esperado["cufe"]]
    assert factura.encabezado.numero_factura == esperado["numero_factura"]
    assert factura.encabezado.fecha_emision == esperado["fecha_emision"]
    assert factura.encabezado.nit_emisor == esperado["nit_emisor"]


@requiere_tesseract
@pytest.mark.parametrize("esperado", ESPERADOS, ids=[e["numero_factura"] for e in ESPERADOS])
def test_extrae_los_productos_de_la_factura_de_ejemplo(facturas, esperado):
    factura = facturas[esperado["cufe"]]
    obtenidos = [
        (p.codigo, sin_espacios(p.descripcion), p.cantidad, p.precio_unitario)
        for p in factura.productos
    ]
    esperados = [
        (p["codigo"], sin_espacios(p["descripcion"]), p["cantidad"], p["precio_unitario"])
        for p in esperado["productos"]
    ]
    assert obtenidos == esperados
