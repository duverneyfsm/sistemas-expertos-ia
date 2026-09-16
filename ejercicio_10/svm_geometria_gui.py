"""Taller 10: geometria de SVM, margen y kernels.

Ejecutar con:
    py -3.12 svm_geometria_gui.py

Instalar una sola vez las librerias necesarias:
    py -3.12 -m pip install numpy matplotlib scikit-learn

Para explicarlo: una SVM dibuja la frontera que deja el mayor margen posible
entre dos clases. Los puntos que quedan mas cerca de esa frontera se llaman
vectores de soporte. El kernel RBF permite separar patrones curvos.
"""

# Este import me ayuda a crear la ventana, los botones, las tablas y las pestanas.
import tkinter as tk
from tkinter import messagebox, ttk

# Este import me ayuda a guardar las coordenadas X, Y y las etiquetas de cada clase.
import numpy as np
# Este import me ayuda a dibujar la frontera, el margen y los vectores de soporte.
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
# Esta clase me ayuda a usar una Support Vector Machine ya implementada en scikit-learn.
from sklearn.svm import SVC


def crear_datos_lineales():
    """Crea los seis puntos del taller: tres de Clase A y tres de Clase B.

    Clase A = 0 y Clase B = 1. Estan ubicadas de forma que una recta puede
    separarlas. Estos datos sirven para estudiar el margen maximo.
    """
    # Esta tabla me ayuda a guardar las coordenadas (x, y) de los seis puntos historicos.
    x = np.array([[2, 2], [3, 3], [4, 2], [6, 6], [7, 8], [8, 7]], dtype=float)
    # Esta lista me ayuda a relacionar cada fila de X con su clase, en el mismo orden.
    y = np.array([0, 0, 0, 1, 1, 1])
    return x, y


def crear_datos_no_lineales():
    """Agrega el punto (5, 5) de Clase A pedido por el laboratorio.

    Ese punto se acerca a los datos de Clase B y hace que la recta lineal se
    vea forzada. Esto permite comparar el kernel lineal contra el kernel RBF.
    """
    x, y = crear_datos_lineales()
    # Este codigo me ayuda a agregar el punto nuevo y su etiqueta de Clase A.
    return np.vstack([x, [5, 5]]), np.append(y, 0)


def nombre_clase(etiqueta):
    """Convierte el 0 o 1 que usa la SVM en un nombre entendible."""
    return "Clase A (circulo)" if int(etiqueta) == 0 else "Clase B (equis)"


class VentanaSVM:
    """Reune la practica, el grafico y la teoria del ejercicio 10."""

    def __init__(self, ventana):
        # Esta variable me ayuda a configurar el titulo, el tamano y el color de mi ventana.
        self.ventana = ventana
        self.ventana.title("Taller 10 - SVM: Margen, vectores y kernels")
        self.ventana.geometry("1080x760")
        self.ventana.minsize(900, 650)
        self.color_fondo = "#F4F7FB"
        self.ventana.configure(bg=self.color_fondo)

        # Estas variables me ayudan a recordar las opciones que elijo en la interfaz.
        self.tipo_datos = tk.StringVar(value="Lineales: seis puntos del taller")
        self.kernel = tk.StringVar(value="lineal")
        self.valor_c = tk.StringVar(value="1.0")

        # Este Notebook me ayuda a separar la practica, la comparacion y la teoria en pestanas.
        self.pestanas = ttk.Notebook(ventana)
        self.pestanas.pack(fill="both", expand=True, padx=16, pady=16)

        self.crear_pestana_geometria()
        self.crear_pestana_comparacion()
        self.crear_pestana_teoria()
        # Esta llamada me ayuda a mostrar un caso inicial apenas abro la aplicacion.
        self.actualizar_grafico()

    def obtener_datos(self):
        """Devuelve el dataset que el estudiante selecciono en la interfaz."""
        if self.tipo_datos.get().startswith("No lineales"):
            return crear_datos_no_lineales()
        return crear_datos_lineales()

    def entrenar_modelo(self, x, y, kernel=None, valor_c=None):
        """Entrena una SVM con el kernel y C seleccionados.

        C controla la tolerancia al error: un C bajo permite mas margen y suele
        generalizar mejor; un C alto intenta corregir mas los datos de entrenamiento.
        """
        kernel_elegido = kernel or self.kernel.get()
        # Esta equivalencia me ayuda a mostrar "lineal" en espanol, pero enviar
        # "linear" a scikit-learn, que es el nombre tecnico que la libreria acepta.
        kernel_final = "linear" if kernel_elegido == "lineal" else kernel_elegido
        c_final = self.leer_valor_c() if valor_c is None else float(valor_c)
        # Esta instruccion me ayuda a entrenar la SVM: aprende la frontera y guarda sus vectores de soporte.
        modelo = SVC(kernel=kernel_final, C=c_final, gamma="scale")
        modelo.fit(x, y)
        return modelo

    def leer_valor_c(self):
        """Lee y valida C antes de entrenar el modelo.

        Acepto punto o coma decimal para que pueda escribir 0.1 o 0,1 sin
        generar un error por la configuracion regional del computador.
        """
        try:
            c_final = float(self.valor_c.get().strip().replace(",", "."))
        except ValueError as error:
            raise ValueError("C no es un numero") from error
        if c_final not in (0.1, 1.0, 10.0):
            raise ValueError("C no es una opcion del taller")
        return c_final

    def crear_pestana_geometria(self):
        """Crea los controles y el grafico principal del margen SVM."""
        pagina = tk.Frame(self.pestanas, bg=self.color_fondo)
        self.pestanas.add(pagina, text="Margen y vectores")

        tk.Label(
            pagina, text="SVM: busca la frontera con el margen de seguridad mas grande",
            font=("Arial", 16, "bold"), bg=self.color_fondo, fg="#153E75",
        ).pack(pady=(15, 3))
        tk.Label(
            pagina,
            text="Los puntos rodeados son los vectores de soporte: ellos definen la posicion de la frontera.",
            font=("Arial", 10), bg=self.color_fondo, fg="#475569",
        ).pack(pady=(0, 8))

        # Este marco me ayuda a mantener juntas las opciones que cambian el modelo y el dibujo.
        controles = tk.LabelFrame(pagina, text=" Opciones del experimento ", bg=self.color_fondo, padx=8, pady=8)
        controles.pack(fill="x", padx=18, pady=5)

        tk.Label(controles, text="Datos:", bg=self.color_fondo).grid(row=0, column=0, padx=(6, 3), pady=4)
        selector_datos = ttk.Combobox(
            controles, textvariable=self.tipo_datos, state="readonly", width=31,
            values=("Lineales: seis puntos del taller", "No lineales: agrega A en (5, 5)"),
        )
        selector_datos.grid(row=0, column=1, padx=(0, 14), pady=4)

        tk.Label(controles, text="Kernel:", bg=self.color_fondo).grid(row=0, column=2, padx=(4, 3), pady=4)
        ttk.Combobox(
            controles, textvariable=self.kernel, state="readonly", width=10,
            values=("lineal", "rbf"),
        ).grid(row=0, column=3, padx=(0, 14), pady=4)

        tk.Label(controles, text="C:", bg=self.color_fondo).grid(row=0, column=4, padx=(4, 3), pady=4)
        ttk.Combobox(
            controles, textvariable=self.valor_c, state="readonly", width=7,
            values=("0.1", "1.0", "10.0"),
        ).grid(row=0, column=5, padx=(0, 14), pady=4)

        # Este boton me ayuda a entrenar otra vez y ver como cambia la frontera.
        tk.Button(
            controles, text="Entrenar y dibujar", command=self.actualizar_grafico,
            bg="#2563EB", fg="white", font=("Arial", 10, "bold"), padx=10,
        ).grid(row=0, column=6, padx=5, pady=4)

        # Esta figura me ayuda a mostrar el plano cartesiano donde se ve la SVM.
        self.figura = Figure(figsize=(8.6, 4.7), dpi=100)
        self.ejes = self.figura.add_subplot(111)
        self.lienzo = FigureCanvasTkAgg(self.figura, master=pagina)
        self.lienzo.get_tk_widget().pack(fill="both", expand=True, padx=18, pady=(4, 2))

        # Esta etiqueta me ayuda a traducir el resultado matematico a una explicacion corta.
        self.resumen = tk.Label(
            pagina, text="", justify="left", anchor="w", wraplength=980,
            bg="#EAF2FF", fg="#153E75", padx=12, pady=8, font=("Arial", 10),
        )
        self.resumen.pack(fill="x", padx=18, pady=(3, 14))

    def dibujar_frontera(self, modelo, x, y):
        """Dibuja puntos, frontera de decision, margenes y vectores de soporte."""
        self.ejes.clear()
        # Esta malla me ayuda a colorear la region que la SVM asigna a cada clase.
        limite_min, limite_max = 0.5, 9.5
        coordenadas = np.linspace(limite_min, limite_max, 260)
        cuadricula_x, cuadricula_y = np.meshgrid(coordenadas, coordenadas)
        puntos_malla = np.c_[cuadricula_x.ravel(), cuadricula_y.ravel()]
        decision = modelo.decision_function(puntos_malla).reshape(cuadricula_x.shape)

        # Este contourf me ayuda a pintar suavemente las dos regiones separadas por la SVM.
        self.ejes.contourf(cuadricula_x, cuadricula_y, decision, levels=[-99, 0, 99],
                           colors=["#FEE2E2", "#DBEAFE"], alpha=0.55)
        # Estas lineas me ayudan a ver el hiperplano central y los limites del margen.
        self.ejes.contour(cuadricula_x, cuadricula_y, decision, levels=[-1, 0, 1],
                          colors=["#64748B", "#153E75", "#64748B"],
                          linestyles=["--", "-", "--"], linewidths=[1.1, 2.2, 1.1])

        # Estos puntos me ayudan a diferenciar visualmente las clases, como pide el taller.
        self.ejes.scatter(x[y == 0, 0], x[y == 0, 1], c="#DC2626", marker="o", s=75,
                          label="Clase A", edgecolors="white", linewidths=0.8)
        self.ejes.scatter(x[y == 1, 0], x[y == 1, 1], c="#2563EB", marker="X", s=85,
                          label="Clase B", edgecolors="white", linewidths=0.8)
        # Estos circulos me ayudan a reconocer los puntos que sostienen la frontera.
        self.ejes.scatter(modelo.support_vectors_[:, 0], modelo.support_vectors_[:, 1],
                          s=250, facecolors="none", edgecolors="#F59E0B", linewidths=2.2,
                          label="Vector de soporte")

        self.ejes.set_title("Frontera de decision y margen de la SVM", fontweight="bold", color="#153E75")
        self.ejes.set_xlabel("Coordenada X")
        self.ejes.set_ylabel("Coordenada Y")
        self.ejes.set_xlim(limite_min, limite_max)
        self.ejes.set_ylim(limite_min, limite_max)
        self.ejes.grid(alpha=0.25)
        self.ejes.legend(loc="upper left")
        self.figura.tight_layout()
        self.lienzo.draw()

    def actualizar_grafico(self):
        """Lee las opciones, entrena la SVM y actualiza el resultado visual."""
        try:
            x, y = self.obtener_datos()
            modelo = self.entrenar_modelo(x, y)
        except ValueError as error:
            messagebox.showerror("Valor de C invalido", "Selecciona C = 0.1, 1.0 o 10.0.")
            return
        except Exception as error:
            # Este mensaje me ayuda a diferenciar un problema del modelo de un valor de C invalido.
            messagebox.showerror("No fue posible entrenar la SVM", str(error))
            return

        self.dibujar_frontera(modelo, x, y)
        exactitud = modelo.score(x, y) * 100
        texto_kernel = "una recta" if self.kernel.get() == "lineal" else "una frontera curva (RBF)"
        self.resumen.config(
            text=(
                f"Kernel {self.kernel.get().upper()} con C = {self.valor_c.get()}: la SVM uso "
                f"{len(modelo.support_vectors_)} vectores de soporte y obtuvo {exactitud:.0f}% en estos datos.\n"
                f"El modelo esta intentando separar las clases con {texto_kernel}. "
                "C bajo prioriza un margen mas amplio; C alto castiga mas los errores de entrenamiento."
            )
        )
        self.actualizar_comparacion()

    def crear_pestana_comparacion(self):
        """Crea una practica para predecir un punto y comparar los kernels."""
        pagina = tk.Frame(self.pestanas, bg=self.color_fondo)
        self.pestanas.add(pagina, text="Lineal vs. RBF")

        tk.Label(pagina, text="Comparacion de kernels", font=("Arial", 16, "bold"),
                 bg=self.color_fondo, fg="#153E75").pack(pady=(18, 3))
        tk.Label(
            pagina,
            text="Prueba un punto nuevo. En datos no lineales, RBF puede adaptarse mejor que una recta.",
            bg=self.color_fondo, fg="#475569",
        ).pack(pady=(0, 12))

        marco = tk.LabelFrame(pagina, text=" Punto nuevo a clasificar ", bg=self.color_fondo, padx=10, pady=8)
        marco.pack(fill="x", padx=24, pady=5)
        tk.Label(marco, text="Coordenada X:", bg=self.color_fondo).grid(row=0, column=0, padx=(8, 3))
        self.entrada_x = tk.Entry(marco, width=10)
        self.entrada_x.insert(0, "5")
        self.entrada_x.grid(row=0, column=1, padx=(0, 14))
        tk.Label(marco, text="Coordenada Y:", bg=self.color_fondo).grid(row=0, column=2, padx=(3, 3))
        self.entrada_y = tk.Entry(marco, width=10)
        self.entrada_y.insert(0, "4")
        self.entrada_y.grid(row=0, column=3, padx=(0, 14))
        tk.Button(marco, text="Predecir con ambos", command=self.predecir_punto,
                  bg="#2563EB", fg="white", font=("Arial", 10, "bold")).grid(row=0, column=4, padx=8)

        # Esta tabla me ayuda a comparar la exactitud y los vectores de soporte de ambos modelos.
        self.tabla_comparacion = ttk.Treeview(
            pagina, columns=("kernel", "exactitud", "soportes", "frontera"), show="headings", height=3,
        )
        for columna, titulo, ancho in (
            ("kernel", "Kernel", 150), ("exactitud", "Exactitud en entrenamiento", 210),
            ("soportes", "Vectores de soporte", 190), ("frontera", "Tipo de frontera", 250),
        ):
            self.tabla_comparacion.heading(columna, text=titulo)
            self.tabla_comparacion.column(columna, width=ancho, anchor="center")
        self.tabla_comparacion.pack(padx=30, pady=18)

        self.resultado_prediccion = tk.Label(
            pagina, text="Escribe un punto y pulsa el boton para comparar las dos predicciones.",
            bg="#EAF2FF", fg="#153E75", justify="left", anchor="w", wraplength=920, padx=12, pady=10,
        )
        self.resultado_prediccion.pack(fill="x", padx=30, pady=5)

    def actualizar_comparacion(self):
        """Entrena lineal y RBF sobre los mismos datos y llena la tabla."""
        if not hasattr(self, "tabla_comparacion"):
            return
        x, y = self.obtener_datos()
        for fila in self.tabla_comparacion.get_children():
            self.tabla_comparacion.delete(fila)
        for kernel in ("lineal", "rbf"):
            modelo = self.entrenar_modelo(x, y, kernel=kernel)
            frontera = "Recta" if kernel == "lineal" else "Curva mediante Kernel Trick"
            self.tabla_comparacion.insert(
                "", "end", values=(kernel.upper(), f"{modelo.score(x, y) * 100:.0f}%",
                                  len(modelo.support_vectors_), frontera),
            )

    def predecir_punto(self):
        """Clasifica el punto escrito por el usuario con SVM lineal y RBF."""
        try:
            punto = np.array([[float(self.entrada_x.get()), float(self.entrada_y.get())]])
        except ValueError:
            messagebox.showerror("Dato invalido", "Escribe dos numeros para las coordenadas X y Y.")
            return

        x, y = self.obtener_datos()
        # Este paso me ayuda a comparar de forma justa: uso los mismos datos y el mismo C.
        lineal = self.entrenar_modelo(x, y, kernel="lineal")
        rbf = self.entrenar_modelo(x, y, kernel="rbf")
        clase_lineal = nombre_clase(lineal.predict(punto)[0])
        clase_rbf = nombre_clase(rbf.predict(punto)[0])
        self.resultado_prediccion.config(
            text=(
                f"Punto evaluado: ({punto[0, 0]:g}, {punto[0, 1]:g})\n\n"
                f"SVM lineal predice: {clase_lineal}.\n"
                f"SVM RBF predice: {clase_rbf}.\n\n"
                "Si los datos forman grupos curvos o una clase rodea a otra, RBF puede construir una "
                "frontera mas adecuada al proyectar el problema a un espacio de mayor dimension."
            )
        )

    def crear_pestana_teoria(self):
        """Resume las ideas solicitadas en las dos guias de SVM."""
        pagina = tk.Frame(self.pestanas, bg=self.color_fondo)
        self.pestanas.add(pagina, text="Explicacion")
        tk.Label(pagina, text="Como explicar este ejercicio", font=("Arial", 16, "bold"),
                 bg=self.color_fondo, fg="#153E75").pack(pady=(20, 8))

        respuesta = (
            "1. Hiperplano: en dos dimensiones es la linea central que separa Clase A y Clase B. "
            "Su forma general es W·X + b = 0.\n\n"
            "2. Margen: son las dos lineas punteadas. La SVM elige la frontera que deja la mayor "
            "distancia de seguridad posible entre las clases.\n\n"
            "3. Vectores de soporte: son los puntos mas cercanos al margen. Si se agrega un punto "
            "lejano como (1, 1) de Clase A, normalmente no cambia la frontera porque no es un vector de soporte.\n\n"
            "4. Kernel lineal: funciona rapido cuando una recta puede separar los datos. Kernel RBF: "
            "sirve cuando los grupos tienen una forma curva o una clase rodea a la otra; aplica el Kernel Trick.\n\n"
            "5. Parametro C: C bajo acepta algunos errores para lograr una frontera mas general; C alto "
            "busca pocos errores de entrenamiento y puede sobreajustarse al ruido."
        )
        tk.Label(pagina, text=respuesta, justify="left", anchor="w", wraplength=920,
                 bg=self.color_fondo, fg="#334155", font=("Arial", 12)).pack(padx=42, pady=12, fill="x")


if __name__ == "__main__":
    # Este codigo me ayuda a crear la ventana solo cuando ejecuto este archivo directamente.
    raiz = tk.Tk()
    VentanaSVM(raiz)
    # Este mainloop me ayuda a mantener la ventana abierta mientras uso los botones.
    raiz.mainloop()
