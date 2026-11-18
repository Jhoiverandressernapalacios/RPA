"""Genera facturas de EJEMPLO (datos ficticios) con la estructura de la representación
gráfica de la DIAN, cifradas con un NIT como las reales, más un JSON con los valores
esperados. Sirven como fixtures de prueba: nunca se usan facturas reales en tests/.

Uso:  python scripts/generar_pdf_ejemplo.py [carpeta_salida]
"""

import csv
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

import pymupdf

ANCHO, ALTO = 595, 842  # A4 en puntos
NEGRO, GRIS, ROJO, VERDE = (0, 0, 0), (0.35, 0.35, 0.35), (0.8, 0, 0), (0.6, 0.95, 0.8)

# Columnas de la tabla (x inicial, x final) en puntos, como en la representación DIAN
COLUMNAS = {
    "nro": (30, 51),
    "codigo": (51, 82),
    "descripcion": (82, 156),
    "um": (156, 186),
    "cantidad": (186, 225),
    "precio": (225, 284),
    "descuento": (284, 343),
    "recargo": (343, 402),
    "iva": (402, 446),
    "iva_pct": (446, 469),
    "inc": (469, 505),
    "inc_pct": (505, 520),
    "precio_venta": (520, 565),
}
TAM_TABLA = 5.5
ALTO_LINEA = 7.5

FACTURAS = [
    {
        "nombre": "ejemplo-1",
        "numero_factura": "SETT-1001",
        "fecha_emision": "2025-03-14",
        "nit_emisor": "900123456",
        "dv_emisor": "7",
        "razon_social": "COMERCIALIZADORA DE EJEMPLO S.A.S",
        "productos": [
            {
                "codigo": "7701234567890",
                "descripcion": "TELEVISOR DE EJEMPLO 50 PULGADAS LED SMART TV NEGRO UNIDAD",
                "cantidad": 1.0,
                "precio_unitario": 1260504.2,
            },
            {
                "codigo": "7700000099991",
                "descripcion": "SOPORTE DE PARED PARA TV 32 A 55 PULGADAS",
                "cantidad": 2.0,
                "precio_unitario": 45378.15,
            },
        ],
    },
    {
        "nombre": "ejemplo-2",
        "numero_factura": "FE-20250",
        "fecha_emision": "2024-12-01",
        "nit_emisor": "800987654",
        "dv_emisor": "1",
        "razon_social": "DISTRIBUIDORA FICTICIA LTDA",
        "productos": [
            {
                "codigo": "PRD-001",
                "descripcion": "RESMA PAPEL CARTA",
                "cantidad": 12.5,
                "precio_unitario": 18900.0,
            },
            {
                "codigo": "7709876543210",
                "descripcion": (
                    "IMPRESORA MULTIFUNCIONAL DE EJEMPLO CON SISTEMA DE TINTA CONTINUA Y WIFI"
                ),
                "cantidad": 1.0,
                "precio_unitario": 1234567.89,
            },
            {
                "codigo": "SRV-10",
                "descripcion": "SERVICIO DE INSTALACION",
                "cantidad": 3.0,
                "precio_unitario": 50000.0,
            },
        ],
    },
]


def formato_colombiano(valor: float) -> str:
    """1234567.89 -> '1.234.567,89'"""
    entero, decimales = f"{valor:,.2f}".split(".")
    return f"{entero.replace(',', '.')},{decimales}"


def partir(texto: str, tamano: int) -> list[str]:
    """Parte el texto cada `tamano` caracteres, como la representación DIAN (corta palabras)."""
    return [texto[i : i + tamano].strip() for i in range(0, len(texto), tamano)]


def texto(pagina, x, y, contenido, tam=8, negrita=False, color=NEGRO):
    """Escribe un texto en la página (Helvetica, normal o negrita) en la posición dada."""
    fuente = "hebo" if negrita else "helv"
    pagina.insert_text((x, y), contenido, fontsize=tam, fontname=fuente, color=color)


def ancho(contenido, tam, negrita=False):
    # get_text_length subestima los caracteres con tilde en las fuentes base-14:
    # se mide la versión sin tildes, que tiene el mismo ancho visual.
    """Ancho en puntos que ocupará el texto con la fuente y el tamaño indicados."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", contenido) if not unicodedata.combining(c)
    )
    return pymupdf.get_text_length(sin_tildes, fontname="hebo" if negrita else "helv", fontsize=tam)


def centrado(pagina, x0, x1, y, contenido, tam=TAM_TABLA, negrita=False):
    """Escribe el texto centrado entre x0 y x1 (celdas de la tabla)."""
    texto(pagina, (x0 + x1 - ancho(contenido, tam, negrita)) / 2, y, contenido, tam, negrita)


def a_la_derecha(pagina, x1, y, contenido, tam=TAM_TABLA):
    """Escribe el texto alineado a la derecha de x1 (valores en pesos)."""
    texto(pagina, x1 - 2 - ancho(contenido, tam), y, contenido, tam)


def seccion(pagina, y, titulo):
    """Dibuja el título de una sección con su línea verde; devuelve la y siguiente."""
    texto(pagina, 70, y, titulo, 10, negrita=True, color=GRIS)
    pagina.draw_line((28, y + 5), (567, y + 5), color=VERDE, width=2)
    return y + 20


def campo(pagina, x, y, etiqueta, valor):
    """Escribe una etiqueta en negrita seguida de su valor (p. ej., 'Nit del Emisor: …')."""
    texto(pagina, x, y, etiqueta, 7.5, negrita=True, color=GRIS)
    texto(pagina, x + ancho(etiqueta, 7.5, True) + 4, y, valor, 7.5)


def dibujar_tabla(pagina, y, productos):
    """Dibuja la tabla 'Detalles de Productos' con su cuadrícula; parte el código y la descripción
    en varias líneas como la representación DIAN. Devuelve la y final.
    """
    x_ini, x_fin = COLUMNAS["nro"][0], COLUMNAS["precio_venta"][1]
    encabezados = {
        "nro": ["Nro."],
        "codigo": ["Código"],
        "descripcion": ["Descripción"],
        "um": ["U/M"],
        "cantidad": ["Cantidad"],
        "precio": ["Precio unitario"],
        "descuento": ["Descuento", "detalle"],
        "recargo": ["Recargo detalle"],
        "iva": ["IVA"],
        "iva_pct": ["%"],
        "inc": ["INC"],
        "inc_pct": ["%"],
        "precio_venta": ["Precio", "unitario de", "venta"],
    }
    alto_enc = 26
    y_tabla = y
    pagina.draw_rect(pymupdf.Rect(x_ini, y, x_fin, y + alto_enc), color=VERDE, fill=VERDE)
    for clave, lineas in encabezados.items():
        x0, x1 = COLUMNAS[clave]
        base = y + alto_enc / 2 - (len(lineas) - 1) * 3.5 + 2
        for i, linea in enumerate(lineas):
            centrado(pagina, x0, x1, base + i * 7, linea, 5.5, negrita=True)
    y += alto_enc
    pagina.draw_line((x_ini, y), (x_fin, y), color=VERDE, width=1)

    for nro, prod in enumerate(productos, start=1):
        codigo = partir(prod["codigo"], 8)
        descripcion = partir(prod["descripcion"], 20)
        lineas = max(len(codigo), len(descripcion), 1)
        alto = lineas * ALTO_LINEA + 8
        centro = y + alto / 2 + 2

        def bloque(clave, lineas_celda, centrar=True, centro=centro):
            """Escribe las líneas de una celda centradas verticalmente en la fila."""
            x0, x1 = COLUMNAS[clave]
            inicio = centro - (len(lineas_celda) - 1) * ALTO_LINEA / 2
            for i, linea in enumerate(lineas_celda):
                if centrar:
                    centrado(pagina, x0, x1, inicio + i * ALTO_LINEA, linea)
                else:
                    texto(pagina, x0 + 2, inicio + i * ALTO_LINEA, linea, TAM_TABLA)

        bloque("nro", [str(nro)])
        bloque("codigo", codigo)
        bloque("descripcion", descripcion, centrar=False)
        bloque("um", ["WSD"])
        bloque("cantidad", [formato_colombiano(prod["cantidad"])])
        iva = prod["precio_unitario"] * 0.19
        for clave, valor in [
            ("precio", prod["precio_unitario"]),
            ("descuento", 0.0),
            ("recargo", 0.0),
            ("iva", iva),
            ("precio_venta", prod["precio_unitario"]),
        ]:
            x0, x1 = COLUMNAS[clave]
            texto(pagina, x0 + 2, centro, "$", TAM_TABLA)
            a_la_derecha(pagina, x1, centro, formato_colombiano(valor))
        centrado(pagina, *COLUMNAS["iva_pct"], centro, "19.00")
        y += alto
        pagina.draw_line((x_ini, y), (x_fin, y), color=VERDE, width=0.8)

    for x0, _ in COLUMNAS.values():
        pagina.draw_line((x0, y_tabla), (x0, y), color=VERDE, width=0.8)
    pagina.draw_line((x_fin, y_tabla), (x_fin, y), color=VERDE, width=0.8)
    return y


def generar(factura: dict, carpeta: Path) -> dict:
    """Crea una factura de EJEMPLO cifrada con su NIT y el JSON con los valores esperados; devuelve
    esos valores.
    """
    cufe = hashlib.sha384(factura["nombre"].encode()).hexdigest()
    doc = pymupdf.open()
    pagina = doc.new_page(width=ANCHO, height=ALTO)

    texto(pagina, 120, 22, "EJEMPLO - DATOS FICTICIOS - NO ES UNA FACTURA REAL", 9, True, ROJO)
    centrado(pagina, 0, ANCHO, 52, "FACTURA ELECTRÓNICA DE VENTA", 13, negrita=True)
    centrado(pagina, 0, ANCHO, 82, "Representación Gráfica", 10, negrita=True)
    pagina.draw_line((28, 95), (567, 95), color=VERDE, width=4)

    y = seccion(pagina, 112, "Datos del Documento")
    texto(pagina, 76, y, "Código Único de Factura - CUFE :", 7.5, True, GRIS)
    texto(pagina, 76, y + 12, cufe, 7)
    y += 26
    campo(pagina, 76, y, "Número de Factura:", factura["numero_factura"])
    campo(pagina, 297, y, "Forma de pago:", "Contado")
    d = factura["fecha_emision"].split("-")
    campo(pagina, 76, y + 12, "Fecha de Emisión:", f"{d[2]}/{d[1]}/{d[0]}")
    campo(pagina, 297, y + 12, "Medio de Pago:", "Efectivo")

    y = seccion(pagina, y + 40, "Datos del Emisor / Vendedor")
    campo(pagina, 76, y, "Razón Social:", factura["razon_social"])
    campo(pagina, 76, y + 12, "Nit del Emisor:", factura["nit_emisor"])
    campo(pagina, 297, y + 12, "País:", "Colombia")
    campo(pagina, 76, y + 24, "Tipo de Contribuyente:", "Persona Jurídica")
    campo(pagina, 297, y + 24, "Municipio / Ciudad:", "Ciudad de Ejemplo")

    y = seccion(pagina, y + 52, "Datos del Adquiriente / Comprador")
    campo(pagina, 76, y, "Nombre o Razón Social:", "CLIENTE DE EJEMPLO")
    campo(pagina, 76, y + 12, "Número Documento:", "1000000001")
    campo(pagina, 297, y + 12, "País:", "Colombia")

    y = seccion(pagina, y + 40, "Detalles de Productos")
    y = dibujar_tabla(pagina, y, factura["productos"])

    seccion(pagina, y + 30, "Anticipos")
    texto(pagina, 520, 820, "Hoja 1 de 1", 9)

    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_pdf = carpeta / f"{cufe}.pdf"
    doc.save(
        ruta_pdf,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw=factura["nit_emisor"],
        owner_pw=f"propietario-{factura['nit_emisor']}",
        permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_COPY,
    )
    esperado = {
        "cufe": cufe,
        "nit_clave": factura["nit_emisor"],
        "numero_factura": factura["numero_factura"],
        "fecha_emision": factura["fecha_emision"],
        "nit_emisor": factura["nit_emisor"],
        "productos": factura["productos"],
    }
    (carpeta / f"{cufe}.json").write_text(
        json.dumps(esperado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return esperado


def main() -> None:
    """Genera todas las facturas de ejemplo y su consultas.csv en la carpeta indicada."""
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/pdf")
    esperados = [generar(f, carpeta) for f in FACTURAS]
    with (carpeta / "consultas.csv").open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo, lineterminator="\n")
        escritor.writerow(["cufe", "nit"])
        for e in esperados:
            escritor.writerow([e["cufe"], e["nit_clave"]])
    print(f"{len(esperados)} facturas de ejemplo en {carpeta}")


if __name__ == "__main__":
    main()
