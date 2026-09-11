"""Sistema experto sencillo para diagnostico de servidores con Tkinter."""

import tkinter as tk
from tkinter import messagebox


def diagnosticar_servidor(hechos):
    """Aplica las reglas del sistema experto y devuelve el diagnostico."""
    # Regla 1: critica y de maxima precedencia.
    if hechos["temperatura"] > 80 and not hechos["ventilador_activo"]:
        return (
            "CRITICO: riesgo de sobrecalentamiento "
            "(temperatura alta y ventilador apagado)."
        )

    # Regla 2: servidor saturado de recursos.
    if hechos["cpu_uso"] > 90 and hechos["memoria_libre"] < 10:
        return "CRITICO: servidor saturado (CPU muy alto y memoria casi agotada)."

    # Regla 3: senales de lentitud.
    if hechos["ping_respuesta"] > 100 or hechos["memoria_libre"] < 20:
        return "ADVERTENCIA: el servidor muestra lentitud, conviene revisarlo."

    # Regla por defecto.
    return "NORMAL: el servidor opera dentro de los parametros esperados."


def ejecutar_diagnostico():
    """Lee los datos de la ventana y actualiza el resultado."""
    try:
        hechos = {
            "cpu_uso": float(entrada_cpu.get()),
            "memoria_libre": float(entrada_memoria.get()),
            "ping_respuesta": float(entrada_ping.get()),
            "temperatura": float(entrada_temperatura.get()),
            "ventilador_activo": ventilador_var.get(),
        }
    except ValueError:
        messagebox.showerror(
            "Datos invalidos", "Los campos numericos deben contener numeros."
        )
        return

    resultado = diagnosticar_servidor(hechos)
    etiqueta_resultado.config(text=f"Diagnostico: {resultado}")


ventana = tk.Tk()
ventana.title("Sistema Experto - Diagnostico de Servidor")
ventana.geometry("420x380")
ventana.resizable(False, False)

tk.Label(
    ventana,
    text="Sistema Experto: Diagnostico de Servidor",
    font=("Arial", 13, "bold"),
).pack(pady=10)

campos = tk.Frame(ventana)
campos.pack(pady=5)

tk.Label(campos, text="CPU en uso (%):").grid(
    row=0, column=0, sticky="e", padx=5, pady=5
)
entrada_cpu = tk.Entry(campos)
entrada_cpu.insert(0, "45")
entrada_cpu.grid(row=0, column=1, padx=5, pady=5)

tk.Label(campos, text="Memoria libre (%):").grid(
    row=1, column=0, sticky="e", padx=5, pady=5
)
entrada_memoria = tk.Entry(campos)
entrada_memoria.insert(0, "30")
entrada_memoria.grid(row=1, column=1, padx=5, pady=5)

tk.Label(campos, text="Ping de respuesta (ms):").grid(
    row=2, column=0, sticky="e", padx=5, pady=5
)
entrada_ping = tk.Entry(campos)
entrada_ping.insert(0, "60")
entrada_ping.grid(row=2, column=1, padx=5, pady=5)

tk.Label(campos, text="Temperatura (C):").grid(
    row=3, column=0, sticky="e", padx=5, pady=5
)
entrada_temperatura = tk.Entry(campos)
entrada_temperatura.insert(0, "85")
entrada_temperatura.grid(row=3, column=1, padx=5, pady=5)

ventilador_var = tk.BooleanVar(value=False)
tk.Checkbutton(campos, text="Ventilador activo", variable=ventilador_var).grid(
    row=4, column=0, columnspan=2, pady=5
)

tk.Button(
    ventana,
    text="Diagnosticar",
    command=ejecutar_diagnostico,
    bg="#2563EB",
    fg="white",
    font=("Arial", 11, "bold"),
).pack(pady=10)

etiqueta_resultado = tk.Label(
    ventana,
    text="Diagnostico: (presiona el boton)",
    wraplength=380,
    justify="left",
    font=("Arial", 10),
)
etiqueta_resultado.pack(pady=10, padx=10)

ventana.mainloop()
