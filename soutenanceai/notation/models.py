"""Modèles de notation : NoteIA + QuestionPosee."""
from django.conf import settings
from django.db import models

from sessions_app.models import CritereNotation, PassageEtudiant


class NoteIA(models.Model):
    """Note attribuée par l'IA pour un étudiant sur un critère, modifiable par le prof."""

    passage = models.ForeignKey(
        PassageEtudiant, on_delete=models.CASCADE, related_name='notes',
    )
    etudiant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notes_obtenues',
    )
    critere = models.ForeignKey(
        CritereNotation, on_delete=models.CASCADE, related_name='notes_attribuees',
    )

    note_ia = models.FloatField(
        help_text='Note brute donnée par Claude (0-20)',
    )
    note_finale = models.FloatField(
        help_text='Note finale (initialement = note_ia, modifiable par le prof)',
    )
    commentaire_ia = models.TextField(blank=True)
    commentaire_prof = models.TextField(blank=True)
    modifiee_par_prof = models.BooleanField(default=False)

    date_notation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('passage', 'etudiant', 'critere')
        ordering = ['critere__ordre']
        verbose_name = 'Note IA'
        verbose_name_plural = 'Notes IA'

    def save(self, *args, **kwargs):
        if self.pk is None and self.note_finale is None:
            self.note_finale = self.note_ia
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.etudiant} — {self.critere.nom}: {self.note_finale}/20'


class QuestionPosee(models.Model):
    """Question générée par l'IA (ou par le prof) pendant la session questions."""

    AUTEUR_CHOICES = [('ia', 'IA'), ('prof', 'Professeur')]

    passage = models.ForeignKey(
        PassageEtudiant, on_delete=models.CASCADE, related_name='questions_posees',
    )
    auteur = models.CharField(max_length=10, choices=AUTEUR_CHOICES, default='ia')
    question = models.TextField()
    reponse_etudiant = models.TextField(blank=True)
    evaluation_ia = models.TextField(blank=True)
    note_reponse = models.FloatField(null=True, blank=True)
    date_posee = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date_posee']

    def __str__(self) -> str:
        return f'Q ({self.auteur}) — {self.question[:60]}'
