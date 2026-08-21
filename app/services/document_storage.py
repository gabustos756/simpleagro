from __future__ import annotations

"""
Servicio de Almacenamiento Privado de Documentos Digitales (EduAgro V1).

Proporciona la persistencia segura de facturas, recibos, presupuestos y comprobantes
en el sistema de archivos del VPS (fuera del acceso público de Nginx).

Garantiza:
- Prevención de Path Traversal mediante resolución estricta con Path.resolve().
- Límite de tamaño máximo de 10 MiB.
- Validación de tipos binarios (Magic Bytes) para PDF, JPEG, PNG y WEBP.
- Generación de claves de almacenamiento relativas con UUIDv4.
- Streaming por chunks con cálculo continuo de hash SHA-256.
- Limpieza automática de archivos parciales en caso de error.
"""

from pathlib import Path
from typing import Tuple, Optional, BinaryIO
from uuid import UUID, uuid4
import os
import re
import hashlib
from fastapi import UploadFile

# Tamaño máximo permitido por archivo: 10 MiB (10 * 1024 * 1024 bytes)
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
CHUNK_SIZE_BYTES = 64 * 1024

# Extensiones permitidas en allowlist
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}

# Cabeceras binarias (Magic Bytes) esperadas por tipo
MAGIC_HEADER_PDF = b"%PDF-"
MAGIC_HEADER_JPEG = b"\xff\xd8\xff"
MAGIC_HEADER_PNG = b"\x89PNG\r\n\x1a\n"


def get_storage_root() -> Path:
    """
    Retorna la ruta raíz parametrizable para el almacenamiento privado de documentos.
    En local: 'data/uploads' dentro de la carpeta del proyecto.
    En producción: Configurable vía la variable de entorno DOCUMENT_STORAGE_ROOT.
    """
    env_root = os.getenv("DOCUMENT_STORAGE_ROOT")
    if env_root and env_root.strip():
        root_path = Path(env_root.strip()).resolve()
    else:
        root_path = (Path(os.getcwd()) / "data" / "uploads").resolve()

    root_path.mkdir(parents=True, exist_ok=True)
    return root_path


def sanitize_original_filename(filename: Optional[str]) -> str:
    """
    Sanitiza el nombre original del archivo eliminando secuencias de Path Traversal,
    caracteres de control, bytes nulos y delimitadores de directorio.
    """
    if not filename or not str(filename).strip():
        return "documento_adjunto.pdf"

    # Extraer sólo el basename sin directorios
    basename = Path(str(filename).strip()).name
    # Eliminar bytes nulos y caracteres de control
    basename = re.sub(r"[\x00-\x1f\x7f]", "", basename)
    # Reemplazar caracteres inseguros
    basename = re.sub(r'[\\/:*?"<>|]', "_", basename)
    basename = basename.strip(" .")

    if not basename:
        return "documento_adjunto.pdf"

    return basename[:255]


def detect_file_type_from_magic_bytes(header: bytes) -> str:
    """
    Inspecciona los primeros bytes del archivo para confirmar el tipo real de contenido (Magic Bytes).
    Rechaza archivos HTML, SVG, ZIP, ejecutables o modificados maliciosamente.
    """
    if not header or len(header) < 4:
        raise ValueError("El archivo subido está vacío o corrupto.")

    if header.startswith(MAGIC_HEADER_PDF):
        return "application/pdf"
    elif header.startswith(MAGIC_HEADER_JPEG):
        return "image/jpeg"
    elif header.startswith(MAGIC_HEADER_PNG):
        return "image/png"
    elif len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    else:
        raise ValueError("Tipo de contenido no permitido. Sólo se admiten documentos PDF e imágenes JPG, PNG o WEBP.")


def resolve_safe_path(storage_key: str) -> Path:
    """
    Resuelve la ruta física absoluta de una clave de almacenamiento,
    garantizando que permanezca estrictamente dentro de DOCUMENT_STORAGE_ROOT (Prevención Path Traversal).
    """
    root = get_storage_root()
    # Prevenir que la clave comience con barras absolutas
    clean_key = storage_key.lstrip("/\\")
    target_path = (root / clean_key).resolve()

    # Comprobar que la ruta objetivo pertenezca al root
    try:
        target_path.relative_to(root)
    except ValueError:
        raise ValueError("Ruta de almacenamiento inválida o intento de Path Traversal detectado.")

    return target_path


def generate_storage_key(cliente_id: UUID, target_id: UUID, extension: str) -> str:
    """
    Genera una clave de almacenamiento relativa estandarizada con UUIDv4.
    Estructura: servicios/<cliente_id>/<target_id>/<uuid>.<ext>
    """
    ext_clean = extension.lower().strip()
    if not ext_clean.startswith("."):
        ext_clean = f".{ext_clean}"

    if ext_clean not in ALLOWED_EXTENSIONS:
        ext_clean = ".pdf"

    filename = f"{uuid4()}{ext_clean}"
    return f"servicios/{cliente_id}/{target_id}/{filename}"


async def save_document_file(
    upload_file: UploadFile,
    cliente_id: UUID,
    target_id: UUID,
) -> Tuple[str, str, int, str, str]:
    """
    Lee y escribe de forma segura un archivo subido vía streaming de chunks.
    
    Retorna la tupla: (sanit_filename, storage_key, size_bytes, mime_type, sha256_hash)
    Lanza ValueError si el archivo no cumple las reglas de seguridad.
    """
    orig_name = sanitize_original_filename(upload_file.filename)
    ext = Path(orig_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extensión '{ext}' no permitida. Formatos válidos: PDF, JPG, JPEG, PNG, WEBP.")

    storage_key = generate_storage_key(cliente_id, target_id, ext)
    file_path = resolve_safe_path(storage_key)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    sha256 = hashlib.sha256()
    total_size = 0
    detected_mime = ""

    try:
        # Asegurar lectura desde el inicio
        await upload_file.seek(0)
        first_chunk = await upload_file.read(CHUNK_SIZE_BYTES)
        if not first_chunk:
            raise ValueError("El archivo seleccionado está vacío (0 bytes).")

        # Validar tipo real por Magic Bytes
        detected_mime = detect_file_type_from_magic_bytes(first_chunk)

        # Abrir archivo en disco para escritura streaming
        with open(file_path, "wb") as f:
            # Procesar primer chunk
            f.write(first_chunk)
            sha256.update(first_chunk)
            total_size += len(first_chunk)

            if total_size > MAX_FILE_SIZE_BYTES:
                raise ValueError("El archivo excede el tamaño máximo permitido de 10 MiB.")

            # Procesar subsecuentes chunks
            while True:
                chunk = await upload_file.read(CHUNK_SIZE_BYTES)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE_BYTES:
                    raise ValueError("El archivo excede el tamaño máximo permitido de 10 MiB.")
                f.write(chunk)
                sha256.update(chunk)

    except Exception as err:
        # Si ocurre un error, eliminar inmediatamente el archivo parcial en disco
        delete_document_file(storage_key)
        if isinstance(err, ValueError):
            raise err
        raise ValueError(f"Error al guardar el archivo en almacenamiento: {err}")

    # Establecer permisos restrictivos en el archivo creado (0640)
    try:
        os.chmod(file_path, 0o640)
    except Exception:
        pass

    return orig_name, storage_key, total_size, detected_mime, sha256.hexdigest()


def delete_document_file(storage_key: str) -> bool:
    """
    Elimina un archivo físico del disco a partir de su clave de almacenamiento.
    """
    if not storage_key:
        return False

    try:
        file_path = resolve_safe_path(storage_key)
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
            return True
    except Exception:
        pass
    return False
