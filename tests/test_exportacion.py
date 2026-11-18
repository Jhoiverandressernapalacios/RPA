"""Pruebas de la lectura de consultas y la exportación a CSV (sin OCR)."""

import pandas as pd
import pytest

from rpa_dian.consultas import Consulta, leer_consultas
from rpa_dian.exportacion import COLUMNAS_CSV, exportar, factura_a_dataframe
from rpa_dian.extraccion import Encabezado, Producto
from rpa_dian.proceso import Factura

CUFE_A = "a" * 96
CUFE_B = "b" * 96


def factura_con_dos_productos() -> Factura:
    return Factura(
        cufe=CUFE_A,
        encabezado=Encabezado("SETT-1001", "2025-03-14", "900123456"),
        productos=[
            Producto("7701234567890", "TELEVISOR DE EJEMPLO", 1.0, 1260504.2),
            Producto("SRV-10", "INSTALACIÓN Y CONFIGURACIÓN AÑO", 3.0, 50000.0),
        ],
    )


def factura_sin_productos() -> Factura:
    return Factura(cufe=CUFE_B, encabezado=Encabezado("FE-1", "", "800987654"), productos=[])


# --- Consultas ----------------------------------------------------------------


def test_lee_las_consultas_con_y_sin_nit(tmp_path):
    ruta = tmp_path / "consultas.csv"
    ruta.write_text(f"cufe,nit\n{CUFE_A},900123456\n{CUFE_B},\n", encoding="utf-8")
    assert leer_consultas(ruta) == [Consulta(CUFE_A, "900123456"), Consulta(CUFE_B, "")]


def test_limpia_espacios_y_mayusculas_del_cufe_y_puntos_del_nit(tmp_path):
    ruta = tmp_path / "consultas.csv"
    ruta.write_text(f"cufe,nit\n  {CUFE_A.upper()} , 900.123.456 \n", encoding="utf-8")
    assert leer_consultas(ruta) == [Consulta(CUFE_A, "900123456")]


def test_rechaza_un_archivo_sin_las_columnas_cufe_y_nit(tmp_path):
    ruta = tmp_path / "consultas.csv"
    ruta.write_text("codigo\n123\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cufe"):
        leer_consultas(ruta)


# --- DataFrame ----------------------------------------------------------------


def test_el_dataframe_tiene_una_fila_por_producto_con_el_encabezado_repetido():
    tabla = factura_a_dataframe(factura_con_dos_productos())
    assert list(tabla.columns) == COLUMNAS_CSV
    assert len(tabla) == 2
    assert tabla["numero_factura"].tolist() == ["SETT-1001", "SETT-1001"]
    assert tabla["codigo"].tolist() == ["7701234567890", "SRV-10"]
    assert tabla["precio_unitario"].tolist() == [1260504.2, 50000.0]


def test_una_factura_sin_productos_conserva_una_fila_con_su_encabezado():
    tabla = factura_a_dataframe(factura_sin_productos())
    assert len(tabla) == 1
    assert tabla.loc[0, "numero_factura"] == "FE-1"
    assert pd.isna(tabla.loc[0, "cantidad"])


# --- CSV ----------------------------------------------------------------------


def test_escribe_un_csv_por_factura_y_el_consolidado(tmp_path):
    rutas = exportar([factura_con_dos_productos(), factura_sin_productos()], tmp_path)
    assert sorted(r.name for r in rutas) == sorted(
        [f"{CUFE_A}.csv", f"{CUFE_B}.csv", "consolidado.csv"]
    )
    consolidado = pd.read_csv(tmp_path / "consolidado.csv", encoding="utf-8-sig", dtype=str)
    assert len(consolidado) == 3


def test_el_csv_conserva_tildes_y_enes_y_los_codigos_como_texto(tmp_path):
    exportar([factura_con_dos_productos()], tmp_path)
    contenido = (tmp_path / f"{CUFE_A}.csv").read_bytes()
    assert contenido.startswith(b"\xef\xbb\xbf")  # BOM: Excel abre bien las tildes
    texto = contenido.decode("utf-8-sig")
    assert "INSTALACIÓN Y CONFIGURACIÓN AÑO" in texto
    assert "7701234567890" in texto
