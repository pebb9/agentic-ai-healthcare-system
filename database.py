# database.py — SQLite setup, patient import, slot seeding, and queries

import csv
import os
import random
import sqlite3
import string
from datetime import datetime, timedelta

from config import DB_FILE, CSV_FILE, DOCTORS, _FIRST_M, _FIRST_F, _FIRST_O, _LAST, INSURERS

random.seed(42)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _random_name(gender: str) -> str:
    if gender == "Male":   return f"{random.choice(_FIRST_M)} {random.choice(_LAST)}"
    if gender == "Female": return f"{random.choice(_FIRST_F)} {random.choice(_LAST)}"
    return f"{random.choice(_FIRST_O)} {random.choice(_LAST)}"

def _random_dob(age: int) -> str:
    return f"{2026 - age}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"

def _random_insurance() -> str:
    return f"{random.choice(INSURERS)} – #DE{random.randint(10_000_000, 99_999_999)}"

def generate_booking_ref() -> str:
    return "BK-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


# ── Connection ────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create tables, import patient CSV, and seed doctor slots."""
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id  TEXT PRIMARY KEY,
            name        TEXT,
            dob         TEXT,
            age         INTEGER,
            gender      TEXT,
            insurance   TEXT,
            symptoms    TEXT,
            disease     TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS slots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id TEXT NOT NULL,
            slot_key  TEXT NOT NULL,
            status    TEXT NOT NULL DEFAULT 'free'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_ref         TEXT NOT NULL,
            patient_id          TEXT,
            patient_name        TEXT NOT NULL,
            patient_dob         TEXT,
            patient_age         INTEGER,
            patient_gender      TEXT,
            patient_insurance   TEXT,
            presenting_symptoms TEXT,
            doctor_id           TEXT NOT NULL,
            doctor_name         TEXT NOT NULL,
            slot_key            TEXT NOT NULL,
            booked_at           TEXT NOT NULL
        )
    """)
    conn.commit()

    patient_count = cur.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    if patient_count == 0:
        _import_csv(conn)
    else:
        print(f"  [DB] Patients already loaded: {patient_count:,} records")

    seeded  = {r[0] for r in cur.execute("SELECT DISTINCT doctor_id FROM slots").fetchall()}
    missing = [d for d in DOCTORS if d["id"] not in seeded]
    if missing:
        print(f"  [DB] Seeding {len(missing)} doctor(s): {[d['name'] for d in missing]}")
        _seed_slots(conn, missing)
    else:
        total = cur.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
        print(f"  [DB] Loaded existing calendar ({total} slots)")

    conn.close()


# ── Import ────────────────────────────────────────────────────────────────────

def _import_csv(conn: sqlite3.Connection) -> None:
    candidates = [
        CSV_FILE,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), CSV_FILE),
    ]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if not path:
        print(f"  [DB] WARNING: {CSV_FILE} not found — skipping patient import.")
        return

    print(f"  [DB] Importing {path} …", end="", flush=True)
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            age    = int(row["Age"])
            gender = row["Gender"]
            rows.append((
                f"PT-{int(row['Patient_ID']):05d}",
                _random_name(gender),
                _random_dob(age),
                age,
                gender,
                _random_insurance(),
                row["Symptoms"],
                row["Disease"],
            ))

    conn.executemany("INSERT OR IGNORE INTO patients VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    print(f" {len(rows):,} patients imported.")


# ── Slot seeding ──────────────────────────────────────────────────────────────

def _seed_slots(conn: sqlite3.Connection, doctors: list[dict]) -> None:
    """Insert two weeks of free working slots for the given doctors."""
    hours = ["09:00", "10:00", "11:00", "13:00", "14:00", "15:00"]
    today = datetime.now()
    rows  = []

    for doc in doctors:
        for offset in range(1, 15):
            date = today + timedelta(days=offset)
            if date.weekday() >= 5:
                continue
            for hour in hours:
                rows.append((doc["id"], f"{date.strftime('%Y-%m-%d')} {hour}", "free"))

    for row in rows:
        try:
            conn.execute(
                "INSERT INTO slots (doctor_id, slot_key, status) VALUES (?, ?, ?)", row
            )
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    print(f"  [DB] Inserted {len(rows)} slots for {len(doctors)} doctor(s)")


# ── Patient queries ───────────────────────────────────────────────────────────

def get_patient(patient_id: str) -> sqlite3.Row | None:
    conn = get_connection()
    row  = conn.execute(
        "SELECT * FROM patients WHERE patient_id = ?",
        (patient_id.upper(),)
    ).fetchone()
    conn.close()
    return row


def create_patient(patient_id: str, name: str, age: int,
                   gender: str, symptoms: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO patients (patient_id, name, age, gender, symptoms) "
        "VALUES (?, ?, ?, ?, ?)",
        (patient_id, name, age, gender, symptoms),
    )
    conn.commit()
    conn.close()


def get_patients_near(patient_id: str, n: int = 3) -> list[sqlite3.Row]:
    """Return up to n patient records neighbouring patient_id by ID order."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT patient_id, name, dob, age, gender, insurance, symptoms, disease
        FROM   patients
        WHERE  patient_id != ?
        ORDER  BY patient_id
        LIMIT  ?
        """,
        (patient_id.upper(), n),
    ).fetchall()
    conn.close()
    return rows


# ── Slot queries ──────────────────────────────────────────────────────────────

def get_free_slots(doctor_id: str, from_dt: datetime,
                   to_dt: datetime, limit: int = 5) -> list[sqlite3.Row]:
    conn      = get_connection()
    from_str  = from_dt.strftime("%Y-%m-%d") + " 00:00"
    to_str    = to_dt.strftime("%Y-%m-%d")   + " 23:59"
    rows      = conn.execute(
        """
        SELECT slot_key FROM slots
        WHERE  doctor_id = ?
          AND  status    = 'free'
          AND  slot_key >= ?
          AND  slot_key <= ?
        ORDER  BY slot_key
        LIMIT  ?
        """,
        (doctor_id, from_str, to_str, limit),
    ).fetchall()
    conn.close()
    return rows


def is_slot_free(doctor_id: str, slot_key: str) -> bool:
    conn = get_connection()
    row  = conn.execute(
        "SELECT status FROM slots WHERE doctor_id = ? AND slot_key = ?",
        (doctor_id, slot_key),
    ).fetchone()
    conn.close()
    return bool(row and row["status"] == "free")


def mark_slot_booked(doctor_id: str, slot_key: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE slots SET status = 'booked' WHERE doctor_id = ? AND slot_key = ?",
        (doctor_id, slot_key),
    )
    conn.commit()
    conn.close()


# ── Booking queries ───────────────────────────────────────────────────────────

def create_booking(
    ref: str, patient_id: str, patient_name: str,
    patient_dob: str | None, patient_age: int | None,
    patient_gender: str | None, patient_insurance: str | None,
    symptoms: str, doctor_id: str, doctor_name: str, slot_key: str,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO bookings (
            booking_ref, patient_id, patient_name, patient_dob,
            patient_age, patient_gender, patient_insurance,
            presenting_symptoms, doctor_id, doctor_name,
            slot_key, booked_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ref, patient_id, patient_name, patient_dob, patient_age,
            patient_gender, patient_insurance, symptoms,
            doctor_id, doctor_name, slot_key,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()
