"""Motor de fraude bancario con encadenamiento hacia adelante y Tkinter."""

import tkinter as tk
from tkinter import messagebox


# Base de reglas del sistema experto.
REGLAS = [
    {
        "id": "R1",
        "condiciones": {"monto_alto": True},
        "conclusion": {"transaccion_inusual": True},
    },
    {
        "id": "R2",
        "condiciones": {"transaccion_inusual": True, "pais_extranjero": True},
        "conclusion": {"bloquear_tarjeta": True},
    },
    {
        "id": "R3",
        "condiciones": {"multiples_compras_rapidas": True},
        "conclusion": {"transaccion_inusual": True},
    },
    {
        "id": "R4",
        "condiciones": {"tarjeta_reportada_robada": True},
        "conclusion": {"bloquear_tarjeta": True},
    },
]


def evaluar_transaccion(hechos):
    """Ejecuta las reglas hasta que no se puedan deducir hechos nuevos."""
    traza = []
    nuevos_hechos = True

    while nuevos_hechos:
        nuevos_hechos = False

        for regla in REGLAS:
            # all() funciona como una compuerta AND entre las condiciones.
            condiciones_cumplidas = all(
                hechos.get(clave) == valor
                for clave, valor in regla["condiciones"].items()
            )

            if condiciones_cumplidas:
                for clave, valor in regla["conclusion"].items():
                    if clave not in hechos:
                        hechos[clave] = valor
                        nuevos_hechos = True
                        traza.append(
                            f"Disparando {regla['id']} -> "
                            f"Nuevo hecho: {clave}={valor}"
                        )

    return hechos, traza


def ejecutar_evaluacion():
    """Obtiene los hechos de la interfaz y presenta el resultado."""
    try:
        hechos = {
            "monto": float(entrada_monto.get()),
            "pais_extranjero": pais_var.get(),
            "compras_ultima_hora": int(entrada_compras.get()),
            "tarjeta_reportada_robada": robada_var.get(),
        }
    except ValueError:
        messagebox.showerror(
            "Datos invalidos", "Monto y compras deben ser valores numericos."
        )
        return

    # Umbrales de negocio transformados en hechos booleanos.
    hechos["monto_alto"] = hechos["monto"] > 5000
    hechos["multiples_compras_rapidas"] = hechos["compras_ultima_hora"] >= 3

    memoria_final, traza = evaluar_transaccion(hechos)
    veredicto = (
        "BLOQUEAR TARJETA"
        if memoria_final.get("bloquear_tarjeta")
        else "Transaccion permitida"
    )

    texto_resultado.delete("1.0", tk.END)
    if traza:
        texto_resultado.insert(tk.END, "\n".join(traza) + "\n\n")
    else:
        texto_resultado.insert(
            tk.END, "El motor no encontro ninguna regla aplicable.\n\n"
        )
    texto_resultado.insert(tk.END, f"Veredicto final: {veredicto}")


ventana = tk.Tk()
ventana.title("Motor de Fraude Bancario")
ventana.geometry("450x430")
ventana.resizable(False, False)

tk.Label(
    ventana,
    text="Motor de Fraude Bancario",
    font=("Arial", 13, "bold"),
).pack(pady=10)

campos = tk.Frame(ventana)
campos.pack(pady=5)

tk.Label(campos, text="Monto de la transaccion (USD):").grid(
    row=0, column=0, sticky="e", padx=5, pady=5
)
entrada_monto = tk.Entry(campos)
entrada_monto.insert(0, "7500")
entrada_monto.grid(row=0, column=1, padx=5, pady=5)

tk.Label(campos, text="Compras en la ultima hora:").grid(
    row=1, column=0, sticky="e", padx=5, pady=5
)
entrada_compras = tk.Entry(campos)
entrada_compras.insert(0, "4")
entrada_compras.grid(row=1, column=1, padx=5, pady=5)

pais_var = tk.BooleanVar(value=True)
tk.Checkbutton(
    campos,
    text="Transaccion en pais extranjero",
    variable=pais_var,
).grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=5)

robada_var = tk.BooleanVar(value=False)
tk.Checkbutton(
    campos,
    text="Tarjeta reportada como robada",
    variable=robada_var,
).grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)

tk.Button(
    ventana,
    text="Evaluar transaccion",
    command=ejecutar_evaluacion,
    bg="#2563EB",
    fg="white",
    font=("Arial", 11, "bold"),
).pack(pady=10)

texto_resultado = tk.Text(ventana, height=8, width=48, wrap="word")
texto_resultado.pack(pady=10, padx=10)

ventana.mainloop()
