from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path


class LocalSecretStore:
    """Local-only provider secrets with atomic writes and restrictive permissions."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    def get_provider(self, provider: str) -> dict:
        return self._read().get(provider, {})

    def set_provider(self, provider: str, values: dict) -> None:
        with self._lock:
            data = self._read()
            current = data.get(provider, {})
            data[provider] = {**current, **values}
            self._write(data)

    def delete_provider_secret(self, provider: str, key: str) -> None:
        with self._lock:
            data = self._read()
            if provider in data:
                data[provider].pop(key, None)
                self._write(data)

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError("本地 Provider 密钥文件无法读取") from exc

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            temporary.unlink(missing_ok=True)
