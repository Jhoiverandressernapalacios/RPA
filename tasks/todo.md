# Tareas: RPA DIAN — V1

Plan: [`tasks/plan.md`](plan.md) · Especificación: [`SPEC.md`](../SPEC.md)

Tamaños: XS = 1 archivo · S = 1-2 archivos · M = 3-5 archivos.

---

## Fase 0: Preparación

### T1: Instalar Python 3.12 y Tesseract

**Descripción:** Instalar con winget Python 3.12 y Tesseract OCR 5, con el paquete de idioma español. Hoy no están en el equipo. *Requiere tu autorización.*

**Criterios de aceptación:**
- [x] `python --version` muestra 3.12.x (3.12.10, instalado el 2026-11-17 23:51)
- [x] `tesseract --list-langs` incluye `spa`. Tesseract 5.4.0 está en `C:\Program Files\Tesseract-OCR\tesseract.exe` (no en el PATH). `spa.traineddata` (tessdata oficial, 17,4 MB, SHA-256 `0B0FCBB4…7C96`) y `osd.traineddata` están en `%LOCALAPPDATA%\tessdata`; se usa con `--tessdata-dir`.

**Verificación:**
- [x] `python --version` → 3.12.10; `tesseract --tessdata-dir %LOCALAPPDATA%\tessdata --list-langs` → `osd`, `spa`
- [x] OCR de prueba en español: leyó "Facturación electrónica - Año 2025" y "Descripción: Señalización 1.234,50" sin errores (tildes, ñ y formato numérico)

**Nota para T2:** `config.py` debe tomar la ruta de Tesseract y de `tessdata` de variables de entorno (`TESSERACT_CMD`, `TESSDATA_PREFIX`), con estos valores por defecto.

**Depende de:** nada · **Archivos:** ninguno del proyecto · **Tamaño:** XS

---

### T2: Esqueleto del proyecto, dependencias y repositorio Git local

**Descripción:** Crear la estructura de carpetas del SPEC, el entorno virtual, `requirements.txt` con versiones fijas, la configuración de pytest y ruff en `pyproject.toml`, `.gitignore` (excluye `output/`, `.venv/` y el `.docx`), `data/cufes.txt` con los 10 CUFE y `git init`.

**Criterios de aceptación:**
- [x] `pip install -r requirements.txt` y `python -m playwright install chromium` terminan sin errores
- [x] `data/cufes.txt` tiene exactamente 10 líneas de 96 caracteres hexadecimales (extraídos del `.docx` con un script, no copiados a mano)
- [x] `git status` no muestra el `.docx`, `.venv/` ni `output/`

**Verificación:**
- [x] `pytest -q` → 4 pruebas pasan; `ruff check .` y `ruff format --check .` sin errores
- [x] Prueba `tests/test_datos.py` que valida el formato de `cufes.txt` (escrita primero, falló en rojo y luego pasó)

**Notas:** el paquete se instala en modo editable (`pip install -e .`) para que `python -m rpa_dian` funcione. Git no tiene configurada la identidad (`user.name`, `user.email`); hay que definirla antes del primer commit.

**Depende de:** T1 · **Archivos:** `pyproject.toml`, `requirements.txt`, `.gitignore`, `data/cufes.txt`, `src/rpa_dian/__init__.py`, `tests/test_datos.py` · **Tamaño:** S

---

### T3: Reconocimiento de la página DIAN

**Descripción:** Abrir la página en el navegador integrado y consultar el primer CUFE. Tú resuelves el captcha cuando aparezca. El objetivo es responder cuatro preguntas antes de escribir el bot: ¿el NIT es obligatorio?, ¿qué captcha usa?, ¿el CUFE devuelve una factura?, ¿cómo se descarga el PDF (botón, enlace o endpoint)? Se anotan los selectores de los campos.

**Criterios de aceptación:**
- [x] `docs/reconocimiento-dian.md` responde las cuatro preguntas, con los selectores encontrados
- [x] Queda decidido el camino: entrada `cufe,nit`, CUFE de la prueba → `requiere_nit`, validación con facturas reales en `privado/` y PDF de ejemplo

**Verificación:**
- [x] Revisión contigo del documento: consulta real con tu factura, descarga del PDF y apertura con el NIT del receptor (2 páginas, capa de texto presente)

**Resultado:** NIT obligatorio · captcha Cloudflare Turnstile (falla en el navegador integrado de Claude, pasa en Chrome) · resultado en `/Document/ShowDocumentToPublic` · "Descargar PDF" → aviso → `<CUFE>.pdf` cifrado con el NIT. El PDF es la representación gráfica de la "Solución Gratuita DIAN": la tabla de productos parte el código y la descripción en varias líneas.

**Depende de:** nada (se puede hacer antes de T1) · **Archivos:** `docs/reconocimiento-dian.md` · **Tamaño:** XS

---

### T3b: Migrar la entrada a `data/consultas.csv`

**Descripción:** Reemplazar `data/cufes.txt` por `data/consultas.csv` con columnas `cufe,nit` (los 10 CUFE de la prueba con NIT vacío) y adaptar `tests/test_datos.py` y `config.py`.

**Criterios de aceptación:**
- [x] `data/consultas.csv` tiene encabezado `cufe,nit` y 10 filas; NIT vacío o solo dígitos
- [x] `data/cufes.txt` ya no existe

**Verificación:**
- [x] `pytest -q` → 7 pruebas pasan (escritas primero, en rojo); `ruff check .` sin errores

**Depende de:** T3 · **Archivos:** `data/consultas.csv`, `tests/test_datos.py`, `src/rpa_dian/config.py` · **Tamaño:** XS

---

## Checkpoint 1: Preparación
- [ ] `pytest -q` y `ruff check .` sin errores
- [ ] Reconocimiento revisado contigo y camino decidido

---

## Fase 1: Extracción (PDF → CSV)

> **Estado (2026-11-18 01:18): T4–T8 completas.** Cambios de diseño respecto al plan, descubiertos al probar con la factura real:
> - **Tabla:** las columnas y filas salen de la cuadrícula detectada en la imagen (líneas delgadas), buscada solo en la franja de la tabla para no confundir el logo DIAN con un borde. Cada celda se recorta y se lee por separado (psm 6, x2), porque el OCR de página completa perdía caracteres sueltos.
> - **Números:** cada precio y cantidad se lee a 3 escalas (x3, x2, x4) solo con dígitos, y se vota carácter por carácter: cada escala confundía un dígito distinto en la factura real.
> - **Encabezado:** OCR de página con psm 4, que deja cada etiqueta en la misma línea que su valor.
> - **Módulos nuevos:** `consultas.py` (lectura del CSV de consultas) y `proceso.py` (une conversión, OCR y extracción para una factura).

### T4: Fixtures de prueba

**Descripción:** Generar con un script PDF sintéticos con la estructura de la representación gráfica DIAN ("Datos del Documento", "Datos del Emisor / Vendedor", "Detalles de Productos" con código y descripción partidos en varias líneas), marcados visiblemente como **EJEMPLO**, con datos inventados y **cifrados con un NIT ficticio**, igual que los reales. Se agregan textos OCR de ejemplo, incluidos errores típicos de OCR (`O`/`0`, `l`/`1`, espacios partidos). Los PDF reales se quedan en `privado/` y nunca se copian a `tests/`.

**Criterios de aceptación:**
- [ ] Al menos 2 PDF en `tests/fixtures/pdf/`, con los valores esperados en un JSON al lado
- [ ] Al menos 3 textos OCR en `tests/fixtures/texto/` (uno limpio y dos con errores)

**Verificación:**
- [ ] Revisión visual de los PDF y de que cada uno tiene su JSON de valores esperados

**Depende de:** T2, T3 · **Archivos:** `tests/fixtures/`, `scripts/generar_pdf_ejemplo.py` (solo si hace falta) · **Tamaño:** S

---

### T5: Extraer el encabezado

**Descripción:** En `extraccion.py`, la función `extraer_encabezado(texto) -> Encabezado` obtiene el número de factura, la fecha de emisión (normalizada a AAAA-MM-DD) y el NIT del emisor (sin puntos, con el dígito de verificación aparte). Pruebas primero.

**Criterios de aceptación:**
- [ ] Extrae los 3 campos correctamente de todos los textos de ejemplo
- [ ] Un campo no encontrado queda vacío y se registra una advertencia, sin romper el proceso

**Verificación:**
- [ ] `pytest tests/test_extraccion.py -q`

**Depende de:** T4 · **Archivos:** `src/rpa_dian/extraccion.py`, `tests/test_extraccion.py` · **Tamaño:** S

---

### T6: Extraer la tabla de productos

**Descripción:** En `extraccion.py`, la función `extraer_productos(texto) -> list[Producto]` obtiene el código, la descripción, la cantidad y el precio unitario de cada fila de "Detalles del Producto". Convierte los números de formato colombiano (`1.234,50` → `1234.5`). Pruebas primero.

**Criterios de aceptación:**
- [ ] Extrae todas las filas de los textos de ejemplo con los valores esperados
- [ ] Maneja descripciones que ocupan más de una línea
- [ ] Convierte bien los números con miles y decimales

**Verificación:**
- [ ] `pytest tests/test_extraccion.py -q`

**Depende de:** T4 · **Archivos:** `src/rpa_dian/extraccion.py`, `tests/test_extraccion.py` · **Tamaño:** S

---

### T7: PDF a PNG y OCR

**Descripción:** `conversion.py` abre el PDF con su NIT como contraseña (`doc.authenticate(nit)`; si falla, error claro) y convierte cada página en PNG a 300 dpi con PyMuPDF. `ocr.py` aplica un preprocesado básico (escala de grises, umbral) y lee el texto con Tesseract en español. También expone la capa de texto del PDF, si existe, para medir la precisión del OCR después.

**Criterios de aceptación:**
- [ ] Un PDF de ejemplo genera un PNG por página en `output/img/`
- [ ] El texto OCR contiene los títulos de las tres secciones

**Verificación:**
- [ ] `pytest tests/test_pipeline.py -q -k ocr`

**Depende de:** T1, T4 · **Archivos:** `src/rpa_dian/conversion.py`, `src/rpa_dian/ocr.py`, `tests/test_pipeline.py` · **Tamaño:** S

---

### T8: Exportación a CSV y subcomando `extraer`

**Descripción:** `exportacion.py` arma un DataFrame por factura (una fila por producto, encabezado repetido, 8 columnas del SPEC) y lo guarda en `output/csv/<CUFE>.csv`, más `consolidado.csv`, en UTF-8 con BOM. `__main__.py` agrega el subcomando `extraer`, que une T5, T6 y T7.

**Criterios de aceptación:**
- [ ] `python -m rpa_dian extraer --entrada tests/fixtures/pdf --salida output/csv` genera un CSV por PDF más el consolidado
- [ ] Las columnas y los tipos coinciden con la tabla de salida del SPEC
- [ ] El CSV abre bien en Excel (tildes y ñ correctas)

**Verificación:**
- [ ] `pytest -q` completo
- [ ] Abrir un CSV en Excel

**Depende de:** T5, T6, T7 · **Archivos:** `src/rpa_dian/exportacion.py`, `src/rpa_dian/__main__.py`, `src/rpa_dian/config.py`, `tests/test_exportacion.py`, `tests/test_pipeline.py` · **Tamaño:** M

---

## Checkpoint 2: Extracción
- [ ] `pytest -q` pasa; cobertura ≥ 90 % en `extraccion.py` y `exportacion.py` (`pytest --cov=rpa_dian`)
- [ ] CSV de ejemplo revisados contigo

---

## Fase 2: Descarga

### T9: Bot: consulta y espera del captcha

**Descripción:** `descarga.py` lee el CSV de consultas, abre Chromium visible con Playwright y, para cada fila: si el NIT está vacío, marca `requiere_nit` sin consultar; si no, entra a la página, llena `#DocumentKey` y `#SearchDocumentNit`, muestra en consola "Resuelve el captcha en el navegador" y espera hasta 180 s a que la página pase a `/Document/ShowDocumentToPublic`. La persona pulsa "Buscar" después del captcha, o el bot lo pulsa cuando `cf-turnstile-response` tenga valor. Una consulta a la vez, con una pausa entre consultas. **Primera comprobación:** si Turnstile deja pasar a una persona dentro del Chromium de Playwright; si no, se documenta y no se intenta ocultar la automatización.

**Criterios de aceptación:**
- [ ] Con una factura de `privado/consultas.csv`, el bot llega a la pantalla de resultado después de que resuelves el captcha
- [ ] Las filas sin NIT terminan en `requiere_nit` sin abrir la página
- [ ] Si pasan 180 s sin resolverlo, marca `timeout` y sigue con el siguiente
- [ ] El bot nunca interactúa con el widget del captcha

**Verificación:**
- [ ] Corrida manual con 2 CUFE
- [ ] Prueba unitaria de la lectura y validación de `cufes.txt`

**Depende de:** T2, T3 · **Archivos:** `src/rpa_dian/descarga.py`, `src/rpa_dian/config.py`, `tests/test_descarga.py` · **Tamaño:** S

---

### T10: Bot: descarga del PDF, errores y subcomando `descargar`

**Descripción:** Desde la pantalla de resultado, pulsar "Descargar PDF", aceptar el aviso de contraseña y capturar la descarga con `page.expect_download()` como `output/pdf/<CUFE>.pdf`. Detectar y marcar `sin_resultado` (el CUFE no existe) y `error` (red o página caída). Agregar el subcomando `descargar` en `__main__.py`.

**Criterios de aceptación:**
- [ ] Cada CUFE termina en un estado: `ok`, `sin_resultado`, `error` o `timeout`
- [ ] Un PDF descargado abre bien y pesa más de 0 bytes
- [ ] Un error en un CUFE no detiene los demás

**Verificación:**
- [ ] Corrida real con los 10 CUFE (Checkpoint 3)

**Depende de:** T9 · **Archivos:** `src/rpa_dian/descarga.py`, `src/rpa_dian/__main__.py`, `tests/test_descarga.py` · **Tamaño:** S

---

## Checkpoint 3: Descarga
- [ ] Corrida real con los 10 CUFE; estados registrados
- [ ] Revisión contigo de los resultados

---

## Fase 3: Métricas e integración

### T11: Métricas por etapa y precisión del OCR

**Descripción:** `metricas.py` ofrece un cronómetro por etapa (navegación, captcha, descarga, conversión, OCR, extracción) y escribe `output/metricas/metricas.csv` con una fila por CUFE. Calcula la precisión del OCR por campo comparando contra la capa de texto del PDF, cuando existe.

**Criterios de aceptación:**
- [ ] `metricas.csv` tiene una fila por CUFE con los 6 tiempos y el estado
- [ ] El tiempo del captcha (humano) está separado del tiempo automático
- [ ] La precisión por campo se calcula para los PDF que tengan capa de texto

**Verificación:**
- [ ] `pytest tests/test_metricas.py -q`

**Depende de:** T8, T10 · **Archivos:** `src/rpa_dian/metricas.py`, `src/rpa_dian/descarga.py`, `src/rpa_dian/__main__.py`, `tests/test_metricas.py` · **Tamaño:** M

---

### T12: Proceso completo e informe

**Descripción:** `python -m rpa_dian` sin subcomando corre descarga → extracción → métricas y genera `docs/informe.md`: tiempo total, promedio por factura, tiempo humano contra automático, tasa de éxito, precisión del OCR y restricciones.

**Criterios de aceptación:**
- [ ] Una sola orden produce PDF, PNG, CSV, `metricas.csv` e `informe.md`
- [ ] El informe cubre todo lo que pide el criterio de éxito 6 del SPEC

**Verificación:**
- [ ] Corrida completa real
- [ ] `pytest -q` y `ruff check .`

**Depende de:** T11 · **Archivos:** `src/rpa_dian/__main__.py`, `src/rpa_dian/metricas.py`, `docs/informe.md` · **Tamaño:** S

---

## Checkpoint 4: Integración
- [ ] Se cumplen los 8 criterios de éxito del SPEC
- [ ] Revisión contigo

---

## Fase 4: Revisión y entrega

### T13: Revisión de código, seguridad y simplificación

**Descripción:** Revisión con los agentes `code-reviewer` y `security-auditor`, y una pasada de `code-simplification`. Se corrigen los hallazgos que apliquen.

**Criterios de aceptación:**
- [ ] Hallazgos críticos e importantes corregidos o justificados por escrito
- [ ] El comportamiento no cambia: las pruebas siguen pasando

**Verificación:**
- [ ] `pytest -q` y `ruff check .`

**Depende de:** T12 · **Archivos:** los que señale la revisión · **Tamaño:** S-M

---

### T14: README, ADR y tiempos de desarrollo

**Descripción:** README con objetivo, requisitos, instalación, uso, estructura, resultados, métricas y restricciones. `docs/adr/0001-captcha-resuelto-por-persona.md` con contexto, decisión y consecuencias. `docs/tiempos-desarrollo.md` con el tiempo de cada tarea.

**Criterios de aceptación:**
- [ ] Siguiendo solo el README, una instalación limpia corre el proceso
- [ ] El ADR explica por qué el captcha no es automático y qué implica

**Verificación:**
- [ ] Prueba del README en una carpeta limpia (clonar, instalar, ejecutar `extraer` con los fixtures)

**Depende de:** T13 · **Archivos:** `README.md`, `docs/adr/0001-captcha-resuelto-por-persona.md`, `docs/tiempos-desarrollo.md` · **Tamaño:** S

---

### T15: Commits, repositorio en GitHub y respuestas en el `.docx`

**Descripción:** Historial de commits ordenado. Crear el repositorio en GitHub y subir el código *(requiere tu autorización y tu cuenta)*. Escribir las respuestas en una copia del `.docx` de la prueba con el enlace al repositorio, las métricas y las restricciones *(requiere tu autorización)*.

**Criterios de aceptación:**
- [ ] El repositorio en GitHub tiene el README visible y no incluye `output/`, `.venv/` ni el `.docx`
- [ ] El `.docx` de respuestas está listo para enviar

**Verificación:**
- [ ] Clonar el repositorio desde GitHub en una carpeta limpia y correr `pytest -q`
- [ ] Revisión final contigo

**Depende de:** T14 · **Archivos:** `.docx` de respuestas (fuera del repositorio) · **Tamaño:** S

---

## Checkpoint final
- [ ] Todos los criterios de éxito del SPEC cumplidos
- [ ] Revisión final contigo antes de enviar la prueba
