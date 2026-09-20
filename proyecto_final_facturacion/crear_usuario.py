"""Asistente para crear el primer usuario de la aplicación."""

from getpass import getpass

from base_datos import crear_usuario, inicializar_base_de_datos


if __name__ == "__main__":
    print("Creación de usuario para FactuGuard IA\n")
    # También asegura que las tablas existan antes de insertar el usuario.
    inicializar_base_de_datos()
    nombre_completo = input("Nombre completo: ").strip()
    nombre_usuario = input("Usuario (ejemplo: duverney): ").strip()
    print("Roles: administrador (todo, incluido borrar datos de prueba), analista o revisor.")
    rol = input("Rol [analista]: ").strip().lower() or "analista"
    if rol not in {"administrador", "analista", "revisor"}:
        raise SystemExit("Rol no válido. Usa administrador, analista o revisor.")
    contrasena = getpass("Contraseña (mínimo 6 caracteres; 10 en producción): ")
    confirmacion = getpass("Repite la contraseña: ")
    if contrasena != confirmacion:
        raise SystemExit("Las contraseñas no coinciden. No se creó ningún usuario.")
    try:
        crear_usuario(nombre_usuario, nombre_completo, contrasena, rol)
    except ValueError as error:
        raise SystemExit(f"No se creó el usuario: {error}") from error
    print(f"Usuario '{nombre_usuario.lower()}' creado correctamente con rol {rol}.")
