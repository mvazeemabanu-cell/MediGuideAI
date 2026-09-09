from google import genai
import json
import os
import time
import urllib.parse

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL_NAME = "gemini-3.6-flash"


def call_model_with_retry(prompt, max_retries=3):
    """Calls the Gemini API with automatic retry on network errors."""
    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
            return response.text.strip()
        except Exception as e:
            last_error = e
            print(f"(Network hiccup, retrying... attempt {attempt + 1}/{max_retries})")
            time.sleep(2)
    raise last_error


# ---------------------------------------------------
# FEATURE 1: Patient state = our "memory" for the conversation
# ---------------------------------------------------
patient_state = {
    "main_symptom": None,
    "duration": None,
    "severity": None,
    "associated_symptoms": [],
    "location_on_body": None,
    "breathing_difficulty": None,
    "fainting_or_severe_weakness": None
}

QUESTION_BANK = [
    {"field": "breathing_difficulty", "question": "Are you having any difficulty breathing?", "priority": 1},
    {"field": "fainting_or_severe_weakness", "question": "Have you felt faint, dizzy, or extremely weak?", "priority": 1},
    {"field": "severity", "question": "On a scale of mild, moderate, or severe, how bad is the pain/discomfort?", "priority": 2},
    {"field": "duration", "question": "When exactly did this start?", "priority": 2},
    {"field": "location_on_body", "question": "Where exactly on your body do you feel this?", "priority": 3},
    {"field": "associated_symptoms", "question": "Are you experiencing any other symptoms along with this, like fever, vomiting, or fatigue?", "priority": 3}
]

SPECIALTY_KEYWORDS = {
    "Cardiology": ["chest", "heart", "palpitation", "breathless"],
    "Gastroenterology": ["stomach", "abdomen", "abdominal", "vomit", "nausea", "digestion", "liver"],
    "Neurology": ["head", "headache", "migraine", "dizziness", "seizure", "numbness"],
    "Dermatology": ["skin", "rash", "itching", "acne"],
    "Orthopedics": ["bone", "joint", "back", "knee", "fracture", "muscle"],
    "ENT": ["ear", "nose", "throat", "sinus"],
    "Ophthalmology": ["eye", "vision"],
    "Pulmonology": ["lung", "cough", "breathing", "asthma"],
    "General Medicine": []
}

HOSPITAL_DB = [
    {"name": "City Central Hospital", "specialties": ["Cardiology", "General Medicine", "Orthopedics"], "emergency_available": True, "distance_km": 2.3, "contact": "044-1234-5678", "address": "12 Anna Salai, Chennai"},
    {"name": "Sunrise Multispecialty Hospital", "specialties": ["Gastroenterology", "General Medicine", "Neurology"], "emergency_available": True, "distance_km": 4.1, "contact": "044-2345-6789", "address": "45 OMR Road, Chennai"},
    {"name": "Wellness Clinic", "specialties": ["Dermatology", "ENT", "General Medicine"], "emergency_available": False, "distance_km": 1.5, "contact": "044-3456-7890", "address": "8 Gandhi Street, Chennai"},
    {"name": "MedCare Superspecialty Hospital", "specialties": ["Cardiology", "Neurology", "Pulmonology", "Gastroenterology"], "emergency_available": True, "distance_km": 6.8, "contact": "044-4567-8901", "address": "23 ECR Road, Chennai"},
    {"name": "Vision & Eye Care Center", "specialties": ["Ophthalmology", "General Medicine"], "emergency_available": False, "distance_km": 3.2, "contact": "044-5678-9012", "address": "67 Mount Road, Chennai"}
]


def extract_symptoms(user_text):
    prompt = f"""
    Extract medical symptom information from this text and return ONLY valid JSON, no other text, no markdown formatting, no code fences.

    Text: "{user_text}"

    Return JSON with these fields (use null if not mentioned, use [] for associated_symptoms if none mentioned):
    {{
        "main_symptom": "",
        "duration": "",
        "severity": "",
        "associated_symptoms": [],
        "location_on_body": "",
        "breathing_difficulty": "",
        "fainting_or_severe_weakness": ""
    }}
    """
    raw_text = call_model_with_retry(prompt)
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json", "", 1).strip()
    return raw_text


def extract_answer_for_field(field, user_text):
    prompt = f"""
    The user was asked a medical follow-up question about their symptom.
    Their answer was: "{user_text}"

    Extract the value for the field "{field}" from their answer.
    Return ONLY valid JSON like this, no other text, no markdown:
    {{"{field}": "extracted value or null if unclear"}}
    """
    raw_text = call_model_with_retry(prompt)
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json", "", 1).strip()
    return raw_text


def get_next_question():
    missing_fields = []
    for item in QUESTION_BANK:
        field = item["field"]
        value = patient_state.get(field)
        if value is None or value == "" or value == []:
            missing_fields.append(item)
    if not missing_fields:
        return None
    missing_fields.sort(key=lambda x: x["priority"])
    return missing_fields[0]


def classify_urgency():
    breathing = str(patient_state.get("breathing_difficulty") or "").lower()
    fainting = str(patient_state.get("fainting_or_severe_weakness") or "").lower()
    severity = str(patient_state.get("severity") or "").lower()
    danger_words = ["yes", "severe", "a lot", "very", "extreme", "can't breathe", "unable"]

    if any(word in breathing for word in danger_words):
        return "EMERGENCY", "🔴 EMERGENCY — Please seek immediate medical attention."
    if any(word in fainting for word in danger_words):
        return "EMERGENCY", "🔴 EMERGENCY — Please seek immediate medical attention."
    if "severe" in severity:
        return "URGENT", "🟠 URGENT — Please seek prompt medical consultation."
    if "moderate" in severity:
        return "ROUTINE", "🟡 ROUTINE — Please schedule a doctor's appointment soon."
    return "LOW", "🟢 LOW URGENCY — Monitor your symptoms and seek care if they worsen."


def recommend_specialty_rule_based():
    text_to_check = " ".join([
        str(patient_state.get("main_symptom") or ""),
        str(patient_state.get("location_on_body") or ""),
        " ".join(patient_state.get("associated_symptoms") or [])
    ]).lower()

    for specialty, keywords in SPECIALTY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_to_check:
                return specialty
    return "General Medicine"


def find_matching_hospitals(specialty, urgency_level, top_n=3):
    candidates = [h for h in HOSPITAL_DB if specialty in h["specialties"]]
    if not candidates:
        candidates = [h for h in HOSPITAL_DB if "General Medicine" in h["specialties"]]
    if urgency_level == "EMERGENCY":
        candidates = [h for h in candidates if h["emergency_available"]] or candidates
    candidates.sort(key=lambda h: h["distance_km"])
    return candidates[:top_n]


def generate_navigation_link(hospital_address):
    base_url = "https://www.google.com/maps/dir/?api=1"
    destination = urllib.parse.quote(hospital_address)
    return f"{base_url}&destination={destination}"


def print_state():
    print("\n--- Current Patient State ---")
    print(json.dumps(patient_state, indent=2))


def print_hospitals(hospitals):
    print("\n=== RECOMMENDED HOSPITALS ===")
    if not hospitals:
        print("No matching hospitals found in the database.")
        return
    for i, h in enumerate(hospitals, start=1):
        emergency_tag = "🚨 Emergency Available" if h["emergency_available"] else "No Emergency Dept."
        print(f"\n{i}. {h['name']}")
        print(f"   Address: {h['address']}")
        print(f"   Distance: {h['distance_km']} km")
        print(f"   Contact: {h['contact']}")
        print(f"   Specialties: {', '.join(h['specialties'])}")
        print(f"   {emergency_tag}")


def main():
    print("Bot: Hi! Please describe what you're feeling today.")
    user_input = input("You: ")

    result = extract_symptoms(user_input)
    try:
        parsed = json.loads(result)
        patient_state.update(parsed)
    except json.JSONDecodeError:
        pass

    print_state()

    while True:
        next_q = get_next_question()
        if next_q is None:
            break
        print(f"\nBot: {next_q['question']}")
        answer = input("You: ")
        field = next_q["field"]
        result = extract_answer_for_field(field, answer)
        try:
            parsed = json.loads(result)
            value = parsed.get(field)
            if field == "associated_symptoms" and value and not isinstance(value, list):
                value = [value]
            patient_state[field] = value
        except json.JSONDecodeError:
            patient_state[field] = "unclear"
        print_state()

    print("\n=== FINAL ASSESSMENT ===")
    print_state()

    urgency_level, urgency_text = classify_urgency()
    print(f"\nUrgency Level: {urgency_text}")

    specialty = recommend_specialty_rule_based()
    print(f"\nRecommended Specialty: {specialty}")

    hospitals = find_matching_hospitals(specialty, urgency_level)
    print_hospitals(hospitals)

    if hospitals:
        print("\nBot: Which hospital would you like directions to? (enter the number, e.g. 1)")
        choice = input("You: ").strip()
        try:
            index = int(choice) - 1
            selected = hospitals[index]
            link = generate_navigation_link(selected["address"])
            print(f"\n=== NAVIGATION ===")
            print(f"Directions to {selected['name']}:")
            print(link)
        except (ValueError, IndexError):
            print("\n(Invalid selection, skipping navigation.)")


if __name__ == "__main__":
    main()