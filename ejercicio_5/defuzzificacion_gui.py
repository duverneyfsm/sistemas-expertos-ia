"""Programa sencillo para explicar la defuzzificacion por centroide (COG).

Ejecutar con:
    python defuzzificacion_gui.py

Este programa usa NumPy para trabajar con listas de numeros.
"""

# tk crea la ventana, las etiquetas, las cajas y los botones.
import tkinter as tk
# messagebox muestra avisos de datos incorrectos y ttk permite crear pestanas.
from tkinter import messagebox, ttk

# NumPy nos ayuda a hacer los calculos de forma corta y ordenada.
import numpy as np


def centroide(x, mu):
    """Esta funcion convierte valores difusos en un unico resultado exacto."""
    # Convertimos las listas recibidas en arreglos de numeros.
    # asarray asegura que x sea una lista de numeros decimales.
    x = np.asarray(x, dtype=float)
    # Hacemos lo mismo con los grados de pertenencia mu.
    mu = np.asarray(mu, dtype=float)

    # Cada valor de x debe tener un grado de pertenencia mu.
    if len(x) != len(mu):
        raise ValueError("x y mu deben tener la misma cantidad de valores.")

    # Abajo usamos la formula: COG = suma(x * mu) / suma(mu).
    denominador = np.sum(mu)
    # Si todos los grados son cero no hay pertenencia y no se puede dividir.
    if denominador == 0:
        raise ValueError("No es posible dividir entre cero: la suma de mu es 0.")

    numerador = np.sum(x * mu)  # Multiplicamos cada valor por su importancia.
    # Devolvemos el COG y tambien los dos valores para poder explicarlos en pantalla.
    return numerador / denominador, numerador, denominador


def calcular_descuento():
    """Este boton calcula el descuento recomendado en el ejemplo de la guia."""
    # x son los descuentos posibles y mu indica que tanto pertenece cada uno.
    x = np.array([10, 20, 30, 40])
    mu = np.array([0.2, 0.8, 0.8, 0.0])
    # Llamamos la funcion principal para obtener el descuento exacto.
    resultado, numerador, denominador = centroide(x, mu)

    # Habilitamos la caja, escribimos el resultado y la volvemos a bloquear.
    texto_descuento.config(state="normal")
    # delete borra el resultado anterior desde la primera posicion hasta el final.
    texto_descuento.delete("1.0", tk.END)
    texto_descuento.insert(
        tk.END,
        "Datos: x = [10, 20, 30, 40] y mu = [0.2, 0.8, 0.8, 0.0]\n\n"
        f"Numerador = suma(x * mu) = {numerador:.2f}\n"
        f"Denominador = suma(mu) = {denominador:.2f}\n\n"
        f"COG = {numerador:.2f} / {denominador:.2f} = {resultado:.2f}\n"
        f"Descuento exacto recomendado: {resultado:.2f}%"
    )
    texto_descuento.config(state="disabled")


def calcular_frenado():
    """Este boton calcula una fuerza de frenado exacta desde una curva difusa."""
    try:
        # Leemos el centro y el ancho que escribio el usuario.
        # get lee el texto de la caja y float lo convierte en numero.
        centro = float(entrada_centro.get())
        dispersion = float(entrada_dispersion.get())
        # Revisamos que el centro este en el rango y que el ancho sea positivo.
        if not 0 <= centro <= 100 or dispersion <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror(
            "Datos invalidos",
            "El centro debe estar entre 0 y 100 y la dispersion debe ser mayor que cero.",
        )
        return

    # Creamos 100 fuerzas posibles, desde 0 hasta 100 Newtons.
    x = np.linspace(0, 100, 100)
    # Esta formula crea una campana: los valores cercanos al centro son mas importantes.
    mu = np.exp(-((x - centro) ** 2) / (2 * dispersion ** 2))
    # Convertimos la curva difusa en una sola fuerza exacta usando el centroide.
    fuerza, numerador, denominador = centroide(x, mu)

    # Mostramos el resultado en la caja de texto.
    texto_frenado.config(state="normal")
    # Borramos el resultado anterior antes de mostrar el nuevo.
    texto_frenado.delete("1.0", tk.END)
    texto_frenado.insert(
        tk.END,
        "Se creo una curva Gaussiana con 100 puntos.\n\n"
        f"Numerador: {numerador:.2f}\n"
        f"Denominador: {denominador:.2f}\n"
        f"Centroide (fuerza crisp): {fuerza:.2f} Newtons\n\n"
        "Interpretacion: este es el unico valor de fuerza que recomienda el sistema."
    )
    texto_frenado.config(state="disabled")


def crear_interfaz():
    """Esta funcion crea la ventana, las pestanas y los botones del programa."""
    # global permite que los botones usen estas cajas creadas dentro de la ventana.
    global texto_descuento, entrada_centro, entrada_dispersion, texto_frenado

    # Creamos la ventana principal.
    ventana = tk.Tk()
    # Configuramos el texto, tamaño, bloqueo de tamaño y color de la ventana.
    ventana.title("Taller 5 - Defuzzificacion por Centroide")
    ventana.geometry("650x480")
    ventana.resizable(False, False)
    ventana.configure(bg="#F4F7FB")

    # Esta etiqueta muestra el titulo principal del taller.
    tk.Label(ventana, text="Taller 5: Defuzzificacion (Centroide / COG)",
             font=("Arial", 16, "bold"), bg="#F4F7FB", fg="#153E75").pack(pady=(15, 3))
    tk.Label(ventana, text="Formula: COG = suma(x * mu) / suma(mu)",
             bg="#F4F7FB").pack(pady=(0, 10))

    # Usamos pestanas para separar el ejemplo de descuento y el de frenado.
    pestanas = ttk.Notebook(ventana)
    pestanas.pack(fill="both", expand=True, padx=18, pady=(0, 16))

    # Frame crea la primera pagina y add la agrega a las pestanas.
    pagina_descuento = tk.Frame(pestanas, bg="#F4F7FB")
    pestanas.add(pagina_descuento, text="Descuento comercial")
    tk.Label(pagina_descuento, text="Ejemplo de la guia: 10%, 20%, 30%, 40%",
             bg="#F4F7FB", font=("Arial", 11, "bold")).pack(pady=(22, 8))
    # Al hacer clic, este boton llama a calcular_descuento.
    tk.Button(pagina_descuento, text="Calcular centroide del descuento",
              command=calcular_descuento, bg="#2563EB", fg="white",
              font=("Arial", 10, "bold")).pack(pady=5)
    # Text es el cuadro donde se explican los pasos y se deja bloqueado para escribir.
    texto_descuento = tk.Text(pagina_descuento, height=11, width=66, wrap="word", state="disabled")
    texto_descuento.pack(padx=16, pady=14)

    # Esta es la segunda pagina: calcula una fuerza de frenado.
    pagina_frenado = tk.Frame(pestanas, bg="#F4F7FB")
    pestanas.add(pagina_frenado, text="Frenado automatico")
    # LabelFrame agrupa los dos datos que necesita la curva Gaussiana.
    marco = tk.LabelFrame(pagina_frenado, text=" Curva Gaussiana ", bg="#F4F7FB", padx=10, pady=8)
    marco.pack(fill="x", padx=18, pady=18)
    tk.Label(marco, text="Centro de la campana (0-100 N):", bg="#F4F7FB").grid(
        row=0, column=0, sticky="w", padx=5, pady=5
    )
    # Entry crea la caja para indicar el centro de la campana.
    entrada_centro = tk.Entry(marco, width=10)
    entrada_centro.insert(0, "70")
    entrada_centro.grid(row=0, column=1, padx=5, pady=5)
    tk.Label(marco, text="Dispersion (ancho de la campana):", bg="#F4F7FB").grid(
        row=1, column=0, sticky="w", padx=5, pady=5
    )
    # Esta caja permite escribir que tan ancha sera la campana.
    entrada_dispersion = tk.Entry(marco, width=10)
    entrada_dispersion.insert(0, "12")
    entrada_dispersion.grid(row=1, column=1, padx=5, pady=5)
    # Este boton ejecuta calcular_frenado cuando el usuario hace clic.
    tk.Button(pagina_frenado, text="Calcular fuerza de frenado", command=calcular_frenado,
              bg="#16803C", fg="white", font=("Arial", 10, "bold")).pack(pady=5)
    # Aqui se muestran numerador, denominador y fuerza final del frenado.
    texto_frenado = tk.Text(pagina_frenado, height=10, width=66, wrap="word", state="disabled")
    texto_frenado.pack(padx=16, pady=12)

    # mainloop mantiene la ventana abierta para que el usuario pueda usarla.
    ventana.mainloop()


if __name__ == "__main__":
    # Esta linea inicia la ventana solo cuando ejecutamos este archivo.
    crear_interfaz()
