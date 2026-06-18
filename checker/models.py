from django.db import models
from django.contrib.auth.models import User


# -----------------------------
# PATIENT PROFILE
# -----------------------------
class PatientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='patient_profile')
    age = models.IntegerField(null=True, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=15, blank=True)

    height_cm = models.FloatField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    bmi = models.FloatField(null=True, blank=True)
    bmi_category = models.CharField(max_length=20, blank=True)

    location = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def compute_bmi(self):
        if self.height_cm and self.weight_kg and self.height_cm > 0:
            h = self.height_cm / 100
            self.bmi = round(self.weight_kg / (h * h), 1)

            if self.bmi < 18.5:
                self.bmi_category = 'Underweight'
            elif self.bmi < 25.0:
                self.bmi_category = 'Normal'
            elif self.bmi < 30.0:
                self.bmi_category = 'Overweight'
            else:
                self.bmi_category = 'Obese'

        return self.bmi

    def __str__(self):
        return f"{self.user.username}'s Profile"


# -----------------------------
# DOCTOR PROFILE
# -----------------------------
class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='doctor_profile')
    specialization = models.CharField(max_length=100)
    experience_years = models.IntegerField(null=True, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    hospital = models.CharField(max_length=150, blank=True)

    # IMPORTANT → matches admin
    available = models.BooleanField(default=True)

    def __str__(self):
        return f"Dr. {self.user.username} ({self.specialization})"


# -----------------------------
# SYMPTOM CHECK
# -----------------------------
class SymptomCheck(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    symptoms_selected = models.TextField()

    input_mode = models.CharField(
        max_length=20,
        default='manual',
        choices=[
            ('manual', 'Manual'),
            ('voice', 'Voice'),
            ('image', 'Image'),
            ('video', 'Video'),
            ('multimodal', 'Multimodal')
        ]
    )

    voice_transcript = models.TextField(blank=True)
    image_path = models.CharField(max_length=300, blank=True)
    video_path = models.CharField(max_length=300, blank=True)

    predicted_disease = models.CharField(max_length=200)
    all_predictions = models.TextField(blank=True)

    model_used = models.CharField(max_length=50)
    confidence = models.FloatField(default=0.0)

    precautions = models.TextField(blank=True)
    home_care = models.TextField(blank=True)
    medications = models.TextField(blank=True)

    severity = models.CharField(max_length=30, default='Moderate Confidence')
    action_level = models.CharField(max_length=20, default='home_care')

    patient_age = models.IntegerField(null=True, blank=True)
    patient_bmi = models.FloatField(null=True, blank=True)
    patient_gender = models.CharField(max_length=20, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.predicted_disease} ({self.created_at.strftime('%Y-%m-%d')})"


# -----------------------------
# CONSULTATION
# -----------------------------
class Consultation(models.Model):
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='consultations')
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.SET_NULL, null=True, blank=True)

    symptom_check = models.ForeignKey(SymptomCheck, on_delete=models.SET_NULL, null=True, blank=True)

    status = models.CharField(
        max_length=20,
        default='Pending',
        choices=[
            ('Pending', 'Pending'),
            ('Approved', 'Approved'),
            ('Completed', 'Completed')
        ]
    )

    notes = models.TextField(blank=True)
    prescription_notes = models.TextField(blank=True, help_text="Doctor's notes for the prescription")
    prescription_meds = models.TextField(blank=True, help_text="JSON list of prescribed medications")
    meet_link = models.URLField(blank=True, max_length=500)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.patient.username} → {self.doctor} ({self.status})"


# -----------------------------
# CHAT MESSAGE
# -----------------------------
class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    role = models.CharField(
        max_length=10,
        choices=[
            ('user', 'User'),
            ('bot', 'Bot')
        ]
    )

    message = models.TextField()
    intent = models.CharField(max_length=40, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.user.username} ({self.role})"

# -----------------------------
# VITALS LOG
# -----------------------------
class VitalsLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vitals_logs')
    systolic = models.IntegerField()
    diastolic = models.IntegerField()
    heart_rate = models.IntegerField()
    temperature = models.FloatField()
    blood_glucose = models.IntegerField()
    sleep_hours = models.FloatField()
    hydration_ml = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username}'s Vitals ({self.timestamp.strftime('%Y-%m-%d')})"

# -----------------------------
# MEDICATION REMINDER
# -----------------------------
class Medication(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='medications')
    name = models.CharField(max_length=150)
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    time = models.TimeField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['time']

    def __str__(self):
        return f"{self.name} - {self.dosage} for {self.user.username}"