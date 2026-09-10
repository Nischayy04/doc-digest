import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings

CHUNK_SIZE = 1024 * 1024  # 1 MB, read incrementally so large files don't sit fully in memory


class UploadTooLargeError(Exception):
    def __init__(self, max_size_bytes: int):
        self.max_size_bytes = max_size_bytes
        super().__init__(f"Upload exceeds the {max_size_bytes} byte limit")


def save_upload_file(upload_file: UploadFile) -> tuple[str, int]:
    """Streams an uploaded file to disk under a generated name.

    Returns (file_path, size_in_bytes). Raises UploadTooLargeError (and
    cleans up the partial file) if the stream exceeds the configured limit.
    """
    storage_dir = Path(settings.storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)

    extension = Path(upload_file.filename or "").suffix
    destination = storage_dir / f"{uuid.uuid4()}{extension}"

    size = 0
    try:
        with destination.open("wb") as buffer:
            while chunk := upload_file.file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > settings.max_upload_size_bytes:
                    raise UploadTooLargeError(settings.max_upload_size_bytes)
                buffer.write(chunk)
    except UploadTooLargeError:
        destination.unlink(missing_ok=True)
        raise

    return str(destination), size
