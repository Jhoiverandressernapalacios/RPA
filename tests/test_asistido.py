"""Pruebas del modo asistido: el robot abre el navegador normal, copia los datos y vigila
la carpeta de Descargas. El navegador, el portapapeles y la consola se reemplazan por
funciones falsas.
"""

import os
import time
from pathlib import Path

import pytest

from rpa_dian.asistido import ConsultorAsistido, buscar_pdf
from rpa_dian.consultas import Consulta
from rpa_dian.descarga import TiempoAgotado, descargar_todas

CUFE = "c" * 96
OTRO_CUFE = "d" * 96
PDF_MINIMO = b"%PDF-1.7\n%%EOF\n"


def escribir(ruta: Path, contenido: bytes = PDF_MINIMO, antiguedad_s: float = 0) -> Path:
    ruta.write_bytes(contenido)
    if antiguedad_s:
        marca = time.time() - antiguedad_s
        os.utime(ruta, (marca, marca))
    return ruta


# --- buscar_pdf -----------------------------------------------------------------


def test_encuentra_el_pdf_del_cufe_descargado_despues_de_abrir_la_consulta(tmp_path):
    desde = time.time() - 1
    pdf = escribir(tmp_path / f"{CUFE}.pdf")
    assert buscar_pdf(tmp_path, CUFE, desde) == pdf


def test_acepta_el_nombre_que_pone_chrome_cuando_el_archivo_ya_existia(tmp_path):
    desde = time.time() - 1
    escribir(tmp_path / f"{CUFE}.pdf", antiguedad_s=3600)  # descarga de otro día
    nuevo = escribir(tmp_path / f"{CUFE} (1).pdf")
    assert buscar_pdf(tmp_path, CUFE, desde) == nuevo


def test_ignora_descargas_viejas_de_otros_cufe_y_las_incompletas(tmp_path):
    desde = time.time() - 1
    escribir(tmp_path / f"{CUFE}.pdf", antiguedad_s=3600)
    escribir(tmp_path / f"{OTRO_CUFE}.pdf")
    escribir(tmp_path / f"{CUFE}.pdf.crdownload")
    assert buscar_pdf(tmp_path, CUFE, desde) is None


# --- ConsultorAsistido ------------------------------------------------------------


class PersonaSimulada:
    """Registra lo que el robot pide y, en la primera espera, "descarga" el PDF."""

    def __init__(self, descargas: Path, contenido: bytes = PDF_MINIMO):
        self.descargas = descargas
        self.contenido = contenido
        self.urls: list[str] = []
        self.portapapeles: list[str] = []
        self.avisos: list[str] = []

    def abrir(self, url: str) -> None:
        self.urls.append(url)

    def copiar(self, texto: str) -> None:
        self.portapapeles.append(texto)

    def dormir(self, _segundos: float) -> None:
        destino = self.descargas / f"{CUFE}.pdf"
        if not destino.exists():
            destino.write_bytes(self.contenido)


def consultor_con(persona: PersonaSimulada, espera_s: float = 60) -> ConsultorAsistido:
    return ConsultorAsistido(
        carpeta_descargas=persona.descargas,
        espera_s=espera_s,
        abrir_url=persona.abrir,
        copiar=persona.copiar,
        avisar=persona.avisos.append,
        dormir=persona.dormir,
    )


@pytest.fixture
def carpetas(tmp_path):
    descargas, salida = tmp_path / "Descargas", tmp_path / "pdf"
    descargas.mkdir()
    return descargas, salida


def test_abre_el_enlace_oficial_con_el_cufe_y_deja_el_nit_en_el_portapapeles(carpetas):
    descargas, salida = carpetas
    persona = PersonaSimulada(descargas)
    tiempos: dict[str, float] = {}
    pdf = consultor_con(persona).consultar(Consulta(CUFE, "900123456"), salida, tiempos)
    # El NIT va después de "#": el navegador no lo envía a la DIAN; lo lee el botón de favoritos.
    assert persona.urls == [
        f"https://catalogo-vpfe.dian.gov.co/User/SearchDocument?DocumentKey={CUFE}#nit=900123456"
    ]
    assert persona.portapapeles == ["900123456"]
    assert pdf == salida / f"{CUFE}.pdf"
    assert pdf.read_bytes() == PDF_MINIMO
    assert not (descargas / f"{CUFE}.pdf").exists()
    assert tiempos["persona"] >= 0


def test_si_el_pdf_no_llega_a_tiempo_queda_en_timeout(carpetas):
    descargas, salida = carpetas
    persona = PersonaSimulada(descargas)
    with pytest.raises(TiempoAgotado, match="Descargas"):
        consultor_con(persona, espera_s=0).consultar(Consulta(CUFE, "1"), salida, {})


def test_rechaza_un_archivo_que_no_es_pdf(carpetas):
    descargas, salida = carpetas
    persona = PersonaSimulada(descargas, contenido=b"<html>error</html>")
    with pytest.raises(ValueError, match="no es un PDF"):
        consultor_con(persona).consultar(Consulta(CUFE, "1"), salida, {})


def test_funciona_con_la_misma_logica_de_estados_que_el_bot_automatico(carpetas):
    descargas, salida = carpetas
    persona = PersonaSimulada(descargas)
    resultados = descargar_todas(
        [Consulta(CUFE, "900123456"), Consulta(OTRO_CUFE, "")],
        consultor_con(persona),
        salida,
        dormir=lambda _s: None,
    )
    assert [r.estado for r in resultados] == ["ok", "requiere_nit"]
