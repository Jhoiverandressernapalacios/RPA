"""Pruebas de la lógica de estados del bot de descarga (sin navegador).

El navegador se reemplaza por un consultor falso: así se prueba qué estado queda en cada
caso y que un fallo no detiene las demás consultas.
"""

from pathlib import Path

from rpa_dian.consultas import Consulta
from rpa_dian.descarga import (
    Resultado,
    SinResultado,
    TiempoAgotado,
    descargar_todas,
    guardar_resultados,
)

CUFE_1, CUFE_2, CUFE_3 = "1" * 96, "2" * 96, "3" * 96


class ConsultorFalso:
    """Devuelve, por CUFE, una ruta o lanza la excepción configurada."""

    def __init__(self, respuestas: dict):
        self.respuestas = respuestas
        self.consultados: list[str] = []

    def consultar(self, consulta: Consulta, carpeta: Path, tiempos: dict) -> Path:
        self.consultados.append(consulta.cufe)
        tiempos["captcha"] = 4.0
        respuesta = self.respuestas[consulta.cufe]
        if isinstance(respuesta, Exception):
            raise respuesta
        return carpeta / respuesta


def sin_pausa(_segundos: float) -> None:
    pass


def test_sin_nit_queda_en_requiere_nit_y_no_se_consulta(tmp_path):
    consultor = ConsultorFalso({})
    [resultado] = descargar_todas([Consulta(CUFE_1, "")], consultor, tmp_path, dormir=sin_pausa)
    assert resultado.estado == "requiere_nit"
    assert consultor.consultados == []


def test_sin_ningun_nit_no_necesita_navegador(tmp_path):
    resultados = descargar_todas(
        [Consulta(CUFE_1, ""), Consulta(CUFE_2, "")], None, tmp_path, dormir=sin_pausa
    )
    assert [r.estado for r in resultados] == ["requiere_nit", "requiere_nit"]


def test_una_descarga_exitosa_queda_ok_con_su_pdf_y_sus_tiempos(tmp_path):
    consultor = ConsultorFalso({CUFE_1: f"{CUFE_1}.pdf"})
    [resultado] = descargar_todas(
        [Consulta(CUFE_1, "900123456")], consultor, tmp_path, dormir=sin_pausa
    )
    assert resultado.estado == "ok"
    assert resultado.pdf == tmp_path / f"{CUFE_1}.pdf"
    assert resultado.tiempos["captcha"] == 4.0
    assert resultado.tiempos["total"] >= 0


def test_cada_tipo_de_fallo_queda_con_su_estado_y_el_proceso_sigue(tmp_path):
    consultor = ConsultorFalso(
        {
            CUFE_1: SinResultado("Documento no encontrado"),
            CUFE_2: TiempoAgotado("Captcha sin resolver en 180 s"),
            CUFE_3: RuntimeError("Se cayó la conexión"),
        }
    )
    consultas = [Consulta(c, "900123456") for c in (CUFE_1, CUFE_2, CUFE_3)]
    resultados = descargar_todas(consultas, consultor, tmp_path, dormir=sin_pausa)
    assert [(r.estado, r.detalle) for r in resultados] == [
        ("sin_resultado", "Documento no encontrado"),
        ("timeout", "Captcha sin resolver en 180 s"),
        ("error", "RuntimeError: Se cayó la conexión"),
    ]


def test_hace_una_pausa_entre_consultas_reales_pero_no_despues_de_la_ultima(tmp_path):
    pausas: list[float] = []
    consultor = ConsultorFalso({CUFE_1: "a.pdf", CUFE_3: "c.pdf"})
    consultas = [Consulta(CUFE_1, "1"), Consulta(CUFE_2, ""), Consulta(CUFE_3, "3")]
    descargar_todas(consultas, consultor, tmp_path, pausa=5, dormir=pausas.append)
    assert pausas == [5]


def test_guarda_los_resultados_en_un_csv(tmp_path):
    resultados = [
        Resultado(CUFE_1, "ok", pdf=tmp_path / "a.pdf", tiempos={"captcha": 4.0, "total": 12.5}),
        Resultado(CUFE_2, "requiere_nit", detalle="Falta el NIT"),
    ]
    ruta = guardar_resultados(resultados, tmp_path / "descargas.csv")
    lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
    assert lineas[0] == (
        "cufe,estado,detalle,pdf,t_navegacion,t_captcha,t_consulta,t_descarga,t_persona,t_total"
    )
    assert lineas[1].startswith(f"{CUFE_1},ok,,")
    assert lineas[1].endswith(",,4.0,,,,12.5")
    assert lineas[2] == f"{CUFE_2},requiere_nit,Falta el NIT,,,,,,,"
