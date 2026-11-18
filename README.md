# RPA DIAN: descarga de facturas por CUFE y extracción con OCR

Proceso en Python que consulta facturas electrónicas en el catálogo de la DIAN (`catalogo-vpfe.dian.gov.co`), descarga el PDF de su representación gráfica, convierte cada página en imagen, extrae los datos con OCR y genera un DataFrame y un CSV por factura, con un informe de tiempos, métricas y restricciones.

Prueba técnica · Analista de Ciencia de Datos / Innovación · noviembre de 2026.

## Resultados en una mirada

| Requisito de la prueba | Estado |
|---|---|
| RPA que entra a la DIAN, consulta los CUFE y descarga los PDF | ✅ Implementado en dos modos (asistido y automático). **Validado de punta a punta en modo asistido con una factura real** (descarga `ok` + extracción). Los 10 CUFE de la prueba no se pueden consultar: **la DIAN exige también el NIT**, que la prueba no entrega |
| "El proceso automatizado debe resolver el captcha" | ⚠️ No se evade el captcha. Cloudflare rechaza navegadores automatizados aunque una persona marque la casilla; la descarga usa un **modo asistido** (un clic de la persona por página). Ver [ADR-0001](docs/adr/0001-captcha-resuelto-por-persona.md) |
| Extraer texto de las imágenes (número de factura, fecha, NIT emisor, código, descripción, cantidad, precio unitario) | ✅ 100 % de campos correctos en facturas de ejemplo; 90,9 % en una factura real |
| Un DataFrame por archivo exportado a CSV | ✅ `output/csv/<CUFE>.csv` + `consolidado.csv` |
| Reportar tiempos, métricas y restricciones | ✅ [`docs/informe.md`](docs/informe.md) y, por ejecución, `output/metricas/` |

## Instalación (Windows)

Requisitos: Python 3.12, [Tesseract OCR 5](https://github.com/UB-Mannheim/tesseract/wiki) con el idioma español (`spa.traineddata`) y Google Chrome o Microsoft Edge.

```powershell
git clone https://github.com/Jhoiverandressernapalacios/RPA.git
cd RPA
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m playwright install chromium   # solo para el modo automático
```

Si Tesseract no está en la ruta por defecto, indique su ubicación:

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
$env:TESSDATA_PREFIX = "C:\ruta\a\tessdata"   # carpeta que contiene spa.traineddata
```

## Uso

**Entrada: el Excel `LISTADO_CUFE.xlsx`** en la raíz del proyecto, una factura por fila:

| CUFE | NIT | Estado |
|---|---|---|
| (96 caracteres hexadecimales) | NIT del emisor o receptor (con o sin puntos y dígito de verificación) | Lo escribe el robot |

- El robot lo lee de arriba abajo y consulta **una factura a la vez**.
- **La columna Estado es la memoria del proceso.** Apenas termina cada factura, el robot escribe ahí cómo quedó: `Descargado`, `Validado` (descargada y extraída) o `Pendiente: …` con el motivo. En la siguiente corrida **salta las filas que dicen `Validado`** y continúa con las demás; si el proceso se interrumpe, retoma donde quedó.
- Si la columna Estado no existe, el robot la crea. Cierre el Excel mientras el robot corre: Windows no deja escribir en un archivo abierto (el robot avisa y sigue).
- `LISTADO_CUFE.xlsx` no se sube a GitHub (`*.xlsx` está en `.gitignore`): un CUFE con su NIT permite descargar la factura del portal público.
- Si no existe `LISTADO_CUFE.xlsx`, el proceso usa [`data/consultas.csv`](data/consultas.csv) (columnas `cufe,nit`), que trae los 10 CUFE de la prueba con el NIT vacío. Cualquier otro archivo se indica con `--consultas`.

| Comando | Qué hace |
|---|---|
| `python -m rpa_dian` | Proceso completo: descarga → extracción → métricas e informe, todo en `output/` |
| `python -m rpa_dian descargar` | Solo la descarga (modo asistido por defecto) |
| `python -m rpa_dian descargar --modo automatico` | Descarga con Playwright (Cloudflare la bloquea; se conserva como evidencia) |
| `python -m rpa_dian extraer` | Solo la extracción de los PDF de `output/pdf` + métricas e informe |
| `pytest -q` | Más de 100 pruebas (unitarias e integración con Tesseract real), ~70 s |
| `ruff check .` | Estilo y errores comunes |

Opciones útiles: `--consultas archivo.csv`, `--carpeta salida/`, `--descargas C:\Users\yo\Downloads`, `--espera 600`.

**Probar sin datos reales:** las facturas de ejemplo (ficticias y cifradas como las reales) están en `tests/fixtures/pdf`:

```powershell
python -m rpa_dian extraer --consultas tests\fixtures\pdf\consultas.csv --entrada tests\fixtures\pdf
```

### Modo asistido (recomendado)

**Una sola vez, instale la extensión que escribe el NIT** (carpeta [`extension/`](extension/), sin dependencias externas):

1. En Chrome, abra `chrome://extensions` y active **Modo de desarrollador** (arriba a la derecha).
2. Pulse **Cargar descomprimida** y elija la carpeta `extension` del proyecto.

El robot abre las consultas en Chrome (no en el navegador predeterminado), porque ahí se instala la extensión; otro navegador se indica con la variable `RPA_NAVEGADOR_ASISTIDO` (ruta del ejecutable). Con la extensión, cada consulta abre con el **CUFE y el NIT ya escritos**: solo hay que esperar el visto verde de Cloudflare y pulsar **Buscar**, y en el resultado **Descargar PDF** y **Aceptar**. La extensión solo actúa en `catalogo-vpfe.dian.gov.co`, no pulsa botones ni toca el captcha.

Alternativa sin extensión: abra [`docs/marcador-dian.html`](docs/marcador-dian.html) en Chrome y arrastre el botón **RPA DIAN** a la barra de favoritos.
2. Ponga sus CUFE y NIT en `LISTADO_CUFE.xlsx` y ejecute `python -m rpa_dian`.
3. Por cada factura, el robot abre la consulta en su navegador con el CUFE escrito. Pulse **RPA DIAN**: escribe el NIT, espera el visto verde de Cloudflare y busca. En el resultado, pulse **RPA DIAN** otra vez: descarga el PDF.
4. El robot detecta el PDF en Descargas, lo valida, lo mueve a `output/pdf/`, mide el tiempo y sigue con la siguiente factura. Al final extrae todo y escribe el informe.

### Salidas

```
output/
├── pdf/<CUFE>.pdf            PDF descargados (cifrados con el NIT)
├── img/<CUFE>_p<N>.png       Páginas a 300 dpi
├── csv/<CUFE>.csv            Un DataFrame por factura: una fila por producto
├── csv/consolidado.csv       Todas las facturas, también las de corridas anteriores
└── metricas/
    ├── descargas.csv         Estado y tiempos de cada consulta
    ├── metricas.csv          Tiempos por etapa y precisión del OCR por factura
    └── informe.md            Resumen de tiempos, precisión y restricciones
```

Columnas del CSV: `cufe, numero_factura, fecha_emision (AAAA-MM-DD), nit_emisor, codigo, descripcion, cantidad, precio_unitario`. UTF-8 con BOM para abrir bien en Excel.

## Cómo funciona

```
consultas.csv ─► descarga (asistida o automática) ─► PDF cifrado
                                                       │  abrir con el NIT (PyMuPDF)
                                                       ▼
                                                 PNG 300 dpi
                       ┌───────────────────────────────┴───────────────────────────┐
             OCR de página (psm 4)                              palabras con posición (psm 11)
                       │                                                          │
           encabezado por expresiones                      cuadrícula detectada en la imagen
           regulares (número, fecha, NIT)                  → OCR de cada celda (psm 6)
                       │                                   → números leídos a 3 escalas y votados
                       └───────────────────────────┬───────────────────────────┘
                                                   ▼
                                  DataFrame por factura → CSV + métricas + informe
```

| Módulo | Responsabilidad |
|---|---|
| `consultas.py` | Lee y valida el listado (Excel `LISTADO_CUFE.xlsx` o CSV) y escribe la columna Estado (memoria) |
| `asistido.py` | Modo asistido: abre la consulta oficial, vigila Descargas, valida y mueve el PDF |
| `descarga.py` | Estados (`ok`, `requiere_nit`, `sin_resultado`, `timeout`, `error`), tiempos y bot automático con Playwright |
| `conversion.py` | Abre el PDF cifrado con el NIT y lo convierte a PNG |
| `ocr.py` | Tesseract, detección de la cuadrícula, limpieza de bordes y voto de números |
| `extraccion.py` | Funciones puras: texto/palabras → campos |
| `proceso.py` | Une conversión, OCR y extracción para una factura |
| `exportacion.py` | DataFrame y CSV |
| `metricas.py` | Precisión contra la capa de texto del PDF, tabla de métricas e informe |

## Decisiones y documentación

- [`SPEC.md`](SPEC.md): especificación (objetivo, criterios de éxito, límites).
- [`docs/adr/0001-captcha-resuelto-por-persona.md`](docs/adr/0001-captcha-resuelto-por-persona.md): por qué no se evade el captcha, alternativas descartadas y recomendación para producción (servicios web de la DIAN).
- [`docs/reconocimiento-dian.md`](docs/reconocimiento-dian.md): cómo funciona realmente el portal (selectores, NIT obligatorio, PDF cifrado, dos captchas).
- [`docs/informe.md`](docs/informe.md): tiempos, precisión y restricciones medidos.
- [`docs/tiempos-desarrollo.md`](docs/tiempos-desarrollo.md): tiempo invertido por tarea.
- [`tasks/plan.md`](tasks/plan.md) y [`tasks/todo.md`](tasks/todo.md): plan de trabajo y tareas con criterios de aceptación.

## Restricciones conocidas

1. **Sin NIT no hay consulta.** El portal exige CUFE + NIT; el NIT no se deduce del CUFE.
2. **El captcha requiere una persona.** Cloudflare bloquea navegadores automatizados; el proyecto no oculta la automatización.
3. **Descripciones con cortes de línea:** el PDF parte palabras al final de la celda; se conservan como espacios.
4. **Precisión del OCR:** letras parecidas (`III` → `II`) pueden fallar; el informe lo mide por campo.

## Privacidad

Las facturas reales usadas para validar el proceso nunca se versionan: `privado/`, `output/`, los `.docx`, las grabaciones de pantalla y, por tipo, los PDF, CSV e imágenes fuera de las carpetas de ejemplo están en `.gitignore`.

**Ponga los NIT reales en `LISTADO_CUFE.xlsx` o en `privado/`**, nunca en `data/consultas.csv` (versionado): un CUFE junto con su NIT basta para descargar la factura del portal público. Una prueba falla si `data/consultas.csv` tiene algún NIT. El NIT viaja al navegador en el fragmento `#nit=…` del enlace (no se envía en la petición HTTP y el favorito lo borra de la barra de direcciones, aunque puede quedar en el historial del navegador). El portapapeles no se usa. Las pruebas usan solo facturas ficticias generadas por [`scripts/generar_pdf_ejemplo.py`](scripts/generar_pdf_ejemplo.py). El informe muestra solo los primeros 12 caracteres de cada CUFE y ningún dato del comprador.
