"""Funciones de seguridad para contraseñas de usuarios de FactuGuard IA."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from config import ES_PRODUCCION

# scrypt es una función diseñada para proteger contraseñas. Los parámetros se
# mantienen aquí para que el proceso de crear y validar use exactamente los mismos.
N_SCRYPT = 2**14
R_SCRYPT = 8
P_SCRYPT = 1
LONGITUD_SAL = 16
LONGITUD_HASH = 64


def validar_contrasena(contrasena: str) -> None:
    """Exige 6 caracteres en el prototipo local y 10 cuando el entorno es de producción."""
    minimo = 10 if ES_PRODUCCION else 6
    if len(contrasena) < minimo:
        raise ValueError(f"La contraseña debe tener al menos {minimo} caracteres.")


def crear_hash_contrasena(contrasena: str) -> tuple[str, str]:
    """Devuelve sal y hash hexadecimal; nunca devuelve ni guarda la contraseña."""
    validar_contrasena(contrasena)
    sal = secrets.token_bytes(LONGITUD_SAL)
    hash_contrasena = hashlib.scrypt(
        contrasena.encode("utf-8"), salt=sal, n=N_SCRYPT, r=R_SCRYPT, p=P_SCRYPT,
        dklen=LONGITUD_HASH,
    )
    return sal.hex(), hash_contrasena.hex()


def verificar_contrasena(contrasena: str, sal_hex: str, hash_esperado_hex: str) -> bool:
    """Calcula de nuevo el hash y compara de forma segura contra el guardado."""
    hash_calculado = hashlib.scrypt(
        contrasena.encode("utf-8"), salt=bytes.fromhex(sal_hex), n=N_SCRYPT,
        r=R_SCRYPT, p=P_SCRYPT, dklen=LONGITUD_HASH,
    ).hex()
    return hmac.compare_digest(hash_calculado, hash_esperado_hex)
