from datetime import date, datetime

from app.core.migrate_to_multitenancy import migrate_to_multitenancy
from app.models.client import Client
from app.models.day_log import DayLog
from app.models.photo import Photo, ProcessingStatus
from app.models.pose import Pose
from app.models.user import User


def _seed_pre_migration_data(db_session):
    """Legt Pose/DayLog/Photo OHNE client_id an - simuliert den Stand vor
    der Mandantenfähigkeit (die Spalte existiert dank Task 13 bereits,
    ist hier aber bewusst NULL)."""
    pose = Pose(name="Front Double Biceps", sort_order=0)
    db_session.add(pose)
    db_session.flush()

    day_log = DayLog(date=date(2026, 1, 1), weight_kg=80.0)
    db_session.add(day_log)
    db_session.flush()

    photo = Photo(
        filename="test.jpg",
        original_path="photos_processed/2026-01-01/test.jpg",
        taken_at=datetime(2026, 1, 1, 12, 0, 0),
        status=ProcessingStatus.PROCESSED,
        pose_id=pose.id,
        day_log_id=day_log.id,
    )
    db_session.add(photo)
    db_session.commit()
    return pose, day_log, photo


def test_migration_creates_account_and_client(db_session):
    _seed_pre_migration_data(db_session)

    migrate_to_multitenancy(
        db_session,
        email="basti@example.com",
        password="Grindcore123!",
        display_name="Basti",
    )

    user = db_session.query(User).filter(User.email == "basti@example.com").first()
    assert user is not None
    assert user.account_type.value == "coach"

    client_row = db_session.query(Client).filter(Client.owner_id == user.id).first()
    assert client_row is not None
    assert client_row.name == "Mein Profil"


def test_migration_backfills_client_id_on_existing_rows(db_session):
    pose, day_log, photo = _seed_pre_migration_data(db_session)

    migrate_to_multitenancy(
        db_session,
        email="basti@example.com",
        password="Grindcore123!",
        display_name="Basti",
    )

    client_row = db_session.query(Client).first()
    db_session.refresh(pose)
    db_session.refresh(day_log)
    db_session.refresh(photo)
    assert pose.client_id == client_row.id
    assert day_log.client_id == client_row.id
    assert photo.client_id == client_row.id


def test_migration_is_a_noop_when_a_user_already_exists(db_session):
    _seed_pre_migration_data(db_session)
    migrate_to_multitenancy(
        db_session, email="basti@example.com", password="Grindcore123!", display_name="Basti"
    )
    user_count_after_first_run = db_session.query(User).count()

    migrate_to_multitenancy(
        db_session, email="basti@example.com", password="Grindcore123!", display_name="Basti"
    )
    user_count_after_second_run = db_session.query(User).count()

    assert user_count_after_first_run == user_count_after_second_run == 1
