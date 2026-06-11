from django.contrib import admin

from .models import NoteIA, QuestionPosee


@admin.register(NoteIA)
class NoteIAAdmin(admin.ModelAdmin):
    list_display = ('etudiant', 'passage', 'critere', 'note_ia', 'note_finale', 'modifiee_par_prof')
    list_filter = ('modifiee_par_prof', 'passage__session')
    search_fields = ('etudiant__username', 'critere__nom')


@admin.register(QuestionPosee)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('passage', 'auteur', 'note_reponse', 'date_posee')
    list_filter = ('auteur',)
