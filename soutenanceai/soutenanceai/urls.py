"""URLs racine du projet SoutenanceAI."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts import views as accounts_views
from sessions_app import views as sessions_views


urlpatterns = [
    path('', accounts_views.landing_view, name='landing'),
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),   # set_language endpoint
    path('accounts/', include('accounts.urls')),
    path('sessions/', include('sessions_app.urls')),
    path('classes/rejoindre/<str:code>/', sessions_views.rejoindre_classe, name='rejoindre_classe'),
    path('notation/', include('notation.urls')),
    path('presentation/', include('presentation.urls')),
    path('assistant/', include('assistant.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
