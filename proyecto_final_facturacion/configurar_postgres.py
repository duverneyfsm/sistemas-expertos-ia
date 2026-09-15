"""Asistente sencillo para crear el archivo .env de conexión local.

Este archivo pregunta por la contraseña y la guarda solo en el computador.
El archivo .env está ignorado por Git, por lo que no se publica.
"""

from getpass import getpass
import secrets

from config import RUTA_ENV


def pedir(mensaje: str, valor_predeterminado: str) -> str:
    """Permite conservar el valor entre corchetes si se presiona Enter."""
    valor = input(f"{mensaje} [{valor_predeterminado}]: ").strip()
    return valor or valor_predeterminado


if __name__ == "__main__":
    print("Configuración local de PostgreSQL para FactuGuard IA")
    print("Presiona Enter para conservar los valores recomendados.\n")
    host = pedir("Servidor", "localhost")
    puerto = pedir("Puerto", "5432")
    usuario = pedir("Usuario de PostgreSQL", "postgres")
    nombre_base = pedir("Nombre de la nueva base", "factuguard_ia")
    contrasena = getpass("Contraseña de PostgreSQL: ")
    if not contrasena:
        raise SystemExit("No se creó .env porque la contraseña está vacía.")

    contenido = (
        f"DB_HOST={host}\nDB_PORT={puerto}\nDB_NAME={nombre_base}\n"
        f"DB_ADMIN_NAME=postgres\nDB_USER={usuario}\nDB_PASSWORD={contrasena}\n"
        f"FLASK_SECRET_KEY={secrets.token_urlsafe(32)}\n"
    )
    RUTA_ENV.write_text(contenido, encoding="utf-8")
    print(f"\nArchivo local creado: {RUTA_ENV.name}")
    print("Siguiente paso: ejecuta  py inicializar_postgres.py")
