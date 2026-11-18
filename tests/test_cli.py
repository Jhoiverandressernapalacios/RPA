"""Pruebas del comando `python -m rpa_dian extraer`."""

import shutil
from pathlib import Path

import pandas as pd
import pytest

from rpa_dian import config
from rpa_dian.__main__ import main

FIXTURES = Path(__file__).parent / "fixtures" / "pdf"
CONSULTAS_EJEMPLO = FIXTURES / "consultas.csv"
hay_tesseract = Path(config.TESSERACT_CMD).is_file() or shutil.which("tesseract") is not None


def escribir_consultas(ruta: Path, filas: list[tuple[str, str]]) -> Path:
    ruta.write_text("cufe,nit\n" + "".join(f"{c},{n}\n" for c, n in filas), encoding="utf-8")
    return ruta


def ejecutar_extraer(tmp_path: Path, consultas: Path) -> int:
    return main(
        [
            "extraer",
            "--consultas",
            str(consultas),
            "--entrada",
            str(FIXTURES),
            "--salida",
            str(tmp_path / "csv"),
            "--imagenes",
            str(tmp_path / "img"),
            "--metricas",
            str(tmp_path / "metricas"),
        ]
    )


def leer_consolidado(tmp_path: Path) -> pd.DataFrame:
    return pd.read_csv(tmp_path / "csv" / "consolidado.csv", encoding="utf-8-sig", dtype=str)


def test_sigue_sin_romperse_cuando_falta_el_pdf_o_el_nit_o_el_nit_no_abre_el_pdf(tmp_path):
    cufe_real = next(FIXTURES.glob("*.pdf")).stem
    consultas = escribir_consultas(
        tmp_path / "consultas.csv",
        [("f" * 96, "900123456"), ("e" * 96, ""), (cufe_real, "111")],
    )
    assert ejecutar_extraer(tmp_path, consultas) == 0
    assert leer_consolidado(tmp_path).empty


def test_descargar_con_los_cufe_de_la_prueba_marca_requiere_nit_sin_abrir_el_navegador(
    tmp_path,
):
    resultados = tmp_path / "descargas.csv"
    codigo = main(
        [
            "descargar",
            "--consultas",
            str(config.RUTA_CONSULTAS),
            "--salida",
            str(tmp_path / "pdf"),
            "--resultados",
            str(resultados),
        ]
    )
    assert codigo == 0
    tabla = pd.read_csv(resultados, encoding="utf-8-sig", dtype=str)
    assert len(tabla) == 10
    assert set(tabla["estado"]) == {"requiere_nit"}


@pytest.mark.skipif(not hay_tesseract, reason="Tesseract no está instalado")
def test_extrae_las_facturas_de_ejemplo_a_csv(tmp_path):
    assert ejecutar_extraer(tmp_path, CONSULTAS_EJEMPLO) == 0
    consolidado = leer_consolidado(tmp_path)
    assert len(consolidado) == 5  # 2 + 3 productos
    assert set(consolidado["numero_factura"]) == {"SETT-1001", "FE-20250"}
    assert len(list((tmp_path / "csv").glob("*.csv"))) == 3
    metricas = pd.read_csv(tmp_path / "metricas" / "metricas.csv", encoding="utf-8-sig")
    # 3 campos de encabezado + 4 por producto: ejemplo 1 tiene 2 productos, ejemplo 2 tiene 3
    assert list(metricas["campos_verificados"]) == [3 + 4 * 2, 3 + 4 * 3]
    assert list(metricas["campos_correctos"]) == list(metricas["campos_verificados"])
    assert "Precisión del OCR por campo" in (tmp_path / "metricas" / "informe.md").read_text(
        encoding="utf-8"
    )


def test_sin_subcomando_corre_el_proceso_completo(tmp_path):
    codigo = main(
        [
            "--consultas",
            str(escribir_consultas(tmp_path / "consultas.csv", [("e" * 96, "")])),
            "--carpeta",
            str(tmp_path / "salida"),
        ]
    )
    assert codigo == 0
    informe = (tmp_path / "salida" / "metricas" / "informe.md").read_text(encoding="utf-8")
    assert "| requiere_nit | 1 |" in informe
