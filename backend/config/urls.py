"""Root URL conf. Each app owns its own urls.py so two people adding endpoints
on the same day never touch the same file."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def health(request):
    """GET /api/health -> 200 {"ok": true, "db": true}

    Unauthenticated ON PURPOSE. Render polls a health check path and treats
    anything that is not 2xx as a dead instance, so pointing it at /api/state --
    which is behind IsAuthenticated and answers 401 -- gets the service restarted
    in a loop for ever.

    It touches the database, because a web process that is up but cannot reach
    Neon is not healthy in any sense the word is useful.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse({"ok": db_ok, "db": db_ok}, status=200 if db_ok else 503)


urlpatterns = [
    path("api/health", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.reports.urls")),
    path("api/", include("apps.resources.urls")),
    path("api/", include("apps.dispatch.urls")),
    path("api/", include("apps.alerts.urls")),
    path("api/", include("apps.ingest.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
