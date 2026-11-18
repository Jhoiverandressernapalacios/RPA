# ADR-0001: El captcha lo resuelve Cloudflare en el navegador de una persona (modo asistido)

## Estado
Aceptada

## Fecha
2026-11-18

## Contexto

La prueba pide un RPA que consulte 10 CUFE en `https://catalogo-vpfe.dian.gov.co/User/SearchDocument`, descargue el PDF de cada factura y "resuelva" el captcha de la página.

Lo que se encontró al reconocer la página ([`docs/reconocimiento-dian.md`](../reconocimiento-dian.md)) y al probar el bot:

1. **El captcha es Cloudflare Turnstile.** Aparece en el formulario y otra vez en la página de resultado; sin su respuesta, la búsqueda falla ("Falta Token de validación de captcha") y la descarga también ("El campo de seguridad no está completo").
2. **En un navegador normal se valida solo**, en unos 10 segundos y sin clic (observado en una grabación de pantalla de una consulta manual).
3. **En un navegador controlado por Playwright no se valida solo.** Con Edge y con Chrome, Turnstile muestra la casilla "Verifique que es un ser humano" ([captura](../evidencia/turnstile-navegador-automatizado.png)) y, **aunque una persona real la marque, responde "La verificación falló"**. Cloudflare evalúa las señales del navegador (marca de automatización, perfil nuevo, protocolo de depuración), no solo el clic.
4. La consulta exige además el NIT del emisor o receptor, que la prueba no entrega, y el PDF viene cifrado con ese NIT.

Turnstile es un control de seguridad de una entidad del Estado cuyo propósito es impedir el acceso automatizado. Que el bot lo pase exige que Cloudflare confíe en el navegador.

## Decisión

Se divide la descarga en tres partes:

1. **Modo asistido (flujo principal, `descargar --modo asistido`).** El robot no controla el navegador: abre la consulta en el navegador normal de la persona (`webbrowser.open`), donde Cloudflare valida solo, con el enlace oficial `SearchDocument?DocumentKey=<CUFE>` (el mismo que la DIAN pone en el QR de cada factura), que trae el CUFE escrito; deja el NIT en el portapapeles (la página no acepta prellenarlo por la URL); y vigila la carpeta de Descargas hasta que llega `<CUFE>*.pdf`, que valida y mueve a `output/pdf/`. La persona pega el NIT y pulsa "Buscar", "Descargar PDF" y "Aceptar". El robot mide cada consulta y sigue con la siguiente; la extracción, los CSV y las métricas son automáticos.
2. **Modo automático (`descargar --modo automatico`), conservado como evidencia.** El bot con Playwright recorre todo el flujo (CUFE, NIT que aparece después, espera del captcha en el formulario y en el resultado, "Descargar PDF", aviso de contraseña, reintentos). Nunca interactúa con el widget del captcha: solo espera su respuesta. Su resultado real es el del punto 3 del contexto.
3. **Recomendación para producción.** Para un proceso real a escala no se debe usar la página pública: la DIAN expone servicios web SOAP para facturadores y proveedores tecnológicos habilitados (servicio `WcfDianCustomerServices`, p. ej. la operación `GetStatus`, que consulta el estado de un documento por su identificador), con autenticación WS-Security. No pasan por el captcha porque el acceso se controla con credenciales. Detalle técnico en los anexos de la DIAN (ver Referencias); habría que confirmar las operaciones disponibles y los requisitos de habilitación en el anexo técnico vigente antes de implementarlo.

### Adenda (2026-11-18): favorito "RPA DIAN" en el modo asistido

Para reducir el trabajo manual se agregó un favorito de navegador (bookmarklet, [`docs/marcador-dian.html`](../marcador-dian.html)). Lo que hace, sin rodeos:

- **En el formulario:** escribe el NIT que el robot puso en el fragmento `#nit=…` del enlace, espera a que Turnstile tenga respuesta y hace clic en "Buscar".
- **En el resultado:** espera la respuesta del segundo Turnstile y hace clic en "Descargar PDF" y "Aceptar".

Es automatización dentro del navegador de la persona, con estos límites, que lo hacen compatible con la decisión:

1. **Una orden humana por página.** Solo actúa cuando la persona lo pulsa; no hay ciclos entre facturas ni ejecución desatendida. Cada consulta la inicia una persona frente al navegador, que es lo que el captcha comprueba.
2. **No toca el captcha.** No interactúa con el widget ni con su respuesta; solo espera a que Cloudflare la emita.
3. **No se oculta.** Los clics del script son eventos sintéticos (`isTrusted = false`) que la página puede distinguir.
4. **Solo funciona en `catalogo-vpfe.dian.gov.co`** y borra el NIT de la barra de direcciones al leerlo (puede quedar en el historial del navegador).

Encadenar facturas dentro del navegador (que el favorito abra la siguiente consulta) sí sería la alternativa rechazada abajo, y no se hace.

### Adenda (2026-11-18): extensión "RPA DIAN - NIT automático"

A pedido del usuario, para que la consulta abra con el CUFE **y el NIT** escritos (la página solo acepta el CUFE por el enlace), se agregó una extensión local de Chrome ([`extension/`](../../extension/)). Su script se ejecuta solo en `catalogo-vpfe.dian.gov.co/User/SearchDocument`, **escribe el NIT** del fragmento `#nit=…` en su campo y borra el fragmento. **No pulsa ningún botón ni toca el captcha**: equivale al autocompletado del navegador. La búsqueda y la descarga las sigue iniciando la persona, una por página, así que la decisión de este ADR se mantiene.

## Alternativas consideradas

### Ocultar la automatización para que Cloudflare valide solo
- A favor: el bot sería 100 % automático en la página pública.
- En contra: consiste en engañar un control anti-bots de una entidad pública (quitar marcas de automatización, plugins "stealth", reutilizar el perfil real de una persona). Es frágil (Cloudflare cambia sus señales) y su legitimidad es dudosa.
- **Rechazada.**

### Servicios pagos que resuelven captchas
- En contra: mismo problema de fondo (saltarse el control) y dependencia de un tercero.
- **Rechazada.**

### Que la persona marque la casilla en el navegador del bot
- Era el plan inicial.
- En contra: Cloudflare rechaza la verificación en el navegador automatizado aunque el clic sea humano (punto 3 del contexto).
- **Descartada por evidencia.**

### Automatizar el navegador normal de la persona (teclado y mouse simulados, o conectarse a su Chrome)
- A favor: el captcha ya está en verde en ese navegador, así que el bot podría escribir, buscar y descargar sin intervención.
- En contra: Cloudflare da el visto verde porque cree que el navegador lo maneja una persona; si después lo maneja un bot, se está usando esa confianza para pasar un control diseñado para frenarlo, solo que por una vía que Cloudflare no detecta. También es frágil: deja de funcionar en cuanto Cloudflare lo detecte.
- **Rechazada** (se evaluó a pedido del usuario el 2026-11-18). En su lugar se redujo el trabajo manual con el enlace oficial que trae el CUFE escrito.

## Consecuencias

- El requisito literal "tu proceso automatizado lo debe resolver" **no se cumple**. Se documenta como restricción del proceso, con evidencia, en el README y en el informe.
- La descarga requiere una persona presente (unos segundos por factura); el resto del proceso es automático.
- Los 10 CUFE de la prueba no se pueden consultar de ninguna forma sin su NIT: terminan en `requiere_nit`. El flujo completo se validó con facturas reales del usuario (no incluidas en el repositorio).
- Las métricas separan el tiempo humano (`t_persona`) del tiempo automático.
- Si la DIAN cambia la página o Cloudflare cambia su política, el modo asistido sigue funcionando porque no depende de cómo se detecta la automatización.

## Referencias

- Reconocimiento de la página y grabación: [`docs/reconocimiento-dian.md`](../reconocimiento-dian.md)
- Captura del bot automático: [`docs/evidencia/turnstile-navegador-automatizado.png`](../evidencia/turnstile-navegador-automatizado.png)
- DIAN, anexo técnico del servicio de recepción de facturas electrónicas (autenticación WS-Security, UsernameToken): [Anexo 5 R000001-18](https://cdn.actualicese.com/normatividad/2018/Resoluciones/Anexo-5-R000001-18.pdf)
- DIAN, anexo técnico 1.0 de documento soporte (sección "WS Consulta del estado de DE – GetStatus"): [Anexo técnico 1.0](https://cdn.actualicese.com/normatividad/2020/Resoluciones/Anexo-tecnico-1.0-para-documeto-soporte-compras-no-obligados-facturar.pdf)
- Ejemplo de terceros de la llamada SOAP `GetStatus`: [Stenfrank/soap-dian](https://github.com/Stenfrank/soap-dian)
