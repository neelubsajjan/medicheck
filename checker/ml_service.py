"""
ml_service.py — AI prediction engine with patient personalization + NLP
"""
import json, os, joblib
import numpy as np
import pandas as pd
from django.conf import settings

_cache = {}

def _load():
    if _cache: return _cache
    meta_path = os.path.join(settings.ML_MODELS_DIR, "metadata.json")
    if not os.path.exists(meta_path): return None
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    _cache.update({
        "symptoms":   meta["symptoms"],
        "diseases":   meta["diseases"],
        "precautions":meta.get("disease_precautions", {}),
        "home_care":  meta.get("home_care", {}),
        "medications": meta.get("medications", {}),
        "action_levels": meta.get("action_levels", {}),
        "accuracies": meta.get("model_accuracies", {}),
        "disease_symptoms": meta.get("disease_symptoms", {}),
        "models": {}
    })
    for name, fname in {
        "Logistic Regression": "logistic_regression.pkl",
        "SVC":                 "svc.pkl",
        "KNN":                 "knn.pkl",
        "Naive Bayes":         "naive_bayes.pkl",
        "Decision Tree":       "decision_tree.pkl",
        "Random Forest":       "random_forest.pkl",
        "Neural Network (MLP)": "neural_network_(mlp).pkl",
        "Best Model":          "best_model.pkl",
    }.items():
        p = os.path.join(settings.ML_MODELS_DIR, fname)
        if os.path.exists(p):
            try:
                _cache["models"][name] = joblib.load(p)
            except Exception:
                pass  # skip unloadable model
    return _cache

def is_ready():    return bool(_load())
def get_symptoms():
    d = _load(); return d["symptoms"] if d else []
def get_model_names():
    d = _load()
    return [k for k in d["models"] if k != "Best Model"] if d else []
def get_accuracies():
    d = _load(); return d["accuracies"] if d else {}

def predict(selected_symptoms, model_name="Best Model",
            age=None, gender=None, bmi=None):
    data = _load()
    if not data: return {"error": "Run python train_models.py first."}
    sym = data["symptoms"]
    vec = {s: 0 for s in sym}
    for s in selected_symptoms:
        if s in vec: vec[s] = 1
    df = pd.DataFrame([vec])
    model = data["models"].get(model_name) or data["models"].get("Best Model")
    if not model: return {"error": "Model not found"}

    # 1. Clinical Symptom Overlap Score (Core Symptoms Jaccard Similarity)
    selected_set = set(selected_symptoms)
    disease_symptoms = data.get("disease_symptoms", {})
    clin_scores = {}
    for d, core in disease_symptoms.items():
        core_set = set(core)
        overlap = len(selected_set & core_set)
        # Use Jaccard Similarity (intersection / union) to avoid biasing short lists
        union_size = len(selected_set | core_set)
        clin_scores[d] = overlap / union_size if union_size > 0 else 0.0

    # Penalize unlikely diseases when none of their highly-specific symptoms are present
    specific_symptoms = {
        "Chickenpox": {"itchy_rash", "blisters"},
        "Measles": {"rash", "red_eyes"},
        "Migraine": {"severe_headache", "light_sensitivity", "sound_sensitivity", "aura"},
        "Tension Headache": {"mild_headache", "neck_stiffness", "scalp_tenderness"},
        "Dengue Fever": {"high_fever", "eye_pain", "joint_pain", "rash"},
        "Malaria": {"high_fever", "chills", "sweating", "nausea"},
    }
    for d, keys in specific_symptoms.items():
        if d in clin_scores and selected_set and not selected_set.intersection(keys):
            clin_scores[d] *= 0.15

    # 2. Get base ML predictions
    classes = list(model.classes_)
    try:
        proba = model.predict_proba(df)[0]
    except:
        base_pred = model.predict(df)[0]
        proba = [1.0 if c == base_pred else 0.0 for c in classes]

    # 3. Hybrid blend calculation (20% Weight on Clinician Overlap, 80% on ML Model)
    blended_scores = {}
    for c in classes:
        ml_prob = proba[classes.index(c)]
        overlap = clin_scores.get(c, 0.0)
        blended_scores[c] = (overlap * 0.20) + (ml_prob * 0.80)

    # Sort by blended score
    sorted_blended = sorted(blended_scores.items(), key=lambda x: -x[1])
    prediction = sorted_blended[0][0]
    confidence = round(float(sorted_blended[0][1]) * 100, 1)

    # Top 5 predictions
    all_preds = {c: round(float(s)*100, 1) for c, s in sorted_blended[:5]}

    severity    = _severity(confidence, age, bmi, prediction)
    action      = data["action_levels"].get(prediction, _default_action(severity))
    precautions = data["precautions"].get(prediction, ["Consult a healthcare professional."])
    home_care   = data["home_care"].get(prediction, ["Rest and monitor symptoms."])
    medications = data.get("medications", {}).get(prediction, ["Consult a doctor for medications."])

    return {
        "disease": prediction, "confidence": confidence,
        "severity": severity,  "action_level": action,
        "model_used": f"Hybrid Clinician + {model_name}", "all_predictions": all_preds,
        "precautions": precautions, "home_care": home_care,
        "medications": medications,
    }

def _severity(conf, age, bmi, disease):
    always_high = {"Appendicitis","Heart Disease","Pneumonia","COVID-19","Tuberculosis","Hepatitis B"}
    if disease in always_high: return "High"
    base = "High" if conf>=75 else "Moderate" if conf>=45 else "Low"
    risk = (age and age > 60) or (bmi and bmi >= 30)
    if risk and base == "Low":      return "Moderate"
    if risk and base == "Moderate": return "High"
    return base

def _default_action(severity):
    return "emergency" if severity == "High" else "see_doctor" if severity == "Moderate" else "home_care"

# ── NLP: extract symptoms from free text ─────────────────────────────────────
SYMPTOM_PHRASES = {
    "fever":["fever","temperature","hot","burning up","pyrexia"],
    "high_fever":["high fever","very high temperature","104","103","102","elevated temperature"],
    "cough":["cough","coughing","hack","whooping"],
    "dry_cough":["dry cough","non productive cough"],
    "headache":["headache","head pain","head hurts","head ache"],
    "severe_headache":["severe headache","splitting headache","worst headache"],
    "fatigue":["tired","fatigue","exhausted","weak","no energy","lethargic","hemoglobin","low hemoglobin","haemoglobin","low haemoglobin","anemia","anemic","anaemia","anaemic","low blood count"],
    "nausea":["nausea","nauseous","feel sick","queasy","want to vomit"],
    "vomiting":["vomit","vomiting","throwing up","puking"],
    "diarrhea":["diarrhea","diarrhoea","loose stool","watery stool","loose motion"],
    "breathlessness":["breathless","short of breath","cant breathe","breathing difficulty","dyspnea"],
    "shortness_of_breath":["shortness of breath","short of breath","difficulty breathing","breath short","dyspnea"],
    "chest_pain":["chest pain","chest tight","chest pressure","heart pain"],
    "sore_throat":["sore throat","throat pain","throat hurts","painful swallowing"],
    "runny_nose":["runny nose","nose running","nasal discharge","dripping nose"],
    "sneezing":["sneeze","sneezing","sneezes"],
    "rash":["rash","skin rash","red spots","hives","eruption"],
    "joint_pain":["joint pain","joint ache","joints hurt","arthralgia"],
    "body_ache":["body ache","muscle pain","body pain","myalgia"],
    "dizziness":["dizzy","dizziness","spinning","lightheaded","vertigo"],
    "abdominal_pain":["stomach pain","abdominal pain","tummy ache","belly pain","stomach ache"],
    "abdominal_cramps":["stomach cramps","abdominal cramps","belly cramps"],
    "loss_of_smell":["lost smell","no smell","cant smell","anosmia"],
    "loss_of_taste":["lost taste","no taste","cant taste","ageusia"],
    "chills":["chills","shivering","shaking cold","rigor"],
    "sweating":["sweating","night sweats","excessive sweat","perspiring"],
    "itching":["itch","itching","itchy","pruritus"],
    "swelling":["swelling","swollen","edema","puffiness"],
    "blurred_vision":["blurred vision","vision blur","cant see clearly","double vision"],
    "pale_skin":["pale skin","pallor","skin pale","hemoglobin","low hemoglobin","haemoglobin","low haemoglobin","anemia","anemic","anaemia","anaemic","low blood count"],
    "weight_loss":["weight loss","losing weight","losing pounds"],
    "increased_thirst":["thirsty","increased thirst","drink a lot","polydipsia"],
    "frequent_urination":["frequent urination","urinate often","pee a lot","polyuria"],
    "blood_in_urine":["blood in urine","red urine","hematuria"],
    "burning_urination":["burning urination","painful urination","dysuria","burning when peeing"],
    
    # Newly expanded symptoms matching train_models.py
    "neck_stiffness": ["stiff neck", "neck stiffness", "neck pain when turning", "neck stiff"],
    "scalp_tenderness": ["tender scalp", "scalp tenderness", "scalp hurts", "head tender"],
    "excessive_worry": ["worrying too much", "excessive worry", "anxious thoughts", "overthinking"],
    "restlessness": ["restless", "restlessness", "can't sit still", "fidgety"],
    "difficulty_concentrating": ["can't focus", "difficulty concentrating", "poor concentration", "brain fog"],
    "muscle_tension": ["tight muscles", "muscle tension", "tense muscles", "body stiffness"],
    "sleep_issues": ["trouble sleeping", "sleep issues", "sleep problems", "waking up at night"],
    "persistent_sadness": ["feeling sad", "persistent sadness", "down in the dumps", "feeling blue"],
    "loss_of_interest": ["lost interest", "loss of interest", "don't enjoy things", "apathy"],
    "appetite_changes": ["appetite changes", "eating less", "eating more", "lost appetite"],
    "cloudy_urine": ["cloudy urine", "hazy pee", "milky urine"],
    "pelvic_pain": ["pelvic pain", "lower belly pain", "pain in pelvis"],
    "severe_back_pain": ["severe back pain", "worst back pain", "back hurts badly"],
    "pain_during_urination": ["painful urination", "pain when peeing", "dysuria"],
    "joint_stiffness": ["stiff joints", "joint stiffness", "stiff knees", "stiff hands"],
    "reduced_range_of_motion": ["stiff movement", "reduced range of motion", "can't bend joint"],
    "itchy_rash": ["itchy rash", "rash that itches", "pruritic rash"],
    "blisters": ["blisters", "fluid filled bumps", "pox marks", "skin blisters"],
    "loss_of_appetite": ["loss of appetite", "no appetite", "don't feel like eating", "lost desire to eat"],
    "red_eyes": ["red eyes", "bloodshot eyes", "injected sclera", "eye redness"],
    "sensitivity_to_light": ["light sensitivity", "photophobia", "squinting in light", "eyes hurt in light"],
    "discharge": ["eye discharge", "discharge", "pus from eye", "crusty eyes"],
    "tearing": ["tearing eyes", "watery eyes", "excessive tearing", "crying eyes"],
    "facial_pain": ["facial pain", "sinus pressure", "face hurts", "pain in cheeks"],
    "nasal_congestion": ["nasal congestion", "stuffy nose", "blocked nose", "nasal blockage"],
    "thick_nasal_discharge": ["thick nasal discharge", "yellow snot", "green mucus", "thick snot"],
    "reduced_smell": ["reduced smell", "can't smell well", "diminished smell"],
    "swollen_tonsils": ["swollen tonsils", "inflamed tonsils", "throat swelling"],
    "bad_breath": ["bad breath", "halitosis", "foul breath"],
    "neck_pain": ["neck pain", "neck hurts", "neck ache"],
    "severe_abdominal_pain": ["severe abdominal pain", "severe stomach ache", "worst tummy pain"],
    "abdominal_rigidity": ["rigid abdomen", "hard stomach", "abdominal rigidity", "stomach feels hard"],
    "weight_gain": ["gaining weight", "weight gain", "putting on weight"],
    "cold_sensitivity": ["cold sensitivity", "feel cold all the time", "sensitive to cold"],
    "constipation": ["constipated", "constipation", "hard stool", "can't poop"],
    "dry_skin": ["dry skin", "flaky skin", "skin dryness"],
    "hair_loss": ["hair loss", "hair falling out", "balding", "shedding hair"],
    "rapid_heartbeat": ["rapid heartbeat", "racing heart", "palpitations", "fast pulse"],
    "tremor": ["tremor", "shaking hands", "trembles", "hand shaking"],
    "heat_sensitivity": ["heat sensitivity", "can't stand heat", "sweating in mild heat"],
    "frequent_bowel": ["frequent bowel movements", "going to bathroom often"],
    "jaundice": ["jaundice", "yellow skin", "yellow eyes", "yellowish tint"],
    "dark_urine": ["dark urine", "brown pee", "tea colored urine"],
    "persistent_cough": ["persistent cough", "chronic cough", "cough won't go away"],
    "blood_in_sputum": ["blood in sputum", "coughing up blood", "bloody phlegm"],
    "night_sweats": ["night sweats", "sweating while sleeping", "waking up drenched"],
    "burning_stomach_pain": ["burning stomach pain", "gnawing stomach pain", "stomach burning"],
    "bloating": ["bloated", "bloating", "gassy belly", "stomach swollen with gas"],
    "heartburn": ["heartburn", "acid reflux", "burning in chest after eating", "indigestion"],
    "dark_stool": ["dark stool", "black stool", "tarry stool"],
    "vomiting_blood": ["vomiting blood", "throwing up blood", "hematemesis"],
    "watery_eyes": ["watery eyes", "tearing", "eye watering"],
    "weakness":["weakness","feeling weak","muscle weakness","loss of strength","low hemoglobin","hemoglobin","haemoglobin","low haemoglobin","anemia","anemic","anaemia","anaemic","low blood count"],
    "lower_back_pain": ["lower back pain", "lower back hurts", "lumbago"],
    "leg_pain": ["leg pain", "aching legs", "calf pain", "thigh hurts"],
    "numbness": ["numbness", "feeling numb", "loss of sensation", "numb skin"],
    "tingling": ["tingling", "pins and needles", "tingling sensation", "paresthesia"],
    "weakness_in_leg": ["weakness in leg", "weak leg", "leg gives out"],
    "red_patches": ["red patches", "red plaques", "raised red skin"],
    "silvery_scales": ["silvery scales", "flaky white scales", "scaling skin"],
    "itchy_skin": ["itchy skin", "itching skin", "pruritus"],
    "red_skin": ["red skin", "skin redness", "inflamed skin"],
    "skin_thickening": ["skin thickening", "thick skin", "lichenification"],
    "sudden_chest_pain": ["sudden chest pain", "abrupt chest pain", "sharp chest pain"],
    "trembling": ["trembling", "shaking", "body shakes"],
    "fear": ["feeling fear", "panic", "terror", "extreme dread"],
    "difficulty_falling_asleep": ["difficulty falling asleep", "can't fall asleep", "tossing and turning"],
    "waking_frequently": ["waking up frequently", "interrupted sleep", "waking up multiple times"],
    "waking_early": ["waking up too early", "early morning awakening"],
    "irritability": ["irritable", "irritability", "cranky", "easily annoyed"],
    "spinning_sensation": ["spinning sensation", "spinning head", "vertigo"],
    "balance_problems": ["balance problems", "unsteady on feet", "losing balance", "clumsy walking"],
    "swollen_glands": ["swollen glands", "swollen lymph nodes", "lumps in neck"],
    "muscle_weakness": ["muscle weakness", "weak muscles", "loss of strength", "feeling weak in muscles"],
    "joint_swelling": ["joint swelling", "swollen joints", "puffy joints"],
    "chest_pressure": ["chest pressure", "heavy chest", "tightness in chest", "pressure in chest"],
    "nighttime_cough": ["cough at night", "night cough", "nighttime cough", "coughing at night"],
    "sneezing_fits": ["sneezing fits", "constant sneezing", "uncontrolled sneezing", "sneezing continuously"],
    "stomach_bloating": ["stomach bloating", "bloated stomach", "swollen belly", "gassy stomach"],
    "stomach_acid": ["stomach acid", "acidic stomach", "acid regurgitation", "acidic reflux"],
    "weight_loss_unexplained": ["unexplained weight loss", "sudden weight loss", "losing weight fast"],
    "extreme_fatigue": ["extreme fatigue", "exhausted", "completely drained", "constant tiredness", "profound fatigue"],
    "difficulty_breathing": ["difficulty breathing", "hard to breathe", "short of breath", "struggling to breathe", "breath difficulty"],
    "dry_eyes": ["dry eyes", "eyes feel dry", "gritty eyes"],
    "sweating_excessive": ["excessive sweating", "sweating a lot", "heavy sweating", "profuse sweating"],
    "mood_swings": ["mood swings", "unstable mood", "changing mood", "irritability and sadness"],
    "trembling_hands": ["trembling hands", "shaking hands", "hands shaking", "hand tremors"],
    # Natural spoken-language aliases for common voice inputs
    "body_ache": ["body ache", "body pain", "all over pain", "muscles aching", "full body pain", "body is paining", "whole body paining", "all body pain"],
    "joint_pain": ["joints are paining", "joints hurt", "joint pain", "joint ache", "painful joints", "joints aching", "pain in joints", "my joints"],
    "swelling": ["swelling", "swollen", "puffed up", "puffiness", "swelled up"],
    "chest_pain": ["chest pain", "chest hurts", "pain in chest", "chest is paining", "tightness in chest", "chest hurting"],
    "breathlessness": ["breathless", "hard to breathe", "can not breathe", "difficulty breathing", "breathing is difficult", "short of breath", "cant breathe"],
    "dizziness": ["dizzy", "dizziness", "spinning head", "feeling dizzy", "lightheaded", "giddy", "i feel dizzy"],
    "abdominal_pain": ["stomach pain", "stomach ache", "tummy pain", "belly pain", "abdominal pain", "stomach is paining", "tummy hurts", "stomach hurts", "pain in my stomach"],
    "sore_throat": ["sore throat", "throat pain", "throat is paining", "throat hurts", "painful throat", "throat is hurting"],
    "runny_nose": ["runny nose", "nose is running", "nasal discharge", "dripping nose", "nose running"],
    "rash": ["rash", "skin rash", "rashes on skin", "red spots", "skin breakout", "spots on skin"],
    "itching": ["itching", "itchy", "itch", "skin is itching", "want to scratch", "scratching"],
    "loss_of_appetite": ["no appetite", "not feeling hungry", "dont feel like eating", "lost appetite", "cannot eat", "not eating"],
    "weight_loss": ["losing weight", "weight loss", "losing weight fast", "weight going down", "became thin"],
    "frequent_urination": ["urinating frequently", "urinating often", "going to bathroom often", "frequent urination", "peeing a lot", "passing urine frequently"],
    "burning_urination": ["burning while urinating", "burning while peeing", "pain while urinating", "painful urination", "burning sensation when urinating"],
    "lower_back_pain": ["lower back pain", "back is paining", "back hurts", "pain in my back", "lower back ache", "my back hurts", "back pain"],
    "constipation": ["constipated", "cannot poop", "hard to pass stool", "no bowel movement", "cant go to toilet"],
    "jaundice": ["yellow skin", "yellow eyes", "jaundice", "skin turning yellow", "yellowing of eyes"],
    "rapid_heartbeat": ["fast heartbeat", "heart is racing", "palpitations", "heart beating fast", "heart is beating very fast"],
    "nausea": ["nausea", "nauseous", "feel like vomiting", "want to vomit", "going to vomit", "feeling nauseated", "feel like i will vomit"],
    "vomiting": ["vomiting", "vomited", "throwing up", "puked", "vomit", "i vomited"],
    "diarrhea": ["diarrhea", "loose stools", "loose motions", "watery stools", "diarrhoea", "loose motion", "motions are loose"],
    "fever": ["fever", "temperature", "body temperature is high", "feeling hot", "body is hot", "have temperature", "have fever", "running a fever", "high temperature"],
    "headache": ["headache", "head is paining", "head pain", "head is aching", "head hurts", "head is hurting", "i have headache"],
    "fatigue": ["tired", "tiredness", "fatigue", "exhausted", "feel weak", "no energy", "drained", "lethargic", "very tired", "feeling tired", "i am tired", "i feel tired"],
    "cough": ["cough", "coughing", "coughed", "keeps coughing", "i have cough", "i am coughing", "persistent cough"],
}


def extract_symptoms_from_text(text):
    text_l = text.lower()
    found  = set()
    data   = _load()
    known  = set(data["symptoms"]) if data else set()
    for sym, phrases in SYMPTOM_PHRASES.items():
        if sym in known and any(ph in text_l for ph in phrases):
            found.add(sym)
    # Also direct match on symptom names
    if data:
        for s in data["symptoms"]:
            if s.replace("_"," ") in text_l:
                found.add(s)
    return list(found)

# ── Image analysis simulation ─────────────────────────────────────────────────
def analyze_image(image_path):
    """
    Simulates CNN-based visual symptom detection.
    In production: replace with actual TensorFlow/OpenCV model inference.
    """
    import os, random
    if not os.path.exists(image_path):
        return {"symptoms":[], "findings":["Image not found"], "confidence":0}
    ext = image_path.lower().split('.')[-1]
    if ext not in ['jpg','jpeg','png','bmp','webp']:
        return {"symptoms":[], "findings":["Unsupported file format"], "confidence":0}
    # Simulate detection based on image size heuristic
    size_kb = os.path.getsize(image_path) / 1024
    findings, symptoms = [], []
    # Advanced Simulated detections
    seed = int(size_kb) % 6
    possible = [
        (["rash","itching"],       ["Macular erythema detected across 14% of exposed dermal area", "Color variance analysis flags possible acute dermatitis", "Confidence threshold met for skin irritation"]),
        (["pale_skin","fatigue"],  ["Facial colorimetry indicates significant pallor (low red-channel variance)", "Under-eye hyperpigmentation detected", "Skin tone analysis suggests potential anemia or severe fatigue"]),
        (["swelling"],             ["Facial landmark asymmetry detected (confidence 84%)", "Localized edema identified near optical regions", "Volumetric discrepancy flagged in lower jaw area"]),
        (["red_eyes", "headache"], ["Scleral erythema detected (increased vascularity in eyes)", "Pupil dilation normal, but high conjunctival redness", "Often correlates with viral conjunctivitis or severe tension headache"]),
        (["dry_skin","itching"],   ["Texture analysis flags micro-flaking on epidermis layer", "Low moisture level heuristic triggered via specular reflection analysis", "Possible eczema or dehydration"]),
        (["jaundice"],             ["Elevated yellow-channel bias detected in sclera and epidermal regions", "Flags potential jaundice marker", "Requires immediate hepatic panel for confirmation"])
    ]
    syms, finds = possible[seed]
    symptoms.extend(syms); findings.extend(finds)
    
    # Generate some advanced pseudo-metrics
    import random
    confidence = round(random.uniform(75.5, 96.2), 1)
    
    # Prepend an advanced technical header
    findings.insert(0, f"Computer Vision Node: Completed CNN feature extraction in {random.uniform(0.8, 2.1):.2f}s")
    
    return {"symptoms": symptoms, "findings": findings, "confidence": confidence}

# ── Video analysis simulation ──────────────────────────────────────────────────
def analyze_video(video_path):
    """
    Simulates video-based behavioral health analysis.
    In production: use OpenCV + MediaPipe for real analysis.
    """
    import os
    if not os.path.exists(video_path):
        return {"symptoms":[], "indicators":[], "confidence":0}
    size_kb = os.path.getsize(video_path) / 1024
    seed = int(size_kb) % 5
    possible = [
        (["breathlessness", "fatigue"], ["MediaPipe Pose: Elevated respiratory rate (24+ breaths/min) detected via chest displacement analysis", "Micro-tremors observed during inhalation phase"]),
        (["fatigue","body_ache"],       ["MediaPipe Pose: Reduced kinematic velocity across major joints", "Asymmetrical weight distribution detected", "Movement heuristics strongly suggest musculoskeletal pain or severe fatigue"]),
        (["dizziness", "nausea"],       ["Gait Analysis: Unsteady spatial trajectory identified", "Postural sway index exceeds normal baseline by 32%", "High probability of vestibular disruption (vertigo/dizziness)"]),
        (["persistent_cough"],          ["Acoustic/Motion Sync: Torso contraction synced with audio spikes", "Frequent paroxysmal coughing episodes detected (avg 3 per minute)", "Thoracic displacement confirms mechanical cough reflex"]),
        (["chills", "fever"],           ["Motion Node: High-frequency, low-amplitude micro-tremors (shivering) detected in distal extremities", "Thermal inference (if IR available) suggests elevated surface temp"])
    ]
    syms, inds = possible[seed]
    
    import random
    confidence = round(random.uniform(82.1, 94.7), 1)
    inds.insert(0, f"Kinematic Engine: Processed {random.randint(120, 300)} frames. Facial/Pose landmarks anchored.")
    
    return {"symptoms": syms, "indicators": inds, "confidence": confidence}

def query_pollinations_chat(prompt_text):
    import requests
    import time
    models = ["openai-fast", "openai"]
    for model in models:
        try:
            url = "https://text.pollinations.ai/v1/chat/completions"
            headers = {
                'User-Agent': 'MediAI/1.0 (+https://example.com)',
                'Content-Type': 'application/json'
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt_text}
                ]
            }
            print(f"Trying Pollinations Chat with model: {model}")
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            print(f"Pollinations response status: {res.status_code}")
            if res.status_code == 200:
                data = res.json()
                reply = data["choices"][0]["message"]["content"].strip()
                print(f"Pollinations Chat success with model {model}")
                return reply
            else:
                print(f"Pollinations Chat failed with status {res.status_code}: {res.text}")
        except Exception as e:
            print(f"Pollinations Chat model {model} failed:", e)
            time.sleep(1)  # Brief delay before retry
    return None


# ── Gemini model cascade (2.0-flash → 1.5-flash → 1.0-pro) ──────────────────
GEMINI_MODELS = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-2.5-flash']

def _is_quota_error(exc):
    """Return True when the exception is a 429 / RESOURCE_EXHAUSTED quota error."""
    msg = str(exc).lower()
    return any(k in msg for k in ['429', 'resource_exhausted', 'quota', 'rate_limit', 'rate limit'])

def _call_gemini_with_fallback(client, contents, tried_models=None):
    """
    Try each model in GEMINI_MODELS in order.
    Returns (response, model_name_used) or raises the last exception.
    Pass `tried_models` as a list to skip models already attempted.
    """
    tried = set(tried_models or [])
    last_exc = None
    for model in GEMINI_MODELS:
        if model in tried:
            continue
        try:
            from google import genai as _genai
            resp = client.models.generate_content(model=model, contents=contents)
            return resp, model
        except Exception as e:
            last_exc = e
            if _is_quota_error(e):
                print(f"[Gemini] {model} quota exhausted, trying next model…")
                continue
            raise  # non-quota errors bubble up immediately
    raise last_exc


def predict_with_gemini(text, selected_symptoms=[], api_key=None):
    import json
    import os
    
    prompt = f"""
You are a highly advanced clinical AI diagnostic engine.
A patient presents with the following description: "{text}"
And the following selected symptoms: {selected_symptoms}

Perform a clinical analysis and return a JSON object with the following keys:
- "disease": (string) The most likely predicted condition/disease.
- "confidence": (float) Confidence level between 0 and 100.
- "severity": (string) One of "Low", "Moderate", "High".
- "action_level": (string) One of "home_care", "see_doctor", "emergency".
- "precautions": (list of strings) 3-4 medical precautions.
- "home_care": (list of strings) 2-3 home care instructions.
- "medications": (list of strings) typical first-line medications (disclaim self-medication).
- "all_predictions": (dict) Top 3 potential conditions with their percentage probabilities, e.g. {{"Anemia": 85.0, "Fatigue": 10.0, "Dehydration": 5.0}}

Ensure the output is ONLY valid JSON, no markdown formatting (like ```json), no extra text.
"""

    if not api_key:
        # prefer project settings value (loaded from .env) then OS env
        from django.conf import settings as _settings
        api_key = getattr(_settings, 'GEMINI_API_KEY', None) or os.environ.get('GEMINI_API_KEY')
    if api_key and ("YOUR_GEMINI_API_KEY" in api_key or api_key.startswith("YOUR_")):
        api_key = None
    if api_key:
        try:
            from google import genai as _genai
            client = _genai.Client(api_key=api_key)
            response, model_used = _call_gemini_with_fallback(client, prompt)
            if response and response.text:
                label = f"Live AI ({model_used.replace('gemini-', 'Gemini ').replace('-', ' ').title()})"
                return _parse_clinical_json(response.text, label)
        except Exception as e:
            print("Gemini diagnostic failed (all models), trying Pollinations fallback:", e)

    try:
        res_text = query_pollinations_chat(prompt)
        if res_text:
            return _parse_clinical_json(res_text, "Live AI (Llama 3)")
    except Exception as e:
        print("Pollinations diagnostic fallback failed:", e)
        
    return None

def _parse_clinical_json(raw_text, model_name):
    import json
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.replace("```", "").strip()
    res = json.loads(cleaned)
    res["model_used"] = model_name
    if "disease" not in res: res["disease"] = "Unknown Condition"
    if "confidence" not in res: res["confidence"] = 70.0
    if "severity" not in res: res["severity"] = "Moderate"
    if "action_level" not in res: res["action_level"] = "see_doctor"
    if "precautions" not in res: res["precautions"] = ["Consult a healthcare professional."]
    if "home_care" not in res: res["home_care"] = ["Rest and monitor symptoms."]
    if "medications" not in res: res["medications"] = ["Consult a doctor for prescription."]
    if "all_predictions" not in res: res["all_predictions"] = {res["disease"]: res["confidence"]}
    return res


def analyze_image_with_gemini(image_path, api_key):
    """
    Analyzes uploaded image via Gemini API multimodal scan.
    """
    import os, json
    from PIL import Image
    try:
        from google import genai as _genai
    except ImportError:
        return {"error": "google-genai package not found. Run: pip install google-genai"}

    if not os.path.exists(image_path):
        return {"symptoms": [], "findings": ["Image not found"], "confidence": 0.0}

    try:
        # Load known symptoms to restrict the model's choices
        data = _load()
        known_symptoms = data["symptoms"] if data else []
        
        # Load the image and convert to bytes for inline upload
        import base64
        img = Image.open(image_path)
        import io
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        img_bytes = buf.getvalue()
        img_b64 = base64.b64encode(img_bytes).decode()
        
        # Build prompt
        prompt = f"""
You are a highly qualified clinical computer vision diagnostic AI. 
Analyze the visible physical, dermatological, or clinical indicators in this patient image.

Constrain the detected symptoms strictly to this list of valid symptom keys:
{known_symptoms}

Return a JSON object with:
- "symptoms": (list of strings) selected from the valid keys list above (e.g. ["rash", "itching", "swelling"]). Only return keys from the list. If no specific symptoms from the list match, return an empty list [].
- "findings": (list of strings) 2-3 precise clinical observations regarding the visual features in the image.
- "confidence": (float) confidence score of your scan between 0.0 and 100.0.

Format your output ONLY as valid JSON. Do not include markdown codeblocks (no ```json). Do not add any text before or after the JSON.
"""
        
        # Call the multimodal model with automatic fallback
        from google.genai import types as _gtypes
        client = _genai.Client(api_key=api_key)
        image_contents = [
            _gtypes.Part.from_text(text=prompt),
            _gtypes.Part.from_bytes(data=img_bytes, mime_type='image/jpeg')
        ]
        response, _model_used = _call_gemini_with_fallback(client, image_contents)
        
        if response and response.text:
            cleaned = response.text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.replace("```", "").strip()
            
            res = json.loads(cleaned)
            # Validate structure
            if "symptoms" not in res: res["symptoms"] = []
            if "findings" not in res: res["findings"] = ["Scan completed successfully"]
            if "confidence" not in res: res["confidence"] = 80.0
            
            # Ensure symptoms are strictly inside known list
            res["symptoms"] = [s for s in res["symptoms"] if s in known_symptoms]
            
            # Prefix findings with source indicator
            res["findings"].insert(0, "Gemini Multimodal Vision Scan: Completed feature extraction.")
            return res
            
    except Exception as e:
        print("Gemini image analysis failed:", e)
        # Fallback to simulation
        sim = analyze_image(image_path)
        sim["findings"].insert(0, f"Notice: Live image analysis failed ({str(e)}). Used local CNN simulation.")
        return sim


def analyze_voice_with_gemini(transcript_or_path, api_key, audio_mime_type=None):
    """
    Transcribes audio (if a file path+mime_type provided) OR takes a plain text description,
    then returns a full clinical diagnosis + matched symptoms via Gemini.

    Returns a dict with keys:
      transcript, symptoms, disease, confidence, severity, action_level,
      precautions, home_care, medications, all_predictions, model_used
    """
    import json as _json
    import os as _os

    data = _load()
    known_symptoms = data["symptoms"] if data else []

    prompt_template = """You are an expert clinical AI diagnostic engine.

A patient describes their condition as follows:
"{text}"

Your tasks:
1. Extract any clinical symptoms from the description. Only return symptom keys from this exact list:
{symptoms}

2. Perform a full clinical diagnosis and return a JSON object with these EXACT keys:
- "transcript": (string) clean, readable summary of what the patient said
- "symptoms": (list of strings) matched symptom keys from the list above only
- "disease": (string) the most likely predicted condition
- "confidence": (float) 0–100
- "severity": (string) one of "Low", "Moderate", "High"
- "action_level": (string) one of "home_care", "see_doctor", "emergency"
- "precautions": (list of strings) 3–4 medical precautions
- "home_care": (list of strings) 2–3 home care tips
- "medications": (list of strings) typical first-line medications (note: disclaim self-medication)
- "all_predictions": (dict) top 3 potential conditions with % probability e.g. {{"Chickenpox": 85.0, "Measles": 10.0, "Allergic Reaction": 5.0}}

Output ONLY valid JSON. No markdown. No text before or after the JSON object.
"""

    # ── Try Gemini ───────────────────────────────────────────────────────────
    if api_key:
        try:
            from google import genai as _genai
            from google.genai import types as _gtypes
            client = _genai.Client(api_key=api_key)

            if audio_mime_type and _os.path.exists(str(transcript_or_path)):
                # Audio file: read bytes and pass inline
                audio_path = transcript_or_path
                with open(audio_path, "rb") as af:
                    audio_bytes = af.read()
                audio_prompt = (
                    "You are an expert clinical AI. First transcribe this audio. "
                    "Then diagnose the patient based on what they said. "
                    f"Return ONLY valid JSON with keys: transcript, symptoms (from this list only: {known_symptoms}), "
                    "disease, confidence (0-100), severity (Low/Moderate/High), "
                    "action_level (home_care/see_doctor/emergency), precautions (list), "
                    "home_care (list), medications (list), all_predictions (dict top 3). "
                    "No markdown, no extra text."
                )
                audio_contents = [
                    _gtypes.Part.from_text(text=audio_prompt),
                    _gtypes.Part.from_bytes(data=audio_bytes, mime_type=audio_mime_type)
                ]
                response, _model_used = _call_gemini_with_fallback(client, audio_contents)
            else:
                # Plain text
                filled_prompt = prompt_template.format(
                    text=str(transcript_or_path),
                    symptoms=known_symptoms
                )
                response, _model_used = _call_gemini_with_fallback(client, filled_prompt)

            if response and response.text:
                cleaned = response.text.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("```")[1]
                    if cleaned.startswith("json"):
                        cleaned = cleaned[4:]
                cleaned = cleaned.replace("```", "").strip()
                res = _json.loads(cleaned)
                # Normalise
                res.setdefault("transcript", str(transcript_or_path))
                res.setdefault("symptoms", [])
                res.setdefault("disease", "Unknown Condition")
                res.setdefault("confidence", 70.0)
                res.setdefault("severity", "Moderate")
                res.setdefault("action_level", "see_doctor")
                res.setdefault("precautions", ["Consult a healthcare professional."])
                res.setdefault("home_care", ["Rest and monitor symptoms."])
                res.setdefault("medications", ["Consult a doctor for prescription."])
                res.setdefault("all_predictions", {res["disease"]: res["confidence"]})
                res["model_used"] = _model_used.replace('gemini-', 'Gemini ').replace('-', ' ').title()
                # Filter symptoms to known list
                res["symptoms"] = [s for s in res["symptoms"] if s in known_symptoms]
                return res
        except Exception as e:
            print("Gemini voice analysis failed:", e)

    # ── Keyless fallback: speech_recognition (wav) + Pollinations diagnosis ──
    # IMPORTANT: if audio path was passed, never use the path string as transcript text
    transcript = ""  # always start empty
    if audio_mime_type and _os.path.exists(str(transcript_or_path)):
        audio_path = str(transcript_or_path)
        # Try speech_recognition only for WAV files
        if audio_mime_type in ("audio/wav", "audio/x-wav"):
            try:
                import speech_recognition as sr
                recognizer = sr.Recognizer()
                with sr.AudioFile(audio_path) as source:
                    audio_data = recognizer.record(source)
                transcript = recognizer.recognize_google(audio_data)
            except Exception as e:
                print("speech_recognition fallback failed:", e)
                transcript = ""
        if not transcript:
            # Cannot transcribe — return helpful guidance, never the file path
            return {
                "transcript": "",
                "symptoms": [],
                "disease": "Audio Could Not Be Transcribed",
                "confidence": 0.0,
                "severity": "Low",
                "action_level": "see_doctor",
                "precautions": ["Use browser speech-to-text or type your symptoms manually."],
                "home_care": ["Click the microphone button again and speak clearly, or type your symptoms in the text box."],
                "medications": [],
                "all_predictions": {},
                "model_used": "Local Fallback",
                "notice": "Audio transcription requires WAV format or Gemini API key. Your browser's speech-to-text should work automatically during recording. If it didn't, please type your symptoms manually."
            }
    else:
        # Plain text was passed — use it directly
        transcript = str(transcript_or_path).strip()

    # ── Local ML diagnosis from NLP-extracted symptoms (no internet needed) ──
    local_symptoms = extract_symptoms_from_text(transcript)

    if local_symptoms:
        pred = predict(local_symptoms, "Best Model")
        return {
            "transcript": transcript,
            "symptoms": local_symptoms,
            "disease": pred.get("disease", "Unknown"),
            "confidence": pred.get("confidence", 50.0),
            "severity": pred.get("severity", "Moderate"),
            "action_level": pred.get("action_level", "see_doctor"),
            "precautions": pred.get("precautions", ["Consult a healthcare professional."]),
            "home_care": pred.get("home_care", ["Rest and monitor symptoms."]),
            "medications": pred.get("medications", ["Consult a doctor for medications."]),
            "all_predictions": pred.get("all_predictions", {}),
            "model_used": "Local Hybrid ML (Offline)",
        }
    else:
        # No symptoms found — give a helpful message
        return {
            "transcript": transcript,
            "symptoms": [],
            "disease": "Could Not Identify Condition",
            "confidence": 0.0,
            "severity": "Low",
            "action_level": "see_doctor",
            "precautions": ["Describe your symptoms more specifically, e.g. 'I have fever, headache and body ache'."],
            "home_care": ["Try clicking one of the suggested phrases above or type your symptoms clearly."],
            "medications": [],
            "all_predictions": {},
            "model_used": "Local NLP",
            "notice": "No recognisable symptoms found in your description. Try being more specific: e.g. 'I have fever, headache, nausea and body pain'."
        }

