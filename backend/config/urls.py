"""Root URL conf. Each app owns its own urls.py so two people adding endpoints
on the same day never touch the same file."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("reports.urls")),
    path("api/", include("resources.urls")),
    path("api/", include("dispatch.urls")),
    path("api/", include("alerts.urls")),
    path("api/", include("ingest.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
