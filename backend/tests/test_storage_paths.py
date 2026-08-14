from pathlib import PurePosixPath

from app.services.storage_paths import (
    incoming_dir_for_client,
    normalized_dir_for_client_pose,
    processed_dir_for_client_date,
)


def test_incoming_dir_includes_client_id():
    result = incoming_dir_for_client(client_id=7)
    assert PurePosixPath(result).name == "7"
    assert "photos_incoming" in result.as_posix()


def test_processed_dir_includes_client_id_and_date():
    result = processed_dir_for_client_date(client_id=7, date_str="2026-01-01")
    parts = result.as_posix().split("/")
    assert "7" in parts
    assert "2026-01-01" in parts
    assert parts.index("7") < parts.index("2026-01-01")


def test_normalized_dir_includes_client_and_pose():
    result = normalized_dir_for_client_pose(client_id=7, pose_id=3)
    parts = result.as_posix().split("/")
    assert "7" in parts
    assert "3" in parts
