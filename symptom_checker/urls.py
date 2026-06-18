from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse

# Custom Admin Panel
admin.site.site_header = "AI Disease Recognizer Admin"
admin.site.site_title = "Disease Recognizer"
admin.site.index_title = "Dashboard"

# Health Check Endpoint
def health_check(request):
    return JsonResponse({
        "status": "running",
        "version": "2.0",
        "message": "AI Disease Recognizer API Active"
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('checker.urls')),
    path('api/', include('checker.urls')),      # API support
    path('health/', health_check),              # System status
]

# Development Media & Static Files
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL,
                          document_root=settings.STATIC_ROOT)
