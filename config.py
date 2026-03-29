# config.py — application-wide constants and static data

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL      = "alibayram/medgemma:4b"
DB_FILE = "healthcare.db"
DOCTORS_CSV = "doctors.csv"
PATIENTS_CSV = "patients.csv"
APPOINTMENTS_CSV = "appointments.csv"
MEDICAL_RECORDS_CSV = "medical_records.csv"

DOCTORS = [
    {
        "id":       "D1",
        "name":     "Dr. Nikolaj Carstens",
        "specialty":"Cardiologist",
        "keywords": ["chest pain", "heart", "palpitations", "breathless", "shortness of breath"],
    },
    {
        "id":       "D2",
        "name":     "Dr. Vu Nguyen",
        "specialty":"Neurologist",
        "keywords": ["headache", "migraine", "dizziness", "numbness", "confusion"],
    },
    {
        "id":       "D3",
        "name":     "Dr. Henrik Flugstad",
        "specialty":"Dermatologist",
        "keywords": ["rash", "skin", "itching", "acne", "eczema"],
    },
    {
        "id":       "D4",
        "name":     "Dr. Pablito Arias Champagne",
        "specialty":"Psychiatrist",
        "keywords": ["anxiety", "depression", "stress", "sleep", "panic", "worry"],
    },
    {
        "id":       "D5",
        "name":     "Dr. Argyris Fragkos",
        "specialty":"General Practitioner",
        "keywords": ["fever", "cough", "cold", "tired", "fatigue", "stomach", "nausea"],
    },
]

# Synthetic PII pools used when enriching imported CSV rows
_FIRST_M = ["Lars", "Jonas", "Erik", "Mikkel", "Thomas", "Anders", "Mads", "Henrik", "Peter", "Niels"]
_FIRST_F = ["Anna", "Emma", "Laura", "Sofia", "Maria", "Sara", "Julie", "Mette", "Ida", "Maja"]
_FIRST_O = ["Alex", "Sam", "Robin", "Taylor", "Jordan"]
_LAST    = ["Nielsen", "Jensen", "Hansen", "Pedersen", "Andersen", "Christensen", "Larsen", "Olsen"]
INSURERS = ["AOK Bayern", "TK", "Barmer", "DAK", "IKK", "BKK"]
