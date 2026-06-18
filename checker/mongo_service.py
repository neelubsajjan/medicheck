import pymongo
from django.conf import settings
from datetime import datetime

client = None
db = None

try:
    temp_client = pymongo.MongoClient(settings.MONGODB_HOST, settings.MONGODB_PORT, serverSelectionTimeoutMS=1000)
    # Ping the server to check connection; raises ServerSelectionTimeoutError if down
    temp_client.admin.command('ping')
    client = temp_client
    db = client[settings.MONGODB_DB]
except Exception as e:
    print("MongoDB is offline. Logging to MongoDB is disabled. Error:", e)
    client = None
    db = None

def log_symptom_check(user_id, symptoms, input_mode, disease, confidence, severity, action_level, medications, multimodal_ref=None):
    if db is None: return
    try:
        db.symptom_checks.insert_one({
            "user_id": user_id,
            "symptoms": symptoms,
            "input_mode": input_mode,
            "disease": disease,
            "confidence": confidence,
            "severity": severity,
            "action_level": action_level,
            "medications": medications,
            "multimodal_ref": multimodal_ref,
            "timestamp": datetime.utcnow()
        })
    except:
        pass

def log_chat_message(user_id, role, message, intent, symptoms_context):
    if db is None: return
    try:
        db.chat_history.insert_one({
            "user_id": user_id,
            "role": role,
            "message": message,
            "intent": intent,
            "symptoms_context": symptoms_context,
            "timestamp": datetime.utcnow()
        })
    except:
        pass

def log_patient_profile(user_id, age, gender, bmi, location):
    if db is None: return
    try:
        db.patient_profiles.update_one(
            {"user_id": user_id},
            {"$set": {
                "age": age,
                "gender": gender,
                "bmi": bmi,
                "location": location,
                "updated_at": datetime.utcnow()
            }},
            upsert=True
        )
    except:
        pass

def delete_user_data(user_id):
    if db is None: return
    try:
        db.symptom_checks.delete_many({"user_id": user_id})
        db.chat_history.delete_many({"user_id": user_id})
        db.patient_profiles.delete_one({"user_id": user_id})
    except:
        pass

