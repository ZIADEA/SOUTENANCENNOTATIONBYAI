from django.contrib import admin

from .models import CritereNotation, PassageEtudiant, Session


class CritereInline(admin.TabularInline):
    model = CritereNotation
    extra = 1


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('titre', 'professeur', 'langue', 'personnalite_ia', 'date_creation')
    list_filter = ('langue', 'personnalite_ia', 'mode_notation_groupe')
    search_fields = ('titre', 'professeur__username')
    inlines = [CritereInline]


@admin.register(PassageEtudiant)
class PassageAdmin(admin.ModelAdmin):
    list_display = ('ordre_passage', 'session', 'heure_prevue', 'statut', 'type_groupe')
    list_filter = ('statut', 'type_groupe', 'session')
    filter_horizontal = ('etudiants',)


@admin.register(CritereNotation)
class CritereAdmin(admin.ModelAdmin):
    list_display = ('nom', 'session', 'coefficient', 'est_personnalise')
    list_filter = ('est_personnalise', 'session')
