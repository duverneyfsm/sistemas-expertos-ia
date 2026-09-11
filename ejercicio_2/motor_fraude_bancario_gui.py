"""Ejercicio 2: motor sencillo para detectar posibles fraudes bancarios.

El programa usa encadenamiento hacia adelante: parte de los hechos que se
conocen y aplica reglas hasta descubrir que no hay mas conclusiones nuevas.
"""

# tk permite crear la ventana, botones, etiquetas y cajas de texto.
import tkinter as tk
# messagebox muestra una alerta si el usuario escribe datos incorrectos.
from tkinter import messagebox


# Esta lista es la base de conocimiento del sistema experto.
# Cada regla tiene condiciones (la parte SI) y una conclusion (la parte ENTONCES).
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
    """Aplica reglas a los hechos hasta que no aparezcan hechos nuevos."""
    # traza guardara los pasos para que el usuario vea que reglas se activaron.
    traza = []
    # Esta variable controla el ciclo while. Inicia en True para revisar las reglas.
    nuevos_hechos = True

    # Repetimos mientras alguna regla haya agregado una conclusion nueva.
    while nuevos_hechos:
        # Suponemos que no habra nuevos hechos en esta vuelta.
        nuevos_hechos = False

        # El ciclo for revisa una por una todas las reglas de la lista REGLAS.
        for regla in REGLAS:
            # all() funciona como AND: solo da True si todas las condiciones son True.
            condiciones_cumplidas = all(
                # get(clave) busca el valor del hecho; se compara con el valor esperado.
                hechos.get(clave) == valor
                for clave, valor in regla["condiciones"].items()
            )

            # Si la parte SI de la regla se cumple, aplicamos la parte ENTONCES.
            if condiciones_cumplidas:
                # Algunas reglas pueden agregar uno o varios hechos nuevos.
                for clave, valor in regla["conclusion"].items():
                    # Solo agregamos el hecho si antes no existia en la memoria.
                    if clave not in hechos:
                        # Guardamos la nueva conclusion dentro del diccionario de hechos.
                        hechos[clave] = valor
                        # Avisamos al while que debe hacer otra vuelta de revision.
                        nuevos_hechos = True
                        # Guardamos un texto explicativo de la regla que se disparo.
                        traza.append(
                            f"Disparando {regla['id']} -> "
                            f"Nuevo hecho: {clave}={valor}"
                        )

    # Devolvemos los hechos finales y la lista de pasos que siguio el motor.
    return hechos, traza


def ejecutar_evaluacion():
    """Esta funcion se ejecuta al presionar el boton Evaluar transaccion."""
    try:
        # Leemos las cajas de la ventana y las guardamos como hechos iniciales.
        # float permite usar decimales en el monto e int usa numeros enteros en compras.
        hechos = {
            "monto": float(entrada_monto.get()),
            "pais_extranjero": pais_var.get(),
            "compras_ultima_hora": int(entrada_compras.get()),
            "tarjeta_reportada_robada": robada_var.get(),
        }
    except ValueError:
        # Si el texto no se puede convertir a numero, mostramos una alerta.
        messagebox.showerror(
            "Datos invalidos", "Monto y compras deben ser valores numericos."
        )
        return

    # Convertimos los numeros en hechos True/False que entienden las reglas.
    # Un monto mayor a 5000 se considera alto.
    hechos["monto_alto"] = hechos["monto"] > 5000
    # Tres o mas compras en una hora se consideran compras rapidas.
    hechos["multiples_compras_rapidas"] = hechos["compras_ultima_hora"] >= 3

    # Enviamos los hechos al motor y recibimos la memoria final con la traza.
    memoria_final, traza = evaluar_transaccion(hechos)
    # Si existe el hecho bloquear_tarjeta, el veredicto sera bloquear; si no, permitir.
    veredicto = (
        "BLOQUEAR TARJETA"
        if memoria_final.get("bloquear_tarjeta")
        else "Transaccion permitida"
    )

    # Borramos el resultado anterior antes de escribir uno nuevo.
    texto_resultado.delete("1.0", tk.END)
    if traza:
        # join une todos los pasos de la traza usando un salto de linea.
        texto_resultado.insert(tk.END, "\n".join(traza) + "\n\n")
    else:
        texto_resultado.insert(
            tk.END, "El motor no encontro ninguna regla aplicable.\n\n"
        )
    # Al final siempre mostramos la decision del sistema experto.
    texto_resultado.insert(tk.END, f"Veredicto final: {veredicto}")


# Creamos la ventana principal y configuramos su titulo y tamaño.
ventana = tk.Tk()
ventana.title("Motor de Fraude Bancario")
ventana.geometry("450x430")
ventana.resizable(False, False)

# Esta etiqueta muestra el titulo grande de la aplicacion.
tk.Label(
    ventana,
    text="Motor de Fraude Bancario",
    font=("Arial", 13, "bold"),
).pack(pady=10)  # pack coloca los controles uno debajo de otro.

# Frame es un contenedor para organizar las preguntas en forma de tabla.
campos = tk.Frame(ventana)
campos.pack(pady=5)

# Label explica que dato debe escribir el usuario en la primera caja.
tk.Label(campos, text="Monto de la transaccion (USD):").grid(
    row=0, column=0, sticky="e", padx=5, pady=5
)
# Entry es una caja para que el usuario escriba el monto.
entrada_monto = tk.Entry(campos)
entrada_monto.insert(0, "7500")
entrada_monto.grid(row=0, column=1, padx=5, pady=5)

# Este segundo grupo pide cuantas compras se hicieron en la ultima hora.
tk.Label(campos, text="Compras en la ultima hora:").grid(
    row=1, column=0, sticky="e", padx=5, pady=5
)
entrada_compras = tk.Entry(campos)
entrada_compras.insert(0, "4")
entrada_compras.grid(row=1, column=1, padx=5, pady=5)

# BooleanVar guarda True o False para la casilla de pais extranjero.
pais_var = tk.BooleanVar(value=True)
tk.Checkbutton(
    campos,
    text="Transaccion en pais extranjero",
    variable=pais_var,
).grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=5)

# Esta variable guarda si la tarjeta fue reportada como robada.
robada_var = tk.BooleanVar(value=False)
tk.Checkbutton(
    campos,
    text="Tarjeta reportada como robada",
    variable=robada_var,
).grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)

# Este boton llama a ejecutar_evaluacion cuando el usuario hace clic.
tk.Button(
    ventana,
    text="Evaluar transaccion",
    command=ejecutar_evaluacion,
    bg="#2563EB",
    fg="white",
    font=("Arial", 11, "bold"),
).pack(pady=10)

# Text es una caja grande donde se mostraran las reglas aplicadas y el veredicto.
texto_resultado = tk.Text(ventana, height=8, width=48, wrap="word")
texto_resultado.pack(pady=10, padx=10)

# mainloop deja la ventana abierta y esperando acciones del usuario.
ventana.mainloop()
