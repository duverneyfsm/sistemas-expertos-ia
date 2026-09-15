// Filtro ligero en el navegador para buscar por factura, tipo u origen.
document.addEventListener("DOMContentLoaded", () => {
  const buscador = document.getElementById("buscar-alertas");
  if (!buscador) return;
  buscador.addEventListener("input", () => {
    const texto = buscador.value.toLowerCase();
    document.querySelectorAll("#tabla-alertas tbody tr").forEach((fila) => {
      fila.hidden = !fila.innerText.toLowerCase().includes(texto);
    });
  });
});
