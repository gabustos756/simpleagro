from __future__ import annotations

"""
Módulo de Validación de URLs de Pago y Portales de Proveedores (EduAgro V1).

Garantiza que sólo se persistan URLs válidas de portales externos (http/https),
protegiendo la aplicación contra vulnerabilidades XSS (javascript:, data:),
Path Traversal (file:) y redirecciones a interfaces locales/redes privadas (SSRF).
"""

from urllib.parse import urlparse
from typing import Optional, Set, Tuple
import re

ALLOWED_SCHEMES: Set[str] = {"http", "https"}

# Direcciones/rangos IP privados o de loopback bloqueados para prevenir SSRF y portales locales
DISALLOWED_HOSTS: Set[str] = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
}

# Regex para rangos IP privados (RFC 1918 / Link-Local / Multicast)
PRIVATE_IP_REGEX = re.compile(
    r"^(?:"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"                  # 10.0.0.0/8
    r"172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|"  # 172.16.0.0/12
    r"192\.168\.\d{1,3}\.\d{1,3}|"                    # 192.168.0.0/16
    r"169\.254\.\d{1,3}\.\d{1,3}"                     # 169.254.0.0/16 Link-Local
    r")$"
)


def validate_external_payment_url(value: Optional[str]) -> Optional[str]:
    """
    Valida y sanitiza una URL de pago externa o portal de proveedor.
    
    Retorna la URL sanitizada si es válida, None si está vacía,
    o lanza ValueError con mensaje explicativo en español.
    """
    if not value or not str(value).strip():
        return None

    cleaned = str(value).strip()

    # Prevenir scripts o rutas relativas simples antes del parseo
    cleaned_lower = cleaned.lower()
    if cleaned_lower.startswith(("javascript:", "data:", "file:", "ftp:", "vbscript:", "//", "/")):
        raise ValueError("Esquema de URL no permitido. Utilizar exclusivamente http:// o https://.")

    if not cleaned_lower.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned

    try:
        parsed = urlparse(cleaned)
    except Exception as e:
        raise ValueError(f"Formato de URL inválido: {e}")

    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError("La URL debe comenzar con http:// o https://.")

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        raise ValueError("La URL debe incluir un nombre de dominio o host válido (ej: https://epec.com.ar).")

    # Rechazar credenciales embebidas (ej: http://admin:secret@host)
    if parsed.username or parsed.password:
        raise ValueError("No se permiten credenciales embebidas en la URL.")

    # Verificar hostnames prohibidos (localhost, IPs privadas)
    if hostname in DISALLOWED_HOSTS or hostname.endswith((".local", ".lan", ".internal", ".invalid")):
        raise ValueError("No se permiten URLs que apunten a servidores locales o interfaces privadas.")

    if PRIVATE_IP_REGEX.match(hostname):
        raise ValueError("No se permiten direcciones IP privadas de red local.")

    return cleaned


def get_display_domain(value: Optional[str]) -> str:
    """
    Extrae el dominio limpio (ej. 'epec.com.ar') de una URL de pago para mostrarlo en botones UI.
    """
    if not value or not str(value).strip():
        return "Portal externo"

    try:
        parsed = urlparse(str(value).strip())
        hostname = (parsed.hostname or "").lower().strip()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname if hostname else "Portal externo"
    except Exception:
        return "Portal externo"
