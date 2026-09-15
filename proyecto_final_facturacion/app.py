"""Dashboard local y explicable del detector de anomalías de facturación.

Cada componente visual muestra una parte del experimento: indicadores,
gráficos, tabla de alertas y análisis manual de una factura.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from generar_datos import calcular_importes
from reglas_negocio import aplicar_reglas
from servicio import ejecutar_experimento
from base_datos import autenticar_usuario


# Colores reutilizados en toda la interfaz. Mantenerlos juntos facilita cambiar
# el tema visual sin buscar valores de color por todo el programa.
FONDO = "#F4F7FB"
BLANCO = "#FFFFFF"
TEXTO = "#172033"
TEXTO_SUAVE = "#64748B"
AZUL = "#2563EB"
VERDE = "#16A34A"
NARANJA = "#EA580C"
ROJO = "#DC2626"
LATERAL = "#0F172A"
LATERAL_ACTIVO = "#1E3A8A"


class InicioSesion:
    """Pantalla inicial que solicita las credenciales guardadas con hash."""

    def __init__(self, ventana: tk.Tk) -> None:
        self.ventana = ventana
        self.ventana.title("FactuGuard IA | Iniciar sesión")
        self.ventana.geometry("480x450")
        self.ventana.resizable(False, False)
        self.ventana.configure(bg=FONDO)

        tarjeta = tk.Frame(ventana, bg=BLANCO, highlightbackground="#E2E8F0", highlightthickness=1)
        tarjeta.place(relx=.5, rely=.5, anchor="center", width=370, height=340)
        tk.Label(tarjeta, text="◈  FACTUGUARD", bg=BLANCO, fg=AZUL,
                 font=("Segoe UI", 17, "bold")).pack(pady=(30, 4))
        tk.Label(tarjeta, text="Ingresa con tu usuario local", bg=BLANCO, fg=TEXTO_SUAVE,
                 font=("Segoe UI", 10)).pack(pady=(0, 22))
        tk.Label(tarjeta, text="Usuario", bg=BLANCO, fg=TEXTO_SUAVE,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=40)
        self.entrada_usuario = tk.Entry(tarjeta, font=("Segoe UI", 11), relief="solid", bd=1)
        self.entrada_usuario.pack(fill="x", padx=40, pady=(4, 14), ipady=6)
        tk.Label(tarjeta, text="Contraseña", bg=BLANCO, fg=TEXTO_SUAVE,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=40)
        self.entrada_contrasena = tk.Entry(tarjeta, show="●", font=("Segoe UI", 11), relief="solid", bd=1)
        self.entrada_contrasena.pack(fill="x", padx=40, pady=(4, 18), ipady=6)
        self.entrada_contrasena.bind("<Return>", lambda _evento: self.ingresar())
        tk.Button(tarjeta, text="Iniciar sesión", command=self.ingresar, bg=AZUL, fg="white",
                  activebackground="#1D4ED8", activeforeground="white", relief="flat",
                  padx=16, pady=10, font=("Segoe UI", 10, "bold"), cursor="hand2").pack(fill="x", padx=40)

    def ingresar(self) -> None:
        """Valida usuario/contraseña sin exponer ni comparar claves en texto."""
        try:
            usuario = autenticar_usuario(self.entrada_usuario.get(), self.entrada_contrasena.get())
        except Exception as error:
            messagebox.showerror("No se pudo conectar", str(error))
            return
        if not usuario:
            messagebox.showerror("Acceso denegado", "Usuario o contraseña incorrectos.")
            self.entrada_contrasena.delete(0, tk.END)
            return
        # Se elimina la pantalla de acceso y se crea el panel autenticado.
        for control in self.ventana.winfo_children():
            control.destroy()
        DashboardFacturacion(self.ventana, usuario)


class DashboardFacturacion:
    """Coordina las pantallas del dashboard y el experimento de IA."""

    def __init__(self, ventana: tk.Tk, usuario: dict[str, object]) -> None:
        self.ventana = ventana
        self.usuario = usuario
        self.ventana.title("FactuGuard IA | Detector de anomalías")
        self.ventana.geometry("1280x780")
        self.ventana.resizable(True, True)
        self.ventana.minsize(1080, 680)
        self.ventana.configure(bg=FONDO)

        # Estos datos permanecen vacíos hasta que el usuario entrena el modelo.
        self.facturas: pd.DataFrame | None = None
        self.detector = None
        # Si se activa, el experimento también se guarda en PostgreSQL local.
        self.guardar_postgres = tk.BooleanVar(value=False)
        self.boton_menu: dict[str, tk.Button] = {}
        self.graficos: list[FigureCanvasTkAgg] = []

        self._configurar_estilos()
        self._crear_layout()
        self._mostrar_vista("Resumen")

    def _configurar_estilos(self) -> None:
        """Personaliza la tabla de Tkinter para que parezca parte del dashboard."""
        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure("Treeview", background=BLANCO, foreground=TEXTO,
                         fieldbackground=BLANCO, rowheight=28, font=("Segoe UI", 9))
        estilo.configure("Treeview.Heading", background="#EAF0FF", foreground="#1E3A8A",
                         font=("Segoe UI", 9, "bold"), relief="flat")
        estilo.map("Treeview", background=[("selected", "#DBEAFE")], foreground=[("selected", TEXTO)])

    def _crear_layout(self) -> None:
        """Crea la barra lateral, el encabezado y el contenedor de pantallas."""
        self.ventana.grid_columnconfigure(1, weight=1)
        self.ventana.grid_rowconfigure(0, weight=1)
        self._crear_barra_lateral()

        area = tk.Frame(self.ventana, bg=FONDO)
        area.grid(row=0, column=1, sticky="nsew")
        area.grid_columnconfigure(0, weight=1)
        area.grid_rowconfigure(1, weight=1)

        encabezado = tk.Frame(area, bg=FONDO)
        encabezado.grid(row=0, column=0, sticky="ew", padx=30, pady=(18, 10))
        encabezado.grid_columnconfigure(0, weight=1)
        self.titulo = tk.Label(encabezado, bg=FONDO, fg=TEXTO, font=("Segoe UI", 20, "bold"))
        self.titulo.grid(row=0, column=0, sticky="w")
        self.subtitulo = tk.Label(encabezado, bg=FONDO, fg=TEXTO_SUAVE, font=("Segoe UI", 10))
        self.subtitulo.grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Button(encabezado, text="↻  Ejecutar experimento", command=self.ejecutar,
                  bg=AZUL, fg="white", activebackground="#1D4ED8", activeforeground="white",
                  relief="flat", padx=16, pady=10, font=("Segoe UI", 10, "bold"),
                  cursor="hand2").grid(row=0, column=1, rowspan=2, sticky="e")
        tk.Checkbutton(encabezado, text="Guardar en PostgreSQL local", variable=self.guardar_postgres,
                       bg=FONDO, activebackground=FONDO, fg=TEXTO_SUAVE, selectcolor=FONDO,
                       font=("Segoe UI", 9)).grid(row=2, column=1, sticky="e", pady=(4, 0))

        self.contenedor = tk.Frame(area, bg=FONDO)
        self.contenedor.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 24))
        self.contenedor.grid_columnconfigure(0, weight=1)
        self.contenedor.grid_rowconfigure(0, weight=1)

        # Se crean las tres vistas una vez y luego se muestra la seleccionada.
        self.vistas = {
            "Resumen": self._crear_resumen(),
            "Analizar factura": self._crear_analizador(),
            "Alertas": self._crear_alertas(),
        }

    def _crear_barra_lateral(self) -> None:
        """Añade navegación y un aviso sobre el uso responsable del prototipo."""
        lateral = tk.Frame(self.ventana, bg=LATERAL, width=225)
        lateral.grid(row=0, column=0, sticky="nsew")
        lateral.grid_propagate(False)
        tk.Label(lateral, text="◈  FACTUGUARD", bg=LATERAL, fg="white",
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=22, pady=(28, 3))
        tk.Label(lateral, text="Panel de control con IA", bg=LATERAL, fg="#94A3B8",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=23, pady=(0, 30))
        tk.Label(lateral, text=str(self.usuario["nombre_completo"]), bg=LATERAL, fg="white",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=22)
        tk.Label(lateral, text=f"Rol: {self.usuario['rol']}", bg=LATERAL, fg="#94A3B8",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=22, pady=(2, 16))

        for nombre, icono in (("Resumen", "▦"), ("Analizar factura", "⌕"), ("Alertas", "⚠")):
            boton = tk.Button(
                lateral, text=f" {icono}   {nombre}", command=lambda n=nombre: self._mostrar_vista(n),
                anchor="w", borderwidth=0, padx=22, pady=12, bg=LATERAL,
                activebackground=LATERAL_ACTIVO, fg="#CBD5E1", activeforeground="white",
                font=("Segoe UI", 10), cursor="hand2",
            )
            boton.pack(fill="x", padx=10, pady=2)
            self.boton_menu[nombre] = boton

        tk.Frame(lateral, bg="#334155", height=1).pack(fill="x", padx=22, pady=(30, 14))
        tk.Label(lateral, text="DATOS SINTÉTICOS", bg=LATERAL, fg="#64748B",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=22)
        tk.Label(lateral, text="Las alertas requieren\nrevisión humana.", bg=LATERAL,
                 fg="#CBD5E1", justify="left", font=("Segoe UI", 9)).pack(anchor="w", padx=22, pady=(8, 0))

    @staticmethod
    def _tarjeta(padre: tk.Widget) -> tk.Frame:
        """Devuelve un contenedor blanco con borde suave, usado como tarjeta."""
        return tk.Frame(padre, bg=BLANCO, highlightbackground="#E2E8F0", highlightthickness=1)

    def _crear_resumen(self) -> tk.Frame:
        """Construye indicadores, dos gráficos y una tabla de alertas recientes."""
        vista = tk.Frame(self.contenedor, bg=FONDO)
        for columna in range(4):
            vista.grid_columnconfigure(columna, weight=1, uniform="metricas")
        vista.grid_rowconfigure(2, weight=1)
        self.metricas_labels: dict[str, tk.Label] = {}

        tarjetas = [
            ("Registros evaluados", "registros", "▤", AZUL),
            ("Alertas generadas", "alertas", "⚠", NARANJA),
            ("Precisión", "precision", "◎", VERDE),
            ("Puntaje F1", "f1", "◈", "#7C3AED"),
        ]
        for columna, (texto, clave, icono, color) in enumerate(tarjetas):
            tarjeta = self._tarjeta(vista)
            tarjeta.grid(row=0, column=columna, sticky="ew", padx=(0 if columna == 0 else 8, 8), pady=(0, 14))
            tk.Label(tarjeta, text=icono, bg="#EFF6FF", fg=color, font=("Segoe UI Symbol", 18),
                     width=3, pady=9).grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=14)
            tk.Label(tarjeta, text=texto.upper(), bg=BLANCO, fg=TEXTO_SUAVE,
                     font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="sw", pady=(17, 0))
            valor = tk.Label(tarjeta, text="—", bg=BLANCO, fg=TEXTO, font=("Segoe UI", 18, "bold"))
            valor.grid(row=1, column=1, sticky="nw", pady=(0, 17))
            self.metricas_labels[clave] = valor

        self.marco_tipos = self._tarjeta(vista)
        self.marco_tipos.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=(0, 8), pady=(0, 14))
        self.marco_origen = self._tarjeta(vista)
        self.marco_origen.grid(row=1, column=2, columnspan=2, sticky="nsew", padx=(0, 8), pady=(0, 14))

        contenedor_tabla = self._tarjeta(vista)
        contenedor_tabla.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=(0, 8))
        contenedor_tabla.grid_columnconfigure(0, weight=1)
        contenedor_tabla.grid_rowconfigure(1, weight=1)
        tk.Label(contenedor_tabla, text="Alertas recientes", bg=BLANCO, fg=TEXTO,
                 font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 7))
        self.tabla_resumen = self._crear_tabla(contenedor_tabla)
        self.tabla_resumen.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 15))
        return vista

    def _crear_analizador(self) -> tk.Frame:
        """Construye el formulario que permite probar una factura individual."""
        vista = tk.Frame(self.contenedor, bg=FONDO)
        vista.grid_columnconfigure(0, weight=2)
        vista.grid_columnconfigure(1, weight=3)
        vista.grid_rowconfigure(0, weight=1)
        formulario = self._tarjeta(vista)
        formulario.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        resultado = self._tarjeta(vista)
        resultado.grid(row=0, column=1, sticky="nsew")

        tk.Label(formulario, text="Analizar una factura", bg=BLANCO, fg=TEXTO,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=24, pady=(24, 3))
        tk.Label(formulario, text="Ingresa valores para obtener una explicación.", bg=BLANCO,
                 fg=TEXTO_SUAVE, font=("Segoe UI", 9)).pack(anchor="w", padx=24, pady=(0, 18))
        campos = tk.Frame(formulario, bg=BLANCO)
        campos.pack(fill="x", padx=24)
        self.entradas: dict[str, tk.Entry] = {}
        valores = [
            ("Factura ID", "PRUEBA-001"), ("Cantidad", "2"), ("Precio unitario", "150"),
            ("Descuento (%)", "5"), ("IVA (%)", "19"), ("Hora (0-23)", "10"),
        ]
        for fila, (nombre, valor) in enumerate(valores):
            tk.Label(campos, text=nombre, bg=BLANCO, fg=TEXTO_SUAVE,
                     font=("Segoe UI", 9, "bold")).grid(row=fila, column=0, sticky="w", pady=7)
            entrada = tk.Entry(campos, width=22, font=("Segoe UI", 10), relief="solid", bd=1)
            entrada.insert(0, valor)
            entrada.grid(row=fila, column=1, sticky="ew", padx=(14, 0), pady=7, ipady=5)
            self.entradas[nombre] = entrada
        campos.grid_columnconfigure(1, weight=1)
        tk.Button(formulario, text="Analizar con IA  →", command=self.analizar_factura,
                  bg=VERDE, fg="white", activebackground="#15803D", activeforeground="white",
                  relief="flat", padx=15, pady=10, font=("Segoe UI", 10, "bold"),
                  cursor="hand2").pack(anchor="w", padx=24, pady=22)

        tk.Label(resultado, text="Resultado del análisis", bg=BLANCO, fg=TEXTO,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=24, pady=(24, 3))
        tk.Label(resultado, text="La salida es una recomendación, no una corrección automática.",
                 bg=BLANCO, fg=TEXTO_SUAVE, font=("Segoe UI", 9)).pack(anchor="w", padx=24, pady=(0, 18))
        self.resultado_factura = tk.Label(resultado, text="Ejecuta el experimento y luego analiza una factura.",
                                          bg="#F8FAFC", fg=TEXTO_SUAVE, justify="left", anchor="nw",
                                          wraplength=480, padx=20, pady=18, font=("Segoe UI", 11))
        self.resultado_factura.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        return vista

    def _crear_alertas(self) -> tk.Frame:
        """Crea una bandeja de revisión con todas las alertas generadas."""
        vista = self._tarjeta(self.contenedor)
        vista.grid_columnconfigure(0, weight=1)
        vista.grid_rowconfigure(1, weight=1)
        cabecera = tk.Frame(vista, bg=BLANCO)
        cabecera.grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 10))
        tk.Label(cabecera, text="Bandeja de alertas", bg=BLANCO, fg=TEXTO,
                 font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Label(cabecera, text="Casos para validación humana.", bg=BLANCO, fg=TEXTO_SUAVE,
                 font=("Segoe UI", 9)).pack(side="left", padx=14)
        tk.Button(cabecera, text="Actualizar", command=self._actualizar_tablas,
                  bg="#EAF0FF", fg="#1D4ED8", relief="flat", padx=12, pady=6,
                  font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="right")
        self.tabla_alertas = self._crear_tabla(vista)
        self.tabla_alertas.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 22))
        return vista

    @staticmethod
    def _crear_tabla(padre: tk.Widget) -> ttk.Treeview:
        """Crea una tabla para mostrar ID, tipo, origen, puntaje y explicación."""
        columnas = ("factura", "tipo", "origen", "puntaje", "motivo")
        tabla = ttk.Treeview(padre, columns=columnas, show="headings")
        datos = {
            "factura": ("Factura", 130, "w"), "tipo": ("Tipo", 170, "w"),
            "origen": ("Origen", 105, "center"), "puntaje": ("Puntaje IA", 95, "center"),
            "motivo": ("Explicación", 460, "w"),
        }
        for columna, (titulo, ancho, alineacion) in datos.items():
            tabla.heading(columna, text=titulo)
            tabla.column(columna, width=ancho, minwidth=75, anchor=alineacion,
                         stretch=columna == "motivo")
        return tabla

    def _mostrar_vista(self, nombre: str) -> None:
        """Oculta las demás vistas y muestra la elegida en la barra lateral."""
        textos = {
            "Resumen": ("Resumen ejecutivo", "Indicadores y alertas del prototipo local."),
            "Analizar factura": ("Analizar una factura", "Reglas explícitas y detección de patrones inusuales."),
            "Alertas": ("Bandeja de alertas", "Consulta los casos que requieren revisión humana."),
        }
        self.titulo.config(text=textos[nombre][0])
        self.subtitulo.config(text=textos[nombre][1])
        for vista in self.vistas.values():
            vista.grid_forget()
        self.vistas[nombre].grid(row=0, column=0, sticky="nsew")
        for clave, boton in self.boton_menu.items():
            activo = clave == nombre
            boton.config(bg=LATERAL_ACTIVO if activo else LATERAL, fg="white" if activo else "#CBD5E1")

    def ejecutar(self) -> None:
        """Genera datos, entrena el modelo y actualiza todos los componentes visuales."""
        self.ventana.config(cursor="watch")
        self.ventana.update_idletasks()
        try:
            self.facturas, metricas, self.detector = ejecutar_experimento(
                guardar_en_postgres=self.guardar_postgres.get()
            )
        except Exception as error:
            messagebox.showerror("No se pudo ejecutar", str(error))
            return
        finally:
            self.ventana.config(cursor="")
        self._actualizar_resumen(metricas)
        self._actualizar_tablas()
        self._mostrar_vista("Resumen")

    def _actualizar_resumen(self, metricas: dict[str, object]) -> None:
        """Lleva las métricas del backend a tarjetas y gráficos del dashboard."""
        self.metricas_labels["registros"].config(text=f"{len(self.facturas):,}")
        self.metricas_labels["alertas"].config(text=f"{int(self.facturas['alerta_hibrida'].sum()):,}")
        self.metricas_labels["precision"].config(text=f"{float(metricas['precision']) * 100:.1f}%")
        self.metricas_labels["f1"].config(text=f"{float(metricas['f1']) * 100:.1f}%")
        self._dibujar_graficos()

    def _dibujar_graficos(self) -> None:
        """Inserta gráficos de Matplotlib en los dos espacios del dashboard."""
        for grafico in self.graficos:
            grafico.get_tk_widget().destroy()
        self.graficos.clear()
        for marco in (self.marco_tipos, self.marco_origen):
            for hijo in marco.winfo_children():
                hijo.destroy()

        alertas = self.facturas.loc[self.facturas["alerta_hibrida"]].copy()
        tipos = alertas["tipo_anomalia"].value_counts().sort_values(ascending=True)
        etiquetas = [texto.replace("_", " ").title() for texto in tipos.index]

        tk.Label(self.marco_tipos, text="Alertas por tipo", bg=BLANCO, fg=TEXTO,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=18, pady=(14, 0))
        figura_tipos = Figure(figsize=(5.1, 2.25), dpi=100, facecolor=BLANCO)
        eje = figura_tipos.add_subplot(111)
        eje.barh(etiquetas, tipos.values, color="#3B82F6")
        eje.set_xlabel("Cantidad de alertas", color=TEXTO_SUAVE, fontsize=8)
        eje.tick_params(axis="both", labelsize=8, colors=TEXTO_SUAVE)
        eje.spines[["top", "right", "left"]].set_visible(False)
        eje.grid(axis="x", alpha=.18)
        figura_tipos.tight_layout(pad=1)
        lienzo_tipos = FigureCanvasTkAgg(figura_tipos, master=self.marco_tipos)
        lienzo_tipos.draw()
        lienzo_tipos.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.graficos.append(lienzo_tipos)

        # Separamos alertas de reglas, IA o ambas para explicar el enfoque híbrido.
        valores = [
            int((alertas["alerta_reglas"] & ~alertas["alerta_ia"]).sum()),
            int((~alertas["alerta_reglas"] & alertas["alerta_ia"]).sum()),
            int((alertas["alerta_reglas"] & alertas["alerta_ia"]).sum()),
        ]
        opciones = [("Reglas", valores[0], "#F59E0B"), ("IA", valores[1], "#8B5CF6"), ("Ambos", valores[2], "#16A34A")]
        opciones = [opcion for opcion in opciones if opcion[1] > 0]
        tk.Label(self.marco_origen, text="Origen de las alertas", bg=BLANCO, fg=TEXTO,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=18, pady=(14, 0))
        figura_origen = Figure(figsize=(5.1, 2.25), dpi=100, facecolor=BLANCO)
        eje_origen = figura_origen.add_subplot(111)
        eje_origen.pie([opcion[1] for opcion in opciones], labels=[opcion[0] for opcion in opciones],
                       colors=[opcion[2] for opcion in opciones], autopct="%1.0f%%", startangle=90,
                       textprops={"fontsize": 8, "color": TEXTO})
        eje_origen.text(0, 0, f"{len(alertas)}\nalertas", ha="center", va="center", fontsize=10,
                        weight="bold", color=TEXTO)
        figura_origen.tight_layout(pad=1)
        lienzo_origen = FigureCanvasTkAgg(figura_origen, master=self.marco_origen)
        lienzo_origen.draw()
        lienzo_origen.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.graficos.append(lienzo_origen)

    def _actualizar_tablas(self) -> None:
        """Recarga las tablas con las alertas más recientes del experimento."""
        for tabla in (self.tabla_resumen, self.tabla_alertas):
            for elemento in tabla.get_children():
                tabla.delete(elemento)
        if self.facturas is None:
            return
        alertas = self.facturas.loc[self.facturas["alerta_hibrida"]]
        for _, fila in alertas.head(150).iterrows():
            origen = "Reglas + IA" if fila["alerta_reglas"] and fila["alerta_ia"] else ("Reglas" if fila["alerta_reglas"] else "IA")
            valores = (fila["factura_id"], str(fila["tipo_anomalia"]).replace("_", " ").title(), origen,
                       f"{float(fila['puntaje_ia']):.3f}", fila["motivo_alerta"])
            self.tabla_resumen.insert("", "end", values=valores)
            self.tabla_alertas.insert("", "end", values=valores)

    def analizar_factura(self) -> None:
        """Aplica reglas y modelo ya entrenado a una factura escrita por el usuario."""
        if self.detector is None or self.facturas is None:
            messagebox.showinfo("Primero ejecutar", "Primero ejecuta el experimento para entrenar el modelo.")
            return
        try:
            factura_id = self.entradas["Factura ID"].get().strip()
            cantidad = float(self.entradas["Cantidad"].get())
            precio = float(self.entradas["Precio unitario"].get())
            descuento = float(self.entradas["Descuento (%)"].get()) / 100
            iva = float(self.entradas["IVA (%)"].get()) / 100
            hora = int(self.entradas["Hora (0-23)"].get())
            if not factura_id or cantidad <= 0 or precio <= 0 or not 0 <= descuento < 1 or not 0 <= iva <= 1 or not 0 <= hora <= 23:
                raise ValueError
        except ValueError:
            messagebox.showerror("Datos inválidos", "Usa cantidad/precio positivos, porcentajes válidos y hora entre 0 y 23.")
            return

        subtotal, impuesto, total = calcular_importes(cantidad, precio, descuento, iva)
        factura = pd.DataFrame([{
            "factura_id": factura_id, "cliente_sintetico": "PRUEBA", "categoria": "Prueba",
            "fecha": "2026-08-31", "hora": hora, "cantidad": cantidad,
            "precio_unitario": precio, "descuento_pct": descuento, "tasa_iva": iva,
            "subtotal": subtotal, "impuesto_valor": impuesto, "total": total,
        }])
        # La lista de IDs existentes permite que la regla también detecte duplicados.
        con_reglas = aplicar_reglas(factura, ids_conocidos=set(self.facturas["factura_id"]))
        resultado = self.detector.predecir(con_reglas).iloc[0]
        requiere_revision = bool(resultado["alerta_reglas"] or resultado["alerta_ia"])
        motivos = []
        if bool(resultado["alerta_reglas"]):
            motivos.append(str(resultado["motivos_reglas"]))
        if bool(resultado["alerta_ia"]):
            motivos.append("Patrón inusual detectado por el modelo de IA")
        explicacion = "; ".join(motivos) if motivos else "No activó reglas ni superó el umbral de rareza."
        estado = "REQUIERE REVISIÓN" if requiere_revision else "SIN ALERTA"
        self.resultado_factura.config(
            text=(f"{estado}\n\nTotal calculado: ${total:,.2f}\n"
                  f"Puntaje de rareza IA: {float(resultado['puntaje_ia']):.4f}\n\n"
                  f"Explicación\n{explicacion}\n\n"
                  "La aplicación no modifica ninguna factura automáticamente."),
            fg=ROJO if requiere_revision else TEXTO,
        )


if __name__ == "__main__":
    raiz = tk.Tk()
    InicioSesion(raiz)
    raiz.mainloop()
