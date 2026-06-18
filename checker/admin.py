from django.contrib import admin
from .models import PatientProfile, DoctorProfile, SymptomCheck, Consultation, ChatMessage


# -----------------------------
# PATIENT ADMIN
# -----------------------------
@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'age', 'gender', 'bmi', 'bmi_category', 'created_at')
    search_fields = ('user__username', 'phone', 'location')
    list_filter = ('gender', 'bmi_category')


# -----------------------------
# DOCTOR ADMIN
# -----------------------------
@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'specialization', 'available', 'experience_years')
    search_fields = ('user__username', 'specialization', 'hospital')
    list_filter = ('available', 'specialization')


# -----------------------------
# SYMPTOM CHECK ADMIN
# -----------------------------
@admin.register(SymptomCheck)
class SymptomCheckAdmin(admin.ModelAdmin):
    list_display = ('user', 'predicted_disease', 'confidence', 'severity', 'created_at')
    search_fields = ('predicted_disease', 'user__username')
    list_filter = ('severity', 'input_mode')


# -----------------------------
# CONSULTATION ADMIN
# -----------------------------
@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ('patient', 'doctor', 'status', 'created_at')
    search_fields = ('patient__username', 'doctor__user__username')
    list_filter = ('status',)


# -----------------------------
# CHAT ADMIN
# -----------------------------
@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'timestamp')
    search_fields = ('user__username', 'message')
    list_filter = ('role',)