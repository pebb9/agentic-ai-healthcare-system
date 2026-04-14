import pandas as pd
import re

# Load dataset
df = pd.read_csv("Healthcare.csv")

# ----------------------------
# Base triage mapping
# ----------------------------
BASE_TRIAGE = {
    "Common Cold": "LOW",
    "Influenza": "MEDIUM",
    "COVID-19": "MEDIUM",
    "Pneumonia": "HIGH",
    "Tuberculosis": "HIGH",
    "Diabetes": "MEDIUM",
    "Hypertension": "MEDIUM",
    "Asthma": "HIGH",
    "Heart Disease": "HIGH",
    "Chronic Kidney Disease": "HIGH",
    "Gastritis": "MEDIUM",
    "Food Poisoning": "MEDIUM",
    "Irritable Bowel Syndrome (IBS)": "LOW",
    "Liver Disease": "MEDIUM",
    "Ulcer": "MEDIUM",
    "Migraine": "MEDIUM",
    "Epilepsy": "HIGH",
    "Stroke": "HIGH",
    "Dementia": "LOW",
    "Parkinson’s Disease": "LOW",
    "Allergy": "MEDIUM",
    "Arthritis": "MEDIUM",
    "Anemia": "MEDIUM",
    "Thyroid Disorder": "MEDIUM",
    "Obesity": "LOW",
    "Depression": "MEDIUM",
    "Anxiety": "MEDIUM",
    "Dermatitis": "MEDIUM",
    "Sinusitis": "MEDIUM",
    "Bronchitis": "MEDIUM",
}

# ----------------------------
# Symptom rules
# ----------------------------
HIGH_KEYWORDS = [
    "chest pain",
    "shortness of breath",
    "breathlessness",
    "difficulty breathing",
    "confusion",
    "loss of consciousness",
    "seizure",
    "paralysis",
    "slurred speech",
    "bluish lips",
    "coughing blood",
]

MEDIUM_KEYWORDS = [
    "fever",
    "cough",
    "fatigue",
    "vomiting",
    "nausea",
    "dizziness",
    "headache",
    "abdominal pain",
    "diarrhea",
    "rash",
    "weakness",
]

def normalize(text):
    if pd.isna(text):
        return ""
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s,]", " ", text)
    return text

def make_true_triage(disease, symptoms):
    symptoms = normalize(symptoms)
    base = BASE_TRIAGE.get(disease, "MEDIUM")

    if any(k in symptoms for k in HIGH_KEYWORDS):
        return "HIGH"

    if any(k in symptoms for k in MEDIUM_KEYWORDS):
        return "MEDIUM" if base == "LOW" else base

    return base

# ----------------------------
# Apply
# ----------------------------
df["true_triage"] = df.apply(
    lambda row: make_true_triage(row["Disease"], row["Symptoms"]),
    axis=1
)

# Save
df.to_csv("healthcare_with_triage.csv", index=False)

print(df[["Symptoms", "Disease", "true_triage"]].head())