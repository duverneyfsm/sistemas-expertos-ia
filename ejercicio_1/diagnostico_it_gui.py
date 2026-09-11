"""Ejercicio 1: sistema experto sencillo para diagnosticar un servidor.

El programa pregunta por el estado del servidor y aplica reglas IF/THEN.
La interfaz se hace con Tkinter, que ya viene incluido con Python.
"""

# tk es el nombre corto que usaremos para crear la ventana y sus controles.
import tkinter as tk
# messagebox sirve para mostrar una alerta cuando el usuario escribe un dato invalido.
from tkinter import messagebox


def diagnosticar_servidor(hechos):
    """Recibe los hechos del servidor y devuelve un diagnostico en texto."""
    # REGla 1: si hay mucho calor Y el ventilador esta apagado, es critico.
    # Se revisa primero porque es el problema mas peligroso.
    if hechos["temperatura"] > 80 and not hechos["ventilador_activo"]:
        # return termina la funcion y entrega el resultado de esta regla.
        return (
            "CRITICO: riesgo de sobrecalentamiento "
            "(temperatura alta y ventilador apagado)."
        )

    # REGLA 2: CPU muy alta Y poca memoria significa servidor saturado.
    if hechos["cpu_uso"] > 90 and hechos["memoria_libre"] < 10:
        return "CRITICO: servidor saturado (CPU muy alto y memoria casi agotada)."

    # REGLA 3: un ping lento O poca memoria son señales de advertencia.
    if hechos["ping_respuesta"] > 100 or hechos["memoria_libre"] < 20:
        return "ADVERTENCIA: el servidor muestra lentitud, conviene revisarlo."

    # Si ninguna regla anterior se cumple, el sistema responde que todo esta normal.
    return "NORMAL: el servidor opera dentro de los parametros esperados."


def ejecutar_diagnostico():
    """Esta funcion se ejecuta cuando el usuario presiona Diagnosticar."""
    try:
        # Guardamos en un diccionario los datos leidos de cada caja de texto.
        # float convierte texto como "45" en un numero que se puede comparar.
        hechos = {
            "cpu_uso": float(entrada_cpu.get()),
            "memoria_libre": float(entrada_memoria.get()),
            "ping_respuesta": float(entrada_ping.get()),
            "temperatura": float(entrada_temperatura.get()),
            # get() obtiene True si la casilla esta marcada y False si no lo esta.
            "ventilador_activo": ventilador_var.get(),
        }
    except ValueError:
        # Si no se pudo convertir algun texto en numero, avisamos y detenemos el boton.
        messagebox.showerror(
            "Datos invalidos", "Los campos numericos deben contener numeros."
        )
        return

    # Enviamos los hechos al motor de reglas para obtener el diagnostico.
    resultado = diagnosticar_servidor(hechos)
    # config cambia el texto de la etiqueta que se ve en la ventana.
    etiqueta_resultado.config(text=f"Diagnostico: {resultado}")


# Creamos la ventana principal del programa.
ventana = tk.Tk()
# title cambia el texto que aparece en la parte superior de la ventana.
ventana.title("Sistema Experto - Diagnostico de Servidor")
# geometry define ancho x alto de la ventana en pixeles.
ventana.geometry("420x380")
# False, False evita que el usuario cambie el tamaño de la ventana.
ventana.resizable(False, False)

# Esta etiqueta es el titulo grande que el usuario ve al abrir el programa.
tk.Label(
    ventana,
    text="Sistema Experto: Diagnostico de Servidor",
    font=("Arial", 13, "bold"),
).pack(pady=10)  # pack coloca el control uno debajo de otro.

# Frame es un recuadro invisible que agrupa las etiquetas y las cajas de datos.
campos = tk.Frame(ventana)
campos.pack(pady=5)

# Label muestra el nombre del primer dato que debe escribir el usuario.
tk.Label(campos, text="CPU en uso (%):").grid(
    row=0, column=0, sticky="e", padx=5, pady=5
)
# Entry es la caja donde el usuario escribe el porcentaje de CPU.
entrada_cpu = tk.Entry(campos)
# insert pone un ejemplo inicial para que sea mas facil probar el programa.
entrada_cpu.insert(0, "45")
# grid organiza el control por fila y columna dentro del Frame.
entrada_cpu.grid(row=0, column=1, padx=5, pady=5)

# Repetimos el mismo patron para pedir la memoria libre.
tk.Label(campos, text="Memoria libre (%):").grid(
    row=1, column=0, sticky="e", padx=5, pady=5
)
entrada_memoria = tk.Entry(campos)
entrada_memoria.insert(0, "30")
entrada_memoria.grid(row=1, column=1, padx=5, pady=5)

# Repetimos el mismo patron para pedir el tiempo de respuesta del ping.
tk.Label(campos, text="Ping de respuesta (ms):").grid(
    row=2, column=0, sticky="e", padx=5, pady=5
)
entrada_ping = tk.Entry(campos)
entrada_ping.insert(0, "60")
entrada_ping.grid(row=2, column=1, padx=5, pady=5)

# Repetimos el mismo patron para pedir la temperatura del servidor.
tk.Label(campos, text="Temperatura (C):").grid(
    row=3, column=0, sticky="e", padx=5, pady=5
)
entrada_temperatura = tk.Entry(campos)
entrada_temperatura.insert(0, "85")
entrada_temperatura.grid(row=3, column=1, padx=5, pady=5)

# BooleanVar guarda el estado de la casilla: inicia en False porque no esta marcada.
ventilador_var = tk.BooleanVar(value=False)
# Checkbutton crea la casilla para indicar si el ventilador esta activo.
tk.Checkbutton(campos, text="Ventilador activo", variable=ventilador_var).grid(
    row=4, column=0, columnspan=2, pady=5
)

# Button crea el boton. command indica que funcion se llama al hacer clic.
tk.Button(
    ventana,
    text="Diagnosticar",
    command=ejecutar_diagnostico,
    bg="#2563EB",
    fg="white",
    font=("Arial", 11, "bold"),
).pack(pady=10)

# Esta etiqueta empieza con un mensaje y luego mostrara el diagnostico final.
etiqueta_resultado = tk.Label(
    ventana,
    text="Diagnostico: (presiona el boton)",
    wraplength=380,
    justify="left",
    font=("Arial", 10),
)
etiqueta_resultado.pack(pady=10, padx=10)

# mainloop mantiene la ventana abierta y espera clics del usuario.
ventana.mainloop()
