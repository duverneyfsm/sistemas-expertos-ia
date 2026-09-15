// Este codigo permite encontrar una alerta sin volver a cargar la pagina.
document.addEventListener("DOMContentLoaded", () => {
  // Leemos los controles que el usuario usa para buscar y filtrar.
  const buscador = document.getElementById("buscar-alertas");
  const filtroTipo = document.getElementById("filtro-tipo");
  const filtroOrigen = document.getElementById("filtro-origen");
  // Cada fila marcada asi corresponde a una factura que requiere revision.
  const filas = [...document.querySelectorAll(".alert-row")];

  // Agrega al selector los valores que realmente existen en la bandeja.
  const llenarOpciones = (selector, atributo) => {
    const opciones = [...new Set(filas.map((fila) => fila.dataset[atributo]).filter(Boolean))].sort();
    opciones.forEach((opcion) => {
      const elemento = document.createElement("option");
      elemento.value = opcion;
      elemento.textContent = opcion.replace(/\b\w/g, (letra) => letra.toUpperCase());
      selector.appendChild(elemento);
    });
  };

  // Esta funcion decide si una fila coincide con texto, tipo y origen.
  const aplicarFiltros = () => {
    const texto = buscador.value.trim().toLowerCase();
    const tipo = filtroTipo.value;
    const origen = filtroOrigen.value;
    filas.forEach((fila) => {
      const coincideTexto = fila.innerText.toLowerCase().includes(texto);
      const coincideTipo = !tipo || fila.dataset.tipo === tipo;
      const coincideOrigen = !origen || fila.dataset.origen === origen;
      // hidden oculta solo las filas que no cumplen todos los filtros.
      fila.hidden = !(coincideTexto && coincideTipo && coincideOrigen);
    });
  };

  llenarOpciones(filtroTipo, "tipo");
  llenarOpciones(filtroOrigen, "origen");
  // Cualquier cambio en los controles actualiza la bandeja inmediatamente.
  [buscador, filtroTipo, filtroOrigen].forEach((control) => {
    control.addEventListener("input", aplicarFiltros);
    control.addEventListener("change", aplicarFiltros);
  });
});
