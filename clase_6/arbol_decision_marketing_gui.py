"""Taller de arboles de decision y machine learning con una interfaz Tkinter.

Ejecutar con:
    python arbol_decision_marketing_gui.py

Requiere las librerias del taller:
    pip install numpy scikit-learn
"""

import math
import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np
from sklearn.tree import DecisionTreeClassifier, export_text


def entropia(compraron, no_compraron):
    """Calcula la entropia de un grupo. Un grupo puro tiene entropia 0."""
    total = compraron + no_compraron
    if total == 0 or compraron == 0 or no_compraron == 0:
        return 0.0

    proporcion_si = compraron / total
    proporcion_no = no_compraron / total
    return -(proporcion_si * math.log2(proporcion_si) + proporcion_no * math.log2(proporcion_no))


def ganancia_informacion(grupo_izquierdo, grupo_derecho):
    """Obtiene cuanto reduce la entropia una pregunta candidata del arbol."""
    total_si, total_no = 3, 3  # Datos iniciales indicados por la guia.
    total = total_si + total_no
    entropia_inicial = entropia(total_si, total_no)

    tam_izquierdo = sum(grupo_izquierdo)
    tam_derecho = sum(grupo_derecho)
    entropia_ponderada = (
        (tam_izquierdo / total) * entropia(*grupo_izquierdo)
        + (tam_derecho / total) * entropia(*grupo_derecho)
    )
    return entropia_inicial - entropia_ponderada


def analizar_preguntas():
    """Resuelve el taller en papel: B deja dos grupos puros y por eso gana."""
    # Pregunta A: grupos [2 si, 2 no] y [1 si, 1 no].
    ganancia_a = ganancia_informacion((2, 2), (1, 1))
    # Pregunta B: grupos [3 si, 0 no] y [0 si, 3 no].
    ganancia_b = ganancia_informacion((3, 0), (0, 3))

    texto_analisis.config(state="normal")
    texto_analisis.delete("1.0", tk.END)
    texto_analisis.insert(
        tk.END,
        f"Entropia inicial: H(3 si, 3 no) = {entropia(3, 3):.2f}\n\n"
        f"Ganancia pregunta A (Edad > 30): {ganancia_a:.2f}\n"
        f"Ganancia pregunta B (Tiene auto): {ganancia_b:.2f}\n\n"
        "La pregunta B ofrece la mayor ganancia porque separa grupos puros.\n\n"
        "Reglas aprendidas:\n"
        "SI tiene auto, ENTONCES compra el seguro.\n"
        "SI no tiene auto, ENTONCES no compra el seguro."
    )
    texto_analisis.config(state="disabled")


def crear_datos_marketing():
    """Crea las 12 filas simuladas solicitadas para el departamento de Marketing.

    Columnas: edad, horas en linea y compras previas.
    Etiqueta: 1 si hizo clic; 0 si ignoro el anuncio.
    El patron intencional es: mas horas en linea y mas compras favorecen el clic.
    """
    x = np.array([
        [22, 2, 0], [24, 7, 1], [27, 9, 2], [30, 12, 3],
        [34, 5, 4], [37, 11, 1], [40, 15, 3], [45, 6, 2],
        [48, 18, 5], [52, 10, 2], [55, 4, 0], [60, 20, 6],
    ])
    y = np.array([0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1])
    return x, y


def entrenar_arbol_marketing():
    """Entrena DecisionTreeClassifier y exporta sus reglas como texto legible."""
    x, y = crear_datos_marketing()
    # max_depth=3 mantiene el arbol pequeno y facil de explicar en clase.
    arbol = DecisionTreeClassifier(max_depth=3, random_state=0)
    arbol.fit(x, y)  # fit() es el paso en que la IA busca reglas en los datos.
    reglas = export_text(
        arbol,
        feature_names=["Edad", "Horas_online", "Compras_previas"],
    )
    return arbol, reglas


def mostrar_reglas():
    """Entrena nuevamente y muestra la base de conocimiento extraida del arbol."""
    _, reglas = entrenar_arbol_marketing()
    texto_reglas.config(state="normal")
    texto_reglas.delete("1.0", tk.END)
    texto_reglas.insert(
        tk.END,
        "Base de reglas generada automaticamente por DecisionTreeClassifier:\n\n" + reglas
    )
    texto_reglas.config(state="disabled")


def predecir_clic():
    """Usa el arbol entrenado para clasificar los datos escritos por el usuario."""
    try:
        edad = float(entrada_edad.get())
        horas = float(entrada_horas.get())
        compras = float(entrada_compras.get())
        if edad < 0 or horas < 0 or compras < 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Datos invalidos", "Edad, horas y compras deben ser numeros no negativos.")
        return

    arbol, _ = entrenar_arbol_marketing()
    prediccion = arbol.predict([[edad, horas, compras]])[0]
    probabilidades = arbol.predict_proba([[edad, horas, compras]])[0]
    resultado = "HIZO CLIC EN EL ANUNCIO" if prediccion == 1 else "IGNORO EL ANUNCIO"
    etiqueta_prediccion.config(
        text=(f"Prediccion: {resultado}\n"
              f"Probabilidad estimada de clic: {probabilidades[1] * 100:.0f}%")
    )


def crear_interfaz():
    """Construye la aplicacion con una pestana por cada ejercicio del taller 6."""
    global texto_analisis, texto_reglas, entrada_edad, entrada_horas, entrada_compras, etiqueta_prediccion

    ventana = tk.Tk()
    ventana.title("Taller 6 - Arboles de Decision y Machine Learning")
    ventana.geometry("720x625")
    ventana.resizable(False, False)
    ventana.configure(bg="#F4F7FB")

    tk.Label(ventana, text="Taller 6: Arboles de Decision y Machine Learning",
             font=("Arial", 16, "bold"), bg="#F4F7FB", fg="#153E75").pack(pady=(15, 3))
    tk.Label(ventana, text="El arbol aprende reglas SI... ENTONCES a partir de datos historicos.",
             bg="#F4F7FB").pack(pady=(0, 10))

    pestanas = ttk.Notebook(ventana)
    pestanas.pack(fill="both", expand=True, padx=18, pady=(0, 16))

    pagina_analisis = tk.Frame(pestanas, bg="#F4F7FB")
    pestanas.add(pagina_analisis, text="Algoritmo en papel")
    tk.Button(pagina_analisis, text="Calcular ganancias de informacion", command=analizar_preguntas,
              bg="#2563EB", fg="white", font=("Arial", 10, "bold")).pack(pady=20)
    texto_analisis = tk.Text(pagina_analisis, height=15, width=75, wrap="word", state="disabled")
    texto_analisis.pack(padx=16, pady=5)

    pagina_marketing = tk.Frame(pestanas, bg="#F4F7FB")
    pestanas.add(pagina_marketing, text="Experto de marketing")
    tk.Button(pagina_marketing, text="Entrenar y ver reglas", command=mostrar_reglas,
              bg="#16803C", fg="white", font=("Arial", 10, "bold")).pack(pady=(12, 5))
    texto_reglas = tk.Text(pagina_marketing, height=11, width=75, wrap="word", state="disabled")
    texto_reglas.pack(padx=16, pady=4)

    marco = tk.LabelFrame(pagina_marketing, text=" Probar un nuevo cliente ", bg="#F4F7FB", padx=8, pady=5)
    marco.pack(fill="x", padx=16, pady=6)
    for columna, (nombre, valor) in enumerate((("Edad", "35"), ("Horas online", "12"), ("Compras previas", "3"))):
        tk.Label(marco, text=nombre + ":", bg="#F4F7FB").grid(row=0, column=columna * 2, padx=(5, 2), pady=4)
        entrada = tk.Entry(marco, width=7)
        entrada.insert(0, valor)
        entrada.grid(row=0, column=columna * 2 + 1, padx=(0, 7), pady=4)
        if columna == 0:
            entrada_edad = entrada
        elif columna == 1:
            entrada_horas = entrada
        else:
            entrada_compras = entrada
    tk.Button(marco, text="Predecir", command=predecir_clic).grid(row=0, column=6, padx=6)
    etiqueta_prediccion = tk.Label(pagina_marketing, text="", bg="#F4F7FB", fg="#153E75", justify="left")
    etiqueta_prediccion.pack(pady=3)

    ventana.mainloop()


if __name__ == "__main__":
    crear_interfaz()
