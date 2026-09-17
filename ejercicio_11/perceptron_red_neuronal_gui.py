"""Taller 11: perceptron y neurona artificial construidos desde cero.

Ejecutar con:
    py -3.12 perceptron_red_neuronal_gui.py

Instalar una sola vez la libreria requerida:
    py -3.12 -m pip install numpy

Para explicarlo: el perceptron recibe entradas X, las multiplica por pesos W,
agrega un sesgo b y usa una funcion escalon. Si Z = X.W + b es mayor o igual a
cero, la neurona produce 1; de lo contrario produce 0.
"""

# Este import me ayuda a crear la ventana, botones, cajas y pestañas.
import tkinter as tk
from tkinter import messagebox, ttk

# Este import me ayuda a realizar el producto punto entre entradas y pesos.
import numpy as np


def funcion_escalon(valor_z: float) -> int:
    """Convierte la suma ponderada en una respuesta binaria 0 o 1."""
    # Esta condicion me ayuda a representar la activacion de la neurona.
    return 1 if valor_z >= 0 else 0


def perceptron(entradas: np.ndarray, pesos: np.ndarray, sesgo: float) -> tuple[float, int]:
    """Calcula Z = X.W + b y luego aplica la funcion escalon.

    Esta funcion no usa una libreria de IA: permite ver las operaciones basicas
    de una neurona artificial con algebra matricial y una condicion.
    """
    # Este producto punto me ayuda a multiplicar cada entrada por su importancia.
    valor_z = float(np.dot(entradas, pesos) + sesgo)
    # Esta salida me ayuda a decidir si la neurona se activa con 1 o queda en 0.
    salida = funcion_escalon(valor_z)
    return valor_z, salida


class VentanaPerceptron:
    """Organiza los tres ejercicios visuales de la sesion 11."""

    def __init__(self, ventana: tk.Tk) -> None:
        # Esta variable me ayuda a configurar la ventana principal de mi taller.
        self.ventana = ventana
        self.ventana.title("Taller 11 - Red neuronal: Perceptron")
        self.ventana.geometry("930x680")
        self.ventana.minsize(800, 580)
        self.color_fondo = "#F4F7FB"
        self.ventana.configure(bg=self.color_fondo)

        # Estas pestañas me ayudan a separar el calculo, las compuertas y la teoria.
        self.pestanas = ttk.Notebook(ventana)
        self.pestanas.pack(fill="both", expand=True, padx=18, pady=18)

        self.crear_pestana_credito()
        self.crear_pestana_compuertas()
        self.crear_pestana_teoria()

    @staticmethod
    def leer_numero(caja: tk.Entry, nombre: str) -> float:
        """Lee un numero y acepta coma o punto decimal."""
        try:
            # Este reemplazo me ayuda a aceptar valores como 0,8 o 0.8.
            return float(caja.get().strip().replace(",", "."))
        except ValueError as error:
            raise ValueError(f"{nombre} debe ser un numero.") from error

    def crear_pestana_credito(self) -> None:
        """Crea el ejercicio analitico de aprobacion de credito de la guia."""
        pagina = tk.Frame(self.pestanas, bg=self.color_fondo)
        self.pestanas.add(pagina, text="Credito: Forward")

        tk.Label(pagina, text="Perceptron para aprobar un credito", font=("Arial", 16, "bold"),
                 bg=self.color_fondo, fg="#153E75").pack(pady=(18, 4))
        tk.Label(
            pagina,
            text="La neurona calcula Z = (X1 · W1) + (X2 · W2) + b y luego decide si se activa.",
            bg=self.color_fondo, fg="#475569",
        ).pack(pady=(0, 12))

        marco = tk.LabelFrame(pagina, text=" Datos de la neurona ", bg=self.color_fondo, padx=12, pady=10)
        marco.pack(fill="x", padx=35, pady=6)

        # Estas entradas me ayudan a probar valores diferentes a los de la guia.
        campos = (
            ("Ingresos X1", "50"), ("Deudas X2", "20"),
            ("Peso W1", "0.8"), ("Peso W2", "-0.5"), ("Sesgo b", "-10"),
        )
        self.cajas_credito: dict[str, tk.Entry] = {}
        for columna, (nombre, valor) in enumerate(campos):
            tk.Label(marco, text=nombre + ":", bg=self.color_fondo).grid(
                row=0, column=columna * 2, padx=(5, 2), pady=5,
            )
            caja = tk.Entry(marco, width=10)
            caja.insert(0, valor)
            caja.grid(row=0, column=columna * 2 + 1, padx=(0, 8), pady=5)
            self.cajas_credito[nombre] = caja

        # Este boton me ayuda a ejecutar la propagacion hacia adelante del perceptron.
        tk.Button(marco, text="Calcular disparo", command=self.calcular_credito,
                  bg="#2563EB", fg="white", font=("Arial", 10, "bold")).grid(
            row=1, column=0, columnspan=10, pady=(10, 2),
        )

        # Esta caja me ayuda a explicar cada multiplicacion y la salida final.
        self.resultado_credito = tk.Text(pagina, height=14, wrap="word", state="disabled",
                                         bg="#EEF6FF", fg="#153E75", font=("Consolas", 10))
        self.resultado_credito.pack(fill="both", expand=True, padx=35, pady=(12, 20))
        self.calcular_credito()

    def calcular_credito(self) -> None:
        """Resuelve el ejemplo de credito y muestra la formula paso a paso."""
        try:
            ingresos = self.leer_numero(self.cajas_credito["Ingresos X1"], "Ingresos X1")
            deudas = self.leer_numero(self.cajas_credito["Deudas X2"], "Deudas X2")
            peso_ingresos = self.leer_numero(self.cajas_credito["Peso W1"], "Peso W1")
            peso_deudas = self.leer_numero(self.cajas_credito["Peso W2"], "Peso W2")
            sesgo = self.leer_numero(self.cajas_credito["Sesgo b"], "Sesgo b")
        except ValueError as error:
            messagebox.showerror("Dato invalido", str(error))
            return

        entradas = np.array([ingresos, deudas])
        pesos = np.array([peso_ingresos, peso_deudas])
        valor_z, salida = perceptron(entradas, pesos, sesgo)
        decision = "APROBAR (salida 1)" if salida else "RECHAZAR (salida 0)"
        explicacion_peso_deuda = (
            "El peso W2 es negativo: a mayor deuda, menor es la suma Z y menor la posibilidad de aprobar."
            if peso_deudas < 0 else
            "El peso W2 es positivo: en este ejemplo las deudas aumentan la suma Z."
        )
        texto = (
            "PROPAGACION HACIA ADELANTE\n\n"
            f"Entradas: X1 = {ingresos:g} (ingresos), X2 = {deudas:g} (deudas)\n"
            f"Pesos:   W1 = {peso_ingresos:g}, W2 = {peso_deudas:g}, sesgo b = {sesgo:g}\n\n"
            f"Z = ({ingresos:g} x {peso_ingresos:g}) + ({deudas:g} x {peso_deudas:g}) + ({sesgo:g})\n"
            f"Z = {valor_z:.2f}\n\n"
            f"Funcion escalon: Z {'>= 0' if salida else '< 0'} -> salida = {salida}\n"
            f"Decision de la neurona: {decision}\n\n"
            f"Interpretacion: {explicacion_peso_deuda}"
        )
        self.escribir_resultado(self.resultado_credito, texto)

    def crear_pestana_compuertas(self) -> None:
        """Crea el reto de cambiar pesos y sesgo para AND u OR."""
        pagina = tk.Frame(self.pestanas, bg=self.color_fondo)
        self.pestanas.add(pagina, text="Compuertas AND y OR")

        tk.Label(pagina, text="Reto: cambia manualmente pesos y sesgo", font=("Arial", 16, "bold"),
                 bg=self.color_fondo, fg="#153E75").pack(pady=(18, 4))
        tk.Label(
            pagina,
            text="El valor inicial resuelve AND. Usa el boton OR o modifica W1, W2 y b para descubrir otra solucion.",
            bg=self.color_fondo, fg="#475569",
        ).pack(pady=(0, 12))

        marco = tk.LabelFrame(pagina, text=" Pesos que puedes modificar ", bg=self.color_fondo, padx=12, pady=8)
        marco.pack(fill="x", padx=40, pady=4)
        self.caja_w1 = self.crear_campo(marco, "Peso W1", "0.5", 0)
        self.caja_w2 = self.crear_campo(marco, "Peso W2", "0.5", 1)
        self.caja_sesgo = self.crear_campo(marco, "Sesgo b", "-0.8", 2)
        self.compuerta_objetivo = tk.StringVar(value="AND")
        ttk.Combobox(marco, textvariable=self.compuerta_objetivo, state="readonly", width=8,
                     values=("AND", "OR")).grid(row=0, column=7, padx=(4, 9))
        tk.Button(marco, text="Probar pesos", command=self.probar_compuerta,
                  bg="#2563EB", fg="white", font=("Arial", 10, "bold")).grid(row=0, column=8, padx=4)
        tk.Button(marco, text="Cargar AND", command=lambda: self.cargar_pesos(0.5, 0.5, -0.8),
                  bg="#64748B", fg="white").grid(row=1, column=1, columnspan=2, pady=(9, 2))
        tk.Button(marco, text="Cargar OR", command=lambda: self.cargar_pesos(0.5, 0.5, -0.2),
                  bg="#16A34A", fg="white").grid(row=1, column=4, columnspan=2, pady=(9, 2))

        # Esta tabla me ayuda a comparar las cuatro entradas posibles con la salida esperada.
        self.tabla_compuerta = ttk.Treeview(
            pagina, columns=("x1", "x2", "z", "salida", "esperada", "estado"), show="headings", height=4,
        )
        for columna, titulo, ancho in (
            ("x1", "X1", 100), ("x2", "X2", 100), ("z", "Z = X.W + b", 170),
            ("salida", "Salida", 120), ("esperada", "Esperada", 120), ("estado", "Verificacion", 180),
        ):
            self.tabla_compuerta.heading(columna, text=titulo)
            self.tabla_compuerta.column(columna, width=ancho, anchor="center")
        self.tabla_compuerta.pack(padx=60, pady=20)

        self.resultado_compuerta = tk.Label(pagina, text="", bg="#EEF6FF", fg="#153E75",
                                             justify="left", wraplength=760, padx=14, pady=10)
        self.resultado_compuerta.pack(fill="x", padx=50, pady=5)
        self.probar_compuerta()

    def crear_campo(self, marco: tk.LabelFrame, nombre: str, valor: str, columna: int) -> tk.Entry:
        """Crea una etiqueta y una caja reutilizable para un peso o sesgo."""
        tk.Label(marco, text=nombre + ":", bg=self.color_fondo).grid(row=0, column=columna * 2, padx=(5, 2))
        caja = tk.Entry(marco, width=9)
        caja.insert(0, valor)
        caja.grid(row=0, column=columna * 2 + 1, padx=(0, 10))
        return caja

    def cargar_pesos(self, peso_1: float, peso_2: float, sesgo: float) -> None:
        """Carga una solucion conocida y permite ver el resultado inmediatamente."""
        for caja, valor in ((self.caja_w1, peso_1), (self.caja_w2, peso_2), (self.caja_sesgo, sesgo)):
            caja.delete(0, tk.END)
            caja.insert(0, str(valor))
        self.probar_compuerta()

    def probar_compuerta(self) -> None:
        """Evalua las cuatro combinaciones binarias con los pesos escritos."""
        try:
            pesos = np.array([
                self.leer_numero(self.caja_w1, "Peso W1"),
                self.leer_numero(self.caja_w2, "Peso W2"),
            ])
            sesgo = self.leer_numero(self.caja_sesgo, "Sesgo b")
        except ValueError as error:
            messagebox.showerror("Dato invalido", str(error))
            return

        objetivo = self.compuerta_objetivo.get()
        for fila in self.tabla_compuerta.get_children():
            self.tabla_compuerta.delete(fila)
        correctas = 0
        for x1, x2 in ((0, 0), (0, 1), (1, 0), (1, 1)):
            valor_z, salida = perceptron(np.array([x1, x2]), pesos, sesgo)
            esperada = (x1 and x2) if objetivo == "AND" else (x1 or x2)
            estado = "Correcta" if salida == int(esperada) else "Cambiar pesos"
            correctas += int(salida == int(esperada))
            self.tabla_compuerta.insert("", "end", values=(x1, x2, f"{valor_z:.2f}", salida, int(esperada), estado))
        self.resultado_compuerta.config(
            text=(
                f"Objetivo: compuerta {objetivo}. Con W = ({pesos[0]:g}, {pesos[1]:g}) y b = {sesgo:g}, "
                f"la neurona resolvio {correctas}/4 casos. "
                "Cuando ajustes pesos y sesgo manualmente, estas haciendo de forma visible lo que el entrenamiento automatiza."
            )
        )

    def crear_pestana_teoria(self) -> None:
        """Resume las ideas de neurona artificial y su limite lineal."""
        pagina = tk.Frame(self.pestanas, bg=self.color_fondo)
        self.pestanas.add(pagina, text="Como explicarlo")
        tk.Label(pagina, text="La neurona artificial paso a paso", font=("Arial", 16, "bold"),
                 bg=self.color_fondo, fg="#153E75").pack(pady=(20, 8))
        texto = (
            "1. Entradas (X): son los datos que recibe la neurona. En FactuGuard pueden ser monto, "
            "descuento, IVA, hora y otros valores de una factura.\n\n"
            "2. Pesos (W): indican la importancia aprendida de cada entrada. Un peso negativo reduce "
            "la suma; un peso positivo la aumenta.\n\n"
            "3. Sesgo (b): desplaza el umbral de decision. Gracias al sesgo, la neurona no necesita "
            "que el producto punto sea exactamente cero para activarse.\n\n"
            "4. Suma ponderada: Z = X.W + b. Es la combinacion lineal estudiada en el taller.\n\n"
            "5. Activacion: la funcion escalon devuelve 0 o 1. Una red profunda usa muchas neuronas "
            "y activaciones no lineales como ReLU; un unico perceptron no puede separar patrones curvos complejos.\n\n"
            "En el proyecto final, el perceptron es una tercera opinion supervisada. No corrige facturas "
            "ni toma decisiones finales: solo ayuda a priorizar la revision humana."
        )
        tk.Label(pagina, text=texto, justify="left", anchor="w", wraplength=820,
                 bg=self.color_fondo, fg="#334155", font=("Arial", 12)).pack(padx=42, pady=12, fill="x")

    @staticmethod
    def escribir_resultado(caja: tk.Text, texto: str) -> None:
        """Actualiza un cuadro de texto sin permitir que se edite manualmente."""
        caja.config(state="normal")
        caja.delete("1.0", tk.END)
        caja.insert(tk.END, texto)
        caja.config(state="disabled")


if __name__ == "__main__":
    # Este codigo me ayuda a abrir la interfaz solo si ejecuto este archivo.
    raiz = tk.Tk()
    VentanaPerceptron(raiz)
    # Este ciclo me ayuda a mantener la ventana activa mientras uso el taller.
    raiz.mainloop()
