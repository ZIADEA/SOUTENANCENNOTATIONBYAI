from django.urls import path

from . import views

app_name = 'sessions_app'

urlpatterns = [
    # ── Dashboard prof ─────────────────────────────────────────────
    path('', views.dashboard_professeur, name='dashboard_professeur'),

    # ── CRUD Classes ───────────────────────────────────────────────
    path('classes/nouvelle/', views.creer_classe, name='creer_classe'),
    path('classes/<int:classe_id>/', views.detail_classe, name='detail_classe'),
    path('classes/<int:classe_id>/editer/', views.editer_classe, name='editer_classe'),
    path('classes/<int:classe_id>/supprimer/', views.supprimer_classe, name='supprimer_classe'),
    path('classes/<int:classe_id>/code/', views.code_classe, name='code_classe'),
    path('classes/<int:classe_id>/inscrits/<int:user_id>/retirer/', views.retirer_inscrit_classe, name='retirer_inscrit_classe'),

    # ── Soutenances dans une classe ────────────────────────────────
    path('classes/<int:classe_id>/soutenances/nouvelle/', views.creer_session, name='creer_session'),
    path('<int:session_id>/', views.detail_session, name='detail_session'),
    path('<int:session_id>/editer/', views.editer_session, name='editer_session'),
    path('<int:session_id>/supprimer/', views.supprimer_session, name='supprimer_session'),

    # ── Code & planning soutenance ─────────────────────────────────
    path('<int:session_id>/code/', views.code_session, name='code_session'),
    path('<int:session_id>/planifier/', views.planifier_passages, name='planifier_passages'),
    path('<int:session_id>/planifier/auto/', views.planifier_auto, name='planifier_auto'),
    path('<int:session_id>/planifier/recalculer/', views.recalculer_planning, name='recalculer_planning'),
    path('<int:session_id>/planifier/importer/', views.importer_groupes, name='importer_groupes'),
    path('<int:session_id>/planifier/importer/confirmer/', views.importer_groupes_confirmer, name='importer_groupes_confirmer'),
    path('<int:session_id>/planifier/export/', views.exporter_planning_xlsx, name='exporter_planning_xlsx'),
    path('<int:session_id>/notes/', views.notes_session, name='notes_session'),
    path('<int:session_id>/notes/export/', views.exporter_notes_xlsx, name='exporter_notes_xlsx'),
    path('<int:session_id>/inscrits/<int:user_id>/retirer/', views.retirer_inscrit, name='retirer_inscrit'),

    # ── Passages ────────────────────────────────────────────────────
    # Note : la création se fait inline dans planifier_passages (plus de page séparée)
    path('passages/<int:passage_id>/editer/', views.editer_passage, name='editer_passage'),
    path('passages/<int:passage_id>/supprimer/', views.supprimer_passage, name='supprimer_passage'),
    path('passages/<int:passage_id>/live/', views.suivi_live_passage, name='suivi_live'),

    # ── Rejoindre (public) ─────────────────────────────────────────
    path('rejoindre/<str:code>/', views.rejoindre_session, name='rejoindre_session'),
]
