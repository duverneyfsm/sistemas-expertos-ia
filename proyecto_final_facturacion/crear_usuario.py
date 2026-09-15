"""Asistente para crear el primer usuario de la aplicación."""

from getpass import getpass

from base_datos import crear_usuario, inicializar_base_de_datos


if __name__ == "__main__":
    print("Creación de usuario para FactuGuard IA\n")
    # También asegura que las tablas existan antes de insertar el usuario.
    inicializar_base_de_datos()
    nombre_completo = input("Nombre completo: ").strip()
    nombre_usuario = input("Usuario (ejemplo: duverney): ").strip()
    contrasena = getpass("Contraseña (mínimo 6 caracteres): ")
    confirmacion = getpass("Repite la contraseña: ")
    if contrasena != confirmacion:
        raise SystemExit("Las contraseñas no coinciden. No se creó ningún usuario.")
    try:
        crear_usuario(nombre_usuario, nombre_completo, contrasena)
    except ValueError as error:
        raise SystemExit(f"No se creó el usuario: {error}") from error
    print(f"Usuario '{nombre_usuario.lower()}' creado correctamente.")
