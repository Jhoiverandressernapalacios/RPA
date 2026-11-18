"""Pruebas de la extracción de campos a partir del texto OCR (funciones puras)."""

from pathlib import Path

import pytest

from rpa_dian.extraccion import (
    Encabezado,
    Palabra,
    Producto,
    a_numero,
    extraer_encabezado,
    extraer_productos,
    producto_desde_textos,
    ubicar_celdas,
    zona_tabla,
)

TEXTOS = Path(__file__).parent / "fixtures" / "texto"


def leer(nombre: str) -> str:
    return (TEXTOS / nombre).read_text(encoding="utf-8")


# --- Encabezado -------------------------------------------------------------


def test_extrae_el_encabezado_de_un_texto_limpio():
    assert extraer_encabezado(leer("encabezado_limpio.txt")) == Encabezado(
        numero_factura="SETT-1001", fecha_emision="2025-03-14", nit_emisor="900123456"
    )


def test_extrae_el_encabezado_cuando_el_ocr_une_las_dos_columnas_en_una_linea():
    assert extraer_encabezado(leer("encabezado_dos_columnas.txt")) == Encabezado(
        numero_factura="FE-20250", fecha_emision="2024-12-01", nit_emisor="800987654"
    )


def test_tolera_errores_tipicos_del_ocr_sin_tildes_punto_y_coma_y_espacios():
    encabezado = extraer_encabezado(leer("encabezado_errores_ocr.txt"))
    assert encabezado.numero_factura == "SETT-1001"
    assert encabezado.fecha_emision == "2025-03-14"


def test_el_nit_queda_sin_puntos_sin_digito_de_verificacion_y_con_o_corregidas_a_cero():
    encabezado = extraer_encabezado(leer("encabezado_errores_ocr.txt"))
    assert encabezado.nit_emisor == "900123456"


def test_un_campo_que_no_aparece_queda_vacio_sin_romper_el_proceso():
    encabezado = extraer_encabezado("Datos del Documento\nNúmero de Factura: FE-1\n")
    assert encabezado == Encabezado(numero_factura="FE-1", fecha_emision="", nit_emisor="")


def test_no_confunde_el_numero_de_documento_del_comprador_con_el_nit_del_emisor():
    encabezado = extraer_encabezado("Número Documento: 1000000001\n")
    assert encabezado.nit_emisor == ""


# --- Números en formato colombiano -----------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1,00", 1.0),
        ("12,50", 12.5),
        ("882.352,94", 882352.94),
        ("1.234.567,89", 1234567.89),
        ("$ 45.378,15", 45378.15),
        ("50000", 50000.0),
        ("1.260.504,2O", 1260504.2),
    ],
)
def test_convierte_numeros_en_formato_colombiano(texto, esperado):
    assert a_numero(texto) == pytest.approx(esperado)


@pytest.mark.parametrize("texto", ["", "WSD", "$"])
def test_un_texto_sin_numero_devuelve_none(texto):
    assert a_numero(texto) is None


# --- Tabla de productos -----------------------------------------------------
# Las palabras simulan la salida del OCR con posición, en píxeles: cada carácter
# mide 8 px de ancho y cada palabra 20 px de alto.


def p(texto: str, x: int, y: int) -> Palabra:
    return Palabra(texto, x, y, x + 8 * len(texto), y + 20)


ENCABEZADO_TABLA = [
    p("Nro.", 5, 10),
    p("Código", 60, 10),
    p("Descripción", 150, 10),
    p("U/M", 310, 10),
    p("Cantidad", 370, 10),
    p("Precio", 450, 10),
    p("unitario", 502, 10),
    p("Descuento", 570, 4),
    p("detalle", 580, 22),
]
# Cuadrícula de la tabla: columnas Nro | Código | Descripción | U/M | Cantidad | Precio | Descuento
LINEAS_VERTICALES = [0, 50, 120, 300, 360, 440, 560, 680]
LINEAS_HORIZONTALES = [0, 40, 120, 180]

FILA_1 = [
    p("1", 20, 70),
    p("77012345", 55, 50),
    p("67890", 65, 75),
    p("TELEVISOR", 125, 45),
    p("DE", 202, 45),
    p("EJEMPLO", 222, 45),
    p("5", 282, 45),
    p("0", 125, 70),
    p("PULGADAS", 135, 70),
    p("LED", 205, 70),
    p("SMART", 233, 70),
    p("T", 277, 70),
    p("V", 125, 95),
    p("NEGRO", 135, 95),
    p("UNIDAD", 180, 95),
    p("WSD", 310, 70),
    p("1,00", 380, 70),
    p("$", 445, 70),
    p("1.260.504,20", 460, 70),
    p("$", 565, 70),
    p("0,00", 600, 70),
]
FILA_2 = [
    p("2", 20, 140),
    p("SRV-10", 55, 140),
    p("SERVICIO", 125, 130),
    p("DE", 195, 130),
    p("INSTALAC", 215, 130),
    p("ION", 125, 155),
    p("WSD", 310, 140),
    p("3,00", 380, 140),
    p("$", 445, 140),
    p("50.000,00", 470, 140),
]
DESPUES_DE_LA_TABLA = [p("Anticipos", 100, 250), p("44.000,00", 380, 270), p("9", 20, 270)]

PRODUCTO_1 = Producto(
    codigo="7701234567890",
    descripcion="TELEVISOR DE EJEMPLO 5 0 PULGADAS LED SMART T V NEGRO UNIDAD",
    cantidad=1.0,
    precio_unitario=1260504.2,
)
PRODUCTO_2 = Producto(
    codigo="SRV-10",
    descripcion="SERVICIO DE INSTALAC ION",
    cantidad=3.0,
    precio_unitario=50000.0,
)


def test_extrae_cada_fila_de_la_tabla_usando_la_cuadricula():
    palabras = ENCABEZADO_TABLA + FILA_1 + FILA_2 + DESPUES_DE_LA_TABLA
    productos = extraer_productos(palabras, LINEAS_HORIZONTALES, LINEAS_VERTICALES)
    assert productos == [PRODUCTO_1, PRODUCTO_2]


def test_une_sin_espacios_el_codigo_partido_en_varias_lineas():
    palabras = ENCABEZADO_TABLA + FILA_1
    productos = extraer_productos(palabras, LINEAS_HORIZONTALES, LINEAS_VERTICALES)
    assert productos[0].codigo == "7701234567890"


def test_el_orden_de_las_palabras_del_ocr_no_cambia_el_resultado():
    palabras = list(reversed(ENCABEZADO_TABLA + FILA_1 + FILA_2 + DESPUES_DE_LA_TABLA))
    productos = extraer_productos(palabras, LINEAS_HORIZONTALES, LINEAS_VERTICALES)
    assert productos == [PRODUCTO_1, PRODUCTO_2]


def test_ignora_lo_que_aparece_despues_de_la_seccion_anticipos():
    palabras = ENCABEZADO_TABLA + FILA_1 + FILA_2 + DESPUES_DE_LA_TABLA
    productos = extraer_productos(palabras, LINEAS_HORIZONTALES + [300], LINEAS_VERTICALES)
    assert len(productos) == 2


def test_sin_cuadricula_usa_los_encabezados_para_filas_de_una_linea():
    palabras = ENCABEZADO_TABLA + [
        p("1", 20, 60),
        p("A1", 65, 60),
        p("CAFE", 160, 60),
        p("WSD", 310, 60),
        p("2,00", 380, 60),
        p("$", 450, 60),
        p("3.500,00", 470, 60),
        p("2", 20, 100),
        p("B2", 65, 100),
        p("PAN", 160, 100),
        p("WSD", 310, 100),
        p("10,00", 375, 100),
        p("$", 450, 100),
        p("800,00", 480, 100),
    ]
    assert extraer_productos(palabras) == [
        Producto(codigo="A1", descripcion="CAFE", cantidad=2.0, precio_unitario=3500.0),
        Producto(codigo="B2", descripcion="PAN", cantidad=10.0, precio_unitario=800.0),
    ]


def test_sin_encabezado_de_tabla_devuelve_una_lista_vacia():
    assert extraer_productos([p("Hola", 0, 0), p("1", 20, 40)]) == []


def test_con_cuadricula_encuentra_la_fila_aunque_el_ocr_no_lea_su_numero():
    sin_el_numero_2 = [w for w in FILA_2 if w.texto != "2"]
    palabras = ENCABEZADO_TABLA + FILA_1 + sin_el_numero_2 + DESPUES_DE_LA_TABLA
    productos = extraer_productos(palabras, LINEAS_HORIZONTALES, LINEAS_VERTICALES)
    assert productos == [PRODUCTO_1, PRODUCTO_2]


def test_ubica_las_celdas_de_cada_fila_con_la_cuadricula():
    palabras = ENCABEZADO_TABLA + FILA_1 + FILA_2 + DESPUES_DE_LA_TABLA
    celdas = ubicar_celdas(palabras, LINEAS_HORIZONTALES, LINEAS_VERTICALES)
    assert celdas == [
        {
            "codigo": (50, 40, 120, 120),
            "descripcion": (120, 40, 300, 120),
            "cantidad": (360, 40, 440, 120),
            "precio": (440, 40, 560, 120),
        },
        {
            "codigo": (50, 120, 120, 180),
            "descripcion": (120, 120, 300, 180),
            "cantidad": (360, 120, 440, 180),
            "precio": (440, 120, 560, 180),
        },
    ]


def test_la_zona_de_la_tabla_va_del_encabezado_hasta_la_seccion_anticipos():
    palabras = ENCABEZADO_TABLA + FILA_1 + FILA_2 + DESPUES_DE_LA_TABLA
    assert zona_tabla(palabras) == (4, 250)


def test_sin_encabezado_de_tabla_no_hay_zona():
    assert zona_tabla([p("Hola", 0, 0)]) is None


def test_sin_cuadricula_no_ubica_celdas():
    assert ubicar_celdas(ENCABEZADO_TABLA + FILA_1, [], []) == []


def test_arma_el_producto_con_el_texto_leido_en_cada_celda():
    producto = producto_desde_textos(
        codigo="77012345\n67890\n",
        descripcion="TELEVISOR DE EJEMPLO 5\n0 PULGADAS LED SMART T\n\nV NEGRO UNIDAD\n",
        cantidad="1,00\n",
        precio="$ 1.260.504,20\n",
    )
    assert producto == PRODUCTO_1


def test_un_valor_ilegible_queda_como_none_sin_romper_la_fila():
    fila = [p("1", 20, 60), p("A1", 65, 60), p("CAFE", 160, 60), p("x,yz", 380, 60)]
    productos = extraer_productos(ENCABEZADO_TABLA + fila, [0, 40, 100], LINEAS_VERTICALES)
    assert productos == [
        Producto(codigo="A1", descripcion="CAFE", cantidad=None, precio_unitario=None)
    ]
