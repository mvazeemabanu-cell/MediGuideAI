from flask import Flask, request, jsonify, session, send_from_directory
from google import genai
import json
import os
import time
import urllib.parse
import uuid

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL_NAME = "gemini-3.1-flash-lite"

# ---------------------------------------------------
# In-memory session storage
# Key: session_id -> patient_state dict
# For a real product this would be a database; for a prototype,
# an in-memory dict keyed by browser session is enough.
# ---------------------------------------------------
SESSIONS = {}

QUESTION_BANK = {
    "en": [
        {"field": "breathing_difficulty", "question": "Are you having any difficulty breathing?", "priority": 1},
        {"field": "fainting_or_severe_weakness", "question": "Have you felt faint, dizzy, or extremely weak?", "priority": 1},
        {"field": "severity", "question": "On a scale of mild, moderate, or severe, how bad is the pain/discomfort?", "priority": 2},
        {"field": "duration", "question": "When exactly did this start?", "priority": 2},
        {"field": "location_on_body", "question": "Where exactly on your body do you feel this?", "priority": 3},
        {"field": "associated_symptoms", "question": "Are you experiencing any other symptoms along with this, like fever, vomiting, or fatigue?", "priority": 3}
    ],
    "ta": [
        {"field": "breathing_difficulty", "question": "நீங்கள் சுவாசிக்க சிரமப்படுகிறீர்களா?", "priority": 1},
        {"field": "fainting_or_severe_weakness", "question": "மயக்கமாகவோ, தலைச்சுற்றலாகவோ, அல்லது கடுமையான பலவீனமாகவோ உணர்கிறீர்களா?", "priority": 1},
        {"field": "severity", "question": "வலி அல்லது அசௌகரியம் லேசானதா, நடுத்தரமானதா, அல்லது கடுமையானதா?", "priority": 2},
        {"field": "duration", "question": "இது சரியாக எப்போது தொடங்கியது?", "priority": 2},
        {"field": "location_on_body", "question": "இது உடலின் எந்தப் பகுதியில் உணர்கிறீர்கள்?", "priority": 3},
        {"field": "associated_symptoms", "question": "காய்ச்சல், வாந்தி, அல்லது சோர்வு போன்ற வேறு அறிகுறிகள் உள்ளதா?", "priority": 3}
    ]
}

LANG_NAMES = {"en": "English", "ta": "Tamil"}

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
    # Chennai
    {"name": "City Central Hospital", "city": "Chennai", "specialties": ["Cardiology", "General Medicine", "Orthopedics"], "emergency_available": True, "distance_km": 2.3, "contact": "044-1234-5678", "address": "12 Anna Salai, Chennai"},
    {"name": "Sunrise Multispecialty Hospital", "city": "Chennai", "specialties": ["Gastroenterology", "General Medicine", "Neurology"], "emergency_available": True, "distance_km": 4.1, "contact": "044-2345-6789", "address": "45 OMR Road, Chennai"},
    {"name": "Wellness Clinic", "city": "Chennai", "specialties": ["Dermatology", "ENT", "General Medicine"], "emergency_available": False, "distance_km": 1.5, "contact": "044-3456-7890", "address": "8 Gandhi Street, Chennai"},
    {"name": "MedCare Superspecialty Hospital", "city": "Chennai", "specialties": ["Cardiology", "Neurology", "Pulmonology", "Gastroenterology"], "emergency_available": True, "distance_km": 6.8, "contact": "044-4567-8901", "address": "23 ECR Road, Chennai"},
    {"name": "Vision & Eye Care Center", "city": "Chennai", "specialties": ["Ophthalmology", "General Medicine"], "emergency_available": False, "distance_km": 3.2, "contact": "044-5678-9012", "address": "67 Mount Road, Chennai"},
    {"name": "Apollo Main Hospital", "city": "Chennai", "specialties": ["Cardiology", "Neurology", "Orthopedics", "Gastroenterology", "General Medicine"], "emergency_available": True, "distance_km": 5.0, "contact": "044-2829-3333", "address": "21 Greams Lane, Off Greams Road, Chennai"},
    {"name": "Dr. Mehta's Hospital", "city": "Chennai", "specialties": ["General Medicine", "Gastroenterology", "Orthopedics", "ENT"], "emergency_available": True, "distance_km": 4.6, "contact": "044-4227-4227", "address": "2 McNichols Road, Chetpet, Chennai"},
    {"name": "SIMS Hospital", "city": "Chennai", "specialties": ["Cardiology", "Neurology", "Orthopedics", "Gastroenterology"], "emergency_available": True, "distance_km": 7.2, "contact": "044-4224-4224", "address": "4/112 Mount Poonamallee Rd, Manapakkam, Chennai"},
    {"name": "MIOT International Hospital", "city": "Chennai", "specialties": ["Cardiology", "Orthopedics", "Neurology", "General Medicine"], "emergency_available": True, "distance_km": 8.1, "contact": "044-4200-2288", "address": "Mount Poonamallee Rd, Manapakkam, Chennai"},
    {"name": "Gleneagles Global Health City", "city": "Chennai", "specialties": ["Gastroenterology", "Cardiology", "General Medicine", "Pulmonology"], "emergency_available": True, "distance_km": 9.4, "contact": "044-4477-4477", "address": "439 Cheran Nagar, Perumbakkam, Chennai"},
    # Coimbatore
    {"name": "Kovai General Hospital", "city": "Coimbatore", "specialties": ["General Medicine", "Gastroenterology", "Orthopedics"], "emergency_available": True, "distance_km": 3.0, "contact": "0422-234-5678", "address": "15 Avinashi Road, Coimbatore"},
    {"name": "PSG Super Speciality Hospital", "city": "Coimbatore", "specialties": ["Cardiology", "Neurology", "Pulmonology"], "emergency_available": True, "distance_km": 5.5, "contact": "0422-345-6789", "address": "Peelamedu, Coimbatore"},
    {"name": "Coimbatore Skin & ENT Clinic", "city": "Coimbatore", "specialties": ["Dermatology", "ENT", "General Medicine"], "emergency_available": False, "distance_km": 2.1, "contact": "0422-456-7890", "address": "RS Puram, Coimbatore"},
    # Bengaluru
    {"name": "Bangalore City Hospital", "city": "Bengaluru", "specialties": ["General Medicine", "Cardiology", "Orthopedics"], "emergency_available": True, "distance_km": 2.8, "contact": "080-1234-5678", "address": "MG Road, Bengaluru"},
    {"name": "Whitefield Multispecialty Hospital", "city": "Bengaluru", "specialties": ["Gastroenterology", "Neurology", "General Medicine"], "emergency_available": True, "distance_km": 6.2, "contact": "080-2345-6789", "address": "Whitefield, Bengaluru"},
    {"name": "Koramangala Eye & ENT Center", "city": "Bengaluru", "specialties": ["Ophthalmology", "ENT"], "emergency_available": False, "distance_km": 3.5, "contact": "080-3456-7890", "address": "Koramangala, Bengaluru"},
    # Salem
    {"name": "Manipal Hospital Salem", "city": "Salem", "specialties": ["Cardiology", "Neurology", "General Medicine", "Orthopedics", "Gastroenterology"], "emergency_available": True, "distance_km": 3.4, "contact": "0427-266-6001", "address": "Dalmia Board, Salem-Bangalore Highway, Salem"},
    {"name": "SKS Hospital", "city": "Salem", "specialties": ["Cardiology", "Gastroenterology", "General Medicine", "Orthopedics"], "emergency_available": True, "distance_km": 2.1, "contact": "0427-244-3000", "address": "23 SKS Hospital Rd, Alagapuram, Salem"},
    {"name": "VIMS Super Speciality Hospital", "city": "Salem", "specialties": ["Cardiology", "Neurology", "Orthopedics", "General Medicine"], "emergency_available": True, "distance_km": 5.6, "contact": "0427-355-5000", "address": "NH-47, Sankari Main Road, Seeragapadi, Salem"},
    {"name": "Shri Hospitals", "city": "Salem", "specialties": ["General Medicine", "ENT", "Dermatology"], "emergency_available": False, "distance_km": 1.8, "contact": "+91-77083-33308", "address": "Tamil Sangam Rd, Sankar Nagar, Salem"},
    # Erode
    {"name": "Thanthai Periyar Government Headquarters Hospital", "city": "Erode", "specialties": ["General Medicine", "Orthopedics", "Gastroenterology"], "emergency_available": True, "distance_km": 2.5, "contact": "0424-225-5504", "address": "Government Hospital Road, Erode"},
    {"name": "Erode Medical Centre (EMC)", "city": "Erode", "specialties": ["Cardiology", "General Medicine", "Orthopedics", "Gastroenterology"], "emergency_available": True, "distance_km": 3.8, "contact": "0424-288-8555", "address": "374/2, Perundurai Rd, Erode"},
    {"name": "LKM Hospital", "city": "Erode", "specialties": ["Cardiology", "Neurology", "Orthopedics", "General Medicine"], "emergency_available": True, "distance_km": 4.2, "contact": "0424-225-5000", "address": "Mosunanna Street, Erode"},
    # Karur
    {"name": "Apollo Hospital Karur", "city": "Karur", "specialties": ["Cardiology", "Neurology", "General Medicine", "Orthopedics"], "emergency_available": True, "distance_km": 3.1, "contact": "04324-241-900", "address": "163 A-E, Allwyn Nagar, Kovai Main Rd, Karur"},
    {"name": "Amaravathi Hospital", "city": "Karur", "specialties": ["General Medicine", "Gastroenterology", "Orthopedics"], "emergency_available": True, "distance_km": 2.4, "contact": "09843-231-333", "address": "74, Ramanujam Nagar, Karur"},
    # Namakkal
    {"name": "MM Hospital Namakkal", "city": "Namakkal", "specialties": ["Cardiology", "Neurology", "Gastroenterology", "General Medicine"], "emergency_available": True, "distance_km": 2.8, "contact": "04286-222-000", "address": "Trichy Main Road, Namakkal"},
    {"name": "Thangam Hospital", "city": "Namakkal", "specialties": ["Gastroenterology", "Orthopedics", "ENT", "General Medicine"], "emergency_available": True, "distance_km": 3.5, "contact": "04286-223-000", "address": "Trichy Main Road, Sattur, Namakkal"},
    {"name": "Shree Akhshaya Hospital", "city": "Namakkal", "specialties": ["General Medicine", "Orthopedics"], "emergency_available": False, "distance_km": 1.9, "contact": "04286-224-000", "address": "Namakkal Town"},
]


def new_patient_state():
    return {
        "main_symptom": None,
        "duration": None,
        "severity": None,
        "associated_symptoms": [],
        "location_on_body": None,
        "breathing_difficulty": None,
        "fainting_or_severe_weakness": None
    }


def call_model_with_retry(prompt, max_retries=2):
    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
            return response.text.strip()
        except Exception as e:
            last_error = e
            print(f"[Gemini API error] attempt {attempt + 1}/{max_retries}: {e}")
            time.sleep(1)
    raise last_error


@app.errorhandler(Exception)
def handle_error(e):
    print(f"[Server error] {e}")
    return jsonify({"messages": [{"type": "bot_text", "text": f"Server error: {str(e)}"}], "stage": "intake", "state": {}}), 200


def clean_json_text(raw_text):
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json", "", 1).strip()
    return raw_text


def extract_symptoms(user_text, lang="en", profile=None):
    lang_name = LANG_NAMES.get(lang, "English")
    profile_context = ""
    if profile:
        parts = []
        if profile.get("age"): parts.append(f"Age: {profile['age']}")
        if profile.get("gender"): parts.append(f"Gender: {profile['gender']}")
        if profile.get("weight_kg"): parts.append(f"Weight: {profile['weight_kg']} kg")
        if profile.get("height_cm"): parts.append(f"Height: {profile['height_cm']} cm")
        if profile.get("city"): parts.append(f"Location: {profile['city']}")
        if parts:
            profile_context = f"\n    Patient background: {', '.join(parts)}\n    (Consider this context, e.g. age matters for urgency in children/elderly.)\n"

    prompt = f"""
    You are a warm, caring healthcare navigation assistant. The user just described their symptoms.
    {profile_context}
    Text: "{user_text}"

    Do two things:
    1. Extract medical symptom information into structured fields.
    2. Write a short, warm, natural one-sentence acknowledgment of what they said, IN {lang_name}
       (not robotic, not repeating their words verbatim, no medical judgment or diagnosis).

    Return ONLY valid JSON, no other text, no markdown formatting, no code fences:
    {{
        "main_symptom": "",
        "duration": "",
        "severity": "",
        "associated_symptoms": [],
        "location_on_body": "",
        "breathing_difficulty": "",
        "fainting_or_severe_weakness": "",
        "acknowledgment": "one warm natural sentence in {lang_name}"
    }}
    """
    return clean_json_text(call_model_with_retry(prompt))


def extract_answer_for_field(field, user_text, lang="en"):
    lang_name = LANG_NAMES.get(lang, "English")
    prompt = f"""
    You are a warm, caring healthcare navigation assistant conducting a symptom check-in.
    The user was asked a follow-up question. Their answer was: "{user_text}"

    Do two things:
    1. Extract the value for the field "{field}" from their answer.
    2. Write a short, warm, natural one-sentence acknowledgment of their answer, IN {lang_name}
       (not robotic, no medical judgment). Vary your phrasing -- do not reuse the same
       opening words every time.

    Return ONLY valid JSON like this, no other text, no markdown:
    {{"{field}": "extracted value or null if unclear", "acknowledgment": "one warm natural sentence in {lang_name}"}}
    """
    return clean_json_text(call_model_with_retry(prompt))


def get_next_question(patient_state, lang="en", answered_fields=None):
    answered_fields = answered_fields or []
    bank = QUESTION_BANK.get(lang, QUESTION_BANK["en"])
    missing_fields = []
    for item in bank:
        field = item["field"]
        if field in answered_fields:
            continue  # already explicitly answered, even if the answer was "no"/empty
        value = patient_state.get(field)
        if value is None or value == "" or value == []:
            missing_fields.append(item)
    if not missing_fields:
        return None
    missing_fields.sort(key=lambda x: x["priority"])
    return missing_fields[0]


def classify_urgency(patient_state):
    breathing = str(patient_state.get("breathing_difficulty") or "").lower()
    fainting = str(patient_state.get("fainting_or_severe_weakness") or "").lower()
    severity = str(patient_state.get("severity") or "").lower()
    danger_words = ["yes", "severe", "a lot", "very", "extreme", "can't breathe", "unable"]

    # Build the explainability trail as we evaluate each rule --
    # every factor we looked at gets recorded with its contribution level,
    # whether or not it ended up being the deciding factor.
    factors = []

    breathing_flag = any(word in breathing for word in danger_words)
    factors.append({
        "factor": "Breathing difficulty",
        "value": patient_state.get("breathing_difficulty") or "not reported",
        "contribution": "high" if breathing_flag else "low",
        "detail": "Reported as present — a red-flag symptom." if breathing_flag else "Not reported as a concern."
    })

    fainting_flag = any(word in fainting for word in danger_words)
    factors.append({
        "factor": "Fainting / severe weakness",
        "value": patient_state.get("fainting_or_severe_weakness") or "not reported",
        "contribution": "high" if fainting_flag else "low",
        "detail": "Reported as present — a red-flag symptom." if fainting_flag else "Not reported as a concern."
    })

    severity_level = "high" if "severe" in severity else "medium" if "moderate" in severity else "low"
    factors.append({
        "factor": "Reported severity",
        "value": patient_state.get("severity") or "not specified",
        "contribution": severity_level,
        "detail": f"Severity described as '{patient_state.get('severity')}'." if patient_state.get("severity") else "Severity was not specified."
    })

    duration = str(patient_state.get("duration") or "")
    factors.append({
        "factor": "Duration",
        "value": duration or "not specified",
        "contribution": "low",
        "detail": "Duration mainly informs specialty timing, not emergency status."
    })

    if breathing_flag or fainting_flag:
        return "EMERGENCY", "EMERGENCY — Please seek immediate medical attention.", factors
    if "severe" in severity:
        return "URGENT", "URGENT — Please seek prompt medical consultation.", factors
    if "moderate" in severity:
        return "ROUTINE", "ROUTINE — Please schedule a doctor's appointment soon.", factors
    return "LOW", "LOW URGENCY — Monitor your symptoms and seek care if they worsen.", factors


def recommend_specialty(patient_state):
    text_to_check = " ".join([
        str(patient_state.get("main_symptom") or ""),
        str(patient_state.get("location_on_body") or ""),
        " ".join(patient_state.get("associated_symptoms") or [])
    ]).lower()

    for specialty, keywords in SPECIALTY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_to_check:
                return specialty, f"Matched keyword '{kw}' in your reported symptom/location."
    return "General Medicine", "No specific specialty keyword matched — General Medicine is the safe default starting point."


def get_assessment_extras(patient_state, lang="en"):
    """
    Single combined LLM call that returns both:
    - 2-3 general possible condition categories (not a diagnosis)
    - one short, general, personalized wellness tip
    Combined into one call to conserve API quota.
    """
    lang_name = LANG_NAMES.get(lang, "English")
    prompt = f"""
    You are a cautious healthcare navigation assistant, NOT a doctor.

    Based on this symptom profile:
    {json.dumps(patient_state, indent=2)}

    Do two things, both written IN {lang_name}:
    1. List 2-3 general condition categories that commonly present this way
       (e.g. "a viral infection", "a stomach bug", "dengue or another mosquito-borne
       fever"). Be general, not overconfident, and do NOT claim certainty -- this is
       only to help the person understand what the triage process is considering.
    2. Write one short, general wellness tip relevant to their symptom (e.g. staying
       hydrated, resting, avoiding certain foods). Keep it general and safe -- do not
       suggest medication or dosages.

    Return ONLY valid JSON, no other text, no markdown:
    {{"possible_conditions": ["condition 1", "condition 2"], "health_tip": "one short sentence"}}
    """
    raw_text = clean_json_text(call_model_with_retry(prompt))
    try:
        parsed = json.loads(raw_text)
        return parsed.get("possible_conditions", []), parsed.get("health_tip", "")
    except json.JSONDecodeError:
        return [], ""


import requests

GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")  # optional, not required


def geocode_city_osm(city):
    """Free geocoding via OpenStreetMap Nominatim -- no API key needed."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city, "format": "json", "limit": 1},
            headers={"User-Agent": "MediGuideAI-StudentProject/1.0"},
            timeout=5
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        print(f"[Nominatim geocode error] {e}")
        return None


def haversine_km(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return round(R * 2 * atan2(sqrt(a), sqrt(1 - a)), 1)


def search_hospitals_osm(city, specialty):
    """
    Fully free hospital search using OpenStreetMap Overpass API.
    No API key, no billing required -- works for any city with OSM coverage.
    """
    coords = geocode_city_osm(city)
    if not coords:
        return None
    city_lat, city_lon = coords

    query = f"""
    [out:json][timeout:10];
    node["amenity"="hospital"](around:8000,{city_lat},{city_lon});
    out body 12;
    """
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            headers={"User-Agent": "MediGuideAI-StudentProject/1.0"},
            timeout=8
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        if not elements:
            return None

        hospitals = []
        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue
            lat, lon = el.get("lat"), el.get("lon")
            distance = haversine_km(city_lat, city_lon, lat, lon) if lat and lon else None
            address_parts = [tags.get(k) for k in ["addr:housenumber", "addr:street", "addr:city"] if tags.get(k)]
            address = ", ".join(address_parts) if address_parts else f"Near {city}"

            hospitals.append({
                "name": name,
                "city": city,
                "specialties": [specialty, "General Medicine"],
                "emergency_available": tags.get("emergency") == "yes",
                "distance_km": distance if distance is not None else 999,
                "contact": tags.get("phone", "Not available"),
                "address": address
            })

        hospitals.sort(key=lambda h: h["distance_km"])
        return hospitals if hospitals else None
    except Exception as e:
        print(f"[Overpass API error] {e}")
        return None


def find_matching_hospitals(specialty, urgency_level, city=None, top_n=10):
    # Priority 1: check our fast, reliable offline database first
    city_matches = []
    if city:
        city_matches = [h for h in HOSPITAL_DB if h.get("city", "").lower() == city.strip().lower()]

    if city_matches:
        candidates = [h for h in city_matches if specialty in h["specialties"]]
        if not candidates:
            candidates = [h for h in city_matches if "General Medicine" in h["specialties"]]
        if urgency_level == "EMERGENCY":
            candidates = [h for h in candidates if h["emergency_available"]] or candidates
        candidates.sort(key=lambda h: h["distance_km"])
        return candidates[:top_n], True

    # Priority 2: city not in our offline database -- try live OpenStreetMap search
    if city:
        live_results = search_hospitals_osm(city, specialty)
        if live_results:
            return live_results[:top_n], True

    # Priority 3: nothing found anywhere
    return [], (False if city else True)


def generate_call_link(phone_number):
    digits_only = "".join(ch for ch in phone_number if ch.isdigit() or ch == "+")
    return f"tel:{digits_only}"


def suggest_home_remedy(patient_state, specialty, urgency_level, profile=None, lang="en"):
    if urgency_level in ("EMERGENCY", "URGENT"):
        return None

    lang_name = LANG_NAMES.get(lang, "English")
    profile_line = ""
    if profile:
        parts = []
        if profile.get("age"): parts.append(f"Age: {profile['age']}")
        if profile.get("gender"): parts.append(f"Gender: {profile['gender']}")
        if parts:
            profile_line = f"Patient background: {', '.join(parts)}.\n"

    prompt = f"""
    You are a cautious healthcare assistant. This patient has a LOW or ROUTINE urgency
    symptom (not an emergency), so simple home comfort measures are appropriate.

    {profile_line}Symptom profile: {json.dumps(patient_state)}
    Specialty area: {specialty}

    Write ONE short, safe, general home comfort suggestion IN {lang_name} (rest, hydration,
    simple foods like soup, warm compress, etc). Consider the patient's age if relevant
    (e.g. be gentler with suggestions for children or elderly). Do NOT suggest any
    medication, dosage, or specific drug names.

    Return ONLY valid JSON, no other text, no markdown:
    {{"remedy": "one short sentence"}}
    """
    try:
        raw_text = clean_json_text(call_model_with_retry(prompt))
        parsed = json.loads(raw_text)
        return parsed.get("remedy") or HOME_REMEDY_MAP.get(specialty, HOME_REMEDY_MAP["General Medicine"])
    except Exception:
        return HOME_REMEDY_MAP.get(specialty, HOME_REMEDY_MAP["General Medicine"])


# ---------------------------------------------------
# Simple, safe home comfort suggestions.
# IMPORTANT: only offered for LOW / ROUTINE urgency.
# For URGENT / EMERGENCY we never suggest self-care --
# the priority is getting the person to a professional.
# ---------------------------------------------------
HOME_REMEDY_MAP = {
    "Gastroenterology": "Sipping warm water or a light, clear soup and resting can ease mild stomach discomfort. Avoid heavy, oily, or spicy food until you feel better.",
    "Neurology": "Resting in a quiet, dim room and staying hydrated can help with mild headaches. Avoid screens for a while if you can.",
    "ENT": "Warm fluids, steam inhalation, and rest can soothe a mild sore throat or congestion.",
    "Dermatology": "Keep the area clean and avoid scratching or applying unfamiliar creams until it's been looked at.",
    "Orthopedics": "Resting the area and avoiding strain can help with mild aches. A warm compress may bring some relief.",
    "Pulmonology": "Rest, warm fluids, and staying upright can ease mild throat or chest irritation from a cough.",
    "General Medicine": "Rest, staying hydrated, and light home-cooked food like a simple soup can help your body recover.",
}


def generate_navigation_link(address):
    base_url = "https://www.google.com/maps/dir/?api=1"
    destination = urllib.parse.quote(address)
    return f"{base_url}&destination={destination}"


# ---------------------------------------------------
# Risk percentage indicator.
# NOTE: this is a simple illustrative mapping for the dashboard visual,
# not a calibrated clinical probability. Presented with that caveat in the UI.
# ---------------------------------------------------
RISK_MAP = {
    "EMERGENCY": {"percent": 92, "label": "High"},
    "URGENT": {"percent": 68, "label": "Medium-High"},
    "ROUTINE": {"percent": 38, "label": "Medium"},
    "LOW": {"percent": 15, "label": "Low"},
}


def get_risk_indicator(urgency_level):
    return RISK_MAP.get(urgency_level, {"percent": 30, "label": "Low"})


# ---------------------------------------------------
# BMI category -> general lifestyle guidance.
# IMPORTANT: never suggests medication, supplements, or specific tablets --
# only general diet/activity direction. Actual treatment must come from a doctor.
# ---------------------------------------------------
def get_bmi_info(weight_kg, height_cm):
    try:
        w = float(weight_kg)
        h = float(height_cm) / 100
        if w <= 0 or h <= 0:
            return None
        bmi = round(w / (h * h), 1)
    except (TypeError, ValueError):
        return None

    if bmi < 18.5:
        category = "Underweight"
        tip = "Focus on regular, nutrient-dense meals with enough protein and calories. A doctor or dietitian can help build a safe weight-gain plan suited to you."
    elif bmi < 25:
        category = "Normal range"
        tip = "Your BMI is in the typical healthy range. Keep up a balanced diet and regular activity."
    elif bmi < 30:
        category = "Overweight"
        tip = "Gradual changes -- more vegetables, less refined sugar, regular walks -- tend to help most. A doctor can advise on a plan suited to your health history."
    else:
        category = "Obese"
        tip = "It's worth discussing a structured diet and activity plan with a doctor, since they can account for your full health picture safely."

    return {"bmi": bmi, "category": category, "tip": tip}


def generate_doctor_questions(patient_state, possible_conditions, specialty, lang="en"):
    """
    Generates 3-4 specific questions the patient could ask their doctor,
    based on their symptom profile -- helps them prepare for the visit.
    """
    lang_name = LANG_NAMES.get(lang, "English")
    prompt = f"""
    You are a cautious healthcare navigation assistant helping a patient prepare
    for a doctor's visit. Based on this symptom profile and the specialty they're
    being referred to, write 3-4 short, specific questions the patient could ask
    their doctor. IN {lang_name}. Do not suggest treatments or medications yourself
    -- these are just good questions for the patient to bring to the appointment.

    Symptom profile: {json.dumps(patient_state)}
    Specialty: {specialty}
    Possible general categories being considered: {possible_conditions}

    Return ONLY valid JSON, no other text, no markdown:
    {{"questions": ["question 1", "question 2", "question 3"]}}
    """
    try:
        raw_text = clean_json_text(call_model_with_retry(prompt))
        parsed = json.loads(raw_text)
        return parsed.get("questions", [])
    except Exception:
        return []


def build_assessment(patient_state, lang, profile):
    urgency_level, urgency_text, urgency_factors = classify_urgency(patient_state)
    specialty, specialty_reason = recommend_specialty(patient_state)
    possible_conditions, health_tip = get_assessment_extras(patient_state, lang)
    hospitals, city_has_data = find_matching_hospitals(specialty, urgency_level, city=(profile or {}).get("city"), top_n=10)
    remedy = suggest_home_remedy(patient_state, specialty, urgency_level, profile, lang)
    risk = get_risk_indicator(urgency_level)
    doctor_questions = generate_doctor_questions(patient_state, possible_conditions, specialty, lang)

    hospitals_with_links = []
    for h in hospitals:
        hospitals_with_links.append({
            **h,
            "nav_link": generate_navigation_link(h["address"]),
            "call_link": generate_call_link(h["contact"])
        })

    bmi_info = None
    if profile:
        bmi_info = get_bmi_info(profile.get("weight_kg"), profile.get("height_cm"))

    return {
        "type": "assessment",
        "urgency_level": urgency_level,
        "urgency_text": urgency_text,
        "risk_percent": risk["percent"],
        "risk_label": risk["label"],
        "urgency_factors": urgency_factors,
        "specialty": specialty,
        "specialty_reason": specialty_reason,
        "possible_conditions": possible_conditions,
        "health_tip": health_tip,
        "hospitals": hospitals_with_links,
        "city_has_data": city_has_data,
        "searched_city": (profile or {}).get("city", ""),
        "remedy": remedy,
        "bmi_info": bmi_info,
        "doctor_questions": doctor_questions,
        "patient_state": patient_state
    }


def get_session_id():
    if "sid" not in session:
        session["sid"] = str(uuid.uuid4())
    sid = session["sid"]
    if sid not in SESSIONS:
        SESSIONS[sid] = {
            "patient_state": new_patient_state(),
            "stage": "intake"  # intake -> questions -> done
        }
    return sid


@app.route("/")
def index():
    session.clear()
    return send_from_directory("templates", "index.html")


@app.route("/api/message", methods=["POST"])
def api_message():
    sid = get_session_id()
    data = SESSIONS[sid]
    patient_state = data["patient_state"]
    stage = data["stage"]

    user_text = request.json.get("message", "").strip()
    lang = request.json.get("lang", "en")
    profile = request.json.get("profile")
    if not user_text:
        return jsonify({"error": "Empty message"}), 400

    response_payload = {"messages": [], "stage": stage, "state": patient_state}

    if stage == "intake":
        data["profile"] = profile or {}
        result = extract_symptoms(user_text, lang, profile)
        acknowledgment = None
        try:
            parsed = json.loads(result)
            acknowledgment = parsed.pop("acknowledgment", None)
            patient_state.update(parsed)
        except json.JSONDecodeError:
            pass
        data["stage"] = "questions"

    elif stage == "questions":
        next_q = data.get("pending_question")
        acknowledgment = None
        if next_q:
            field = next_q["field"]
            result = extract_answer_for_field(field, user_text, lang)
            try:
                parsed = json.loads(result)
                acknowledgment = parsed.pop("acknowledgment", None)
                value = parsed.get(field)
                if field == "associated_symptoms" and value and not isinstance(value, list):
                    value = [value]
                patient_state[field] = value
            except json.JSONDecodeError:
                patient_state[field] = "unclear"

            # Mark this field as explicitly answered, even if the answer was
            # "no"/empty -- otherwise the same question would repeat forever.
            data.setdefault("answered_fields", [])
            if field not in data["answered_fields"]:
                data["answered_fields"].append(field)

    elif stage == "hospital_selection":
        response_payload["messages"].append({
            "type": "bot_text",
            "text": "This assessment is already complete. Refresh the page to start a new one."
        })
        response_payload["stage"] = "done"
        return jsonify(response_payload)

    elif stage == "done":
        response_payload["messages"].append({
            "type": "bot_text",
            "text": "This assessment is complete. Refresh the page to start a new one."
        })
        response_payload["stage"] = "done"
        return jsonify(response_payload)

    # After processing intake or a question answer, decide what's next
    next_q = get_next_question(patient_state, lang, data.get("answered_fields"))

    if next_q is not None:
        data["pending_question"] = next_q
        response_payload["messages"].append({
            "type": "bot_question",
            "text": next_q["question"],
            "ack": acknowledgment or ""
        })
        response_payload["state"] = patient_state
        response_payload["stage"] = data["stage"]
        return jsonify(response_payload)

    # All fields collected -> final assessment
    stored_profile = data.get("profile") or {}
    assessment = build_assessment(patient_state, lang, stored_profile)
    data["stage"] = "done"

    if acknowledgment:
        response_payload["messages"].append({"type": "bot_text", "text": acknowledgment})

    response_payload["messages"].append(assessment)
    response_payload["state"] = patient_state
    response_payload["stage"] = data["stage"]
    return jsonify(response_payload)


@app.route("/api/recompute", methods=["POST"])
def api_recompute():
    """
    Re-runs the assessment after the user edits/removes a field from the
    symptom summary on the dashboard (e.g. deletes a wrongly-extracted item).
    """
    sid = get_session_id()
    data = SESSIONS[sid]

    patient_state = request.json.get("patient_state", {})
    lang = request.json.get("lang", "en")
    profile = data.get("profile") or {}

    data["patient_state"] = patient_state
    assessment = build_assessment(patient_state, lang, profile)
    return jsonify({"assessment": assessment})


@app.route("/api/analyze-report", methods=["POST"])
def api_analyze_report():
    """
    Accepts an uploaded medical report (image or PDF) and asks Gemini's
    multimodal understanding to summarize it in plain language.
    This is informational only -- explicitly not a diagnosis.
    """
    from google.genai import types

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    uploaded = request.files["file"]
    file_bytes = uploaded.read()
    mime_type = uploaded.mimetype or "application/octet-stream"
    lang = request.form.get("lang", "en")
    lang_name = LANG_NAMES.get(lang, "English")

    prompt = f"""
    You are a cautious healthcare navigation assistant, NOT a doctor. The user uploaded
    a medical report (lab result, prescription, or scan summary). Read it and, IN {lang_name}:

    1. For each test/value that has an explicit reference range printed on the report,
       compare the value to that range and classify status as one of:
       "normal" (within range), "low" (below range), "high" (above range).
       If no range is printed for a value, use status "unclear" -- do NOT invent a
       reference range yourself.
    2. For each finding with status "low" or "high", add a one-sentence, general,
       plain-language note on what that value broadly relates to in the body
       (e.g. "hemoglobin relates to how blood carries oxygen") -- general education
       only, NOT a diagnosis, NOT a severity judgment.
    3. Calculate overall_score_percent = (count of "normal" findings / count of findings
       with a known status) * 100, rounded to nearest whole number. If no findings have
       a known status, use null.
    4. Summarize in 2-3 plain-language sentences what the report appears to cover overall.
    5. Do NOT diagnose, do NOT say something is dangerous, do NOT recommend treatment.

    Return ONLY valid JSON, no other text, no markdown:
    {{
      "findings": [
        {{"name": "Hemoglobin", "value": "14.2 g/dL", "range": "13.0-17.0", "status": "normal", "note": ""}}
      ],
      "overall_score_percent": 85,
      "summary": "2-3 sentence summary",
      "note": "reminder to consult a doctor"
    }}
    """

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                prompt,
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
            ]
        )
        raw_text = clean_json_text(response.text.strip())
        parsed = json.loads(raw_text)
        return jsonify(parsed)
    except Exception as e:
        print(f"[Report analysis error] {e}")
        return jsonify({"error": f"Could not analyze the report: {str(e)}"}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)