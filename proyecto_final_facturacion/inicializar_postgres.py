"""Crea la base de datos y las tablas locales de FactuGuard IA."""

from base_datos import inicializar_base_de_datos


if __name__ == "__main__":
    creada = inicializar_base_de_datos()
    mensaje = "Base de datos creada" if creada else "La base de datos ya existía"
    print(f"{mensaje}. Las tablas de FactuGuard IA están listas.")
