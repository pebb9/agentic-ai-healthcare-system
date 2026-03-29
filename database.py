# database.py — SQLite setup, CSV seeding, slot seeding, and queries

import csv
import os
import random
import sqlite3
import string
from datetime import datetime, timedelta

from config import (
    DB_FILE,
    DOCTORS_CSV,
    PATIENTS_CSV,
    APPOINTMENTS_CSV,
    MEDICAL_RECORDS_CSV,
)

random.seed(42)


# ── Helpers ───────────────────────────────────────────────────────────────────

def generate_booking_ref() -> str:
    return "BK-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _resolve_csv_path(filename: str) -> str | None:
    candidates = [
        filename,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), filename),
    ]
    return next((p for p in candidates if os.path.exists(p)), None)


# ── Connection ────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create tables, seed from CSVs, and generate doctor slots."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id    TEXT PRIMARY KEY,
            name  TEXT NOT NULL,
            role  TEXT NOT NULL CHECK(role IN ('DOCTOR', 'PATIENT'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL UNIQUE,
            specialty  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id       TEXT PRIMARY KEY,
            user_id  TEXT NOT NULL UNIQUE,
            dob      TEXT,
            age      INTEGER,
            gender   TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id            TEXT PRIMARY KEY,
            booking_ref   TEXT NOT NULL UNIQUE,
            doctor_id     TEXT NOT NULL,
            patient_id    TEXT NOT NULL,
            scheduled_at  TEXT NOT NULL,
            status        TEXT NOT NULL
                          CHECK(status IN ('BOOKED', 'COMPLETED', 'CANCELLED')),
            reason        TEXT,
            created_at    TEXT NOT NULL,
            FOREIGN KEY (doctor_id) REFERENCES doctors(id),
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            UNIQUE (doctor_id, scheduled_at)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS medical_records (
            id             TEXT PRIMARY KEY,
            patient_id     TEXT NOT NULL,
            doctor_id      TEXT,
            appointment_id TEXT,
            symptoms       TEXT,
            symptom_count  INTEGER,
            diagnosis      TEXT,
            created_at     TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id),
            FOREIGN KEY (appointment_id) REFERENCES appointments(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS slots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id TEXT NOT NULL,
            slot_key  TEXT NOT NULL,
            status    TEXT NOT NULL DEFAULT 'free'
                      CHECK(status IN ('free', 'booked')),
            UNIQUE (doctor_id, slot_key),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )
    """)

    conn.commit()

    _seed_doctors(conn)
    _seed_patients(conn)
    _seed_appointments(conn)
    _seed_medical_records(conn)
    _seed_slots_from_doctors(conn)

    conn.close()


# ── Seeders ───────────────────────────────────────────────────────────────────

def _seed_doctors(conn: sqlite3.Connection) -> None:
    path = _resolve_csv_path(DOCTORS_CSV)
    if not path:
        print(f"  [DB] WARNING: {DOCTORS_CSV} not found — skipping doctor seed.")
        return

    count = conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0]
    if count > 0:
        print(f"  [DB] Doctors already loaded: {count:,} records")
        return

    print(f"  [DB] Importing doctors from {path} …", end="", flush=True)

    user_rows = []
    doctor_rows = []

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            doctor_id = row["doctor_id"].strip().upper()
            user_id = f"USER-{doctor_id}"
            name = row["name"].strip()
            specialty = row["specialty"].strip()

            user_rows.append((user_id, name, "DOCTOR"))
            doctor_rows.append((doctor_id, user_id, specialty))

    conn.executemany(
        "INSERT OR IGNORE INTO users (id, name, role) VALUES (?, ?, ?)",
        user_rows,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO doctors (id, user_id, specialty) VALUES (?, ?, ?)",
        doctor_rows,
    )
    conn.commit()
    print(f" {len(doctor_rows):,} doctors imported.")


def _seed_patients(conn: sqlite3.Connection) -> None:
    path = _resolve_csv_path(PATIENTS_CSV)
    if not path:
        print(f"  [DB] WARNING: {PATIENTS_CSV} not found — skipping patient seed.")
        return

    count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    if count > 0:
        print(f"  [DB] Patients already loaded: {count:,} records")
        return

    print(f"  [DB] Importing patients from {path} …", end="", flush=True)

    user_rows = []
    patient_rows = []

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            patient_id = row["patient_id"].strip().upper()
            user_id = f"USER-{patient_id}"
            name = row["name"].strip()
            dob = row["dob"].strip()
            age = int(row["age"])
            gender = row["gender"].strip()

            user_rows.append((user_id, name, "PATIENT"))
            patient_rows.append((patient_id, user_id, dob, age, gender))

    conn.executemany(
        "INSERT OR IGNORE INTO users (id, name, role) VALUES (?, ?, ?)",
        user_rows,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO patients (id, user_id, dob, age, gender) VALUES (?, ?, ?, ?, ?)",
        patient_rows,
    )
    conn.commit()
    print(f" {len(patient_rows):,} patients imported.")


def _seed_appointments(conn: sqlite3.Connection) -> None:
    path = _resolve_csv_path(APPOINTMENTS_CSV)
    if not path:
        print(f"  [DB] WARNING: {APPOINTMENTS_CSV} not found — skipping appointment seed.")
        return

    count = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    if count > 0:
        print(f"  [DB] Appointments already loaded: {count:,} records")
        return

    print(f"  [DB] Importing appointments from {path} …", end="", flush=True)

    rows = []

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((
                row["appointment_id"].strip().upper(),
                row["booking_ref"].strip(),
                row["doctor_id"].strip().upper(),
                row["patient_id"].strip().upper(),
                row["scheduled_at"].strip(),
                row["status"].strip().upper(),
                row["reason"].strip(),
                row["created_at"].strip(),
            ))

    conn.executemany(
        """
        INSERT OR IGNORE INTO appointments (
            id, booking_ref, doctor_id, patient_id,
            scheduled_at, status, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    print(f" {len(rows):,} appointments imported.")


def _seed_medical_records(conn: sqlite3.Connection) -> None:
    path = _resolve_csv_path(MEDICAL_RECORDS_CSV)
    if not path:
        print(f"  [DB] WARNING: {MEDICAL_RECORDS_CSV} not found — skipping medical record seed.")
        return

    count = conn.execute("SELECT COUNT(*) FROM medical_records").fetchone()[0]
    if count > 0:
        print(f"  [DB] Medical records already loaded: {count:,} records")
        return

    print(f"  [DB] Importing medical records from {path} …", end="", flush=True)

    rows = []

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            doctor_id = row["doctor_id"].strip().upper() or None
            appointment_id = row["appointment_id"].strip().upper() or None
            diagnosis = row["diagnosis"].strip() or None

            rows.append((
                row["record_id"].strip().upper(),
                row["patient_id"].strip().upper(),
                doctor_id,
                appointment_id,
                row["symptoms"].strip(),
                int(row["symptom_count"]) if row["symptom_count"].strip() else None,
                diagnosis,
                row["created_at"].strip(),
            ))

    conn.executemany(
        """
        INSERT OR IGNORE INTO medical_records (
            id, patient_id, doctor_id, appointment_id,
            symptoms, symptom_count, diagnosis, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    print(f" {len(rows):,} medical records imported.")


def _seed_slots_from_doctors(conn: sqlite3.Connection) -> None:
    doctor_ids = [r["id"] for r in conn.execute("SELECT id FROM doctors").fetchall()]
    if not doctor_ids:
        print("  [DB] No doctors found — skipping slot seed.")
        return

    seeded = {r[0] for r in conn.execute("SELECT DISTINCT doctor_id FROM slots").fetchall()}
    missing = [doctor_id for doctor_id in doctor_ids if doctor_id not in seeded]

    if not missing:
        total = conn.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
        print(f"  [DB] Loaded existing calendar ({total} slots)")
        return

    print(f"  [DB] Seeding slots for {len(missing)} doctor(s): {missing}")
    _seed_slots(conn, missing)


def _seed_slots(conn: sqlite3.Connection, doctor_ids: list[str]) -> None:
    """Insert two weeks of free working slots for the given doctors."""
    hours = ["09:00", "10:00", "11:00", "13:00", "14:00", "15:00"]
    today = datetime.now()
    rows = []

    for doctor_id in doctor_ids:
        for offset in range(1, 15):
            date = today + timedelta(days=offset)
            if date.weekday() >= 5:
                continue
            for hour in hours:
                rows.append((doctor_id, f"{date.strftime('%Y-%m-%d')} {hour}", "free"))

    for row in rows:
        try:
            conn.execute(
                "INSERT INTO slots (doctor_id, slot_key, status) VALUES (?, ?, ?)",
                row,
            )
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    print(f"  [DB] Inserted {len(rows)} slots for {len(doctor_ids)} doctor(s)")


# ── User / doctor / patient queries ───────────────────────────────────────────

def get_user(user_id: str) -> sqlite3.Row | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id.upper(),),
    ).fetchone()
    conn.close()
    return row


def get_doctor(doctor_id: str) -> sqlite3.Row | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT d.*, u.name, u.role
        FROM doctors d
        JOIN users u ON u.id = d.user_id
        WHERE d.id = ?
        """,
        (doctor_id.upper(),),
    ).fetchone()
    conn.close()
    return row

def get_all_doctors() -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT d.*, u.name, u.role
        FROM doctors d
        JOIN users u ON u.id = d.user_id
        ORDER BY d.id
        """
    ).fetchall()
    conn.close()
    return rows


def get_doctor_by_user(user_id: str) -> sqlite3.Row | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT d.*, u.name, u.role
        FROM doctors d
        JOIN users u ON u.id = d.user_id
        WHERE d.user_id = ?
        """,
        (user_id.upper(),),
    ).fetchone()
    conn.close()
    return row


def get_patient(patient_id: str) -> sqlite3.Row | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT p.*, u.name, u.role
        FROM patients p
        JOIN users u ON u.id = p.user_id
        WHERE p.id = ?
        """,
        (patient_id.upper(),),
    ).fetchone()
    conn.close()
    return row


def get_patient_by_user(user_id: str) -> sqlite3.Row | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT p.*, u.name, u.role
        FROM patients p
        JOIN users u ON u.id = p.user_id
        WHERE p.user_id = ?
        """,
        (user_id.upper(),),
    ).fetchone()
    conn.close()
    return row


# ── Medical record queries ────────────────────────────────────────────────────

def get_medical_records_for_patient(patient_id: str, limit: int = 10) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM medical_records
        WHERE patient_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (patient_id.upper(), limit),
    ).fetchall()
    conn.close()
    return rows


def create_medical_record(
    record_id: str,
    patient_id: str,
    doctor_id: str | None,
    symptoms: str,
    symptom_count: int | None,
    diagnosis: str | None,
    appointment_id: str | None = None,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO medical_records (
            id, patient_id, doctor_id, appointment_id,
            symptoms, symptom_count, diagnosis, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record_id.upper(),
            patient_id.upper(),
            doctor_id.upper() if doctor_id else None,
            appointment_id.upper() if appointment_id else None,
            symptoms,
            symptom_count,
            diagnosis,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()


# ── Slot queries ──────────────────────────────────────────────────────────────

def get_free_slots(doctor_id: str, from_dt: datetime,
                   to_dt: datetime, limit: int = 5) -> list[sqlite3.Row]:
    conn = get_connection()
    from_str = from_dt.strftime("%Y-%m-%d") + " 00:00"
    to_str = to_dt.strftime("%Y-%m-%d") + " 23:59"
    rows = conn.execute(
        """
        SELECT slot_key
        FROM slots
        WHERE doctor_id = ?
          AND status = 'free'
          AND slot_key >= ?
          AND slot_key <= ?
        ORDER BY slot_key
        LIMIT ?
        """,
        (doctor_id.upper(), from_str, to_str, limit),
    ).fetchall()
    conn.close()
    return rows


def is_slot_free(doctor_id: str, slot_key: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT status FROM slots WHERE doctor_id = ? AND slot_key = ?",
        (doctor_id.upper(), slot_key),
    ).fetchone()
    conn.close()
    return bool(row and row["status"] == "free")


def mark_slot_booked(doctor_id: str, slot_key: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE slots SET status = 'booked' WHERE doctor_id = ? AND slot_key = ?",
        (doctor_id.upper(), slot_key),
    )
    conn.commit()
    conn.close()


# ── Appointment queries ───────────────────────────────────────────────────────

def create_appointment(
    appointment_id: str,
    ref: str,
    patient_id: str,
    doctor_id: str,
    slot_key: str,
    reason: str | None = None,
    status: str = "BOOKED",
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO appointments (
            id, booking_ref, doctor_id, patient_id,
            scheduled_at, status, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            appointment_id.upper(),
            ref,
            doctor_id.upper(),
            patient_id.upper(),
            slot_key,
            status.upper(),
            reason,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()


def get_appointment(appointment_id: str) -> sqlite3.Row | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT a.*, d.specialty, du.name AS doctor_name, pu.name AS patient_name
        FROM appointments a
        JOIN doctors d  ON d.id = a.doctor_id
        JOIN users du   ON du.id = d.user_id
        JOIN patients p ON p.id = a.patient_id
        JOIN users pu   ON pu.id = p.user_id
        WHERE a.id = ?
        """,
        (appointment_id.upper(),),
    ).fetchone()
    conn.close()
    return row


def get_appointment_by_ref(ref: str) -> sqlite3.Row | None:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT a.*, d.specialty, du.name AS doctor_name, pu.name AS patient_name
        FROM appointments a
        JOIN doctors d  ON d.id = a.doctor_id
        JOIN users du   ON du.id = d.user_id
        JOIN patients p ON p.id = a.patient_id
        JOIN users pu   ON pu.id = p.user_id
        WHERE a.booking_ref = ?
        """,
        (ref,),
    ).fetchone()
    conn.close()
    return row


def get_appointments_for_doctor(doctor_id: str, limit: int = 20) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT a.*, pu.name AS patient_name
        FROM appointments a
        JOIN patients p ON p.id = a.patient_id
        JOIN users pu   ON pu.id = p.user_id
        WHERE a.doctor_id = ?
        ORDER BY a.scheduled_at
        LIMIT ?
        """,
        (doctor_id.upper(), limit),
    ).fetchall()
    conn.close()
    return rows


def get_appointments_for_patient(patient_id: str, limit: int = 20) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT a.*, du.name AS doctor_name, d.specialty
        FROM appointments a
        JOIN doctors d ON d.id = a.doctor_id
        JOIN users du  ON du.id = d.user_id
        WHERE a.patient_id = ?
        ORDER BY a.scheduled_at
        LIMIT ?
        """,
        (patient_id.upper(), limit),
    ).fetchall()
    conn.close()
    return rows