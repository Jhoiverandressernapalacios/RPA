"""Pruebas del listado en Excel (CUFE, NIT, Estado) y de su columna Estado como memoria.

Los Excel se crean en una carpeta temporal con datos ficticios.
"""

import shutil
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from rpa_dian import config
from rpa_dian.__main__ import main
from rpa_dian.consultas import Consulta, leer_consultas, marcar_estado

CUFE_A, CUFE_B, CUFE_C = "a" * 96, "b" * 96, "c" * 96


def crear_listado(ruta, filas, encabezado=("CUFE", "NIT", "ESTADO")):
    """Crea un Excel con el encabezado dado y una fila por consulta."""
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(list(encabezado))
    for fila in filas:
        hoja.append(list(fila))
    libro.save(ruta)
    return ruta


def leer_columna(ruta, columna):
    """Valores de una columna (sin el encabezado) del Excel guardado."""
    hoja = openpyxl.load_workbook(ruta).active
    return [hoja.cell(fila, columna).value for fila in range(2, hoja.max_row + 1)]


# --- Lectura ------------------------------------------------------------------


def test_lee_cufe_y_nit_del_excel_una_fila_por_consulta(tmp_path):
    ruta = crear_listado(
        tmp_path / "LISTADO_CUFE.xlsx",
        [(CUFE_A + "\n", 900123456, None), (CUFE_B.upper(), "800.987.654-1", "")],
    )
    assert leer_consultas(ruta) == [Consulta(CUFE_A, "900123456"), Consulta(CUFE_B, "800987654")]


def test_lee_la_columna_estado_como_memoria(tmp_path):
    ruta = crear_listado(tmp_path / "l.xlsx", [(CUFE_A, 1, "Validado"), (CUFE_B, 2, None)])
    assert [c.estado for c in leer_consultas(ruta)] == ["Validado", ""]


def test_reconoce_los_encabezados_sin_importar_mayusculas_ni_tildes(tmp_path):
    ruta = crear_listado(
        tmp_path / "l.xlsx", [(CUFE_A, 1, "")], encabezado=("cufe", "Nit", "Estado")
    )
    assert leer_consultas(ruta) == [Consulta(CUFE_A, "1")]


def test_salta_filas_vacias_y_rechaza_un_cufe_invalido_con_su_fila(tmp_path):
    ruta = crear_listado(tmp_path / "l.xlsx", [(None, None, None), ("abc", 1, None)])
    with pytest.raises(ValueError, match="fila 3"):
        leer_consultas(ruta)


def test_rechaza_un_excel_sin_columna_cufe(tmp_path):
    ruta = crear_listado(tmp_path / "l.xlsx", [("x", 1)], encabezado=("Factura", "NIT"))
    with pytest.raises(ValueError, match="CUFE"):
        leer_consultas(ruta)


# --- Escritura del Estado ---------------------------------------------------------


def test_marca_el_estado_en_la_fila_del_cufe_sin_tocar_las_demas(tmp_path):
    ruta = crear_listado(tmp_path / "l.xlsx", [(CUFE_A, 1, "x"), (CUFE_B, 2, None)])
    assert marcar_estado(ruta, CUFE_B, "Validado")
    assert leer_columna(ruta, 3) == ["x", "Validado"]
    assert leer_columna(ruta, 1) == [CUFE_A, CUFE_B]


def test_crea_la_columna_estado_si_no_existe(tmp_path):
    ruta = crear_listado(tmp_path / "l.xlsx", [(CUFE_A, 1)], encabezado=("CUFE", "NIT"))
    marcar_estado(ruta, CUFE_A, "Validado")
    hoja = openpyxl.load_workbook(ruta).active
    assert hoja.cell(1, 3).value == "Estado"
    assert hoja.cell(2, 3).value == "Validado"


def test_si_el_excel_esta_abierto_avisa_y_no_detiene_el_proceso(tmp_path, monkeypatch):
    ruta = crear_listado(tmp_path / "l.xlsx", [(CUFE_A, 1, None)])

    def guardar_bloqueado(self, _ruta):
        raise PermissionError("archivo en uso")

    monkeypatch.setattr(openpyxl.Workbook, "save", guardar_bloqueado)
    assert marcar_estado(ruta, CUFE_A, "Validado") is False


def test_en_un_csv_no_hay_columna_estado_que_marcar(tmp_path):
    ruta = tmp_path / "consultas.csv"
    ruta.write_text(f"cufe,nit\n{CUFE_A},1\n", encoding="utf-8")
    assert marcar_estado(ruta, CUFE_A, "Validado") is False


# --- Proceso con memoria -----------------------------------------------------------


FIXTURES = Path(__file__).parent / "fixtures" / "pdf"


@pytest.mark.skipif(
    not (Path(config.TESSERACT_CMD).is_file() or shutil.which("tesseract")),
    reason="Tesseract no está instalado",
)
def test_la_extraccion_marca_validado_y_la_siguiente_corrida_no_repite(tmp_path):
    ejemplos = pd.read_csv(FIXTURES / "consultas.csv", dtype=str)
    ruta = crear_listado(
        tmp_path / "LISTADO_CUFE.xlsx", [(c, n, None) for c, n in ejemplos.itertuples(index=False)]
    )
    argumentos = ["extraer", "--consultas", str(ruta), "--entrada", str(FIXTURES),
                  "--salida", str(tmp_path / "csv"), "--imagenes", str(tmp_path / "img"),
                  "--metricas", str(tmp_path / "metricas")]  # fmt: skip

    main(argumentos)
    assert leer_columna(ruta, 3) == ["Validado", "Validado"]

    main(argumentos)  # segunda corrida: las dos filas ya están validadas
    metricas = pd.read_csv(tmp_path / "metricas" / "metricas.csv", encoding="utf-8-sig")
    assert metricas.empty  # no se volvió a procesar nada
    consolidado = pd.read_csv(tmp_path / "csv" / "consolidado.csv", encoding="utf-8-sig")
    assert len(consolidado) == 5  # pero la base conserva los 5 productos


def test_la_descarga_salta_las_filas_validadas_y_marca_las_demas(tmp_path):
    ruta = crear_listado(
        tmp_path / "LISTADO_CUFE.xlsx",
        [(CUFE_A, 900123456, "Validado"), (CUFE_B, None, None), (CUFE_C, None, "Error viejo")],
    )
    resultados = tmp_path / "descargas.csv"
    codigo = main(
        ["descargar", "--consultas", str(ruta), "--salida", str(tmp_path / "pdf"),
         "--resultados", str(resultados)]
    )  # fmt: skip
    assert codigo == 0
    tabla = pd.read_csv(resultados, encoding="utf-8-sig", dtype=str)
    assert list(tabla["cufe"]) == [CUFE_B, CUFE_C]  # la fila validada no se vuelve a consultar
    assert leer_columna(ruta, 3) == [
        "Validado",
        "Pendiente: falta el NIT",
        "Pendiente: falta el NIT",
    ]
