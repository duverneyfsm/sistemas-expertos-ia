"""Taller 9: KNN con 10 clientes y tres dimensiones.

Ejecutar con:
    py -3.12 knn_clasificador_universal_gui.py

Instalar una sola vez las librerias requeridas:
    py -3.12 -m pip install numpy scikit-learn

Para explicarlo: KNN no crea una formula complicada; compara un cliente nuevo
con clientes historicos, ordena las distancias y deja que los K vecinos voten.
"""

# tkinter crea la ventana; messagebox muestra mensajes si un dato es invalido.
import tkinter as tk
from tkinter import messagebox, ttk

# NumPy almacena la tabla de datos y scikit-learn implementa KNN.
import numpy as np
from sklearn.neighbors import KNeighborsClassifier


def crear_dataset():
    """Crea los 10 clientes solicitados: edad, salario en miles e hijos.

    Cada fila es un cliente historico. La etiqueta 0 significa NO COMPRA y
    la etiqueta 1 significa COMPRA. La tercera columna cumple la ampliacion
    de dimensionalidad pedida en el taller.
    """
    # X contiene las tres caracteristicas que KNN usara para medir cercania.
    x_entrenamiento = np.array([
        [20, 30, 0], [22, 35, 1], [25, 38, 0], [28, 42, 1], [32, 45, 1],
        [35, 50, 2], [40, 55, 2], [45, 60, 3], [50, 65, 2], [55, 70, 4],
    ], dtype=float)
    # Y tiene una respuesta por cada cliente de X, en el mismo orden.
    y_entrenamiento = np.array([0, 0, 0, 1, 1, 1, 1, 1, 0, 0])
    return x_entrenamiento, y_entrenamiento


def distancia_euclidiana(punto_a, punto_b):
    """Calcula la raiz de la suma de las diferencias al cuadrado.

    Con tres columnas la formula es:
    raiz((edad_a-edad_b)^2 + (salario_a-salario_b)^2 + (hijos_a-hijos_b)^2).
    """
    # Restamos las coordenadas, elevamos al cuadrado, sumamos y sacamos raiz.
    return float(np.sqrt(np.sum((punto_a - punto_b) ** 2)))


class VentanaKNN:
    """Organiza la interfaz y las acciones de los botones del taller."""

    def __init__(self, ventana):
        # Guardamos la ventana principal para configurar su titulo y apariencia.
        self.ventana = ventana
        self.ventana.title("Taller 9 - KNN: Clasificador Universal")
        self.ventana.geometry("860x670")
        self.ventana.minsize(760, 580)
        self.ventana.configure(bg="#F4F7FB")

        # Cargamos una vez los diez ejemplos que representaran la memoria de KNN.
        self.x_entrenamiento, self.y_entrenamiento = crear_dataset()
        # Las pestanas separan la practica, las distancias y la respuesta teorica.
        self.pestanas = ttk.Notebook(ventana)
        self.pestanas.pack(fill="both", expand=True, padx=18, pady=18)

        self.crear_pestana_practica()
        self.crear_pestana_distancias()
        self.crear_pestana_teoria()

    def crear_pestana_practica(self):
        """Crea controles para probar K=1 y K=5 con un cliente nuevo."""
        pagina = tk.Frame(self.pestanas, bg="#F4F7FB")
        self.pestanas.add(pagina, text="Practica KNN")

        tk.Label(
            pagina, text="KNN: clasifica segun los vecinos mas cercanos",
            font=("Arial", 16, "bold"), bg="#F4F7FB", fg="#153E75",
        ).pack(pady=(18, 4))
        tk.Label(
            pagina,
            text="Dataset ampliado: 10 clientes y tres variables (edad, salario e hijos).",
            bg="#F4F7FB", fg="#475569",
        ).pack(pady=(0, 12))

        # Mostramos el dataset para evidenciar las 10 filas y sus etiquetas.
        tabla = ttk.Treeview(pagina, columns=("cliente", "edad", "salario", "hijos", "clase"), show="headings", height=10)
        for columna, texto, ancho in (
            ("cliente", "Cliente", 90), ("edad", "Edad", 90),
            ("salario", "Salario (miles)", 140), ("hijos", "Hijos", 90),
            ("clase", "Clase", 150),
        ):
            tabla.heading(columna, text=texto)
            tabla.column(columna, width=ancho, anchor="center")
        for indice, (fila, etiqueta) in enumerate(zip(self.x_entrenamiento, self.y_entrenamiento), start=1):
            clase = "COMPRA" if etiqueta == 1 else "NO COMPRA"
            tabla.insert("", "end", values=(f"Cliente {indice}", int(fila[0]), int(fila[1]), int(fila[2]), clase))
        tabla.pack(padx=22, pady=4, fill="x")

        marco = tk.LabelFrame(pagina, text=" Nuevo cliente a clasificar ", bg="#F4F7FB", padx=10, pady=8)
        marco.pack(padx=22, pady=13, fill="x")
        self.entradas = {}
        # Cada caja recibe una coordenada del nuevo punto tridimensional.
        for columna, (nombre, valor) in enumerate((("Edad", "30"), ("Salario (miles)", "40"), ("Numero de hijos", "1"))):
            tk.Label(marco, text=nombre + ":", bg="#F4F7FB").grid(row=0, column=columna * 2, padx=(8, 2), pady=5)
            entrada = tk.Entry(marco, width=10)
            entrada.insert(0, valor)
            entrada.grid(row=0, column=columna * 2 + 1, padx=(0, 10), pady=5)
            self.entradas[nombre] = entrada

        # Este boton entrena una vez con K=1 y otra con K=5 para comparar decisiones.
        tk.Button(marco, text="Comparar K = 1 y K = 5", command=self.comparar_k,
                  bg="#2563EB", fg="white", font=("Arial", 10, "bold")).grid(row=0, column=6, padx=10)

        # La etiqueta se actualiza con las dos predicciones y una explicacion corta.
        self.resultado = tk.Label(pagina, text="Pulsa el boton para clasificar el punto nuevo.",
                                  justify="left", bg="#F4F7FB", fg="#153E75", font=("Arial", 11))
        self.resultado.pack(padx=24, pady=4, anchor="w")

    def leer_punto_nuevo(self):
        """Convierte las tres cajas de texto en un vector de numeros."""
        try:
            # float permite probar edades o salarios con decimales si se desea.
            punto = np.array([
                float(self.entradas["Edad"].get()),
                float(self.entradas["Salario (miles)"].get()),
                float(self.entradas["Numero de hijos"].get()),
            ])
            # No existen edades, salarios o cantidades de hijos negativos.
            if (punto < 0).any():
                raise ValueError
            return punto
        except ValueError:
            messagebox.showerror("Dato invalido", "Escribe tres numeros mayores o iguales a cero.")
            return None

    @staticmethod
    def texto_clase(etiqueta):
        """Traduce la etiqueta numerica del modelo a lenguaje humano."""
        return "COMPRA" if int(etiqueta) == 1 else "NO COMPRA"

    def comparar_k(self):
        """Entrena KNN dos veces y compara como cambia la votacion."""
        punto_nuevo = self.leer_punto_nuevo()
        if punto_nuevo is None:
            return

        predicciones = []
        for valor_k in (1, 5):
            # n_neighbors define cuantos vecinos participan en la votacion.
            modelo_knn = KNeighborsClassifier(n_neighbors=valor_k)
            # fit no calcula una formula: KNN guarda los ejemplos historicos.
            modelo_knn.fit(self.x_entrenamiento, self.y_entrenamiento)
            # predict devuelve la clase ganadora para el punto nuevo.
            etiqueta = modelo_knn.predict([punto_nuevo])[0]
            # predict_proba muestra el porcentaje de votos por cada clase.
            probabilidad = modelo_knn.predict_proba([punto_nuevo])[0][int(etiqueta)] * 100
            predicciones.append((valor_k, etiqueta, probabilidad))

        texto = (
            f"Punto nuevo: {tuple(punto_nuevo)}\n\n"
            f"Con K = 1: {self.texto_clase(predicciones[0][1])} "
            f"({predicciones[0][2]:.0f}% de voto)\n"
            f"Con K = 5: {self.texto_clase(predicciones[1][1])} "
            f"({predicciones[1][2]:.0f}% de voto)\n\n"
            "K=1 es mas sensible al vecino inmediato; K=5 toma una decision mas estable por mayoria."
        )
        self.resultado.config(text=texto)
        # Actualizamos tambien la pestana de distancias con el mismo punto.
        self.mostrar_distancias(punto_nuevo)

    def crear_pestana_distancias(self):
        """Crea el espacio para explicar la distancia euclidiana paso a paso."""
        pagina = tk.Frame(self.pestanas, bg="#F4F7FB")
        self.pestanas.add(pagina, text="Distancias")
        tk.Label(pagina, text="Distancia Euclidiana en tres dimensiones", font=("Arial", 16, "bold"),
                 bg="#F4F7FB", fg="#153E75").pack(pady=(18, 5))
        tk.Label(pagina, text="d(A,B) = raiz((x2-x1)^2 + (y2-y1)^2 + (z2-z1)^2)",
                 bg="#F4F7FB", fg="#475569", font=("Arial", 11, "italic")).pack(pady=(0, 10))
        # Text permite mostrar todas las operaciones sin recortar lineas largas.
        self.texto_distancias = tk.Text(pagina, height=23, width=98, wrap="word", state="disabled")
        self.texto_distancias.pack(padx=20, pady=5, fill="both", expand=True)
        self.mostrar_distancias(np.array([30.0, 40.0, 1.0]))

    def mostrar_distancias(self, punto_nuevo):
        """Ordena los diez clientes por cercania al punto indicado."""
        filas = []
        for indice, (cliente, etiqueta) in enumerate(zip(self.x_entrenamiento, self.y_entrenamiento), start=1):
            # Aplicamos la formula de Euclides entre el cliente nuevo y cada historial.
            distancia = distancia_euclidiana(punto_nuevo, cliente)
            filas.append((distancia, indice, cliente, etiqueta))
        filas.sort(key=lambda fila: fila[0])

        self.texto_distancias.config(state="normal")
        self.texto_distancias.delete("1.0", tk.END)
        self.texto_distancias.insert(tk.END, f"Punto evaluado: {tuple(punto_nuevo)}\n\n")
        self.texto_distancias.insert(tk.END, "Vecinos ordenados desde el mas cercano:\n\n")
        for posicion, (distancia, indice, cliente, etiqueta) in enumerate(filas, start=1):
            clase = self.texto_clase(etiqueta)
            self.texto_distancias.insert(
                tk.END,
                f"{posicion}. Cliente {indice}: {tuple(cliente)} | distancia = {distancia:.2f} | {clase}\n",
            )
        self.texto_distancias.insert(
            tk.END,
            "\nLos primeros 1 o 5 registros de esta lista son los que usan K=1 y K=5 para votar.",
        )
        self.texto_distancias.config(state="disabled")

    def crear_pestana_teoria(self):
        """Expone la respuesta escrita a la pregunta de analisis del taller."""
        pagina = tk.Frame(self.pestanas, bg="#F4F7FB")
        self.pestanas.add(pagina, text="Pregunta 5")
        tk.Label(pagina, text="Respuesta: Maldicion de la dimensionalidad", font=("Arial", 16, "bold"),
                 bg="#F4F7FB", fg="#153E75").pack(pady=(20, 8))
        respuesta = (
            "Si se usan 1.000 columnas, la distancia euclidiana sigue calculandose, pero pierde poder para "
            "distinguir vecinos: al sumar muchas diferencias, las distancias entre puntos tienden a parecerse.\n\n"
            "Consecuencia: el vecino mas cercano ya no es mucho mas cercano que los demas, por lo que la "
            "votacion de KNN es menos confiable y requiere mas datos y mas calculos.\n\n"
            "Como solucion se pueden normalizar las variables, seleccionar solo las caracteristicas utiles y "
            "reducir dimensiones con tecnicas como PCA antes de aplicar KNN."
        )
        tk.Label(pagina, text=respuesta, justify="left", wraplength=730, bg="#F4F7FB", fg="#334155",
                 font=("Arial", 12)).pack(padx=35, pady=12, anchor="w")


if __name__ == "__main__":
    # Creamos la ventana solo cuando este archivo se ejecuta directamente.
    raiz = tk.Tk()
    VentanaKNN(raiz)
    # mainloop mantiene activa la interfaz y espera las acciones del estudiante.
    raiz.mainloop()
