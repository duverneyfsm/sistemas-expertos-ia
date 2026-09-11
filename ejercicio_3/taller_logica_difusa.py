"""Interfaz sencilla para el taller de logica difusa.

Ejecutar con: python taller_logica_difusa.py
No necesita instalar librerias: Tkinter ya viene con Python.
"""

# tk permite crear los elementos visuales de la ventana.
import tkinter as tk
# messagebox muestra mensajes de error cuando el dato escrito no es valido.
from tkinter import messagebox


def membresia_triangular(x, a, b, c):
    """Calcula el grado de pertenencia de x en un triangulo (a, b, c).

    El resultado va de 0 a 1. En el lado izquierdo sube y en el lado
    derecho baja. Esta es la funcion principal de la logica difusa.
    """
    # Si x esta fuera del triangulo, no pertenece al conjunto.
    if x <= a or x >= c:
        return 0.0

    # Si x esta entre a y b, se usa el lado que sube del triangulo.
    if x <= b:
        return (x - a) / (b - a)

    # Si x esta entre b y c, se usa el lado que baja del triangulo.
    return (c - x) / (c - b)


def calcular_temperatura():
    """Lee la temperatura escrita por el usuario y muestra su resultado."""
    try:
        # get lee lo escrito; float lo convierte en un numero decimal.
        temperatura = float(entrada_temperatura.get())
    except ValueError:
        messagebox.showerror("Dato invalido", "Escribe una temperatura numerica.")
        return

    # El taller define Temperatura Agradable con los puntos 18, 22 y 26.
    # Llamamos la funcion con el triangulo definido en la guia: 18, 22 y 26.
    grado = membresia_triangular(temperatura, 18, 22, 26)

    # Se indica la formula aplicada para facilitar la explicacion del taller.
    if temperatura <= 18 or temperatura >= 26:
        formula = "Esta fuera del rango 18 a 26, por eso el grado es 0."
    elif temperatura <= 22:
        formula = f"Formula: ({temperatura:g} - 18) / (22 - 18)"
    else:
        formula = f"Formula: (26 - {temperatura:g}) / (26 - 22)"

    # set cambia el texto que se muestra en la etiqueta de resultado.
    texto_temperatura.set(
        f"Grado de membresia: {grado:.2f} ({grado * 100:.0f}%)\n"
        f"{formula}\n"
        "Este valor indica que tanto pertenece a 'Temperatura agradable'."
    )


def clasificar_conductor(anios):
    """Obtiene los tres grados y la categoria que tenga el mayor valor."""
    # Cada categoria tiene los vertices de su triangulo difuso.
    categorias = {
        "Novato": (0, 0, 5),
        "Intermedio": (2, 5, 8),
        "Experto": (5, 10, 20),
    }

    # Se calcula un grado para cada categoria.
    grados = {
        nombre: membresia_triangular(anios, a, b, c)
        for nombre, (a, b, c) in categorias.items()
    }

    # max busca la clave cuyo grado es mas alto.
    categoria_final = max(grados, key=grados.get)
    return grados, categoria_final


def calcular_conductor():
    """Lee los anos de experiencia y actualiza el resultado de la ventana."""
    try:
        # Leemos los anos escritos y los convertimos a numero.
        anios = float(entrada_anios.get())
        if anios < 0:
            raise ValueError
    except ValueError:
        messagebox.showerror(
            "Dato invalido", "Escribe una cantidad de anos igual o mayor que cero."
        )
        return

    # La funcion entrega todos los grados y la categoria de mayor valor.
    grados, categoria = clasificar_conductor(anios)
    texto_conductor.set(
        f"Conductor con {anios:g} anos de experiencia\n\n"
        f"Novato: {grados['Novato']:.2f} ({grados['Novato'] * 100:.0f}%)\n"
        f"Intermedio: {grados['Intermedio']:.2f} ({grados['Intermedio'] * 100:.0f}%)\n"
        f"Experto: {grados['Experto']:.2f} ({grados['Experto'] * 100:.0f}%)\n\n"
        f"Categoria con mayor grado: {categoria}"
    )


def mostrar_ejemplos():
    """Muestra en pantalla los tres conductores solicitados por la guia."""
    # Esta lista guardara una frase con el resultado de cada ejemplo.
    resultados = []

    # El ciclo for repite el calculo para los valores 3, 6 y 12.
    for anios in [3, 6, 12]:
        grados, categoria = clasificar_conductor(anios)
        resultados.append(
            f"{anios} anos -> Novato: {grados['Novato']:.2f}, "
            f"Intermedio: {grados['Intermedio']:.2f}, "
            f"Experto: {grados['Experto']:.2f}. Resultado: {categoria}."
        )

    # join une los textos de la lista y set los muestra en la ventana.
    texto_conductor.set("EJEMPLOS DEL TALLER\n\n" + "\n\n".join(resultados))


# Se crea la ventana principal de la aplicacion.
ventana = tk.Tk()
ventana.title("Taller de Logica Difusa")
ventana.geometry("620x630")
ventana.resizable(False, False)
ventana.configure(bg="#F4F7FB")

# Label crea el titulo visible para el usuario.
tk.Label(
    ventana,
    text="Taller de Logica Difusa",
    font=("Arial", 18, "bold"),
    bg="#F4F7FB",
    fg="#153E75",
).pack(pady=(18, 4))

tk.Label(
    ventana,
    text="Funcion de membresia triangular y clasificacion de conductores",
    font=("Arial", 10),
    bg="#F4F7FB",
).pack(pady=(0, 12))

# Primer recuadro: ejercicio de temperatura agradable.
# LabelFrame crea un recuadro con titulo para separar este primer ejercicio.
marco_temperatura = tk.LabelFrame(
    ventana,
    text=" 1. Temperatura agradable: triangulo (18, 22, 26) ",
    font=("Arial", 11, "bold"),
    bg="#F4F7FB",
    padx=15,
    pady=12,
)
marco_temperatura.pack(fill="x", padx=22, pady=7)

tk.Label(marco_temperatura, text="Temperatura en C:", bg="#F4F7FB").grid(
    row=0, column=0, sticky="w", padx=(0, 8)
)
# Entry permite que el usuario escriba una temperatura.
entrada_temperatura = tk.Entry(marco_temperatura, width=12)
entrada_temperatura.insert(0, "20")
entrada_temperatura.grid(row=0, column=1, sticky="w")

# Este boton llama a calcular_temperatura al hacer clic.
tk.Button(
    marco_temperatura,
    text="Calcular temperatura",
    command=calcular_temperatura,
    bg="#2563EB",
    fg="white",
    font=("Arial", 10, "bold"),
).grid(row=0, column=2, padx=12)

# StringVar guarda un texto que puede cambiar sin crear de nuevo la etiqueta.
texto_temperatura = tk.StringVar(value="Ingresa una temperatura y presiona Calcular.")
tk.Label(
    marco_temperatura,
    textvariable=texto_temperatura,
    justify="left",
    anchor="w",
    wraplength=540,
    bg="#F4F7FB",
).grid(row=1, column=0, columnspan=3, sticky="w", pady=(12, 0))

# Segundo recuadro: ejercicio de la experiencia de conductores.
# Este segundo recuadro contiene el ejercicio de los conductores.
marco_conductor = tk.LabelFrame(
    ventana,
    text=" 2. Experiencia del conductor ",
    font=("Arial", 11, "bold"),
    bg="#F4F7FB",
    padx=15,
    pady=12,
)
marco_conductor.pack(fill="both", expand=True, padx=22, pady=7)

tk.Label(marco_conductor, text="Anos de experiencia:", bg="#F4F7FB").grid(
    row=0, column=0, sticky="w", padx=(0, 8)
)
# Esta caja recibe los anos de experiencia del conductor.
entrada_anios = tk.Entry(marco_conductor, width=12)
entrada_anios.insert(0, "3")
entrada_anios.grid(row=0, column=1, sticky="w")

# Este boton llama a calcular_conductor con los anos escritos.
tk.Button(
    marco_conductor,
    text="Clasificar conductor",
    command=calcular_conductor,
    bg="#16803C",
    fg="white",
    font=("Arial", 10, "bold"),
).grid(row=0, column=2, padx=12)

# Este boton muestra los tres casos que pide la guia del taller.
tk.Button(
    marco_conductor,
    text="Ver ejemplos: 3, 6 y 12 anos",
    command=mostrar_ejemplos,
).grid(row=1, column=0, columnspan=3, sticky="w", pady=(12, 8))

# Esta variable guardara el resultado de la clasificacion del conductor.
texto_conductor = tk.StringVar(value="Ingresa los anos y presiona Clasificar conductor.")
tk.Label(
    marco_conductor,
    textvariable=texto_conductor,
    justify="left",
    anchor="nw",
    wraplength=540,
    bg="#F4F7FB",
).grid(row=2, column=0, columnspan=3, sticky="nw")

# mainloop mantiene la ventana abierta y esperando clics del usuario.
ventana.mainloop()
