"""
storage_sync arbeitet gegen echte lokale Dateien im settings.data_dir -
die R2-Anbindung selbst wird mit einem Fake-Client getestet (kein echter
Netzwerkzugriff in Tests), die Kern-Logik (wann wird gesynct, wann nicht)
ist aber dieselbe wie im echten Betrieb.
"""
from pathlib import Path

import pytest

from app.services import storage_sync


class FakeR2Client:
    """Simuliert boto3's S3-Client-Interface, soweit storage_sync es nutzt."""

    def __init__(self):
        self.uploaded: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def upload_file(self, local_path, bucket, key):
        self.uploaded[key] = Path(local_path).read_bytes()

    def download_file(self, bucket, key, local_path):
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(self.uploaded[key])

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)
        self.uploaded.pop(Key, None)

    def head_object(self, Bucket, Key):
        if Key not in self.uploaded:
            from botocore.exceptions import ClientError
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")


@pytest.fixture()
def fake_r2(monkeypatch, tmp_path):
    fake_client = FakeR2Client()
    monkeypatch.setattr(storage_sync, "_r2_client", lambda: fake_client)
    monkeypatch.setattr(storage_sync.settings, "data_dir", tmp_path)
    monkeypatch.setattr(storage_sync.settings, "storage_backend", "r2")
    monkeypatch.setattr(storage_sync.settings, "r2_bucket", "test-bucket")
    return fake_client


def test_push_uploads_local_file_to_r2(fake_r2, tmp_path):
    local_file = tmp_path / "photos_processed" / "1" / "a.jpg"
    local_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"fake-jpeg-bytes")

    storage_sync.push("photos_processed/1/a.jpg")

    assert fake_r2.uploaded["photos_processed/1/a.jpg"] == b"fake-jpeg-bytes"


def test_push_is_noop_when_backend_is_local(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_sync.settings, "storage_backend", "local")
    # Kein Fake-Client gesetzt - würde eine echte Netzwerkanfrage auslösen
    # und crashen, wenn push() ihn fälschlich aufrufen würde.
    storage_sync.push("irrelevant/path.jpg")  # darf nicht werfen


def test_ensure_local_downloads_missing_file_from_r2(fake_r2, tmp_path):
    fake_r2.uploaded["photos_processed/1/a.jpg"] = b"from-r2"
    local_file = tmp_path / "photos_processed" / "1" / "a.jpg"
    assert not local_file.exists()

    storage_sync.ensure_local("photos_processed/1/a.jpg")

    assert local_file.exists()
    assert local_file.read_bytes() == b"from-r2"


def test_ensure_local_skips_download_if_already_present_locally(fake_r2, tmp_path):
    local_file = tmp_path / "photos_processed" / "1" / "a.jpg"
    local_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"already-here")

    storage_sync.ensure_local("photos_processed/1/a.jpg")

    assert local_file.read_bytes() == b"already-here"
    assert "photos_processed/1/a.jpg" not in fake_r2.uploaded  # nie hochgeladen, nur lokal geprüft


def test_delete_remote_removes_from_r2(fake_r2):
    fake_r2.uploaded["photos_processed/1/a.jpg"] = b"data"

    storage_sync.delete_remote("photos_processed/1/a.jpg")

    assert "photos_processed/1/a.jpg" not in fake_r2.uploaded
    assert "photos_processed/1/a.jpg" in fake_r2.deleted
