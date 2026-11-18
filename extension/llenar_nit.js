/*
 * Extensión "RPA DIAN - NIT automático".
 *
 * El robot abre la consulta con el enlace oficial que ya trae el CUFE
 * (SearchDocument?DocumentKey=<CUFE>) y agrega el NIT en el fragmento (#nit=<NIT>),
 * que no viaja en la petición a la DIAN. Este script, que Chrome ejecuta solo en esa
 * página, escribe el NIT en su campo y borra el fragmento de la barra de direcciones.
 *
 * No pulsa ningún botón ni toca el captcha: la persona espera el visto verde de
 * Cloudflare y pulsa "Buscar" (ver docs/adr/0001-captcha-resuelto-por-persona.md).
 */
(function () {
  // NIT que dejó el robot en el enlace; sin él, no hay nada que hacer.
  var nit = location.hash.match(/nit=(\d+)/);
  if (!nit) {
    return;
  }
  // Quita el NIT de la barra de direcciones apenas se lee.
  history.replaceState(null, '', location.pathname + location.search);

  // El campo NIT aparece después de que la página carga el CUFE: se reintenta unos segundos.
  var intentos = 0;
  (function escribirNit() {
    var campo = document.getElementById('SearchDocumentNit');
    if (campo && campo.offsetParent) {
      campo.value = nit[1];
      // Avisa a la página del cambio, como si se hubiera escrito a mano.
      campo.dispatchEvent(new Event('input', { bubbles: true }));
      campo.dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }
    intentos += 1;
    if (intentos < 40) {
      setTimeout(escribirNit, 250); // hasta 10 segundos
    }
  })();
})();
