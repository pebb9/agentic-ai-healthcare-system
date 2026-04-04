# config.py — application-wide constants and static data

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL      = "alibayram/medgemma:4b"
DB_FILE    = "healthcare.db"
CSV_FILE   = "Healthcare.csv"

DOCTORS = [
    {"id": "DOC-001", "name": "Dr. Nikolaj Carstens",       "specialty": "Cardiology",         "keywords": ["chest pain", "shortness of breath", "sweating", "palpitation"]},
    {"id": "DOC-002", "name": "Dr. Vu Nguyen",              "specialty": "Neurology",           "keywords": ["headache", "dizziness", "blurred vision", "tremors", "seizure"]},
    {"id": "DOC-003", "name": "Dr. Henrik Flugstad",        "specialty": "Dermatology",         "keywords": ["rash", "swelling", "skin", "itch"]},
    {"id": "DOC-004", "name": "Dr. Pablito Arias Champagne","specialty": "Psychiatry",          "keywords": ["anxiety", "depression", "insomnia", "stress", "panic"]},
    {"id": "DOC-005", "name": "Dr. Argyris Fragkos",        "specialty": "General Practice",    "keywords": ["fever", "cough", "fatigue", "nausea", "vomiting", "runny nose", "sore throat"]},
    {"id": "DOC-006", "name": "Dr. Elif Yildiz",            "specialty": "Pulmonology",         "keywords": ["cough", "shortness of breath", "wheezing", "chest tightness"]},
    {"id": "DOC-007", "name": "Dr. Marco Bellini",          "specialty": "Gastroenterology",    "keywords": ["abdominal pain", "diarrhea", "nausea", "vomiting", "appetite loss", "weight loss"]},
    {"id": "DOC-008", "name": "Dr. Amara Diallo",           "specialty": "Endocrinology",       "keywords": ["weight gain", "weight loss", "fatigue", "sweating", "appetite loss"]},
    {"id": "DOC-009", "name": "Dr. Sigrid Halvorsen",       "specialty": "Rheumatology",        "keywords": ["joint pain", "muscle pain", "swelling", "back pain", "stiffness"]},
    {"id": "DOC-010", "name": "Dr. Tariq Al-Rashid",        "specialty": "Immunology",          "keywords": ["rash", "sneezing", "runny nose", "swelling", "fever"]},
    {"id": "DOC-011", "name": "Dr. Lena Hoffmann",          "specialty": "Hematology",          "keywords": ["fatigue", "dizziness", "appetite loss", "weight loss", "back pain"]},
    {"id": "DOC-012", "name": "Dr. Kwame Asante",           "specialty": "Nephrology",          "keywords": ["swelling", "fatigue", "back pain", "nausea", "appetite loss"]},
    {"id": "DOC-013", "name": "Dr. Ingrid Svensson",        "specialty": "ENT",                 "keywords": ["sore throat", "runny nose", "sneezing", "headache", "dizziness"]},
    {"id": "DOC-014", "name": "Dr. Carlos Mendoza",         "specialty": "Infectious Disease",  "keywords": ["fever", "cough", "fatigue", "muscle pain", "diarrhea", "vomiting"]},
]

DISEASE_SPECIALTY = {
    "Allergy":               "Immunology",
    "Anemia":                "Hematology",
    "Anxiety":               "Psychiatry",
    "Arthritis":             "Rheumatology",
    "Asthma":                "Pulmonology",
    "Bronchitis":            "Pulmonology",
    "COVID-19":              "Infectious Disease",
    "Chronic Kidney Disease":"Nephrology",
    "Common Cold":           "General Practice",
    "Dementia":              "Neurology",
    "Depression":            "Psychiatry",
    "Dermatitis":            "Dermatology",
    "Diabetes":              "Endocrinology",
    "Epilepsy":              "Neurology",
    "Food Poisoning":        "General Practice",
    "Gastritis":             "Gastroenterology",
    "Heart Disease":         "Cardiology",
    "Hypertension":          "Cardiology",
    "IBS":                   "Gastroenterology",
    "Influenza":             "General Practice",
    "Liver Disease":         "Gastroenterology",
    "Migraine":              "Neurology",
    "Obesity":               "Endocrinology",
    "Parkinson's":           "Neurology",
    "Pneumonia":             "Pulmonology",
    "Sinusitis":             "ENT",
    "Stroke":                "Neurology",
    "Thyroid Disorder":      "Endocrinology",
    "Tuberculosis":          "Pulmonology",
    "Ulcer":                 "Gastroenterology",
}

_FIRST_M = ["Lars","Jonas","Erik","Mikkel","Thomas","Anders","Mads","Henrik","Peter","Niels","Felix","Leon","Lukas","Noah","Elias"]
_FIRST_F = ["Anna","Emma","Laura","Sofia","Maria","Sara","Julie","Mette","Ida","Maja","Lena","Hannah","Lea","Clara","Nina"]
_FIRST_O = ["Alex","Sam","Robin","Taylor","Jordan","Casey","Morgan"]
_LAST    = ["Nielsen","Jensen","Hansen","Pedersen","Andersen","Christensen","Larsen","Olsen","Moller","Eriksen"]
INSURERS = ["AOK Bayern","TK","Barmer","DAK","IKK","BKK","HEK","KKH"]