from pathlib import Path

from PIL import Image

from app.models.client import Client
from app.models.user import User
from app.services.folder_sync import sync_incoming_folder
from app.services.storage_paths import incoming_dir_for_client


def test_sync_compresses_large_incoming_photo(db_session, monkeypatch, tmp_path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)

    user = User(email="folder-sync@example.com", password_hash="x", display_name="Folder Sync")
    db_session.add(user)
    db_session.commit()
    client = Client(owner_id=user.id, name="Folder Sync Client")
    db_session.add(client)
    db_session.commit()

    incoming_dir = incoming_dir_for_client(client.id)
    incoming_dir.mkdir(parents=True)

    # Großes Test-Bild (4000x3000, deutlich über der 2500px-Grenze).
    large_image_path = incoming_dir / "big.jpg"
    Image.new("RGB", (4000, 3000), color="red").save(large_image_path, "JPEG", quality=100)
    original_size = large_image_path.stat().st_size

    sync_incoming_folder(db_session, client_id=client.id)

    with Image.open(large_image_path) as img:
        assert max(img.size) <= 2500
    assert large_image_path.stat().st_size < original_size
