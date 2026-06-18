from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('',                       views.home,                  name='home'),
    path('register/',              views.register_view,         name='register'),
    path('login/',                 views.login_view,            name='login'),
    path('logout/',                views.logout_view,           name='logout'),
    path('dashboard/',             views.dashboard,             name='dashboard'),
    path('profile/edit/',          views.edit_profile,          name='edit_profile'),
    path('profile/delete/',        views.delete_account_view,   name='delete_account'),
    
    # Direct Password Reset Flow
    path('password-reset/', views.direct_password_reset_view, name='password_reset'),
    
    path('checker/',               views.symptom_checker,       name='symptom_checker'),

    path('predict/',               views.predict_view,          name='predict'),
    path('result/<int:check_id>/', views.result_view,           name='result'),
    path('history/',               views.history_view,          name='history'),
    path('history/delete/<int:check_id>/', views.delete_history,    name='delete_history'),
    path('multimodal/',            views.multimodal_view,       name='multimodal'),
    path('multimodal/voice/',      views.process_voice,         name='voice_input'),
    path('multimodal/image/',      views.process_image,         name='image_input'),
    path('chatbot/',               views.chatbot_view,          name='chatbot'),
    path('chatbot/send/',          views.chatbot_send,          name='chatbot_send'),
    path('chatbot/analyse/',       views.chatbot_analyse,       name='chatbot_analyse'),
    path('chatbot/clear/',         views.chatbot_clear,         name='chatbot_clear'),
    path('api/set-api-key/',       views.set_api_key,           name='set_api_key'),
    path('hospitals/',             views.hospitals_view,        name='hospitals'),
    path('hospitals/suggest/',     views.hospital_suggest,      name='hospital_suggest'),
    path('consult/<int:check_id>/',views.request_consultation,  name='request_consultation'),
    path('consult/book/', views.book_appointment, name='book_appointment'),
    path('consult/approve/<int:consult_id>/', views.approve_consultation, name='approve_consultation'),
    path('consult/video/<int:consult_id>/', views.video_consultation, name='video_consultation'),
    path('consult/prescription/<int:consult_id>/', views.write_prescription, name='write_prescription'),
    path('consult/prescription/pdf/<int:consult_id>/', views.view_prescription, name='view_prescription'),
    path('consult/delete/<int:consult_id>/', views.delete_consultation, name='delete_consultation'),
    path('api/outbreaks/', views.api_outbreaks, name='api_outbreaks'),
    path('api/interactions/', views.api_check_interactions, name='check_interactions'),
    path('about/',                 views.about,                 name='about'),
    
    # Advanced features
    path('result/<int:check_id>/print/', views.result_print,     name='result_print'),
    path('vitals/add/',            views.vitals_add,            name='vitals_add'),
    path('medication/add/',        views.medication_add,        name='medication_add'),
    path('medication/toggle/<int:med_id>/', views.medication_toggle, name='medication_toggle'),
    path('medication/delete/<int:med_id>/', views.medication_delete, name='medication_delete'),
]
