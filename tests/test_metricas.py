"""Pruebas de las métricas: precisión del OCR contra la capa de texto del PDF, tabla de
métricas por consulta e informe en Markdown (funciones puras, sin OCR)."""

from pathlib import Path

import pytest

from rpa_dian.descarga import Resultado
from rpa_dian.extraccion import Encabezado, Producto
from rpa_dian.metricas import (
    CAMPOS,
    formato_colombiano,
    generar_informe,
    precision_por_campo,
    tabla_metricas,
    verificar_factura,
)
from rpa_dian.proceso import Factura

CUFE_A, CUFE_B = "a" * 96, "b" * 96

CAPA_DE_TEXTO = """
Datos del Documento
Número de Factura:   SETT-1001
Fecha de Emisión:   14/03/2025
Datos del Emisor / Vendedor
Nit del Emisor:   900123456
Detalles de Productos
1
77012345
67890
TELEVISOR DE EJEMPLO 5
0 PULGADAS
WSD
1,00
1.260.504,20
"""


def factura(numero="SETT-1001", codigo="7701234567890", precio=1260504.2) -> Factura:
    return Factura(
        cufe=CUFE_A,
        encabezado=Encabezado(numero, "2025-03-14", "900123456"),
        productos=[Producto(codigo, "TELEVISOR DE EJEMPLO 5 0 PULGADAS", 1.0, precio)],
        tiempos={"conversion": 0.3, "ocr": 7.5, "total": 8.0},
    )


# --- Verificación contra la capa de texto ----------------------------------------


def test_formato_colombiano():
    assert formato_colombiano(1260504.2) == "1.260.504,20"
    assert formato_colombiano(1.0) == "1,00"


def test_una_factura_bien_leida_acierta_todos_los_campos():
    aciertos = verificar_factura(factura(), CAPA_DE_TEXTO)
    assert aciertos == {campo: (1, 1) for campo in CAMPOS}


def test_detecta_los_campos_mal_leidos():
    leida = factura(numero="SETT-l001", codigo="770123456789O", precio=1260904.2)
    aciertos = verificar_factura(leida, CAPA_DE_TEXTO)
    assert aciertos["numero_factura"] == (0, 1)
    assert aciertos["codigo"] == (0, 1)
    assert aciertos["precio_unitario"] == (0, 1)
    assert aciertos["fecha_emision"] == (1, 1)


def test_sin_capa_de_texto_no_se_puede_verificar():
    assert verificar_factura(factura(), "") is None


def test_la_precision_por_campo_suma_todas_las_facturas():
    verificaciones = [
        {campo: (1, 1) for campo in CAMPOS},
        {campo: (0 if campo == "codigo" else 1, 1) for campo in CAMPOS},
    ]
    precision = precision_por_campo(verificaciones)
    assert precision["codigo"] == pytest.approx(0.5)
    assert precision["fecha_emision"] == pytest.approx(1.0)
    assert precision["total"] == pytest.approx(13 / 14)


# --- Tabla de métricas e informe --------------------------------------------------


def resultados_de_descarga() -> list[Resultado]:
    return [
        Resultado(CUFE_A, "ok", pdf=Path("a.pdf"), tiempos={"persona": 40.0, "total": 41.0}),
        Resultado(CUFE_B, "requiere_nit", "La DIAN exige el NIT"),
    ]


def test_la_tabla_de_metricas_une_descarga_y_extraccion_por_cufe():
    tabla = tabla_metricas(resultados_de_descarga(), [factura()], {CUFE_A: CAPA_DE_TEXTO})
    assert list(tabla["cufe"]) == [CUFE_A, CUFE_B]
    assert list(tabla["estado"]) == ["ok", "requiere_nit"]
    assert tabla.loc[0, "t_ocr"] == 7.5
    assert tabla.loc[0, "productos"] == 1
    assert tabla.loc[0, "campos_correctos"] == 7
    assert tabla.loc[0, "campos_verificados"] == 7


def test_el_informe_resume_estados_tiempos_precision_y_restricciones():
    informe = generar_informe(
        resultados_de_descarga(), [factura()], {CUFE_A: CAPA_DE_TEXTO}, titulo="Prueba"
    )
    assert informe.startswith("# Prueba")
    for texto in (
        "| ok | 1 |",
        "| requiere_nit | 1 |",
        "Tiempo humano",
        "Precisión del OCR por campo",
        "| codigo | 100,0 % |",
        "Restricciones del proceso",
        "Cloudflare",
        "NIT",
    ):
        assert texto in informe, texto


def test_el_informe_no_incluye_cufe_completos_ni_descripciones():
    informe = generar_informe(resultados_de_descarga(), [factura()], {CUFE_A: CAPA_DE_TEXTO})
    assert CUFE_A not in informe
    assert "TELEVISOR" not in informe
