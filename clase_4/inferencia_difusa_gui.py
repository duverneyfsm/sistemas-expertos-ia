"""Taller de inferencia difusa Mamdani con una interfaz sencilla.

Ejecutar con:
    python inferencia_difusa_gui.py

No requiere instalar librerias externas: Tkinter viene incluido con Python.
"""

import tkinter as tk
from tkinter import messagebox, ttk


def evaluar_proyecto(rentabilidad_alta, impacto_alto, riesgo_bajo, riesgo_alto):
    """Aplica las dos reglas del ejercicio de proyectos.

    En Mamdani, OR se representa con max() y AND se representa con min().
    La fuerza obtenida es la altura a la que se recorta la conclusion.
    """
    # R1: (Rentabilidad ALTA O Impacto ALTO) Y Riesgo BAJO -> SEGURA.
    fuerza_or = max(rentabilidad_alta, impacto_alto)
    segura = min(fuerza_or, riesgo_bajo)

    # R2: Riesgo ALTO -> DENEGADA. Solo se copia su grado de membresia.
    denegada = riesgo_alto
    return fuerza_or, {"SEGURA": segura, "DENEGADA": denegada}


def evaluar_bono(desempeno_pobre, desempeno_promedio, desempeno_excelente,
                 antiguedad_corta, antiguedad_larga):
    """Evalua las tres reglas del motor de Recursos Humanos."""
    # R1: Pobre O Corta -> Bono Bajo.
    bono_bajo = max(desempeno_pobre, antiguedad_corta)

    # R2: Promedio -> Bono Medio.
    bono_medio = desempeno_promedio

    # R3: Excelente Y Larga -> Bono Alto.
    bono_alto = min(desempeno_excelente, antiguedad_larga)
    return {"Bono bajo": bono_bajo, "Bono medio": bono_medio, "Bono alto": bono_alto}


def leer_grado(entrada, nombre):
    """Convierte una caja de texto a numero y comprueba el rango difuso 0..1."""
    try:
        grado = float(entrada.get())
    except ValueError as error:
        raise ValueError(f"{nombre} debe ser un numero entre 0 y 1.") from error

    if not 0 <= grado <= 1:
        raise ValueError(f"{nombre} debe estar entre 0 y 1.")
    return grado


def calcular_proyecto():
    """Lee la primera pestana y escribe cada paso de la inferencia."""
    try:
        rentabilidad = leer_grado(entradas_proyecto["Rentabilidad alta"], "Rentabilidad alta")
        impacto = leer_grado(entradas_proyecto["Impacto social alto"], "Impacto social alto")
        riesgo_bajo = leer_grado(entradas_proyecto["Riesgo bajo"], "Riesgo bajo")
        riesgo_alto = leer_grado(entradas_proyecto["Riesgo alto"], "Riesgo alto")
    except ValueError as error:
        messagebox.showerror("Dato invalido", str(error))
        return

    fuerza_or, conclusiones = evaluar_proyecto(
        rentabilidad, impacto, riesgo_bajo, riesgo_alto
    )
    texto_proyecto.config(state="normal")
    texto_proyecto.delete("1.0", tk.END)
    texto_proyecto.insert(
        tk.END,
        "REGLA R1: (Rentabilidad ALTA O Impacto ALTO) Y Riesgo BAJO\n\n"
        f"1. OR = max({rentabilidad:.2f}, {impacto:.2f}) = {fuerza_or:.2f}\n"
        f"2. AND = min({fuerza_or:.2f}, {riesgo_bajo:.2f}) = {conclusiones['SEGURA']:.2f}\n\n"
        f"La conclusion 'Aprobacion SEGURA' se trunca a la altura: {conclusiones['SEGURA']:.2f}.\n\n"
        f"REGLA R2: Riesgo ALTO -> Aprobacion DENEGADA\n"
        f"Fuerza de 'DENEGADA': {conclusiones['DENEGADA']:.2f}."
    )
    texto_proyecto.config(state="disabled")


def calcular_bono():
    """Ejecuta el motor de bonos y presenta la formula usada por cada regla."""
    try:
        valores = {
            nombre: leer_grado(entrada, nombre)
            for nombre, entrada in entradas_bono.items()
        }
    except ValueError as error:
        messagebox.showerror("Dato invalido", str(error))
        return

    bonos = evaluar_bono(
        valores["Desempeno pobre"], valores["Desempeno promedio"],
        valores["Desempeno excelente"], valores["Antiguedad corta"],
        valores["Antiguedad larga"],
    )
    texto_bono.config(state="normal")
    texto_bono.delete("1.0", tk.END)
    texto_bono.insert(
        tk.END,
        "R1: Bono bajo = max(Desempeno pobre, Antiguedad corta)\n"
        f"    = max({valores['Desempeno pobre']:.2f}, {valores['Antiguedad corta']:.2f}) = {bonos['Bono bajo']:.2f}\n\n"
        "R2: Bono medio = Desempeno promedio\n"
        f"    = {bonos['Bono medio']:.2f}\n\n"
        "R3: Bono alto = min(Desempeno excelente, Antiguedad larga)\n"
        f"    = min({valores['Desempeno excelente']:.2f}, {valores['Antiguedad larga']:.2f}) = {bonos['Bono alto']:.2f}\n\n"
        "Resultado: el diccionario contiene el grado de activacion de cada bono."
    )
    texto_bono.config(state="disabled")


def mostrar_agregacion():
    """Responde la pregunta teorica: dos reglas que concluyen Bono Alto se unen con OR."""
    fuerza_final = max(0.4, 0.7)
    etiqueta_agregacion.config(
        text=("Agregacion Mamdani: max(0.4, 0.7) = "
              f"{fuerza_final:.1f}.\nLa fuerza final de 'Bono alto' es {fuerza_final:.1f}.")
    )


def crear_entrada(marco, fila, texto, valor, destino):
    """Crea una etiqueta y una caja; destino guarda la referencia a esa caja."""
    tk.Label(marco, text=f"{texto} (0 a 1):", bg="#F4F7FB").grid(
        row=fila, column=0, sticky="w", padx=8, pady=5
    )
    entrada = tk.Entry(marco, width=10)
    entrada.insert(0, valor)
    entrada.grid(row=fila, column=1, sticky="w", padx=8, pady=5)
    destino[texto] = entrada


def crear_interfaz():
    """Construye la ventana. Se separa de la logica para poder probar funciones aparte."""
    global entradas_proyecto, entradas_bono, texto_proyecto, texto_bono, etiqueta_agregacion

    ventana = tk.Tk()
    ventana.title("Taller 4 - Inferencia Difusa Mamdani")
    ventana.geometry("680x620")
    ventana.resizable(False, False)
    ventana.configure(bg="#F4F7FB")

    tk.Label(ventana, text="Taller 4: Inferencia Difusa (Mamdani)",
             font=("Arial", 17, "bold"), bg="#F4F7FB", fg="#153E75").pack(pady=(15, 3))
    tk.Label(ventana, text="En Mamdani: OR = max() y AND = min().",
             bg="#F4F7FB").pack(pady=(0, 10))

    pestanas = ttk.Notebook(ventana)
    pestanas.pack(fill="both", expand=True, padx=18, pady=(0, 16))

    # Pestana 1: ejercicio analitico de aprobacion de proyectos.
    pagina_proyecto = tk.Frame(pestanas, bg="#F4F7FB")
    pestanas.add(pagina_proyecto, text="Proyectos")
    marco_proyecto = tk.LabelFrame(pagina_proyecto, text=" Grados de membresia ",
                                   bg="#F4F7FB", padx=10, pady=8)
    marco_proyecto.pack(fill="x", padx=15, pady=14)
    entradas_proyecto = {}
    crear_entrada(marco_proyecto, 0, "Rentabilidad alta", "0.6", entradas_proyecto)
    crear_entrada(marco_proyecto, 1, "Impacto social alto", "0.2", entradas_proyecto)
    crear_entrada(marco_proyecto, 2, "Riesgo bajo", "0.4", entradas_proyecto)
    crear_entrada(marco_proyecto, 3, "Riesgo alto", "0.7", entradas_proyecto)
    tk.Button(pagina_proyecto, text="Evaluar reglas del proyecto", command=calcular_proyecto,
              bg="#2563EB", fg="white", font=("Arial", 10, "bold")).pack(pady=4)
    texto_proyecto = tk.Text(pagina_proyecto, height=11, width=70, wrap="word", state="disabled")
    texto_proyecto.pack(padx=15, pady=12)

    # Pestana 2: motor de recursos humanos solicitado en el laboratorio.
    pagina_bono = tk.Frame(pestanas, bg="#F4F7FB")
    pestanas.add(pagina_bono, text="Bonos de RR. HH.")
    marco_bono = tk.LabelFrame(pagina_bono, text=" Valores difusos del empleado ",
                               bg="#F4F7FB", padx=10, pady=6)
    marco_bono.pack(fill="x", padx=15, pady=12)
    entradas_bono = {}
    crear_entrada(marco_bono, 0, "Desempeno pobre", "0.10", entradas_bono)
    crear_entrada(marco_bono, 1, "Desempeno promedio", "0.25", entradas_bono)
    crear_entrada(marco_bono, 2, "Desempeno excelente", "0.85", entradas_bono)
    crear_entrada(marco_bono, 3, "Antiguedad corta", "0.30", entradas_bono)
    crear_entrada(marco_bono, 4, "Antiguedad larga", "0.60", entradas_bono)
    tk.Button(pagina_bono, text="Calcular bonos", command=calcular_bono,
              bg="#16803C", fg="white", font=("Arial", 10, "bold")).pack(pady=4)
    texto_bono = tk.Text(pagina_bono, height=10, width=70, wrap="word", state="disabled")
    texto_bono.pack(padx=15, pady=8)
    tk.Button(pagina_bono, text="Ver pregunta teorica de agregacion", command=mostrar_agregacion).pack()
    etiqueta_agregacion = tk.Label(pagina_bono, text="", justify="left", bg="#F4F7FB", fg="#153E75")
    etiqueta_agregacion.pack(pady=7)

    ventana.mainloop()


if __name__ == "__main__":
    crear_interfaz()
