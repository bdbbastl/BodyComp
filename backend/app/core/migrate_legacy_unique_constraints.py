"""
Fix für einen echten Bug in der realen Legacy-Datenbank: als `Pose.name`
und `DayLog.date` noch global-unique (single-tenant) waren, hat SQLite
dafür zwei unterschiedliche physische Constraint-Formen erzeugt:

- `poses`: ein INLINE `UNIQUE (name)` im `CREATE TABLE` -> SQLite legt
  dafür einen sogenannten Autoindex an (z.B. `sqlite_autoindex_poses_1`),
  der sich NICHT per `DROP INDEX` entfernen lässt ("index associated
  with a UNIQUE or PRIMARY KEY constraint cannot be dropped"). Um ihn
  loszuwerden, muss die Tabelle per SQLite-Standardverfahren neu gebaut
  werden (temp-Tabelle anlegen, Daten kopieren, alte Tabelle droppen,
  neue umbenennen).
- `day_logs`: ein SEPARATER, benannter `UNIQUE INDEX ix_day_logs_date`
  -> lässt sich einfach per `DROP INDEX IF EXISTS` entfernen.

Weder `run_lightweight_migrations()` (fügt nur die rohe `client_id`-
Spalte hinzu) noch das einmalige `migrate_to_multitenancy()` (reine
Daten-Migration, fasst das Schema nicht an) haben diese alten
Constraints je entfernt. Ergebnis: das Anlegen eines zweiten Client
schlägt beim Seeden der Standard-Posen mit
`sqlite3.IntegrityError: UNIQUE constraint failed: poses.name` fehl,
weil der alte global-unique Autoindex auf `poses.name` weiterhin aktiv
ist - obwohl das aktuelle ORM-Model dafür längst den korrekten
Composite-UniqueConstraint `(client_id, name)` verwendet
(siehe app/models/pose.py).

Diese Funktion läuft bei JEDEM Start (nicht nur beim einmaligen
Daten-Migrationslauf), erkennt die alte Schema-Form anhand der
tatsächlichen SQLite-Constraints (nicht anhand von Datenzuständen) und
ist idempotent: eine bereits reparierte DB oder eine frisch per
`create_all()` angelegte DB (die von Anfang an die korrekten
Composite-Constraints hat) wird unverändert gelassen.

Hinweis zu `day_logs`: nach dem reinen `DROP INDEX` fehlt der neuen
Composite-Unique-Constraint `(client_id, date)` noch die DB-seitige
Durchsetzung (ein gedropptes Legacy-Index fügt nicht automatisch den
neuen Constraint hinzu). Für echtes Defense-in-Depth analog zu `poses`
wird `day_logs` deshalb ebenfalls neu aufgebaut, sobald der alte
Index gefunden wird - Row-Anzahl bei `day_logs` ist typischerweise
klein (POC/Single-User-Historie), der Table-Rebuild ist also günstig
und konsistent mit der `poses`-Behandlung.

Wichtig - Nicht-Atomarität von DDL auf SQLite via pysqlite:
`engine.begin()` schützt normale DML-Statements (INSERT/UPDATE/DELETE)
in einer echten Transaktion, aber SQLite via pysqlite committet
CREATE/DROP/ALTER TABLE NICHT transaktional mit - jedes DDL-Statement
wird sofort durable, sobald es ausgeführt wird (der von SQLAlchemys
Doku beschriebene "transactional DDL"-Workaround
(`isolation_level=None` + expliziter `BEGIN`-Event-Listener) ist im
geteilten Engine-Setup in `app/core/database.py` bewusst NICHT
eingerichtet, da das alle Verbindungen der App beträfe, nicht nur
diesen Fix - zu invasiv für den Scope hier). Ein Crash zwischen
`CREATE TABLE poses_new` und dem finalen RENAME lässt `poses_new`
also dauerhaft stehen. Dagegen zwei Maßnahmen:

1. Jede Rebuild-Funktion räumt am Anfang per `DROP TABLE IF EXISTS
   <name>_new` einen eventuellen Rest eines abgebrochenen Vorlaufs weg
   - das macht den Rebuild resumable: ein Crash mitten im Rebuild
   führt beim nächsten Boot zu einem sauberen Neuversuch statt zu
   einer Crash-Loop mit `OperationalError: table poses_new already
   exists`.
2. `fix_legacy_unique_constraints()` erstellt EINMALIG, bevor der
   erste tatsächliche Rebuild beginnt, eine Datei-Kopie der DB
   (`shutil.copy2`, Pfad via `backup_path_factory`) als zusätzliches
   Sicherheitsnetz für den unwahrscheinlichen Fall, dass trotz Punkt 1
   etwas schiefgeht. Das ist deutlich einfacher und besser abgegrenzt
   als Punkt (2a) - echte transaktionale DDL für die komplette Engine
   einzurichten hätte App-weite Nebenwirkungen und ist für diesen
   punktuellen Schema-Fix nicht gerechtfertigt.
"""
import shutil
from pathlib import Path
from typing import Callable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine, Connection


def _poses_has_legacy_unique(conn: Connection) -> bool:
    """True, wenn `poses` einen Single-Column-UNIQUE-Constraint/Index
    auf `name` allein hat (Autoindex aus inline `UNIQUE (name)`), der
    NICHT der aktuelle Composite-Constraint `(client_id, name)` ist."""
    inspector = inspect(conn)
    for uc in inspector.get_unique_constraints("poses"):
        if uc["column_names"] == ["name"]:
            return True
    for idx in inspector.get_indexes("poses"):
        if idx.get("unique") and idx.get("column_names") == ["name"]:
            return True
    return False


def _day_logs_has_legacy_unique(conn: Connection) -> bool:
    """True, wenn `day_logs` einen Single-Column-UNIQUE-Index auf
    `date` allein hat (egal ob per Name `ix_day_logs_date` oder anders
    benannt - robust per Spalten-Signatur geprüft)."""
    inspector = inspect(conn)
    for uc in inspector.get_unique_constraints("day_logs"):
        if uc["column_names"] == ["date"]:
            return True
    for idx in inspector.get_indexes("day_logs"):
        if idx.get("unique") and idx.get("column_names") == ["date"]:
            return True
    return False


def _rebuild_poses_table(conn: Connection) -> None:
    # Wichtig: `engine.begin()` macht DDL (CREATE/DROP/ALTER TABLE) auf
    # SQLite via pysqlite NICHT transaktional (siehe Moduldocstring) -
    # ein Crash zwischen `CREATE TABLE poses_new` und dem finalen
    # RENAME lässt `poses_new` dauerhaft stehen. Ohne dieses `DROP
    # TABLE IF EXISTS` würde der nächste Start dann mit
    # `OperationalError: table poses_new already exists` in einer
    # Crash-Loop enden. Mit dem DROP hier wird der Rebuild beim
    # nächsten Boot stattdessen einfach sauber neu gestartet.
    conn.execute(text("DROP TABLE IF EXISTS poses_new"))
    conn.execute(text(
        "CREATE TABLE poses_new ("
        "id INTEGER NOT NULL PRIMARY KEY, "
        # client_id ist hier absichtlich NULLABLE (nicht NOT NULL wie im
        # finalen ORM-Model): dieser Fix läuft VOR der einmaligen
        # Daten-Migration (migrate_to_multitenancy), die client_id erst
        # nachträglich befüllt - genau wie schon die bestehende
        # run_lightweight_migrations() die Spalte nullable per ALTER
        # TABLE ADD COLUMN anlegt. Ein NOT NULL hier würde den Rebuild
        # auf einer noch nicht migrierten Legacy-DB mit
        # IntegrityError zum Absturz bringen.
        "client_id INTEGER REFERENCES clients (id) ON DELETE CASCADE, "
        "name VARCHAR(100) NOT NULL, "
        "sort_order INTEGER NOT NULL, "
        "created_at DATETIME NOT NULL, "
        "CONSTRAINT uq_pose_client_name UNIQUE (client_id, name))"
    ))
    conn.execute(text(
        "INSERT INTO poses_new (id, client_id, name, sort_order, created_at) "
        "SELECT id, client_id, name, sort_order, created_at FROM poses"
    ))
    conn.execute(text("DROP TABLE poses"))
    conn.execute(text("ALTER TABLE poses_new RENAME TO poses"))
    conn.execute(text("CREATE INDEX ix_poses_client_id ON poses (client_id)"))


def _rebuild_day_logs_table(conn: Connection) -> None:
    conn.execute(text("DROP INDEX IF EXISTS ix_day_logs_date"))
    # Gleiche Begründung wie in _rebuild_poses_table: macht den Rebuild
    # resumable nach einem Crash mitten im vorherigen Versuch.
    conn.execute(text("DROP TABLE IF EXISTS day_logs_new"))
    conn.execute(text(
        "CREATE TABLE day_logs_new ("
        "id INTEGER NOT NULL PRIMARY KEY, "
        # Siehe Kommentar in _rebuild_poses_table: client_id ist hier
        # bewusst nullable, da dieser Fix vor der Daten-Migration läuft.
        "client_id INTEGER REFERENCES clients (id) ON DELETE CASCADE, "
        "date DATE NOT NULL, "
        "weight_kg FLOAT, "
        "notes VARCHAR(500), "
        "created_at DATETIME NOT NULL, "
        "updated_at DATETIME NOT NULL, "
        "CONSTRAINT uq_daylog_client_date UNIQUE (client_id, date))"
    ))
    conn.execute(text(
        "INSERT INTO day_logs_new "
        "(id, client_id, date, weight_kg, notes, created_at, updated_at) "
        "SELECT id, client_id, date, weight_kg, notes, created_at, updated_at "
        "FROM day_logs"
    ))
    conn.execute(text("DROP TABLE day_logs"))
    conn.execute(text("ALTER TABLE day_logs_new RENAME TO day_logs"))
    conn.execute(text("CREATE INDEX ix_day_logs_client_id ON day_logs (client_id)"))
    conn.execute(text("CREATE INDEX ix_day_logs_date ON day_logs (date)"))


def _default_backup_path(db_path: Path) -> Path:
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return db_path.with_name(f"{db_path.name}.pre-constraint-fix-{ts}")


def _sqlite_file_path(engine: Engine) -> Path | None:
    """Extrahiert den Dateipfad aus der Engine-URL, sofern es ein
    echtes Datei-SQLite ist (nicht `:memory:` - dort ist ein
    Datei-Backup weder möglich noch nötig, z.B. in Tests)."""
    url = engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def fix_legacy_unique_constraints(
    engine: Engine,
    backup_path_factory: Callable[[Path], Path] = _default_backup_path,
) -> None:
    """Entfernt legacy Single-Column-UNIQUE-Constraints auf
    `poses.name` und `day_logs.date`, die aus der Zeit vor der
    Mandantenfähigkeit stammen (siehe Modul-Docstring). Muss bei jedem
    Start laufen, bevor `migrate_to_multitenancy()` oder irgendein
    Code, der Poses/DayLogs pro Client anlegt, ausgeführt wird.
    Idempotent und sicher bei fehlenden Tabellen (frische DB vor
    `create_all()` bzw. Tabelle existiert schlicht noch nicht) sowie
    resumable nach einem Crash mitten in einem vorherigen Rebuild
    (siehe Modul-Docstring zur Nicht-Atomarität von SQLite-DDL).

    Erstellt einmalig, bevor der erste tatsächliche Rebuild beginnt,
    eine Datei-Kopie der DB als zusätzliches Sicherheitsnetz - nur
    wenn überhaupt ein Legacy-Constraint gefunden wurde (kein
    unnötiger Kopieraufwand auf bereits sauberen/frischen DBs)."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    db_file = _sqlite_file_path(engine)
    backup_done = False

    def _ensure_backup_once() -> None:
        nonlocal backup_done
        if backup_done or db_file is None or not db_file.exists():
            return
        backup_path = backup_path_factory(db_file)
        shutil.copy2(db_file, backup_path)
        backup_done = True

    with engine.begin() as conn:
        if "poses" in existing_tables and _poses_has_legacy_unique(conn):
            _ensure_backup_once()
            _rebuild_poses_table(conn)
        if "day_logs" in existing_tables and _day_logs_has_legacy_unique(conn):
            _ensure_backup_once()
            _rebuild_day_logs_table(conn)
