from django.urls import path

from . import views

app_name = 'presentation'

urlpatterns = [
    path('', views.dashboard_etudiant, name='dashboard_etudiant'),
    path('passage/<int:passage_id>/', views.detail_passage, name='detail_passage'),
    path('passage/<int:passage_id>/upload/', views.upload_fichiers, name='upload'),
    path('passage/<int:passage_id>/salle/', views.salle_presentation, name='salle'),

    # Endpoints AJAX
    path('passage/<int:passage_id>/api/demarrer/', views.demarrer, name='api_demarrer'),
    path('passage/<int:passage_id>/api/terminer-presentation/',
         views.terminer_presentation, name='api_terminer_presentation'),
    path('passage/<int:passage_id>/api/terminer-passage/',
         views.terminer_passage, name='api_terminer_passage'),
    # NB : audio-chunk passe désormais par WebSocket (ws/passage/<id>/audio/)
    path('passage/<int:passage_id>/api/video/', views.upload_video, name='api_video'),
    path('passage/<int:passage_id>/api/posture/', views.upload_posture, name='api_posture'),
    path('passage/<int:passage_id>/api/repondre/',
         views.repondre_question, name='api_repondre'),
    # Reconnaissance faciale — photos de référence pour face-api.js
    path('passage/<int:passage_id>/api/face-descriptors/',
         views.face_descriptors, name='api_face_descriptors'),
]
