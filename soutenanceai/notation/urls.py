from django.urls import path

from . import views

app_name = 'notation'

urlpatterns = [
    path('passage/<int:passage_id>/notes/', views.notes_passage, name='notes_passage'),
    path('passage/<int:passage_id>/declencher/', views.declencher_notation, name='declencher'),
    path('passage/<int:passage_id>/rapport.pdf', views.telecharger_rapport, name='rapport_pdf'),
    path('notes/<int:note_id>/modifier/', views.modifier_note, name='modifier_note'),
]
