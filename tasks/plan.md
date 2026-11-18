# Plan de implementación: RPA DIAN — V1

Especificación de origen: [`SPEC.md`](../SPEC.md)
Lista de tareas detallada: [`tasks/todo.md`](todo.md)

> Estado: **aprobado** (2026-11-17)

## Resumen

Un proceso en Python con dos módulos independientes. `descarga-dian` usa Playwright para consultar 10 CUFE en el catálogo DIAN, espera a que una persona resuelva el captcha y guarda los PDF. `extraccion-ocr` convierte cada PDF en imagen, lee el texto con Tesseract, extrae 7 campos y los exporta a CSV. `metricas` mide cada etapa y genera el informe. Todo se entrega con README, ADR y repositorio en GitHub.

## Decisiones de arquitectura

- **Primero el reconocimiento de la página (tarea 3).** Es el mayor riesgo: no sabemos si los CUFE existen, si el NIT es obligatorio ni qué captcha usa. Se resuelve antes de escribir el bot.
- **La extracción se construye antes que la descarga.** Se puede probar con PDF de ejemplo sin depender de la DIAN, y deja resultados aunque la DIAN falle.
- **Extracción como funciones puras** (texto → datos), probadas con textos de ejemplo. El OCR y los archivos quedan en los bordes.
- **El captcha lo resuelve una persona**, con un tiempo de espera de 180 s por CUFE (ver `SPEC.md`).
- **Las métricas se integran desde el principio** con un cronómetro sencillo por etapa, en vez de agregarse al final.
- **Tiempo de desarrollo:** se anota la hora de inicio y fin de cada tarea en `docs/tiempos-desarrollo.md` (lo pide la prueba).

## Grafo de dependencias

```
T1 Entorno ── T2 Esqueleto ──┬── T3 Reconocimiento DIAN ──┬── T9 Bot: consulta + captcha ── T10 Bot: descarga
                             │                            │
                             └── T4 Fixtures ─────────────┘
                                   │
                                   ├── T5 Encabezado ──┐
                                   ├── T6 Productos ───┼── T8 Exportación + subcomando extraer
                                   └── T7 PDF→PNG→OCR ─┘
                                                              T8 + T10 ── T11 Métricas ── T12 Proceso completo
                                                                                              │
                                                              T13 Revisión ── T14 Documentación ── T15 Entrega
```

## Lista de tareas

### Fase 0: Preparación
- [x] T1: Instalar Python 3.12 y Tesseract con el idioma español
- [x] T2: Esqueleto del proyecto, dependencias y repositorio Git local
- [ ] T3: Reconocimiento de la página DIAN con un CUFE real

### Checkpoint 1: Preparación
- [ ] `pytest` y `ruff check .` corren sin errores en el esqueleto
- [ ] Sabemos si los CUFE existen, si el NIT es obligatorio, qué captcha usa la página y cómo se descarga el PDF
- [ ] Revisión contigo: confirmar el camino (PDF reales o de ejemplo)

### Fase 1: Extracción (PDF → CSV)
- [ ] T4: Fixtures: PDF y textos OCR de ejemplo
- [ ] T5: Extraer el encabezado (número de factura, fecha, NIT)
- [ ] T6: Extraer la tabla de productos
- [ ] T7: Convertir PDF a PNG y leer el texto con OCR
- [ ] T8: Exportar a CSV y subcomando `extraer`

### Checkpoint 2: Extracción
- [ ] `python -m rpa_dian extraer` genera un CSV por factura y el consolidado
- [ ] Cobertura ≥ 90 % en `extraccion.py` y `exportacion.py`

### Fase 2: Descarga
- [ ] T9: Bot: abrir la página, llenar el CUFE y esperar el captcha
- [ ] T10: Bot: descargar el PDF, manejar errores y subcomando `descargar`

### Checkpoint 3: Descarga
- [ ] Corrida real con los 10 CUFE (tú resuelves el captcha); cada uno termina en `ok`, `sin_resultado`, `error` o `timeout`

### Fase 3: Métricas e integración
- [ ] T11: Métricas por etapa y precisión del OCR
- [ ] T12: Proceso completo e informe

### Checkpoint 4: Integración
- [ ] `python -m rpa_dian` corre de punta a punta y genera `docs/informe.md`
- [ ] Se cumplen los 8 criterios de éxito del SPEC

### Fase 4: Revisión y entrega
- [ ] T13: Revisión de código, seguridad y simplificación
- [ ] T14: README, ADR del captcha y tiempos de desarrollo
- [ ] T15: Commits, repositorio en GitHub y respuestas en el `.docx` *(requiere tu autorización)*

### Checkpoint final
- [ ] Todos los criterios de éxito cumplidos
- [ ] Revisión final contigo antes de enviar

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Los CUFE son ficticios y la DIAN no devuelve nada | Alto | T3 lo confirma temprano; plan B: PDF de ejemplo marcados como tales, y el bot se demuestra con el estado `sin_resultado` |
| El formulario exige un NIT que la prueba no da | Alto | T3 lo confirma; si es obligatorio, se documenta como restricción y se usa el plan B |
| La página detecta el navegador automatizado y bloquea incluso con el captcha resuelto a mano | Medio | Navegador visible, ritmo humano, sesión persistente; si aun así bloquea, se documenta y se usa el plan B |
| El OCR lee mal la tabla de productos | Medio | Imagen a 300 dpi con preprocesado; comparación contra la capa de texto del PDF; se reporta la precisión real |
| El instalador de Tesseract no trae el idioma español | Bajo | Se agrega `spa.traineddata` del repositorio oficial de Tesseract (te pido permiso para la descarga) |
| El plazo de 24 h | Medio | La extracción va primero y deja resultados presentables aunque la descarga se complique |

## Paralelización

El proyecto es pequeño y las fases comparten archivos (`__main__.py`, `config.py`), así que va en secuencia. Lo único que podría ir en paralelo es T7 junto con T5 y T6, pero no lo justifica.

## Preguntas abiertas

- T1: ¿autorizas instalar Python 3.12 y Tesseract con winget?
- T15: nombre del repositorio (propuesta `rpa-dian-facturas`) y si será público o privado.
