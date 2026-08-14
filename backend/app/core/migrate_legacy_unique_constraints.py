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
"""
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
    conn.execute(text("PRAGMA foreign_keys=OFF"))
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
    conn.execute(text("PRAGMA foreign_keys=ON"))


def _rebuild_day_logs_table(conn: Connection) -> None:
    conn.execute(text("PRAGMA foreign_keys=OFF"))
    conn.execute(text("DROP INDEX IF EXISTS ix_day_logs_date"))
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
    conn.execute(text("PRAGMA foreign_keys=ON"))


def fix_legacy_unique_constraints(engine: Engine) -> None:
    """Entfernt legacy Single-Column-UNIQUE-Constraints auf
    `poses.name` und `day_logs.date`, die aus der Zeit vor der
    Mandantenfähigkeit stammen (siehe Modul-Docstring). Muss bei jedem
    Start laufen, bevor `migrate_to_multitenancy()` oder irgendein
    Code, der Poses/DayLogs pro Client anlegt, ausgeführt wird.
    Idempotent und sicher bei fehlenden Tabellen (frische DB vor
    `create_all()` bzw. Tabelle existiert schlicht noch nicht)."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        if "poses" in existing_tables and _poses_has_legacy_unique(conn):
            _rebuild_poses_table(conn)
        if "day_logs" in existing_tables and _day_logs_has_legacy_unique(conn):
            _rebuild_day_logs_table(conn)
