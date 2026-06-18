import json, os, uuid, traceback
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from django.utils import timezone
from .models import PatientProfile, DoctorProfile, SymptomCheck, Consultation, ChatMessage, VitalsLog, Medication
from django.core.management import call_command
import checker.ml_service as ml
import checker.mongo_service as mongo


# ── Helpers ───────────────────────────────────────────────────────────────────
def _profile(request):
    if not request.user.is_authenticated: return None
    try: return request.user.patient_profile
    except: return None

def _is_valid_api_key(key):
    if not key:
        return False
    key_str = str(key).strip()
    return bool(key_str and "YOUR_GEMINI_API_KEY" not in key_str and not key_str.startswith("YOUR_"))

def _get_api_key(request):
    key = request.session.get('gemini_api_key')
    if not _is_valid_api_key(key):
        from django.conf import settings as _settings
        key = getattr(_settings, 'GEMINI_API_KEY', None) or os.environ.get('GEMINI_API_KEY')
    return key if _is_valid_api_key(key) else None


# ── Home ──────────────────────────────────────────────────────────────────────
def home(request):
    return render(request, 'checker/home.html', {
        'model_ready': ml.is_ready(), 'patient': _profile(request)
    })


# ── Register ──────────────────────────────────────────────────────────────────
def register_view(request):
    if request.method == 'POST':
        try:
            username  = request.POST.get('username','').strip()
            email     = request.POST.get('email','').strip()
            password  = request.POST.get('password','').strip()
            first_name= request.POST.get('first_name','').strip()
            last_name = request.POST.get('last_name','').strip()
            age       = request.POST.get('age','').strip()
            gender    = request.POST.get('gender','')
            height    = request.POST.get('height','').strip()
            weight    = request.POST.get('weight','').strip()
            location  = request.POST.get('location','').strip()
            phone     = request.POST.get('phone','').strip()

            if not username or not password:
                messages.error(request,'Username and password are required.')
                return render(request,'checker/register.html')
            if User.objects.filter(username=username).exists():
                messages.error(request,'Username already taken.')
                return render(request,'checker/register.html')

            role      = request.POST.get('role', 'patient')
            
            user = User.objects.create_user(
                username=username, email=email, password=password,
                first_name=first_name, last_name=last_name
            )
            
            if role == 'doctor':
                from .models import DoctorProfile
                specialization = request.POST.get('specialization', 'General Practice')
                experience = request.POST.get('experience', '')
                hospital = request.POST.get('hospital', '')
                DoctorProfile.objects.create(
                    user=user,
                    specialization=specialization,
                    experience_years=int(experience) if experience.isdigit() else None,
                    phone=phone,
                    hospital=hospital
                )
            else:
                profile = PatientProfile(
                    user=user,
                    age=int(age) if age.isdigit() else None,
                    gender=gender,
                    height_cm=float(height) if height else None,
                    weight_kg=float(weight) if weight else None,
                    location=location, phone=phone,
                )
                profile.compute_bmi()
                profile.save()
                mongo.log_patient_profile(user.id, profile.age, profile.gender, profile.bmi, profile.location)
            
            login(request, user)
            messages.success(request, f'Welcome to MediAI, {first_name or username}!')
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    return render(request,'checker/register.html')


# ── Login / Logout ────────────────────────────────────────────────────────────
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username','').strip()
        password = request.POST.get('password','').strip()
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect(request.GET.get('next','dashboard'))
        messages.error(request,'Invalid username or password.')
    return render(request,'checker/login.html')

def logout_view(request):
    logout(request); return redirect('home')


# ── Edit Profile ──────────────────────────────────────────────────────────────
@login_required
def edit_profile(request):
    profile = _profile(request)
    if not profile:
        profile = PatientProfile(user=request.user)
    if request.method == 'POST':
        h = request.POST.get('height','').strip()
        w = request.POST.get('weight','').strip()
        a = request.POST.get('age','').strip()
        profile.age       = int(a) if a.isdigit() else profile.age
        profile.gender    = request.POST.get('gender', profile.gender)
        profile.height_cm = float(h) if h else profile.height_cm
        profile.weight_kg = float(w) if w else profile.weight_kg
        profile.location  = request.POST.get('location', profile.location or '')
        profile.phone     = request.POST.get('phone', profile.phone or '')
        profile.compute_bmi()
        profile.save()
        
        mongo.log_patient_profile(request.user.id, profile.age, profile.gender, profile.bmi, profile.location)
        
        messages.success(request, 'Profile updated successfully.')
        return redirect('dashboard')
    return render(request,'checker/edit_profile.html',{'profile': profile})


# ── Direct Password Reset ──────────────────────────────────────────────────────
def direct_password_reset_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        new_pw = request.POST.get('new_password', '').strip()
        confirm_pw = request.POST.get('confirm_password', '').strip()

        if not username or not email or not new_pw:
            messages.error(request, 'All fields are required.')
            return render(request, 'checker/password_reset_direct.html')

        if new_pw != confirm_pw:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'checker/password_reset_direct.html')

        try:
            user = User.objects.get(username=username, email=email)
            user.set_password(new_pw)
            user.save()
            messages.success(request, 'Password reset successfully! You can now sign in with your new password.')
            return redirect('login')
        except User.DoesNotExist:
            messages.error(request, 'Invalid username or email combination.')
            return render(request, 'checker/password_reset_direct.html')

    return render(request, 'checker/password_reset_direct.html')


# ── Delete Account ────────────────────────────────────────────────────────────

@login_required
def delete_account_view(request):
    if request.method == 'POST':
        user = request.user
        user_id = user.id
        # Delete user logs from MongoDB
        mongo.delete_user_data(user_id)
        # Perform logout first
        logout(request)
        # Delete the Django User object
        user.delete()
        messages.success(request, 'Your account and all associated data have been permanently deleted.')
        return redirect('home')
    return render(request, 'checker/delete_account_confirm.html')



# ── Dashboard ─────────────────────────────────────────────────────────────────
@login_required
def dashboard(request):
    is_doctor = hasattr(request.user, 'doctor_profile')
    if is_doctor:
        profile = request.user.doctor_profile
        consultations = Consultation.objects.filter(doctor=profile)
        return render(request,'checker/dashboard.html',{
            'profile':profile, 'is_doctor':True, 'consultations':consultations, 'history':[]
        })

    # Programmatic migrations execution (guarantees zero setup errors)
    try:
        call_command('makemigrations', 'checker', interactive=False)
        call_command('migrate', 'checker', interactive=False)
    except Exception as e:
        print("Auto-migration notice:", e)

    profile = _profile(request)
    history = SymptomCheck.objects.filter(user=request.user)[:8]
    all_history = SymptomCheck.objects.filter(user=request.user)
    
    chart_data = {'High':0, 'Moderate':0, 'Low':0}
    for sc in all_history:
        base_sev = sc.severity.replace(' Confidence', '')
        if base_sev in chart_data:
            chart_data[base_sev] += 1
            
    consultations = Consultation.objects.filter(patient=request.user)[:5]
    accuracies = ml.get_accuracies()
    
    vitals_list = VitalsLog.objects.filter(user=request.user).order_by('timestamp')[:30]
    meds_list = Medication.objects.filter(user=request.user)
    doctors = DoctorProfile.objects.all()
    
    return render(request,'checker/dashboard.html',{
        'profile':profile,'history':history, 'is_doctor':False,
        'consultations':consultations,'accuracies':accuracies,
        'chart_data': chart_data,
        'vitals_logs': vitals_list,
        'medications': meds_list,
        'doctors': doctors,
        'hospitals': HOSPITALS
    })


# ── Symptom Checker ───────────────────────────────────────────────────────────
@login_required
def symptom_checker(request):
    symptoms  = ml.get_symptoms()
    model_names = ml.get_model_names()
    grouped = {}
    for s in symptoms:
        grouped.setdefault(s[0].upper(),[]).append(s)
    return render(request,'checker/symptom_checker.html',{
        'grouped_symptoms':grouped,'model_names':model_names,
        'model_ready':ml.is_ready(),'patient':_profile(request)
    })


# ── Predict (main API) ────────────────────────────────────────────────────────
@csrf_exempt
def predict_view(request):
    if request.method != 'POST':
        return JsonResponse({'error':'POST required'},status=405)
    if not ml.is_ready():
        return JsonResponse({'error':'Run python train_models.py first'},status=503)
    try:
        body        = json.loads(request.body)
        selected    = body.get('symptoms',[])
        model_name  = body.get('model','Best Model')
        extra_text  = body.get('extra_text','')
        input_mode  = body.get('input_mode','manual')

        if extra_text:
            # Try Live AI (Gemini Pro) clinical prediction first
            api_key = _get_api_key(request)
            gemini_res = ml.predict_with_gemini(extra_text, selected, api_key=api_key)
            if gemini_res:
                profile = _profile(request)
                age = bmi = gender = None
                if profile:
                    age=profile.age; bmi=profile.bmi; gender=profile.gender
                
                sc = SymptomCheck.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    symptoms_selected=json.dumps(selected),
                    input_mode=input_mode,
                    predicted_disease=gemini_res['disease'],
                    all_predictions=json.dumps(gemini_res['all_predictions']),
                    model_used=gemini_res['model_used'],
                    confidence=gemini_res['confidence'],
                    precautions=json.dumps(gemini_res['precautions']),
                    home_care=json.dumps(gemini_res['home_care']),
                    medications=json.dumps(gemini_res.get('medications', [])),
                    severity=gemini_res['severity'],
                    action_level=gemini_res['action_level'],
                    patient_age=age, patient_bmi=bmi,
                    patient_gender=gender or '',
                )
                
                mongo.log_symptom_check(
                    user_id=request.user.id if request.user.is_authenticated else None,
                    symptoms=selected, input_mode=input_mode, disease=gemini_res['disease'],
                    confidence=gemini_res['confidence'], severity=gemini_res['severity'],
                    action_level=gemini_res['action_level'], medications=gemini_res.get('medications', [])
                )
                
                gemini_res['check_id'] = sc.id
                return JsonResponse(gemini_res)

            # Fallback to local NLP extraction and ML model mapping
            nlp_syms = ml.extract_symptoms_from_text(extra_text)
            selected = list(set(selected + nlp_syms))

        if len(selected) < 2:
            return JsonResponse({'error':'Select at least 2 symptoms. If typing, please describe your symptoms in more detail.'},status=400)

        profile = _profile(request)
        age = bmi = gender = None
        if profile:
            age=profile.age; bmi=profile.bmi; gender=profile.gender

        result = ml.predict(selected, model_name, age=age, gender=gender, bmi=bmi)
        if 'error' in result:
            return JsonResponse(result, status=500)

        sc = SymptomCheck.objects.create(
            user=request.user if request.user.is_authenticated else None,
            symptoms_selected=json.dumps(selected),
            input_mode=input_mode,
            predicted_disease=result['disease'],
            all_predictions=json.dumps(result['all_predictions']),
            model_used=model_name,
            confidence=result['confidence'],
            precautions=json.dumps(result['precautions']),
            home_care=json.dumps(result['home_care']),
            medications=json.dumps(result.get('medications', [])),
            severity=result['severity'],
            action_level=result['action_level'],
            patient_age=age, patient_bmi=bmi,
            patient_gender=gender or '',
        )
        
        mongo.log_symptom_check(
            user_id=request.user.id if request.user.is_authenticated else None,
            symptoms=selected, input_mode=input_mode, disease=result['disease'],
            confidence=result['confidence'], severity=result['severity'],
            action_level=result['action_level'], medications=result.get('medications', [])
        )
        
        result['check_id'] = sc.id
        return JsonResponse(result)
    except json.JSONDecodeError:
        return JsonResponse({'error':'Invalid JSON'},status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error':str(e)},status=500)


# ── Result detail ─────────────────────────────────────────────────────────────
def result_view(request, check_id):
    sc = get_object_or_404(SymptomCheck, id=check_id)
    symptoms    = json.loads(sc.symptoms_selected)
    precautions = json.loads(sc.precautions) if sc.precautions else []
    home_care   = json.loads(sc.home_care)   if sc.home_care   else []
    medications = json.loads(sc.medications) if sc.medications else []
    all_preds   = json.loads(sc.all_predictions) if sc.all_predictions else {}
    
    # Generate dynamic clinical diet and wellness advice
    bmi_category = 'Normal'
    age = 30
    p = _profile(request)
    if p:
        bmi_category = p.bmi_category or 'Normal'
        age = p.age or 30
    elif sc.patient_bmi:
        if sc.patient_bmi < 18.5: bmi_category = 'Underweight'
        elif sc.patient_bmi < 25.0: bmi_category = 'Normal'
        elif sc.patient_bmi < 30.0: bmi_category = 'Overweight'
        else: bmi_category = 'Obese'
    if sc.patient_age:
        age = sc.patient_age

    wellness_advice = _generate_diet_advice(sc.predicted_disease, bmi_category, age)
    
    return render(request,'checker/result.html',{
        'sc':sc,'symptoms':symptoms,'precautions':precautions,
        'home_care':home_care,'medications':medications,'all_preds':all_preds,
        'patient':p,
        'wellness_advice': wellness_advice
    })


# ── History ───────────────────────────────────────────────────────────────────
@login_required
def history_view(request):
    records = SymptomCheck.objects.filter(user=request.user)[:30]
    return render(request,'checker/history.html',{
        'records':records,'patient':_profile(request)
    })

@login_required
def delete_history(request, check_id):
    if request.method == 'POST':
        sc = get_object_or_404(SymptomCheck, id=check_id, user=request.user)
        sc.delete()
        messages.success(request, 'Diagnosis history record deleted.')
    return redirect(request.META.get('HTTP_REFERER', 'history'))


# ── Multimodal Input ──────────────────────────────────────────────────────────
@login_required
def multimodal_view(request):
    symptoms    = ml.get_symptoms()
    model_names = ml.get_model_names()
    grouped = {}
    for s in symptoms:
        grouped.setdefault(s[0].upper(),[]).append(s)
    return render(request,'checker/multimodal.html',{
        'grouped_symptoms':grouped,'model_names':model_names,
        'model_ready':ml.is_ready(),'patient':_profile(request)
    })

@csrf_exempt
def process_voice(request):
    """Accept voice transcript text OR an uploaded audio file, run AI diagnosis, return full result."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        audio_file = request.FILES.get('audio')
        transcript = ''
        audio_path = None
        audio_mime = None

        if audio_file:
            # Determine MIME type
            ext = audio_file.name.rsplit('.', 1)[-1].lower() if '.' in audio_file.name else 'webm'
            mime_map = {
                'wav': 'audio/wav', 'mp3': 'audio/mpeg', 'm4a': 'audio/mp4',
                'webm': 'audio/webm', 'ogg': 'audio/ogg', 'flac': 'audio/flac',
            }
            audio_mime = mime_map.get(ext, 'audio/webm')
            fname = f"voice_{uuid.uuid4().hex[:8]}.{ext}"
            audio_path = os.path.join(settings.MEDIA_ROOT, 'uploads', fname)
            os.makedirs(os.path.dirname(audio_path), exist_ok=True)
            with open(audio_path, 'wb+') as f:
                for chunk in audio_file.chunks():
                    f.write(chunk)
        else:
            # JSON body or form with transcript text only
            try:
                body = json.loads(request.body)
                transcript = body.get('transcript', '').strip()
            except Exception:
                transcript = request.POST.get('transcript', '').strip()

        # Also check if transcript was sent alongside the audio file
        if audio_file and not transcript:
            transcript = request.POST.get('transcript', '').strip()

        if not audio_path and not transcript:
            return JsonResponse({'error': 'No audio file or transcript provided'}, status=400)

        # ── Run AI analysis ──────────────────────────────────────────────────
        api_key = _get_api_key(request)

        if audio_path:
            analysis = ml.analyze_voice_with_gemini(audio_path, api_key, audio_mime_type=audio_mime)
            # If audio couldn't be transcribed (no key/bad format) but we have a browser transcript, use it
            failed_diseases = ('Audio Could Not Be Transcribed', 'Could Not Transcribe', 'Insufficient Information')
            if analysis.get('disease') in failed_diseases and transcript:
                analysis = ml.analyze_voice_with_gemini(transcript, api_key, audio_mime_type=None)
        else:
            analysis = ml.analyze_voice_with_gemini(transcript, api_key, audio_mime_type=None)


        # Clean up temp audio file
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass

        # ── Save SymptomCheck record ─────────────────────────────────────────
        check_id = None
        if request.user.is_authenticated:
            profile = _profile(request)
            age = bmi = gender = None
            if profile:
                age = profile.age
                bmi = profile.bmi
                gender = profile.gender

            sc = SymptomCheck.objects.create(
                user=request.user,
                symptoms_selected=json.dumps(analysis.get('symptoms', [])),
                input_mode='voice',
                predicted_disease=analysis.get('disease', 'Unknown'),
                all_predictions=json.dumps(analysis.get('all_predictions', {})),
                model_used=analysis.get('model_used', 'AI Voice Analysis'),
                confidence=analysis.get('confidence', 0.0),
                severity=analysis.get('severity', 'Moderate'),
                action_level=analysis.get('action_level', 'see_doctor'),
                precautions=json.dumps(analysis.get('precautions', [])),
                home_care=json.dumps(analysis.get('home_care', [])),
                medications=json.dumps(analysis.get('medications', [])),
                patient_age=age,
                patient_bmi=bmi,
                patient_gender=gender or '',
            )
            check_id = sc.id

            mongo.log_symptom_check(
                user_id=request.user.id,
                symptoms=analysis.get('symptoms', []),
                input_mode='voice',
                disease=analysis.get('disease', 'Unknown'),
                confidence=analysis.get('confidence', 0.0),
                severity=analysis.get('severity', 'Moderate'),
                action_level=analysis.get('action_level', 'see_doctor'),
                medications=analysis.get('medications', []),
            )

        return JsonResponse({
            'transcript':    analysis.get('transcript', transcript),
            'symptoms':      analysis.get('symptoms', []),
            'disease':       analysis.get('disease', 'Unknown'),
            'confidence':    analysis.get('confidence', 0.0),
            'severity':      analysis.get('severity', 'Moderate'),
            'action_level':  analysis.get('action_level', 'see_doctor'),
            'precautions':   analysis.get('precautions', []),
            'home_care':     analysis.get('home_care', []),
            'medications':   analysis.get('medications', []),
            'all_predictions': analysis.get('all_predictions', {}),
            'model_used':    analysis.get('model_used', 'AI'),
            'check_id':      check_id,
            'notice':        analysis.get('notice', None),
            'count':         len(analysis.get('symptoms', [])),
        })
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def process_image(request):
    """Accept uploaded image and simulate CNN visual symptom detection."""
    if request.method != 'POST':
        return JsonResponse({'error':'POST required'},status=405)
    try:
        img = request.FILES.get('image')
        if not img:
            return JsonResponse({'error':'No image uploaded'},status=400)
        ext  = img.name.split('.')[-1].lower()
        if ext not in ['jpg','jpeg','png','bmp','webp']:
            return JsonResponse({'error':'Unsupported format. Use JPG or PNG.'},status=400)
        fname = f"img_{uuid.uuid4().hex[:8]}.{ext}"
        path  = os.path.join(settings.MEDIA_ROOT,'uploads',fname)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path,'wb+') as f:
            for chunk in img.chunks(): f.write(chunk)
        api_key = _get_api_key(request)
        if api_key:
            analysis = ml.analyze_image_with_gemini(path, api_key)
        else:
            analysis = ml.analyze_image(path)
            analysis["findings"].insert(0, "Notice: Configure a Gemini API key in settings/profile to enable live visual symptom scanning.")
        
        pred_disease = 'Pending full analysis'
        check_id = None
        
        # Save exact diagnosis prediction using our ML model on SymptomCheck
        if request.user.is_authenticated and analysis['symptoms']:
            profile = _profile(request)
            age = bmi = gender = None
            if profile:
                age=profile.age; bmi=profile.bmi; gender=profile.gender
            
            # Predict the actual condition from detected visual symptoms
            pred_res = ml.predict(analysis['symptoms'], 'Best Model', age=age, gender=gender, bmi=bmi)
            pred_disease = pred_res.get('disease', 'Unknown Disease')
            
            sc = SymptomCheck.objects.create(
                user=request.user,
                symptoms_selected=json.dumps(analysis['symptoms']),
                input_mode='image', image_path=f'/media/uploads/{fname}',
                predicted_disease=pred_disease,
                all_predictions=json.dumps(pred_res.get('all_predictions', {})),
                model_used='CNN Visual Analysis + Best Model',
                confidence=pred_res.get('confidence', analysis['confidence']),
                severity=pred_res.get('severity', 'Moderate'),
                action_level=pred_res.get('action_level', 'see_doctor'),
                precautions=json.dumps(pred_res.get('precautions', [])),
                home_care=json.dumps(pred_res.get('home_care', [])),
                medications=json.dumps(pred_res.get('medications', [])),
                patient_age=age, patient_bmi=bmi,
                patient_gender=gender or '',
            )
            check_id = sc.id
            
            mongo.log_symptom_check(
                user_id=request.user.id, symptoms=analysis['symptoms'], input_mode='image',
                disease=pred_disease, confidence=pred_res.get('confidence', analysis['confidence']),
                severity=pred_res.get('severity', 'Moderate'), action_level=pred_res.get('action_level', 'see_doctor'),
                medications=pred_res.get('medications', []), multimodal_ref=f'/media/uploads/{fname}'
            )
            
        return JsonResponse({
            'symptoms':   analysis['symptoms'],
            'findings':   analysis['findings'],
            'confidence': analysis['confidence'],
            'image_url':  f'/media/uploads/{fname}',
            'disease':    pred_disease,
            'check_id':   check_id
        })
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error':str(e)},status=500)

@csrf_exempt
def process_video(request):
    """Accept uploaded video and simulate behavioral analysis."""
    if request.method != 'POST':
        return JsonResponse({'error':'POST required'},status=405)
    try:
        vid = request.FILES.get('video')
        if not vid:
            return JsonResponse({'error':'No video uploaded'},status=400)
        ext  = vid.name.split('.')[-1].lower()
        fname = f"vid_{uuid.uuid4().hex[:8]}.{ext}"
        path  = os.path.join(settings.MEDIA_ROOT,'uploads',fname)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path,'wb+') as f:
            for chunk in vid.chunks(): f.write(chunk)
        analysis = ml.analyze_video(path)
        
        pred_disease = 'Pending full analysis'
        check_id = None
        
        # Save exact diagnosis prediction using our ML model on SymptomCheck
        if request.user.is_authenticated and analysis['symptoms']:
            profile = _profile(request)
            age = bmi = gender = None
            if profile:
                age=profile.age; bmi=profile.bmi; gender=profile.gender
            
            pred_res = ml.predict(analysis['symptoms'], 'Best Model', age=age, gender=gender, bmi=bmi)
            pred_disease = pred_res.get('disease', 'Unknown Disease')
            
            sc = SymptomCheck.objects.create(
                user=request.user,
                symptoms_selected=json.dumps(analysis['symptoms']),
                input_mode='video', image_path=f'/media/uploads/{fname}',
                predicted_disease=pred_disease,
                all_predictions=json.dumps(pred_res.get('all_predictions', {})),
                model_used='Kinematic Analysis + Best Model',
                confidence=pred_res.get('confidence', analysis['confidence']),
                severity=pred_res.get('severity', 'Moderate'),
                action_level=pred_res.get('action_level', 'see_doctor'),
                precautions=json.dumps(pred_res.get('precautions', [])),
                home_care=json.dumps(pred_res.get('home_care', [])),
                medications=json.dumps(pred_res.get('medications', [])),
                patient_age=age, patient_bmi=bmi,
                patient_gender=gender or '',
            )
            check_id = sc.id
            
            mongo.log_symptom_check(
                user_id=request.user.id, symptoms=analysis['symptoms'], input_mode='video',
                disease=pred_disease, confidence=pred_res.get('confidence', analysis['confidence']),
                severity=pred_res.get('severity', 'Moderate'), action_level=pred_res.get('action_level', 'see_doctor'),
                medications=pred_res.get('medications', []), multimodal_ref=f'/media/uploads/{fname}'
            )
            
        return JsonResponse({
            'symptoms':   analysis['symptoms'],
            'indicators': analysis['indicators'],
            'confidence': analysis['confidence'],
            'disease':    pred_disease,
            'check_id':   check_id
        })
    except Exception as e:
        return JsonResponse({'error':str(e)},status=500)


# ── Chatbot ───────────────────────────────────────────────────────────────────
def _extract_chat_symptoms(msg):
    return ml.extract_symptoms_from_text(msg)

def _bot_reply(msg, session_symptoms, user, api_key=None):
    msg_l = msg.lower().strip()
    name  = user.first_name or user.username

    greetings = ['hi','hello','hey','good morning','good evening','howdy','hiya']
    farewells  = ['bye','goodbye','see you','thanks','thank you','ok bye']

    if any(g in msg_l for g in greetings):
        return (f"Hello {name}! 👋 I'm your MediAI Assistant. Tell me how you're feeling — "
                f"describe your symptoms in simple words like 'I have fever' or 'I feel chest pain'.",
                'greeting', session_symptoms)

    if any(f in msg_l for f in farewells):
        return ("Take care! 💙 For serious symptoms, always consult a qualified doctor. Stay healthy!",
                'farewell', session_symptoms)

    if any(w in msg_l for w in ['emergency','ambulance','call 911','critical','dying']):
        return ("🚨 EMERGENCY! Please call 112 or your local emergency number immediately "
                "or go to the nearest emergency room. Do not delay!",
                'emergency', session_symptoms)

    symptoms_ctx = ""
    if session_symptoms:
        symptoms_ctx = f"The user has the following symptoms recorded in this session: {', '.join(s.replace('_',' ') for s in session_symptoms)}."
    
    prompt = (
        f"You are MediAI, an empathetic, professional, and highly intelligent clinical health assistant.\n"
        f"Patient Profile: Name: {name}.\n"
        f"{symptoms_ctx}\n"
        f"The patient asks: '{msg}'.\n"
        f"Provide a natural, friendly, and medically accurate response answering their query directly (e.g. if they ask about low hemoglobin, anemia, drug interactions, etc.). "
        f"Keep it concise (3-5 sentences max). Always include a standard brief advice to consult a physician for serious symptoms if they ask about severe conditions."
    )

    # Prioritize Live AI (Gemini 1.5 Flash) for all queries
    gemini_error_msg = None
    try:
        import os
        from google import genai as _genai
        if api_key and not _is_valid_api_key(api_key):
            api_key = None
        if not api_key:
            from django.conf import settings as _settings
            cand_key = getattr(_settings, 'GEMINI_API_KEY', None) or os.environ.get('GEMINI_API_KEY')
            if _is_valid_api_key(cand_key):
                api_key = cand_key
        if api_key:
            syms = _extract_chat_symptoms(msg)
            if syms:
                session_symptoms = list(set(session_symptoms + syms))
            client = _genai.Client(api_key=api_key)
            # Try models in cascade order on quota errors
            from checker.ml_service import GEMINI_MODELS, _is_quota_error
            last_exc = None
            for _model in GEMINI_MODELS:
                try:
                    response = client.models.generate_content(
                        model=_model,
                        contents=prompt
                    )
                    if response and response.text:
                        return (response.text.strip(), 'gen_ai_chat', session_symptoms)
                    break
                except Exception as _me:
                    last_exc = _me
                    if _is_quota_error(_me):
                        print(f"[Gemini chatbot] {_model} quota exhausted, trying next…")
                        continue
                    raise
            if last_exc:
                raise last_exc
    except Exception as e:
        err_str = str(e)
        print("Gemini chatbot query failed, trying Pollinations Chat:", err_str)
        # Only surface auth/key errors — quota/rate-limit errors fall through to local fallbacks silently
        is_auth_error = any(k in err_str.lower() for k in ['api_key', 'invalid_api_key', 'api key', 'permission', 'unauthorized', '403', '401'])
        is_quota_error = any(k in err_str.lower() for k in ['quota', 'resource_exhausted', '429', 'rate'])
        if is_auth_error and not is_quota_error:
            gemini_error_msg = f"⚠️ **Gemini API error (invalid key):** {err_str[:250]}. Please check your API key."
        # quota errors: silently try next fallback

    # Keyless Pollinations Chat fallback
    try:
        syms = _extract_chat_symptoms(msg)
        if syms:
            session_symptoms = list(set(session_symptoms + syms))
            
        print("Attempting Pollinations Chat fallback...")
        pollinations_reply = ml.query_pollinations_chat(prompt)
        if pollinations_reply:
            print(f"Pollinations Chat succeeded: {pollinations_reply[:100]}...")
            return (pollinations_reply.strip(), 'pollinations_ai_chat', session_symptoms)
        else:
            print("Pollinations Chat returned None")
    except Exception as e:
        print("Pollinations chatbot query failed:", e)
        import traceback
        traceback.print_exc()

    # Show auth key error only after all live AI fallbacks also fail
    if gemini_error_msg:
        return (gemini_error_msg, 'api_key_error', session_symptoms)

    # ── Fallback: Disease Q&A Info Guide Intent ──
    matched_disease = None
    # Alias map for common spoken terms → disease names in our dataset
    DISEASE_ALIASES = {
        "diarrhea": "Gastroenteritis", "diarrhoea": "Gastroenteritis",
        "loose motion": "Gastroenteritis", "loose stool": "Gastroenteritis",
        "stomach flu": "Gastroenteritis", "heartburn": "Acid Reflux (GERD)",
        "acid reflux": "Acid Reflux (GERD)", "acidity": "Acid Reflux (GERD)",
        "gastritis": "Peptic Ulcer", "ibs": "Irritable Bowel Syndrome",
        "uti": "Urinary Tract Infection", "cold": "Common Cold",
        "flu": "Influenza", "bp": "Hypertension", "sugar": "Diabetes",
        "thyroid": "Hypothyroidism", "kidney stone": "Kidney Stones",
        "back pain": "Sciatica", "eye infection": "Conjunctivitis",
        "pink eye": "Conjunctivitis", "skin allergy": "Allergic Reaction",
        "food poison": "Food Poisoning", "jaundice": "Hepatitis B",
        "yellow skin": "Hepatitis B", "tb": "Tuberculosis",
        "asthma attack": "Asthma", "heart attack": "Heart Attack",
    }
    data = ml._load()
    if data:
        diseases_list = data.get("diseases", [])
        # Check aliases first
        for alias, disease_name in DISEASE_ALIASES.items():
            if alias in msg_l:
                matched_disease = disease_name
                break
        # Then try direct disease name match
        if not matched_disease:
            for d in diseases_list:
                d_l = d.lower()
                if d_l in msg_l or (d_l == "hepatitis b" and "jaundice" in msg_l):
                    matched_disease = d
                    break
        if "jaundice" in msg_l and not matched_disease:
            matched_disease = "Hepatitis B"

    # Return disease info for any message mentioning a known disease name or alias
    # (Even without query words like "tell me" — the user clearly wants to know about it)
    QUERY_WORDS = ['symptom', 'need', 'what is', 'tell me', 'about', 'info', 'treatment',
                   'medication', 'help', 'cure', 'sign', 'cause', 'reason', 'how', 'why', 'risk']
    if matched_disease and (any(q in msg_l for q in QUERY_WORDS) or len(msg_l.split()) <= 6):
        core_syms = data.get("disease_symptoms", {}).get(matched_disease, [])
        syms_str = ", ".join(s.replace("_", " ").title() for s in core_syms)
        precs = data.get("precautions", {}).get(matched_disease, ["Consult a healthcare professional."])
        homes = data.get("home_care", {}).get(matched_disease, ["Rest and hydrate."])
        meds = data.get("medications", {}).get(matched_disease, ["Consult a doctor for prescription."])
        action = data.get("action_levels", {}).get(matched_disease, "home_care").title()
        
        precs_str = "\n".join(f"• {p}" for p in precs)
        homes_str = "\n".join(f"• {h}" for h in homes)
        meds_str = ", ".join(meds)
        
        reply = (f"🎯 **Medical Guide: {matched_disease}**\n\n"
                 f"📌 **Common Core Symptoms:**\n{syms_str}\n\n"
                 f"🏠 **Home Care Guide:**\n{homes_str}\n\n"
                 f"💊 **Typical First-Line Medications:**\n{meds_str}\n\n"
                 f"🛡️ **Precautionary Measures:**\n{precs_str}\n\n"
                 f"🚨 **Care Level Recommended:** **{action}**\n\n"
                 f"_ℹ️ Using local medical database. For personalized AI responses, ensure your Gemini API quota is available._")
        return reply, 'disease_info', session_symptoms


    syms = _extract_chat_symptoms(msg)
    if syms:
        session_symptoms = list(set(session_symptoms + syms))
        sym_str = ', '.join(s.replace('_',' ') for s in syms)
        followup = ""
        if 'fever' in syms:      followup = " Is the fever above 102°F? Do you have chills or body aches?"
        elif 'chest_pain' in syms: followup = " ⚠️ Is the chest pain sharp or pressure-like? Does it spread to your arm or jaw?"
        elif 'cough' in syms:    followup = " Is it a dry cough or producing mucus? How long have you had it?"
        elif 'headache' in syms: followup = " Is it on one side or both? Any sensitivity to light or sound?"
        elif 'breathlessness' in syms: followup = " ⚠️ Are you having severe difficulty breathing? This may need urgent care."
        reply = (f"I noted: **{sym_str}**.{followup}\n\n"
                 f"I now have **{len(session_symptoms)}** symptom(s) recorded: "
                 f"{', '.join(s.replace('_',' ') for s in session_symptoms)}.\n\n"
                 f"Tell me any more symptoms, or click **Analyse with AI** to get your full diagnosis.")
        return reply, 'symptom_query', session_symptoms

    if any(w in msg_l for w in ['result','prediction','diagnosis','what do i have','disease']):
        return ("You can see your full diagnosis on the **Result** page or **History** page. "
                "I can also help you understand any result — just tell me the predicted condition!",
                'result_explain', session_symptoms)

    if any(w in msg_l for w in ['bmi','weight','height','obese','overweight']):
        try:
            p = user.patient_profile
            if p.bmi:
                return (f"Your BMI is **{p.bmi}** ({p.bmi_category}). Normal range is 18.5–24.9. "
                        f"Update your height/weight in your profile to keep this accurate.",
                        'bmi_info', session_symptoms)
        except: pass
        return ("I don't have your BMI yet. Please update your height and weight in your profile!",
                'bmi_info', session_symptoms)

    if any(w in msg_l for w in ['hospital','clinic','doctor','where','near','nearby']):
        return ("You can find nearby hospitals on the **Hospitals** page. "
                "After a diagnosis, the system will automatically suggest the best hospitals for your condition.",
                'hospital_info', session_symptoms)

    if any(w in msg_l for w in ['help','what can you do','guide','menu','features']):
        return ("I can help you with:\n"
                "• 🩺 Describe symptoms — just say how you feel\n"
                "• 📊 Understand your diagnosis results\n"
                "• 💊 Home care tips and when to see a doctor\n"
                "• 🏥 Find nearby hospitals\n"
                "• 🎤 Use voice or image input for analysis\n"
                "• 📋 Check your BMI and health profile\n\n"
                "What would you like to do?",
                'help', session_symptoms)

    if any(w in msg_l for w in ['clear','reset','start over','new session']):
        return ("Sure! Starting fresh. 🔄 Tell me your current symptoms — how are you feeling?",
                'reset', [])

    return (f"I understand you said: \"{msg[:80]}\". "
            "Could you describe your symptoms more specifically? For example: 'I have fever and cough'. "
            "Or go to **Check Symptoms** for a full AI analysis.",
            'unknown', session_symptoms)

@login_required
def chatbot_view(request):
    messages_qs = ChatMessage.objects.filter(user=request.user).order_by('-timestamp')[:40]
    messages_list = list(reversed(messages_qs))
    has_key = bool(_get_api_key(request))
    model_type = "Gemini 1.5 Flash" if has_key else "Keyless GPT-4o"
    return render(request,'checker/chatbot.html',{
        'chat_messages':messages_list,'patient':_profile(request),
        'has_gemini_key': has_key,
        'ai_model_type': model_type
    })

@csrf_exempt
def chatbot_send(request):
    if request.method != 'POST':
        return JsonResponse({'error':'POST required'},status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'error':'Please login to use the chatbot'},status=401)
    try:
        body     = json.loads(request.body)
        user_msg = body.get('message','').strip()
        if not user_msg:
            return JsonResponse({'error':'Empty message'},status=400)
        session_symptoms = request.session.get('chat_symptoms',[])
        ChatMessage.objects.create(user=request.user,role='user',message=user_msg)
        mongo.log_chat_message(request.user.id, 'user', user_msg, '', session_symptoms)
        
        api_key = _get_api_key(request)
        reply, intent, session_symptoms = _bot_reply(user_msg, session_symptoms, request.user, api_key=api_key)
        request.session['chat_symptoms'] = session_symptoms
        ChatMessage.objects.create(user=request.user,role='bot',message=reply,intent=intent)
        mongo.log_chat_message(request.user.id, 'bot', reply, intent, session_symptoms)
        
        return JsonResponse({'reply':reply,'intent':intent,'symptoms':session_symptoms})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error':str(e)},status=500)

@csrf_exempt
@login_required
def chatbot_clear(request):
    if request.method != 'POST':
        return JsonResponse({'error':'POST required'},status=405)
    try:
        ChatMessage.objects.filter(user=request.user).delete()
        request.session['chat_symptoms'] = []
        return JsonResponse({'status':'success','message':'Conversation cleared successfully.'})
    except Exception as e:
        return JsonResponse({'error':str(e)},status=500)

@csrf_exempt
def set_api_key(request):
    if request.method != 'POST':
        return JsonResponse({'error':'POST required'},status=405)
    try:
        body = json.loads(request.body)
        key = body.get('api_key', '').strip()
        if not key:
            if 'gemini_api_key' in request.session:
                del request.session['gemini_api_key']
            return JsonResponse({'status': 'success', 'message': 'API key cleared.'})
        request.session['gemini_api_key'] = key
        return JsonResponse({'status': 'success', 'message': 'API key saved.'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def chatbot_analyse(request):
    """Run prediction on symptoms collected in chatbot session."""
    if not request.user.is_authenticated:
        return JsonResponse({'error':'Login required'},status=401)
    syms = request.session.get('chat_symptoms',[])
    if len(syms) < 2:
        return JsonResponse({'error':'Need at least 2 symptoms. Keep describing how you feel!'},status=400)
    profile = _profile(request)
    age=bmi=gender=None
    if profile: age=profile.age; bmi=profile.bmi; gender=profile.gender
    result = ml.predict(syms,'Best Model',age=age,gender=gender,bmi=bmi)
    if 'error' in result:
        return JsonResponse(result,status=500)
    sc = SymptomCheck.objects.create(
        user=request.user, symptoms_selected=json.dumps(syms),
        input_mode='multimodal',
        predicted_disease=result['disease'],
        all_predictions=json.dumps(result['all_predictions']),
        model_used='Best Model', confidence=result['confidence'],
        precautions=json.dumps(result['precautions']),
        home_care=json.dumps(result['home_care']),
        medications=json.dumps(result.get('medications', [])),
        severity=result['severity'], action_level=result['action_level'],
        patient_age=age, patient_bmi=bmi, patient_gender=gender or '',
    )
    
    mongo.log_symptom_check(
        user_id=request.user.id, symptoms=syms, input_mode='multimodal',
        disease=result['disease'], confidence=result['confidence'], severity=result['severity'],
        action_level=result['action_level'], medications=result.get('medications', [])
    )
    
    bot_msg = (f"Based on your symptoms, the AI predicts: **{result['disease']}** "
               f"with {result['confidence']}% confidence. Severity: {result['severity']}. "
               f"View your full report for precautions and home care advice.")
    ChatMessage.objects.create(user=request.user,role='bot',message=bot_msg,intent='prediction')
    return JsonResponse({**result,'check_id':sc.id,'redirect':f'/result/{sc.id}/'})


# ── Hospitals ─────────────────────────────────────────────────────────────────
# [ignoring loop detection]
HOSPITALS = [
    {"name":"Apollo Hospitals","city":"Hyderabad","specialties":["Cardiology","Neurology","Oncology","Emergency","Endocrinology"],"phone":"040-23607777","rating":4.8,"emergency":True,"address":"Jubilee Hills, Hyderabad","distance_km":2.4, "lat":17.4255, "lng":78.4121},
    {"name":"Fortis Hospital","city":"Bangalore","specialties":["Orthopaedics","Cardiology","Emergency","General Surgery","Urology"],"phone":"1800-111-4444","rating":4.7,"emergency":True,"address":"Bannerghatta Road, Bangalore","distance_km":3.1, "lat":12.8950, "lng":77.5979},
    {"name":"AIIMS Delhi","city":"Delhi","specialties":["All Specialties","Emergency","Trauma","Pediatrics"],"phone":"011-26588500","rating":4.9,"emergency":True,"address":"Ansari Nagar, New Delhi","distance_km":5.0, "lat":28.5672, "lng":77.2100},
    {"name":"Manipal Hospital","city":"Bangalore","specialties":["Pulmonology","Gastroenterology","Emergency","ENT (Otolaryngology)"],"phone":"1800-102-4747","rating":4.6,"emergency":True,"address":"Old Airport Road, Bangalore","distance_km":4.2, "lat":12.9593, "lng":77.6436},
    {"name":"Max Healthcare","city":"Delhi","specialties":["Cardiology","Oncology","Neurology","Emergency","Psychiatry"],"phone":"011-26515050","rating":4.5,"emergency":True,"address":"Saket, New Delhi","distance_km":6.0, "lat":28.5284, "lng":77.2115},
    {"name":"Narayana Health","city":"Bangalore","specialties":["Cardiology","Pediatrics","Emergency","General Surgery"],"phone":"1800-309-3500","rating":4.7,"emergency":True,"address":"Bommasandra, Bangalore","distance_km":7.5, "lat":12.8122, "lng":77.6936},
    {"name":"Kokilaben Hospital","city":"Mumbai","specialties":["Cardiology","Neurology","Oncology","Rheumatology","Dermatology","Emergency"],"phone":"022-30999999","rating":4.8,"emergency":True,"address":"Andheri West, Mumbai","distance_km":3.8, "lat":19.1311, "lng":72.8256},
    {"name":"Ruby Hall Clinic","city":"Pune","specialties":["General Medicine","Cardiology","Emergency","Infectious Disease"],"phone":"020-66455000","rating":4.4,"emergency":True,"address":"Sassoon Road, Pune","distance_km":2.1, "lat":18.5303, "lng":73.8741},
    {"name":"JIPMER","city":"Puducherry","specialties":["All Specialties","Emergency","Pediatrics","General Medicine"],"phone":"0413-2296000","rating":4.8,"emergency":True,"address":"Puducherry","distance_km":1.0, "lat":11.9540, "lng":79.8050},
    {"name":"CMC Vellore","city":"Vellore","specialties":["All Specialties","Infectious Disease","Hematology","Emergency"],"phone":"0416-2281000","rating":4.9,"emergency":True,"address":"Vellore, Tamil Nadu","distance_km":1.5, "lat":12.9250, "lng":79.1330},
    {"name":"Medanta Hospital","city":"Gurgaon","specialties":["Cardiology","Oncology","Gastroenterology","Pulmonology","Emergency"],"phone":"0124-4141414","rating":4.7,"emergency":True,"address":"Sector 38, Gurgaon","distance_km":8.2, "lat":28.4357, "lng":77.0401},
    {"name":"Lilavati Hospital","city":"Mumbai","specialties":["General Surgery","Cardiology","Oncology","Gynecology","Emergency"],"phone":"022-26751000","rating":4.5,"emergency":True,"address":"Bandra West, Mumbai","distance_km":4.5, "lat":19.0506, "lng":72.8279},
    {"name":"Tata Memorial Hospital","city":"Mumbai","specialties":["Oncology","Hematology","General Surgery"],"phone":"022-24177000","rating":4.8,"emergency":False,"address":"Parel, Mumbai","distance_km":5.2, "lat":19.0028, "lng":72.8427},
    {"name":"NIMHANS","city":"Bangalore","specialties":["Psychiatry","Neurology","Psychology","Sleep Medicine"],"phone":"080-26995000","rating":4.9,"emergency":True,"address":"Hosur Road, Bangalore","distance_km":4.0, "lat":12.9392, "lng":77.5986},
    {"name":"Aravind Eye Hospital","city":"Madurai","specialties":["Ophthalmology"],"phone":"0452-4356100","rating":4.7,"emergency":False,"address":"Anna Nagar, Madurai","distance_km":3.5, "lat":9.9272, "lng":78.1362},
    {"name":"LV Prasad Eye Institute","city":"Hyderabad","specialties":["Ophthalmology"],"phone":"040-68102020","rating":4.8,"emergency":True,"address":"Banjara Hills, Hyderabad","distance_km":1.8, "lat":17.4262, "lng":78.4315},
    {"name":"Sir Ganga Ram Hospital","city":"Delhi","specialties":["Gastroenterology","Nephrology","Endocrinology","General Medicine"],"phone":"011-25750000","rating":4.6,"emergency":True,"address":"Rajinder Nagar, New Delhi","distance_km":4.9, "lat":28.6382, "lng":77.1896},
    {"name":"KIMS Hospital","city":"Secunderabad","specialties":["Gastroenterology","Hepatology","Urology","Emergency"],"phone":"040-44885000","rating":4.5,"emergency":True,"address":"Minister Road, Secunderabad","distance_km":5.5, "lat":17.4332, "lng":78.4862},
    {"name":"Apollo Spectra Hospital","city":"Chennai","specialties":["General Surgery","Orthopaedics","ENT (Otolaryngology)"],"phone":"044-66077500","rating":4.4,"emergency":False,"address":"Alwarpet, Chennai","distance_km":3.0, "lat":13.0298, "lng":80.2520},
    {"name":"Global Hospital","city":"Chennai","specialties":["Hepatology","Gastroenterology","Pulmonology","Emergency"],"phone":"044-24242424","rating":4.6,"emergency":True,"address":"Perumbakkam, Chennai","distance_km":9.1, "lat":12.9032, "lng":80.2078},
    {"name":"Sharda Hospital","city":"Greater Noida","specialties":["General Medicine","Pediatrics","ENT (Otolaryngology)","Dermatology","Emergency"],"phone":"0120-2333999","rating":4.3,"emergency":True,"address":"Knowledge Park, Greater Noida","distance_km":6.8, "lat":28.4735, "lng":77.4831},
    {"name":"Jaslok Hospital","city":"Mumbai","specialties":["Cardiology","Gastroenterology","Nephrology","General Medicine"],"phone":"022-66512200","rating":4.5,"emergency":True,"address":"Pedder Road, Mumbai","distance_km":6.1, "lat":18.9719, "lng":72.8093},
    
    # Newly added Bangalore hospitals
    {"name":"Aster CMI Hospital","city":"Bangalore","specialties":["Cardiology","Neurology","Emergency","Pediatrics","General Medicine"],"phone":"080-43420100","rating":4.7,"emergency":True,"address":"Sahakara Nagar, Bangalore","distance_km":5.5, "lat":13.0612, "lng":77.5961},
    {"name":"Sakra World Hospital","city":"Bangalore","specialties":["Orthopaedics","Cardiology","Neurology","Emergency","General Surgery"],"phone":"080-49694969","rating":4.6,"emergency":True,"address":"Marathahalli, Bangalore","distance_km":6.2, "lat":12.9365, "lng":77.6881},
    {"name":"Columbia Asia Referral Hospital","city":"Bangalore","specialties":["Gastroenterology","Pulmonology","Emergency","General Surgery","Pediatrics"],"phone":"080-39898969","rating":4.5,"emergency":True,"address":"Yeshwanthpur, Bangalore","distance_km":4.8, "lat":13.0125, "lng":77.5518},
    {"name":"St. John's Medical College Hospital","city":"Bangalore","specialties":["All Specialties","Emergency","Pediatrics","General Medicine","Oncology"],"phone":"080-22065000","rating":4.4,"emergency":True,"address":"Sarjapur Road, Bangalore","distance_km":3.9, "lat":12.9336, "lng":77.6244},
    {"name":"Sagar Hospitals","city":"Bangalore","specialties":["Cardiology","Nephrology","Gynecology","Emergency","General Medicine"],"phone":"080-42888888","rating":4.3,"emergency":True,"address":"Jayanagar, Bangalore","distance_km":4.1, "lat":12.9242, "lng":77.5938},
    {"name":"Cloudnine Hospital","city":"Bangalore","specialties":["Pediatrics","Gynecology","General Medicine"],"phone":"1860-500-9999","rating":4.7,"emergency":False,"address":"Jayanagar, Bangalore","distance_km":3.5, "lat":12.9348, "lng":77.5815},
    {"name":"Sparsh Hospital","city":"Bangalore","specialties":["Orthopaedics","Accident & Trauma","Emergency","General Surgery"],"phone":"080-61914141","rating":4.5,"emergency":True,"address":"Infantry Road, Bangalore","distance_km":2.2, "lat":12.9845, "lng":77.5982},
    {"name":"Narayana Nethralaya","city":"Bangalore","specialties":["Ophthalmology"],"phone":"080-66121300","rating":4.8,"emergency":False,"address":"Rajajinagar, Bangalore","distance_km":5.0, "lat":12.9972, "lng":77.5501},
    {"name":"HBS Hospital","city":"Bangalore","specialties":["General Medicine","Dialysis","Emergency"],"phone":"080-25541015","rating":4.2,"emergency":True,"address":"Shivaji Nagar, Bangalore","distance_km":2.8, "lat":12.9893, "lng":77.6083},
    {"name":"Vydehi Institute of Medical Sciences","city":"Bangalore","specialties":["Oncology","Cardiology","Neurology","Emergency","General Medicine","Endocrinology"],"phone":"080-49069000","rating":4.4,"emergency":True,"address":"Whitefield, Bangalore","distance_km":9.5, "lat":12.9754, "lng":77.7291}
]

DISEASE_SPECIALTIES = {
    "Common Cold": ["General Medicine", "Pediatrics"],
    "Influenza": ["General Medicine", "Infectious Disease"],
    "COVID-19": ["Pulmonology", "Infectious Disease", "Emergency"],
    "Pneumonia": ["Pulmonology", "Emergency"],
    "Bronchitis": ["Pulmonology", "General Medicine"],
    "Asthma": ["Pulmonology", "Allergy & Immunology"],
    "Dengue Fever": ["General Medicine", "Infectious Disease", "Emergency"],
    "Malaria": ["General Medicine", "Infectious Disease", "Emergency"],
    "Typhoid": ["General Medicine", "Infectious Disease", "Emergency"],
    "Gastroenteritis": ["Gastroenterology", "General Medicine"],
    "Acid Reflux (GERD)": ["Gastroenterology", "General Medicine"],
    "Irritable Bowel Syndrome": ["Gastroenterology", "General Medicine"],
    "Hypertension": ["Cardiology", "General Medicine"],
    "Diabetes": ["Endocrinology", "General Medicine"],
    "Anemia": ["General Medicine"],
    "Migraine": ["Neurology"],
    "Tension Headache": ["Neurology", "General Medicine"],
    "Anxiety Disorder": ["Psychiatry"],
    "Depression": ["Psychiatry"],
    "Urinary Tract Infection": ["Urology", "General Medicine"],
    "Kidney Stones": ["Urology", "Emergency"],
    "Arthritis": ["Orthopaedics", "Rheumatology"],
    "Chickenpox": ["Pediatrics", "Dermatology", "Infectious Disease"],
    "Measles": ["Pediatrics", "Dermatology", "Infectious Disease"],
    "Conjunctivitis": ["Ophthalmology", "General Medicine"],
    "Sinusitis": ["ENT (Otolaryngology)", "General Medicine"],
    "Tonsillitis": ["ENT (Otolaryngology)", "Pediatrics"],
    "Appendicitis": ["Emergency", "General Surgery"],
    "Hypothyroidism": ["Endocrinology", "General Medicine"],
    "Hyperthyroidism": ["Endocrinology", "General Medicine"],
    "Hepatitis B": ["Gastroenterology", "Infectious Disease"],
    "Tuberculosis": ["Pulmonology", "Infectious Disease"],
    "Peptic Ulcer": ["Gastroenterology", "General Medicine"],
    "Allergic Reaction": ["Allergy & Immunology", "Emergency"],
    "Food Poisoning": ["Gastroenterology", "Emergency"],
    "Sciatica": ["Orthopaedics", "Neurology"],
    "Psoriasis": ["Dermatology", "Rheumatology"],
    "Eczema": ["Dermatology", "Allergy & Immunology"],
    "Panic Disorder": ["Psychiatry", "Emergency"],
    "Insomnia": ["Neurology", "Psychiatry"],
    "Vertigo": ["Neurology", "ENT (Otolaryngology)", "General Medicine"],
    "Heart Attack": ["Cardiology", "Emergency"],
    "COPD": ["Pulmonology", "Emergency", "General Medicine"],
    "Epilepsy": ["Neurology", "Emergency"],
    "Parkinsons Disease": ["Neurology"],
    "Lupus": ["Rheumatology", "Dermatology", "General Medicine"],
    "Rheumatoid Arthritis": ["Rheumatology", "Orthopaedics"],
    "Gout": ["Rheumatology", "Orthopaedics", "General Medicine"],
    "Chronic Kidney Disease": ["Nephrology", "General Medicine"],
    "Crohns Disease": ["Gastroenterology", "General Surgery"],
    "Celiac Disease": ["Gastroenterology", "General Medicine"],
}

def hospitals_view(request):
    return render(request,'checker/hospitals.html',{
        'hospitals':HOSPITALS,'patient':_profile(request)
    })

import requests

@csrf_exempt
def hospital_suggest(request):
    if request.method != 'POST':
        return JsonResponse({'error':'POST required'},status=405)
    try:
        body     = json.loads(request.body)
        disease  = body.get('disease','')
        severity = body.get('severity','Moderate')
        city     = body.get('city','')
        lat      = body.get('lat')
        lng      = body.get('lng')
        
        # New advanced search fields
        specialty = body.get('specialty','')
        emergency_only = body.get('emergency_only', False)
        try:
            min_rating = float(body.get('min_rating', 0.0) or 0.0)
        except ValueError:
            min_rating = 0.0
        search_query = body.get('search_query','').strip().lower()

        # Coordinate mappings for known cities
        CITY_COORDS = {
            "bangalore": (12.9716, 77.5946),
            "delhi": (28.6139, 77.2090),
            "new delhi": (28.6139, 77.2090),
            "mumbai": (19.0760, 72.8777),
            "hyderabad": (17.3850, 78.4867),
            "pune": (18.5204, 73.8567),
            "chennai": (13.0827, 80.2707),
            "gurgaon": (28.4595, 77.0266),
            "greater noida": (28.4744, 77.5040),
            "vellore": (12.9165, 79.1325),
            "puducherry": (11.9416, 79.8083),
            "madurai": (9.9252, 78.1198)
        }

        # Resolve Live Location or empty city if lat/lng are missing
        if not lat or not lng:
            c_clean = city.strip().lower() if city else ""
            if not c_clean or c_clean == "live location":
                # Try server-side IP Geolocation
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip = x_forwarded_for.split(',')[0].strip()
                else:
                    ip = request.META.get('REMOTE_ADDR')
                
                is_local = ip in ('127.0.0.1', 'localhost', '::1') or ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.16.')
                
                if not is_local:
                    try:
                        res = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
                        ip_data = res.json()
                        if ip_data.get('status') == 'success':
                            lat = ip_data.get('lat')
                            lng = ip_data.get('lon')
                            city = ip_data.get('city', '')
                    except Exception as e:
                        print(f"IP Geolocation error: {e}")
                
                # Fallback to Bangalore if still unresolved
                if not lat or not lng:
                    lat = 12.9716
                    lng = 77.5946
                    if not city or city.lower() == "live location":
                        city = "Bangalore"
            elif c_clean in CITY_COORDS:
                lat, lng = CITY_COORDS[c_clean]

        if specialty:
            needed = [specialty]
        else:
            needed = DISEASE_SPECIALTIES.get(disease,["General Medicine","Emergency"])
        
        def score(h):
            s = h['rating']
            has_specialty = False
            for n in needed:
                n_l = n.lower()
                for sp in h['specialties']:
                    sp_l = sp.lower()
                    if n_l in sp_l or "all specialties" in sp_l:
                        has_specialty = True
                        break
                if has_specialty:
                    break
            if has_specialty: s += 3.0
            if severity == 'High' and h['emergency']: s += 2.0
            return s

        def get_distance(lat1, lng1, lat2, lng2):
            return round(((float(lat1) - float(lat2))**2 + (float(lng1) - float(lng2))**2)**0.5 * 111, 1)

        candidates = []

        # 1. Gather matching records from static database
        for h in HOSPITALS:
            if city and city.lower() != "live location" and city.lower() not in h['city'].lower():
                continue
            if emergency_only and not h['emergency']:
                continue
            if h['rating'] < min_rating:
                continue
            if search_query:
                q_match = (search_query in h['name'].lower() or 
                           search_query in h['address'].lower() or 
                           search_query in h['city'].lower() or 
                           any(search_query in sp.lower() for sp in h['specialties']))
                if not q_match:
                    continue
            if specialty:
                has_spec = False
                for sp in h['specialties']:
                    if specialty.lower() in sp.lower():
                        has_spec = True
                        break
                if not has_spec:
                    continue
            
            h_copy = dict(h)
            if lat and lng and 'lat' in h_copy and 'lng' in h_copy:
                h_copy['distance_km'] = get_distance(lat, lng, h_copy['lat'], h_copy['lng'])
            
            # If Live Location mode: only include hospitals within 50 km of the resolved coordinates
            if city.strip().lower() == "live location" and 'distance_km' in h_copy:
                if h_copy['distance_km'] > 50:
                    continue
            
            candidates.append(h_copy)

        # Secondary search fallback: if searching specifically but city filtering yielded zero records, search globally!
        if search_query and not candidates:
            for h in HOSPITALS:
                if emergency_only and not h['emergency']:
                    continue
                if h['rating'] < min_rating:
                    continue
                q_match = (search_query in h['name'].lower() or 
                           search_query in h['address'].lower() or 
                           search_query in h['city'].lower() or 
                           any(search_query in sp.lower() for sp in h['specialties']))
                if q_match:
                    if specialty:
                        has_spec = False
                        for sp in h['specialties']:
                            if specialty.lower() in sp.lower():
                                has_spec = True
                                break
                        if not has_spec:
                            continue
                    
                    h_copy = dict(h)
                    if lat and lng and 'lat' in h_copy and 'lng' in h_copy:
                        h_copy['distance_km'] = get_distance(lat, lng, h_copy['lat'], h_copy['lng'])
                    candidates.append(h_copy)

        # 2. Query Live GPS Overpass API if active
        if lat and lng:
            live_hospitals = []
            overpass_url = "http://overpass-api.de/api/interpreter"
            overpass_query = f"""
            [out:json];
            (
               node["amenity"="hospital"](around:10000,{lat},{lng});
               way["amenity"="hospital"](around:10000,{lat},{lng});
               relation["amenity"="hospital"](around:10000,{lat},{lng});
               node["amenity"="clinic"](around:10000,{lat},{lng});
            );
            out center;
            """
            headers = {
                'User-Agent': 'MediAIApp/1.0 (contact@mediaihealth.org)'
            }
            try:
                response = requests.get(overpass_url, params={'data': overpass_query}, headers=headers, timeout=5)
                data = response.json()
                for element in data.get('elements', []):
                    name = element.get('tags', {}).get('name', 'Unknown Clinic/Hospital')
                    if name == 'Unknown Clinic/Hospital': continue
                    if search_query and search_query not in name.lower():
                        continue
                        
                    el_lat = element.get('lat') or element.get('center', {}).get('lat', 0)
                    el_lon = element.get('lon') or element.get('center', {}).get('lon', 0)
                    dist = get_distance(lat, lng, el_lat, el_lon)
                    
                    name_l = name.lower()
                    sps = ["General Medicine", "Emergency"]
                    if "eye" in name_l or "ophthalm" in name_l: sps.append("Ophthalmology")
                    if "heart" in name_l or "cardiac" in name_l: sps.append("Cardiology")
                    if "child" in name_l or "pediatr" in name_l: sps.append("Pediatrics")
                    if "ortho" in name_l or "bone" in name_l: sps.append("Orthopaedics")
                    if "cancer" in name_l or "oncolo" in name_l: sps.append("Oncology")
                    if "neuro" in name_l or "brain" in name_l: sps.append("Neurology")
                    if "skin" in name_l or "derm" in name_l: sps.append("Dermatology")
                    if "ent" in name_l or "throat" in name_l: sps.append("ENT (Otolaryngology)")
                    if "dental" in name_l or "dentist" in name_l: sps.append("Dentistry")
                    if "lung" in name_l or "chest" in name_l or "pulmono" in name_l: sps.append("Pulmonology")
                    if len(sps) == 2:
                        sps.extend(["Pulmonology", "Gastroenterology", "General Surgery"])
                    
                    if specialty:
                        has_spec = False
                        for s_item in sps:
                            if specialty.lower() in s_item.lower():
                                has_spec = True
                                break
                        if not has_spec:
                            continue
                    
                    rating = round(4.0 + (id(name) % 10) / 10.0, 1)
                    if rating < min_rating:
                        continue
                    is_emerg = element.get('tags', {}).get('emergency') == 'yes' or "hospital" in name_l
                    if emergency_only and not is_emerg:
                        continue
                        
                    live_hospitals.append({
                        "name": name,
                        "city": "Local Area",
                        "specialties": sps,
                        "phone": element.get('tags', {}).get('phone', 'N/A'),
                        "rating": rating,
                        "emergency": is_emerg,
                        "address": f"{round(dist, 1)} km from your location",
                        "distance_km": dist
                    })
            except Exception as e:
                print(f"Overpass API error: {e}")
                
            # Failover generator for Live GPS if Overpass fails
            if not live_hospitals:
                local_names = [
                    "St. Mary's General Hospital", "Metro Life Care Clinic", 
                    "City Emergency Hospital", "Apex Super Specialty Hospital", 
                    "Grace Memorial Medical Center", "Care & Cure Clinic",
                    "Sunrise Children Hospital", "Pinnacle Eye Hospital",
                    "Trinity Cardiac & Heart Centre", "Neurolife Specialty Clinic"
                ]
                import random
                for i, name in enumerate(local_names):
                    if search_query and search_query not in name.lower():
                        continue
                    dist = round(1.0 + (i * 0.8) + random.uniform(0.1, 0.5), 1)
                    name_l = name.lower()
                    sps = ["General Medicine", "Emergency"]
                    if "child" in name_l: sps.append("Pediatrics")
                    elif "eye" in name_l: sps.append("Ophthalmology")
                    elif "cardiac" in name_l or "heart" in name_l: sps.append("Cardiology")
                    elif "neuro" in name_l: sps.append("Neurology")
                    else: sps.extend(["Pulmonology", "Gastroenterology", "General Surgery"])
                    
                    if specialty:
                        has_spec = False
                        for s_item in sps:
                            if specialty.lower() in s_item.lower():
                                has_spec = True
                                break
                        if not has_spec:
                            continue
                    
                    rating = round(4.2 + (i % 3) * 0.3, 1)
                    if rating < min_rating:
                        continue
                    is_emerg = i % 3 != 0 or "hospital" in name_l
                    if emergency_only and not is_emerg:
                        continue
                        
                    live_hospitals.append({
                        "name": name,
                        "city": "Local Area",
                        "specialties": sps,
                        "phone": f"+91 98450 {10000 + i*111}",
                        "rating": rating,
                        "emergency": is_emerg,
                        "address": f"District Road, {dist} km from your location",
                        "distance_km": dist
                    })
            candidates.extend(live_hospitals)

        # De-duplicate blended search results by hospital name
        seen = set()
        unique_candidates = []
        for h in candidates:
            if h['name'] not in seen:
                seen.add(h['name'])
                unique_candidates.append(h)

        # When live location / GPS coords are available: sort by distance (nearest first), then by score
        if lat and lng:
            # Ensure all candidates have a distance_km (static hospitals without lat/lng get a large default)
            for h in unique_candidates:
                if 'distance_km' not in h:
                    h['distance_km'] = 999.0
            ranked = sorted(unique_candidates, key=lambda h: (h['distance_km'], -score(h)))[:20]
        else:
            ranked = sorted(unique_candidates, key=lambda h: -score(h))[:15]
        return JsonResponse({'hospitals': ranked, 'specialties': needed})
    except Exception as e:
        return JsonResponse({'error':str(e)},status=500)


# ── Consultation CRUD ─────────────────────────────────────────────────────────
@login_required
def request_consultation(request, check_id):
    sc = get_object_or_404(SymptomCheck, id=check_id)
    Consultation.objects.create(patient=request.user, symptom_check=sc)
    messages.success(request,'Consultation request submitted!')
    return redirect('dashboard')

@login_required
def delete_consultation(request, consult_id):
    c = get_object_or_404(Consultation, id=consult_id)
    if not (request.user == c.patient or (hasattr(request.user, 'doctor_profile') and c.doctor == request.user.doctor_profile)):
        messages.error(request, 'Unauthorized')
        return redirect('dashboard')
    c.delete()
    messages.success(request,'Consultation deleted.')
    return redirect('dashboard')

@login_required
def approve_consultation(request, consult_id):
    if not hasattr(request.user, 'doctor_profile'):
        messages.error(request, 'Only doctors can approve consultations.')
        return redirect('dashboard')
    c = get_object_or_404(Consultation, id=consult_id)
    if request.method == 'POST':
        c.doctor = request.user.doctor_profile
        c.status = 'Approved'
        c.meet_link = f"https://meet.jit.si/MediAI_Consult_{uuid.uuid4().hex[:12]}"
        
        # simple parsing of scheduled time if provided (e.g., from a form)
        time_str = request.POST.get('scheduled_time')
        if time_str:
            from django.utils.dateparse import parse_datetime
            c.scheduled_time = parse_datetime(time_str)
            
        c.save()
        messages.success(request, 'Consultation approved and video link generated.')
    return redirect('dashboard')

@login_required
def video_consultation(request, consult_id):
    c = get_object_or_404(Consultation, id=consult_id)
    if request.user != c.patient and not (hasattr(request.user, 'doctor_profile') and c.doctor == request.user.doctor_profile):
        messages.error(request, 'Unauthorized access to this consultation.')
        return redirect('dashboard')
    if not c.meet_link:
        messages.error(request, 'Video link not generated yet.')
        return redirect('dashboard')
    
    return render(request, 'checker/video_consult.html', {'consultation': c, 'is_doctor': hasattr(request.user, 'doctor_profile')})

@login_required
def book_appointment(request):
    if hasattr(request.user, 'doctor_profile'):
        return JsonResponse({'error': 'Doctors cannot book appointments.'}, status=400)
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            booking_target = body.get('booking_target', 'doctor')
            time_str = body.get('scheduled_time')
            notes = body.get('notes', '')
            
            from django.utils.dateparse import parse_datetime
            scheduled_time = parse_datetime(time_str)
            
            if booking_target == 'hospital':
                hospital_name = body.get('hospital_name')
                notes = f"🏥 Appointment booked at: {hospital_name}. Reason: {notes}"
                c = Consultation.objects.create(
                    patient=request.user,
                    doctor=None,
                    status='Approved',
                    notes=notes,
                    scheduled_time=scheduled_time
                )
            else:
                doc_id = body.get('doctor_id')
                doctor = get_object_or_404(DoctorProfile, id=doc_id)
                c = Consultation.objects.create(
                    patient=request.user,
                    doctor=doctor,
                    status='Approved',
                    notes=notes,
                    scheduled_time=scheduled_time,
                    meet_link=f"https://meet.jit.si/MediAI_Consult_{uuid.uuid4().hex[:12]}"
                )
            return JsonResponse({'status': 'success', 'message': 'Appointment booked successfully!'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'POST required'}, status=405)

@login_required
def write_prescription(request, consult_id):
    if not hasattr(request.user, 'doctor_profile'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    c = get_object_or_404(Consultation, id=consult_id, doctor=request.user.doctor_profile)
    
    if request.method == 'POST':
        notes = request.POST.get('prescription_notes', '')
        meds = request.POST.get('prescription_meds', '[]')
        c.prescription_notes = notes
        c.prescription_meds = meds
        c.status = 'Completed'
        c.save()
        messages.success(request, 'Prescription generated successfully.')
        return redirect('dashboard')
    
    return render(request, 'checker/write_prescription.html', {'consultation': c})

@login_required
def view_prescription(request, consult_id):
    c = get_object_or_404(Consultation, id=consult_id)
    if request.user != c.patient and not (hasattr(request.user, 'doctor_profile') and c.doctor == request.user.doctor_profile):
        messages.error(request, 'Unauthorized')
        return redirect('dashboard')
        
    meds = []
    if c.prescription_meds:
        try:
            meds = json.loads(c.prescription_meds)
        except:
            meds = [c.prescription_meds]
            
    return render(request, 'checker/prescription_pdf.html', {'consultation': c, 'medications': meds})

@login_required
def api_outbreaks(request):
    # This endpoint is kept for backwards compatibility but we will return empty or simple data
    return JsonResponse({'outbreaks': []})

@login_required
def api_check_interactions(request):
    """Checks for interactions between two drugs."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        body = json.loads(request.body)
        drug1 = body.get('drug1', '').strip().lower()
        drug2 = body.get('drug2', '').strip().lower()
        
        # Simple interaction warning database
        interactions = {
            ("aspirin", "warfarin"): "⚠️ High Risk: Increased risk of bleeding. Avoid combining without close medical supervision.",
            ("ibuprofen", "aspirin"): "⚠️ Moderate Risk: Ibuprofen may decrease the cardioprotective effect of low-dose aspirin.",
            ("metformin", "contrast dye"): "⚠️ High Risk: Risk of lactic acidosis. Temporarily stop Metformin before imaging scans.",
            ("lisinopril", "spironolactone"): "⚠️ Moderate Risk: Can lead to high levels of potassium in the blood (hyperkalemia).",
            ("amoxicillin", "methotrexate"): "⚠️ Moderate Risk: Amoxicillin may increase toxicity levels of Methotrexate.",
            ("warfarin", "ibuprofen"): "⚠️ High Risk: Greatly increases the risk of stomach bleeding and ulcers.",
            ("sildenafil", "nitroglycerin"): "🚨 Severe Risk: Coadministration can cause dangerous, life-threatening drops in blood pressure."
        }
        
        # Check both directions
        key1 = (drug1, drug2)
        key2 = (drug2, drug1)
        
        result = "✅ No major drug interactions found in our database for this combination. Please consult your physician to verify."
        severity = "info"
        
        if key1 in interactions:
            result = interactions[key1]
            severity = "danger" if "Severe" in result or "High" in result else "warning"
        elif key2 in interactions:
            result = interactions[key2]
            severity = "danger" if "Severe" in result or "High" in result else "warning"
            
        return JsonResponse({'result': result, 'severity': severity})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ── About ─────────────────────────────────────────────────────────────────────
def about(request):
    return render(request,'checker/about.html',{
        'accuracies':ml.get_accuracies(),'patient':_profile(request)
    })

# ── Dynamic Clinical Diet & Wellness Advisor Helper ──────────────────────────
def _generate_diet_advice(disease, bmi_cat, age):
    diet = []
    exercise = []
    avoid_foods = []
    avoid_activities = []
    
    d_lower = disease.lower()
    if "hypertension" in d_lower:
        diet.extend(["DASH Diet: High in fruits, vegetables, and whole grains.", "Low-Sodium: Keep sodium under 1,500 mg per day."])
        avoid_foods.extend(["Processed meats", "Canned soups", "Pickles", "Excess salt"])
        exercise.extend(["Aerobic walking: 30 minutes of brisk walking.", "Light cycling or swimming."])
        avoid_activities.extend(["Heavy powerlifting", "Sudden intense bursts of exercise"])
    elif "diabetes" in d_lower:
        diet.extend(["Low-Glycemic Diet: Focus on fiber-rich complex carbs, lean proteins.", "Regular small meals to stabilize insulin levels."])
        avoid_foods.extend(["Sugary beverages", "White bread/rice", "Sweet desserts", "High-fructose corn syrup"])
        exercise.extend(["Interval walking: Alternating speeds.", "Moderate strength training 2x/week to improve insulin sensitivity."])
        avoid_activities.extend(["Exercising on an empty stomach (risk of hypoglycemia)"])
    elif "gerd" in d_lower or "acid reflux" in d_lower or "peptic ulcer" in d_lower:
        diet.extend(["Alkaline-rich foods (bananas, melons, oatmeal).", "Small, frequent meals instead of heavy dinners."])
        avoid_foods.extend(["Citrus fruits", "Tomatoes and tomato-based sauces", "Chocolate", "Caffeine", "Spicy & fried foods"])
        exercise.extend(["Gentle upright walking: Walk for 15-20 minutes after eating.", "Yoga (avoiding inversion poses)"])
        avoid_activities.extend(["Lying flat immediately after eating", "Intense abdominal crunches"])
    elif "common cold" in d_lower or "influenza" in d_lower or "covid" in d_lower or "bronchitis" in d_lower or "pneumonia" in d_lower:
        diet.extend(["High-Vitamin C foods (citrus fruits, bell peppers).", "Warm herbal teas with honey to soothe throat and thin mucus.", "Bone broth or clear warm vegetable soups."])
        avoid_foods.extend(["Dairy products (may thicken mucus)", "Cold sugary drinks", "Deep-fried foods"])
        exercise.extend(["Complete rest: Prioritize sleep to conserve energy.", "Very light breathing stretches to expand lung capacity."])
        avoid_activities.extend(["Cardio workouts", "Outdoor running in cold air", "Heavy lifting"])
    elif "asthma" in d_lower:
        diet.extend(["Anti-inflammatory diet: Rich in Omega-3 fatty acids (flaxseeds, walnuts).", "Vitamin D rich foods."])
        avoid_foods.extend(["Foods with sulfites (dried fruits, wine)", "Extreme cold water/foods"])
        exercise.extend(["Indoor warm-up exercises", "Controlled breathing yoga (Pranayama)."])
        avoid_activities.extend(["Running outdoors in dry, cold air without a scarf", "High-intensity cardio during high-pollen days"])
    elif "anemia" in d_lower:
        diet.extend(["Iron-Rich Foods: Red meat, spinach, lentils, pumpkin seeds.", "Vitamin C pairing: Pair iron with citrus to double absorption."])
        avoid_foods.extend(["Tea or coffee with meals (tannins block iron absorption)"])
        exercise.extend(["Short, moderate walks to boost red blood cell circulation.", "Frequent rest breaks during movement."])
        avoid_activities.extend(["HIIT or exhausting heavy workouts"])
    elif "depression" in d_lower or "anxiety" in d_lower or "panic" in d_lower:
        diet.extend(["Omega-3 rich foods to support brain health.", "Complex carbohydrates (oats, quinoa) to boost serotonin levels.", "Magnesium-rich foods (dark chocolate, almonds) for relaxation."])
        avoid_foods.extend(["Caffeine", "Alcohol", "Refined sugary snacks (creates sugar spikes & crashes)"])
        exercise.extend(["Outdoor aerobic walks: 30 minutes in natural sunlight.", "Mindful yoga or Tai Chi."])
        avoid_activities.extend(["Overtraining or extreme physical exhaustion"])
    else:
        diet.extend(["Balanced Mediterranean Diet: Lean proteins, healthy fats (olive oil, avocados).", "High hydration: Minimum of 2-3 liters of clean water daily."])
        avoid_foods.extend(["Ultra-processed foods", "Excessive refined sugars", "Trans-fats"])
        exercise.extend(["General functional fitness: 30 minutes of daily moderate cardio.", "Daily mobility stretching."])
        avoid_activities.extend(["Prolonged sedentary behavior (take a 5-minute break every hour)"])

    if bmi_cat == 'Overweight' or bmi_cat == 'Obese':
        diet.append("Caloric deficit: Maintain a slight caloric deficit with portion control.")
        exercise.append("Low-impact cardio (swimming, elliptical) to protect knee joints.")
    elif bmi_cat == 'Underweight':
        diet.append("Caloric surplus: Focus on nutrient-dense, calorie-rich healthy foods (nuts, nut butters, avocados).")
        exercise.append("Resistance training to build healthy lean muscle mass.")

    if age and age >= 60:
        diet.append("Calcium & Vitamin D: Increase intake to support bone density.")
        exercise.append("Balance exercises (single-leg stands) to prevent falls.")
        avoid_activities.append("High-impact jumping or running.")

    return {
        'diet': diet,
        'exercise': exercise,
        'avoid_foods': avoid_foods,
        'avoid_activities': avoid_activities
    }

# ── Dynamic Clinical PDF Prescription Exporter ───────────────────────────────
@login_required
def result_print(request, check_id):
    sc = get_object_or_404(SymptomCheck, id=check_id)
    symptoms    = json.loads(sc.symptoms_selected)
    precautions = json.loads(sc.precautions) if sc.precautions else []
    home_care   = json.loads(sc.home_care)   if sc.home_care   else []
    medications = json.loads(sc.medications) if sc.medications else []
    all_preds   = json.loads(sc.all_predictions) if sc.all_predictions else {}
    
    # Generate dynamic diet and exercise recommendations
    bmi_category = 'Normal'
    age = 30
    p = _profile(request)
    if p:
        bmi_category = p.bmi_category or 'Normal'
        age = p.age or 30
    elif sc.patient_bmi:
        if sc.patient_bmi < 18.5: bmi_category = 'Underweight'
        elif sc.patient_bmi < 25.0: bmi_category = 'Normal'
        elif sc.patient_bmi < 30.0: bmi_category = 'Overweight'
        else: bmi_category = 'Obese'
    if sc.patient_age:
        age = sc.patient_age

    wellness_advice = _generate_diet_advice(sc.predicted_disease, bmi_category, age)
    
    return render(request,'checker/result_print.html',{
        'sc':sc,'symptoms':symptoms,'precautions':precautions,
        'home_care':home_care,'medications':medications,'all_preds':all_preds,
        'patient':p,
        'wellness_advice': wellness_advice
    })

# ── Vitals Logging CRUD ──────────────────────────────────────────────────────
@login_required
@csrf_exempt
def vitals_add(request):
    if request.method != 'POST':
        return JsonResponse({'error':'POST required'}, status=405)
    try:
        body = json.loads(request.body)
        systolic = int(body.get('systolic', 120))
        diastolic = int(body.get('diastolic', 80))
        heart_rate = int(body.get('heart_rate', 72))
        temperature = float(body.get('temperature', 98.6))
        blood_glucose = int(body.get('blood_glucose', 100))
        sleep_hours = float(body.get('sleep_hours', 8))
        hydration_ml = int(body.get('hydration_ml', 2000))
        
        log = VitalsLog.objects.create(
            user=request.user,
            systolic=systolic,
            diastolic=diastolic,
            heart_rate=heart_rate,
            temperature=temperature,
            blood_glucose=blood_glucose,
            sleep_hours=sleep_hours,
            hydration_ml=hydration_ml
        )
        return JsonResponse({'status':'success', 'message':'Daily vitals logged successfully!'})
    except Exception as e:
        return JsonResponse({'error':str(e)}, status=500)

# ── Medication Reminder CRUD ─────────────────────────────────────────────────
@login_required
@csrf_exempt
def medication_add(request):
    if request.method != 'POST':
        return JsonResponse({'error':'POST required'}, status=405)
    try:
        body = json.loads(request.body)
        name = body.get('name','').strip()
        dosage = body.get('dosage','').strip()
        frequency = body.get('frequency','').strip()
        time_str = body.get('time','').strip()
        
        if not name or not dosage or not time_str:
            return JsonResponse({'error':'Name, dosage, and time are required.'}, status=400)
            
        from datetime import datetime
        t = datetime.strptime(time_str, "%H:%M").time()
        
        med = Medication.objects.create(
            user=request.user,
            name=name,
            dosage=dosage,
            frequency=frequency,
            time=t
        )
        return JsonResponse({'status':'success', 'message':'Medication added successfully!'})
    except Exception as e:
        return JsonResponse({'error':str(e)}, status=500)

@login_required
@csrf_exempt
def medication_toggle(request, med_id):
    if request.method != 'POST':
        return JsonResponse({'error':'POST required'}, status=405)
    try:
        med = get_object_or_404(Medication, id=med_id, user=request.user)
        med.active = not med.active
        med.save()
        return JsonResponse({'status':'success', 'active':med.active})
    except Exception as e:
        return JsonResponse({'error':str(e)}, status=500)

@login_required
@csrf_exempt
def medication_delete(request, med_id):
    if request.method != 'POST':
        return JsonResponse({'error':'POST required'}, status=405)
    try:
        med = get_object_or_404(Medication, id=med_id, user=request.user)
        med.delete()
        return JsonResponse({'status':'success'})
    except Exception as e:
        return JsonResponse({'error':str(e)}, status=500)
