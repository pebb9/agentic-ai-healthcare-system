# database.py — SQLite setup, Healthcare.csv import, slot seeding, and queries

import csv
import os
import random
import sqlite3
import uuid
from datetime import datetime, timedelta

from config import (
    DB_FILE, CSV_FILE, DOCTORS, DISEASE_SPECIALTY,
    _FIRST_M, _FIRST_F, _FIRST_O, _LAST, INSURERS,
)

random.seed(42)


# ── Helpers ───────────────────────────────────────────────────────────────────

def generate_booking_ref() -> str:
    return "BK-" + uuid.uuid4().hex[:8].upper()

def _random_name(gender: str) -> str:
    if gender == "Male":   return f"{random.choice(_FIRST_M)} {random.choice(_LAST)}"
    if gender == "Female": return f"{random.choice(_FIRST_F)} {random.choice(_LAST)}"
    return f"{random.choice(_FIRST_O)} {random.choice(_LAST)}"

def _random_dob(age: int) -> str:
    year = datetime.now().year - age
    return f"{year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"

def _random_insurance() -> str:
    return f"{random.choice(INSURERS)} – #DE{random.randint(10_000_000, 99_999_999)}"

def _resolve_csv_path(filename: str) -> str | None:
    candidates = [
        filename,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), filename),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", filename),
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
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            dob           TEXT,
            age           INTEGER,
            gender        TEXT,
            insurance     TEXT,
            symptoms      TEXT,
            symptom_count INTEGER,
            disease       TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id        TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            specialty TEXT NOT NULL
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id           TEXT PRIMARY KEY,
            booking_ref  TEXT NOT NULL UNIQUE,
            doctor_id    TEXT NOT NULL,
            patient_id   TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            status       TEXT NOT NULL
                         CHECK(status IN ('BOOKED','COMPLETED','CANCELLED')),
            reason       TEXT,
            created_at   TEXT NOT NULL,
            FOREIGN KEY (doctor_id)  REFERENCES doctors(id),
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
            FOREIGN KEY (patient_id)     REFERENCES patients(id),
            FOREIGN KEY (doctor_id)      REFERENCES doctors(id),
            FOREIGN KEY (appointment_id) REFERENCES appointments(id)
        )
    """)

    conn.commit()
    _seed_doctors(conn)
    _seed_patients(conn)
    _seed_slots(conn)
    conn.close()


# ── Seeders ───────────────────────────────────────────────────────────────────

def _seed_doctors(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0]
    if count > 0:
        print(f"  [DB] Doctors already loaded: {count} records")
        return
    rows = [(d["id"], d["name"], d["specialty"]) for d in DOCTORS]
    conn.executemany("INSERT OR IGNORE INTO doctors (id, name, specialty) VALUES (?,?,?)", rows)
    conn.commit()
    print(f"  [DB] Seeded {len(rows)} doctors.")


def _seed_patients(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    if count > 0:
        print(f"  [DB] Patients already loaded: {count:,} records")
        return

    path = _resolve_csv_path(CSV_FILE)
    if not path:
        print(f"  [DB] WARNING: {CSV_FILE} not found — skipping patient import.")
        return

    print(f"  [DB] Importing {path} …", end="", flush=True)
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            age    = int(row["Age"])
            gender = row["Gender"].strip()
            rows.append((
                f"PT-{int(row['Patient_ID']):05d}",
                _random_name(gender),
                _random_dob(age),
                age,
                gender,
                _random_insurance(),
                row["Symptoms"].strip(),
                int(row["Symptom_Count"]),
                row["Disease"].strip(),
            ))

    conn.executemany(
        """INSERT OR IGNORE INTO patients
           (id, name, dob, age, gender, insurance, symptoms, symptom_count, disease)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    print(f" {len(rows):,} patients imported.")


def _seed_slots(conn: sqlite3.Connection) -> None:
    seeded  = {r[0] for r in conn.execute("SELECT DISTINCT doctor_id FROM slots").fetchall()}
    missing = [d for d in DOCTORS if d["id"] not in seeded]
    if not missing:
        total = conn.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
        print(f"  [DB] Slots already seeded ({total:,} total).")
        return

    hours = ["09:00","10:00","11:00","13:00","14:00","15:00","16:00"]
    today = datetime.now()
    rows  = []
    for doc in missing:
        for offset in range(1, 15):
            date = today + timedelta(days=offset)
            if date.weekday() >= 5:
                continue
            for hour in hours:
                rows.append((doc["id"], f"{date.strftime('%Y-%m-%d')} {hour}", "free"))

    for row in rows:
        try:
            conn.execute("INSERT INTO slots (doctor_id, slot_key, status) VALUES (?,?,?)", row)
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    print(f"  [DB] Seeded {len(rows):,} slots for {len(missing)} doctor(s).")


# ── Patient queries ───────────────────────────────────────────────────────────

def get_patient(patient_id: str) -> sqlite3.Row | None:
    conn = get_connection()
    row  = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id.upper(),)).fetchone()
    conn.close()
    return row


def get_all_doctors() -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM doctors").fetchall()
    conn.close()
    return rows


def get_doctor(doctor_id: str) -> sqlite3.Row | None:
    conn = get_connection()
    row  = conn.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id.upper(),)).fetchone()
    conn.close()
    return row


# ── Slot queries ──────────────────────────────────────────────────────────────

def get_free_slots(doctor_id: str, from_dt: datetime, to_dt: datetime, limit: int = 5) -> list[sqlite3.Row]:
    conn     = get_connection()
    from_str = from_dt.strftime("%Y-%m-%d") + " 00:00"
    to_str   = to_dt.strftime("%Y-%m-%d")   + " 23:59"
    rows     = conn.execute(
        "SELECT slot_key FROM slots WHERE doctor_id=? AND status='free' AND slot_key>=? AND slot_key<=? ORDER BY slot_key LIMIT ?",
        (doctor_id.upper(), from_str, to_str, limit),
    ).fetchall()
    conn.close()
    return rows


def is_slot_free(doctor_id: str, slot_key: str) -> bool:
    conn = get_connection()
    row  = conn.execute("SELECT status FROM slots WHERE doctor_id=? AND slot_key=?", (doctor_id.upper(), slot_key)).fetchone()
    conn.close()
    return bool(row and row["status"] == "free")


def mark_slot_booked(doctor_id: str, slot_key: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE slots SET status='booked' WHERE doctor_id=? AND slot_key=?", (doctor_id.upper(), slot_key))
    conn.commit()
    conn.close()


def mark_slot_free(doctor_id: str, slot_key: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE slots SET status='free' WHERE doctor_id=? AND slot_key=?", (doctor_id.upper(), slot_key))
    conn.commit()
    conn.close()


# ── Appointment queries ───────────────────────────────────────────────────────

def create_appointment(appointment_id: str, ref: str, patient_id: str,
                        doctor_id: str, slot_key: str,
                        reason: str | None = None, status: str = "BOOKED") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO appointments (id,booking_ref,doctor_id,patient_id,scheduled_at,status,reason,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (appointment_id.upper(), ref, doctor_id.upper(), patient_id.upper(), slot_key, status.upper(), reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def get_appointment(appointment_id: str) -> sqlite3.Row | None:
    conn = get_connection()
    row  = conn.execute(
        "SELECT a.*, d.name AS doctor_name, d.specialty AS doctor_specialty, p.name AS patient_name FROM appointments a JOIN doctors d ON d.id=a.doctor_id JOIN patients p ON p.id=a.patient_id WHERE a.id=?",
        (appointment_id.upper(),),
    ).fetchone()
    conn.close()
    return row


def get_appointment_by_ref(ref: str) -> sqlite3.Row | None:
    conn = get_connection()
    row  = conn.execute(
        "SELECT a.*, d.name AS doctor_name, d.specialty AS doctor_specialty, p.name AS patient_name FROM appointments a JOIN doctors d ON d.id=a.doctor_id JOIN patients p ON p.id=a.patient_id WHERE a.booking_ref=?",
        (ref.strip(),),
    ).fetchone()
    conn.close()
    return row


def cancel_appointment_by_ref(ref: str) -> bool:
    conn    = get_connection()
    cursor  = conn.execute("UPDATE appointments SET status='CANCELLED' WHERE booking_ref=?", (ref.strip(),))
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_appointments_for_patient(patient_id: str, limit: int = 20) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT a.*, d.name AS doctor_name, d.specialty FROM appointments a JOIN doctors d ON d.id=a.doctor_id WHERE a.patient_id=? ORDER BY a.scheduled_at LIMIT ?",
        (patient_id.upper(), limit),
    ).fetchall()
    conn.close()
    return rows


def get_appointments_for_doctor(doctor_id: str, limit: int = 20) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT a.*, p.name AS patient_name FROM appointments a JOIN patients p ON p.id=a.patient_id WHERE a.doctor_id=? ORDER BY a.scheduled_at LIMIT ?",
        (doctor_id.upper(), limit),
    ).fetchall()
    conn.close()
    return rows


# ── Medical record queries ────────────────────────────────────────────────────

def create_medical_record(record_id: str, patient_id: str, doctor_id: str | None,
                           symptoms: str, symptom_count: int | None,
                           diagnosis: str | None, appointment_id: str | None = None) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO medical_records (id,patient_id,doctor_id,appointment_id,symptoms,symptom_count,diagnosis,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (record_id, patient_id.upper(), doctor_id.upper() if doctor_id else None,
         appointment_id.upper() if appointment_id else None,
         symptoms, symptom_count, diagnosis, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def get_medical_records_for_patient(patient_id: str, limit: int = 10) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM medical_records WHERE patient_id=? ORDER BY created_at DESC LIMIT ?",
        (patient_id.upper(), limit),
    ).fetchall()
    conn.close()
    return rows