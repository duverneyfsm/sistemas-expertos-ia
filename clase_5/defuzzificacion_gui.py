"""Taller de defuzzificacion por centroide (COG) con Tkinter y NumPy.

Ejecutar con:
    python defuzzificacion_gui.py

Si NumPy no esta instalado, usar antes: pip install numpy
"""

import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np


def centroide(x, mu):
    """Calcula el centro de gravedad: suma(x * mu) / suma(mu).

    x contiene los valores posibles de salida y mu sus grados de pertenencia.
    El resultado es un numero crisp (un solo valor exacto).
    """
    x = np.asarray(x, dtype=float)
    mu = np.asarray(mu, dtype=float)

    if len(x) != len(mu):
        raise ValueError("x y mu deben tener la misma cantidad de valores.")

    denominador = np.sum(mu)
    if denominador == 0:
        raise ValueError("No es posible dividir entre cero: la suma de mu es 0.")

    numerador = np.sum(x * mu)
    return numerador / denominador, numerador, denominador


def calcular_descuento():
    """Resuelve el ejemplo de cuatro puntos de descuento de la guia."""
    # Estos son exactamente los arreglos entregados en el taller analitico.
    x = np.array([10, 20, 30, 40])
    mu = np.array([0.2, 0.8, 0.8, 0.0])
    resultado, numerador, denominador = centroide(x, mu)

    texto_descuento.config(state="normal")
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
    """Genera una campana gaussiana y la convierte a fuerza exacta de frenado."""
    try:
        centro = float(entrada_centro.get())
        dispersion = float(entrada_dispersion.get())
        if not 0 <= centro <= 100 or dispersion <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror(
            "Datos invalidos",
            "El centro debe estar entre 0 y 100 y la dispersion debe ser mayor que cero.",
        )
        return

    # linspace crea los 100 puntos del eje X solicitados (0 a 100 Newtons).
    x = np.linspace(0, 100, 100)
    # exp() representa una campana de Gauss centrada en el valor elegido.
    mu = np.exp(-((x - centro) ** 2) / (2 * dispersion ** 2))
    fuerza, numerador, denominador = centroide(x, mu)

    texto_frenado.config(state="normal")
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
    """Crea las dos pantallas del taller: descuento y frenado automatico."""
    global texto_descuento, entrada_centro, entrada_dispersion, texto_frenado

    ventana = tk.Tk()
    ventana.title("Taller 5 - Defuzzificacion por Centroide")
    ventana.geometry("650x480")
    ventana.resizable(False, False)
    ventana.configure(bg="#F4F7FB")

    tk.Label(ventana, text="Taller 5: Defuzzificacion (Centroide / COG)",
             font=("Arial", 16, "bold"), bg="#F4F7FB", fg="#153E75").pack(pady=(15, 3))
    tk.Label(ventana, text="Formula: COG = suma(x * mu) / suma(mu)",
             bg="#F4F7FB").pack(pady=(0, 10))

    pestanas = ttk.Notebook(ventana)
    pestanas.pack(fill="both", expand=True, padx=18, pady=(0, 16))

    pagina_descuento = tk.Frame(pestanas, bg="#F4F7FB")
    pestanas.add(pagina_descuento, text="Descuento comercial")
    tk.Label(pagina_descuento, text="Ejemplo de la guia: 10%, 20%, 30%, 40%",
             bg="#F4F7FB", font=("Arial", 11, "bold")).pack(pady=(22, 8))
    tk.Button(pagina_descuento, text="Calcular centroide del descuento",
              command=calcular_descuento, bg="#2563EB", fg="white",
              font=("Arial", 10, "bold")).pack(pady=5)
    texto_descuento = tk.Text(pagina_descuento, height=11, width=66, wrap="word", state="disabled")
    texto_descuento.pack(padx=16, pady=14)

    pagina_frenado = tk.Frame(pestanas, bg="#F4F7FB")
    pestanas.add(pagina_frenado, text="Frenado automatico")
    marco = tk.LabelFrame(pagina_frenado, text=" Curva Gaussiana ", bg="#F4F7FB", padx=10, pady=8)
    marco.pack(fill="x", padx=18, pady=18)
    tk.Label(marco, text="Centro de la campana (0-100 N):", bg="#F4F7FB").grid(
        row=0, column=0, sticky="w", padx=5, pady=5
    )
    entrada_centro = tk.Entry(marco, width=10)
    entrada_centro.insert(0, "70")
    entrada_centro.grid(row=0, column=1, padx=5, pady=5)
    tk.Label(marco, text="Dispersion (ancho de la campana):", bg="#F4F7FB").grid(
        row=1, column=0, sticky="w", padx=5, pady=5
    )
    entrada_dispersion = tk.Entry(marco, width=10)
    entrada_dispersion.insert(0, "12")
    entrada_dispersion.grid(row=1, column=1, padx=5, pady=5)
    tk.Button(pagina_frenado, text="Calcular fuerza de frenado", command=calcular_frenado,
              bg="#16803C", fg="white", font=("Arial", 10, "bold")).pack(pady=5)
    texto_frenado = tk.Text(pagina_frenado, height=10, width=66, wrap="word", state="disabled")
    texto_frenado.pack(padx=16, pady=12)

    ventana.mainloop()


if __name__ == "__main__":
    crear_interfaz()
