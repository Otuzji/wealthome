/* Las graficas del Overview.
 *
 * Ni un color literal: se leen de las variables CSS en tiempo de ejecucion, o
 * la grafica se vuelve ilegible en Nocturno y pierde el contraste 14:1 que el
 * tema Accesible promete. El tema puede cambiar sin recargar, asi que tambien
 * se vuelven a leer cuando cambia data-theme.
 *
 * Ni una cadena visible: las etiquetas de las series salen de atributos data-
 * del propio <canvas>, para que las traduzca Django.
 */
(function () {
  "use strict";

  function color(nombre) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue(nombre)
      .trim();
  }

  function datos(id) {
    var nodo = document.getElementById(id);
    return nodo ? JSON.parse(nodo.textContent) : null;
  }

  function numeros(lista) {
    return (lista || []).map(function (v) { return parseFloat(v); });
  }

  function rejilla() {
    return {
      y: { grid: { color: color("--chart-grid") } },
      x: { grid: { color: color("--chart-grid") } }
    };
  }

  var graficas = [];

  function dibujar() {
    if (typeof Chart === "undefined") { return; }

    graficas.forEach(function (g) { g.destroy(); });
    graficas = [];

    var porCategoria = datos("series-categorias");
    var lienzoA = document.getElementById("grafica-categorias");
    if (porCategoria && lienzoA && porCategoria.etiquetas.length) {
      graficas.push(new Chart(lienzoA, {
        type: "bar",
        data: {
          labels: porCategoria.etiquetas,
          datasets: [
            { label: lienzoA.dataset.etiquetaPlaneado,
              data: numeros(porCategoria.planeado),
              backgroundColor: color("--chart-2") },
            { label: lienzoA.dataset.etiquetaReal,
              data: numeros(porCategoria.real),
              backgroundColor: color("--chart-1") }
          ]
        },
        options: { responsive: true, scales: rejilla() }
      }));
    }

    var balance = datos("series-balance");
    var lienzoB = document.getElementById("grafica-balance");
    if (balance && lienzoB && balance.etiquetas.length) {
      graficas.push(new Chart(lienzoB, {
        type: "line",
        data: {
          labels: balance.etiquetas,
          datasets: [{ label: lienzoB.dataset.etiquetaBalance,
                       data: numeros(balance.balance),
                       borderColor: color("--chart-1"),
                       backgroundColor: color("--chart-1") }]
        },
        options: { responsive: true, scales: rejilla() }
      }));
    }
  }

  document.addEventListener("DOMContentLoaded", dibujar);

  new MutationObserver(dibujar).observe(document.documentElement, {
    attributes: true, attributeFilter: ["data-theme"]
  });
})();
