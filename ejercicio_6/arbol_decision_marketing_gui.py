"""Programa sencillo para explicar arboles de decision con una interfaz.

Ejecutar con:
    python arbol_decision_marketing_gui.py

Este programa necesita estas librerias:
    pip install numpy scikit-learn

Para explicarlo: el arbol analiza ejemplos de clientes, elige preguntas que
separan mejor las clases y despues usa esas reglas para predecir un caso nuevo.
"""

import math  # Sirve para usar logaritmos al calcular la entropia.
# tk permite crear la ventana y sus controles visuales.
import tkinter as tk
# messagebox muestra avisos y ttk permite trabajar con pestanas.
from tkinter import messagebox, ttk

# NumPy guarda los datos del ejemplo en tablas de numeros.
import numpy as np
# Estas herramientas crean y muestran el arbol de decision.
from sklearn.tree import DecisionTreeClassifier, export_text


def entropia(compraron, no_compraron):
    """Esta funcion mide que tan mezclado esta un grupo de clientes."""
    # Sumamos los clientes que compraron y los que no compraron.
    total = compraron + no_compraron
    # Si el grupo esta vacio o todos hicieron lo mismo, no hay confusion.
    if total == 0 or compraron == 0 or no_compraron == 0:
        return 0.0

    # Convertimos las cantidades en porcentajes para usar la formula.
    # Calculamos la proporcion de personas que compraron.
    proporcion_si = compraron / total
    # Calculamos la proporcion de personas que no compraron.
    proporcion_no = no_compraron / total
    # Aplicamos la formula de entropia y devolvemos el resultado.
    return -(proporcion_si * math.log2(proporcion_si) + proporcion_no * math.log2(proporcion_no))


def ganancia_informacion(grupo_izquierdo, grupo_derecho):
    """Esta funcion dice que tan buena es una pregunta para separar clientes."""
    # Estos son los datos iniciales del ejercicio de la guia.
    total_si, total_no = 3, 3
    # total es la cantidad de personas del ejercicio antes de hacer una pregunta.
    total = total_si + total_no
    entropia_inicial = entropia(total_si, total_no)

    # Contamos las personas que quedaron a cada lado de la pregunta.
    tam_izquierdo = sum(grupo_izquierdo)
    tam_derecho = sum(grupo_derecho)
    # Calculamos la mezcla despues de dividir el grupo.
    entropia_ponderada = (
        (tam_izquierdo / total) * entropia(*grupo_izquierdo)
        + (tam_derecho / total) * entropia(*grupo_derecho)
    )
    # La ganancia es la confusion inicial menos la confusion despues de separar.
    return entropia_inicial - entropia_ponderada


def analizar_preguntas():
    """Este boton resuelve las dos preguntas del ejercicio en papel."""
    # Pregunta A: quedan dos grupos que todavia estan mezclados.
    ganancia_a = ganancia_informacion((2, 2), (1, 1))
    # Pregunta B: quedan dos grupos puros, por eso es mejor.
    ganancia_b = ganancia_informacion((3, 0), (0, 3))

    # Habilitamos, limpiamos y luego llenamos el cuadro de resultados.
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
    """Crea los datos de ejemplo que el arbol va a estudiar."""
    # Cada fila tiene: edad, horas en linea y compras anteriores.
    # x es una tabla: cada fila representa un cliente de ejemplo.
    x = np.array([
        [22, 2, 0], [24, 7, 1], [27, 9, 2], [30, 12, 3],
        [34, 5, 4], [37, 11, 1], [40, 15, 3], [45, 6, 2],
        [48, 18, 5], [52, 10, 2], [55, 4, 0], [60, 20, 6],
    ])
    # 1 significa que hizo clic; 0 significa que ignoro el anuncio.
    y = np.array([0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1])
    # Devolvemos la tabla de datos y las respuestas conocidas de esos clientes.
    return x, y


def entrenar_arbol_marketing():
    """Esta funcion crea el arbol y aprende reglas con los datos."""
    # Obtenemos los datos de entrada x y las respuestas y.
    x, y = crear_datos_marketing()
    # Limitamos el arbol a tres niveles para que sea facil de explicar.
    arbol = DecisionTreeClassifier(max_depth=3, random_state=0)
    # fit() es el paso donde el arbol encuentra patrones en los datos.
    arbol.fit(x, y)
    # Convertimos las decisiones del arbol en texto para mostrarlas.
    reglas = export_text(
        arbol,
        feature_names=["Edad", "Horas_online", "Compras_previas"],
    )
    # Entregamos el arbol entrenado y sus reglas en texto.
    return arbol, reglas


def mostrar_reglas():
    """Este boton muestra las reglas que aprendio el arbol."""
    # El guion bajo indica que no necesitamos guardar el arbol en esta funcion.
    _, reglas = entrenar_arbol_marketing()
    # Habilitamos la caja para borrar y mostrar las reglas nuevas.
    texto_reglas.config(state="normal")
    texto_reglas.delete("1.0", tk.END)
    texto_reglas.insert(
        tk.END,
        "Base de reglas generada automaticamente por DecisionTreeClassifier:\n\n" + reglas
    )
    texto_reglas.config(state="disabled")


def predecir_clic():
    """Este boton predice si un nuevo cliente hara clic en el anuncio."""
    try:
        # Leemos los tres datos escritos en las cajas de la ventana.
        # Leemos los datos escritos y los convertimos de texto a numeros.
        edad = float(entrada_edad.get())
        horas = float(entrada_horas.get())
        compras = float(entrada_compras.get())
        if edad < 0 or horas < 0 or compras < 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Datos invalidos", "Edad, horas y compras deben ser numeros no negativos.")
        return

    # Creamos el arbol y le enviamos los datos del nuevo cliente.
    arbol, _ = entrenar_arbol_marketing()
    # predict devuelve 0 o 1; usamos [0] porque solo evaluamos un cliente.
    prediccion = arbol.predict([[edad, horas, compras]])[0]
    # predict_proba devuelve las probabilidades de 0 y de 1.
    probabilidades = arbol.predict_proba([[edad, horas, compras]])[0]
    # Convertimos el 0 o 1 en una frase facil de leer.
    resultado = "HIZO CLIC EN EL ANUNCIO" if prediccion == 1 else "IGNORO EL ANUNCIO"
    etiqueta_prediccion.config(
        text=(f"Prediccion: {resultado}\n"
              f"Probabilidad estimada de clic: {probabilidades[1] * 100:.0f}%")
    )


def crear_interfaz():
    """Esta funcion crea la ventana, los botones y las cajas de texto."""
    # global permite que las funciones de los botones usen estos controles.
    global texto_analisis, texto_reglas, entrada_edad, entrada_horas, entrada_compras, etiqueta_prediccion

    # Creamos la ventana principal del programa.
    ventana = tk.Tk()
    ventana.title("Taller 6 - Arboles de Decision y Machine Learning")
    ventana.geometry("720x625")
    ventana.resizable(False, False)
    ventana.configure(bg="#F4F7FB")

    # Estas dos etiquetas muestran el titulo y una idea principal del taller.
    tk.Label(ventana, text="Taller 6: Arboles de Decision y Machine Learning",
             font=("Arial", 16, "bold"), bg="#F4F7FB", fg="#153E75").pack(pady=(15, 3))
    tk.Label(ventana, text="El arbol aprende reglas SI... ENTONCES a partir de datos historicos.",
             bg="#F4F7FB").pack(pady=(0, 10))

    # Las pestanas separan el ejercicio en papel y el ejemplo de marketing.
    pestanas = ttk.Notebook(ventana)
    pestanas.pack(fill="both", expand=True, padx=18, pady=(0, 16))

    # Primera pagina: explica la ganancia de informacion con el ejercicio manual.
    pagina_analisis = tk.Frame(pestanas, bg="#F4F7FB")
    pestanas.add(pagina_analisis, text="Algoritmo en papel")
    tk.Button(pagina_analisis, text="Calcular ganancias de informacion", command=analizar_preguntas,
              bg="#2563EB", fg="white", font=("Arial", 10, "bold")).pack(pady=20)
    # Esta caja muestra los calculos de entropia y las reglas obtenidas.
    texto_analisis = tk.Text(pagina_analisis, height=15, width=75, wrap="word", state="disabled")
    texto_analisis.pack(padx=16, pady=5)

    # Segunda pagina: usa el arbol para el ejemplo de marketing.
    pagina_marketing = tk.Frame(pestanas, bg="#F4F7FB")
    pestanas.add(pagina_marketing, text="Experto de marketing")
    tk.Button(pagina_marketing, text="Entrenar y ver reglas", command=mostrar_reglas,
              bg="#16803C", fg="white", font=("Arial", 10, "bold")).pack(pady=(12, 5))
    # Esta caja mostrara las reglas que aprendio DecisionTreeClassifier.
    texto_reglas = tk.Text(pagina_marketing, height=11, width=75, wrap="word", state="disabled")
    texto_reglas.pack(padx=16, pady=4)

    marco = tk.LabelFrame(pagina_marketing, text=" Probar un nuevo cliente ", bg="#F4F7FB", padx=8, pady=5)
    marco.pack(fill="x", padx=16, pady=6)
    # Creamos tres cajas para escribir los datos de un cliente nuevo.
    for columna, (nombre, valor) in enumerate((("Edad", "35"), ("Horas online", "12"), ("Compras previas", "3"))):
        tk.Label(marco, text=nombre + ":", bg="#F4F7FB").grid(row=0, column=columna * 2, padx=(5, 2), pady=4)
        # Creamos una caja para ese dato y escribimos un valor de ejemplo.
        entrada = tk.Entry(marco, width=7)
        entrada.insert(0, valor)
        entrada.grid(row=0, column=columna * 2 + 1, padx=(0, 7), pady=4)
        # Guardamos cada caja en una variable distinta segun la columna.
        if columna == 0:
            entrada_edad = entrada
        elif columna == 1:
            entrada_horas = entrada
        else:
            entrada_compras = entrada
    tk.Button(marco, text="Predecir", command=predecir_clic).grid(row=0, column=6, padx=6)
    # Esta etiqueta se actualiza con la prediccion del nuevo cliente.
    etiqueta_prediccion = tk.Label(pagina_marketing, text="", bg="#F4F7FB", fg="#153E75", justify="left")
    etiqueta_prediccion.pack(pady=3)

    # mainloop deja la ventana activa y esperando clics de los botones.
    ventana.mainloop()


if __name__ == "__main__":
    # Esta linea inicia la ventana solo al ejecutar este archivo.
    crear_interfaz()
