/* Las graficas del Summary.
 *
 * Ni un color literal: se leen de las variables CSS en tiempo de ejecucion, o
 * la grafica se vuelve ilegible en Nocturno y pierde el contraste 14:1 que el
 * tema Accesible promete. El tema puede cambiar sin recargar, asi que tambien
 * se vuelven a leer cuando cambia data-theme.
 *
 * Ni una cadena visible: las etiquetas de las series salen de atributos data-
 * del propio <canvas>, para que las traduzca Django.
 *
 * Las pestanas de la tarjeta esconden tres de las cuatro vistas: un canvas
 * que nace oculto mide cero, asi que la plantilla avisa con el evento
 * graficas:redibujar al cambiar de pestana y aqui se vuelve a pintar todo.
 * Los selectores de mes y de categoria hacen lo mismo al cambiar.
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

  function elegido(id) {
    var nodo = document.getElementById(id);
    return nodo ? nodo.value : null;
  }

  var graficas = [];

  function pintar(lienzo, config) {
    if (!lienzo || lienzo.offsetParent === null) { return; }
    graficas.push(new Chart(lienzo, config));
  }

  // Planeado contra real: barras por categoria, una serie por tipo.
  function barrasPlaneadoReal(lienzo, serie) {
    if (!serie || !serie.etiquetas.length) { return; }
    pintar(lienzo, {
      type: "bar",
      data: {
        labels: serie.etiquetas,
        datasets: [
          { label: lienzo.dataset.etiquetaPlaneado,
            data: numeros(serie.planeado),
            backgroundColor: color("--chart-2") },
          { label: lienzo.dataset.etiquetaReal,
            data: numeros(serie.real),
            backgroundColor: color("--chart-1") }
        ]
      },
      options: { responsive: true, maintainAspectRatio: false, scales: rejilla() }
    });
  }

  function dibujar() {
    if (typeof Chart === "undefined") { return; }

    graficas.forEach(function (g) { g.destroy(); });
    graficas = [];

    var porMes = datos("series-por-mes") || {};
    var mes = porMes[elegido("selector-mes")];
    if (mes) {
      barrasPlaneadoReal(document.getElementById("grafica-plan-gastos"), mes.expense);
      barrasPlaneadoReal(document.getElementById("grafica-plan-ingresos"), mes.income);
    }

    var meses = datos("series-meses");
    var lienzoM = document.getElementById("grafica-meses");
    if (meses && lienzoM && meses.etiquetas.length) {
      var lineas = [["ingresos", "--chart-1"], ["gastos", "--chart-3"],
                    ["ahorro", "--chart-2"], ["mesada", "--chart-4"]];
      pintar(lienzoM, {
        type: "line",
        data: {
          labels: meses.etiquetas,
          datasets: lineas.map(function (par) {
            return { label: lienzoM.dataset["etiqueta" + par[0][0].toUpperCase() + par[0].slice(1)],
                     data: numeros(meses[par[0]]),
                     borderColor: color(par[1]),
                     backgroundColor: color(par[1]),
                     tension: 0.25 };
          })
        },
        options: { responsive: true, maintainAspectRatio: false, scales: rejilla() }
      });
    }

    var categorias = datos("series-categorias");
    var lienzoC = document.getElementById("grafica-categoria");
    var cat = elegido("selector-categoria");
    if (categorias && lienzoC && cat && categorias.real[cat]) {
      barrasPlaneadoReal(lienzoC, {
        etiquetas: categorias.etiquetas,
        planeado: categorias.planeado[cat],
        real: categorias.real[cat]
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    dibujar();
    document.querySelectorAll("[data-selector]").forEach(function (selector) {
      selector.addEventListener("change", dibujar);
    });
  });

  window.addEventListener("graficas:redibujar", dibujar);

  new MutationObserver(dibujar).observe(document.documentElement, {
    attributes: true, attributeFilter: ["data-theme"]
  });
})();
