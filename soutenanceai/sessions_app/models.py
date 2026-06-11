"""Modèles : Classe, Session, CritereNotation, PassageEtudiant."""
import secrets
import string

from django.conf import settings
from django.db import models


def _generer_code(model_class, field='code_acces', length=8):
    """Génère un code unique de `length` caractères alphanumériques majuscules."""
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(secrets.choice(chars) for _ in range(length))
        if not model_class.objects.filter(**{field: code}).exists():
            return code


def _generer_code_session():
    return _generer_code(Session)


# ── Classe (conteneur de soutenances, les étudiants y rejoignent une fois) ──────

class Classe(models.Model):
    """Un groupe de classe créé par un professeur. Contient plusieurs soutenances."""

    professeur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='classes_creees',
    )
    nom = models.CharField(max_length=255, verbose_name='Nom de la classe')
    description = models.TextField(blank=True)
    code_acces = models.CharField(
        max_length=10, unique=True, blank=True,
        verbose_name="Code d'accès",
        help_text="Partagez ce code aux étudiants pour rejoindre la classe",
    )
    inscrits = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='classes_inscrites',
        verbose_name='Étudiants inscrits',
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_creation']
        verbose_name = 'Classe'
        verbose_name_plural = 'Classes'

    def save(self, *args, **kwargs):
        if not self.code_acces:
            self.code_acces = _generer_code(Classe)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.nom} — {self.professeur.get_full_name() or self.professeur.username}'


class Session(models.Model):
    """Une soutenance configurée par un professeur."""

    LANGUE_CHOICES = [
        ('fr', 'Français'),
        ('en', 'Anglais'),
        ('ar', 'Arabe / Darija'),
        ('es', 'Espagnol'),
        ('de', 'Allemand'),
    ]

    # Ancien champ — conservé nullable pour la migration
    PERSONNALITE_CHOICES = [
        ('neutre', 'Neutre — évaluation objective'),
        ('severe', 'Sévère — exigeant'),
        ('empathique', 'Empathique — bienveillant'),
        ('gentil', 'Gentil — encourageant'),
    ]

    STYLE_QUESTIONNEMENT_CHOICES = [
        ('mentor',          'Le Mentor — Questions ouvertes et guidantes'),
        ('pedagogue',       'Le Pédagogue — Explique et enseigne'),
        ('perfectionniste', 'Le Perfectionniste — Traque les imprécisions'),
        ('contradicteur',   'Le Contradicteur — Contre-argumente et teste'),
        ('stratege',        'Le Stratège — Questions précises et ciblées'),
        ('provocateur',     'Le Provocateur — Pousse dans les retranchements'),
        ('impassible',      "L'Impassible — Neutre, aucune réaction"),
    ]

    STYLE_NOTATION_CHOICES = [
        ('genereux',   "Le Généreux — ≈ 15-18/20, valorise l'effort"),
        ('indulgent',  "L'Indulgent — ≈ 13-16/20, bénéfice du doute"),
        ('juste',      'Le Juste — ≈ 12-15/20, grille stricte et équitable'),
        ('avare',      "L'Avare de points — ≈ 10-13/20"),
        ('severe',     'Le Sévère — ≈ 8-12/20, punit les lacunes'),
        ('terroriste', 'Le Terroriste — ≤ 10/20, note comme sanction'),
        ('comptable',  'Le Comptable — Calcule à la décimale'),
    ]

    MODE_GROUPE_CHOICES = [
        ('identique', 'Note identique pour tout le groupe'),
        ('individuelle', 'Note individuelle pour chaque membre'),
        ('mixte', 'Mixte (groupe + individuelle pondérées)'),
    ]

    classe = models.ForeignKey(
        Classe, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='sessions',
        verbose_name='Classe parente',
    )
    professeur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='sessions_creees',
    )
    titre = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    langue = models.CharField(max_length=4, choices=LANGUE_CHOICES, default='fr')
    duree_presentation = models.PositiveIntegerField(
        default=15, help_text='Durée présentation en minutes',
    )
    duree_questions = models.PositiveIntegerField(
        default=5, help_text='Durée session questions en minutes',
    )
    nb_questions_max = models.PositiveIntegerField(default=3)

    rapport_obligatoire = models.BooleanField(default=False)
    coefficient_rapport = models.FloatField(default=1.0)

    # ── Démo vidéo (optionnelle, décidée par le prof) ───────────────────────
    demo_video_requise = models.BooleanField(
        default=False,
        verbose_name='Démo vidéo requise',
        help_text="L'étudiant devra déposer une vidéo de démonstration (app, robot, interface…)",
    )
    demo_video_instructions = models.TextField(
        blank=True,
        verbose_name='Consignes pour la démo vidéo',
        help_text="Ex : Montrez votre robot éviter un obstacle sur 30 secondes",
    )
    coefficient_demo_video = models.FloatField(
        default=1.0,
        verbose_name='Coefficient démo vidéo',
        help_text='Poids de la note démo dans la note finale',
    )

    # ── Dépôt GitHub (optionnel, décidé par le prof) ────────────────────────
    depot_github_requis = models.BooleanField(
        default=False,
        verbose_name='Dépôt GitHub requis',
        help_text="L'étudiant devra fournir l'URL de son dépôt GitHub public",
    )
    criteres_github = models.TextField(
        blank=True,
        verbose_name='Critères d\'évaluation GitHub',
        help_text="Ex : Propreté du code, README complet, tests unitaires, historique commits",
    )
    coefficient_github = models.FloatField(
        default=1.0,
        verbose_name='Coefficient GitHub',
        help_text='Poids de la note GitHub dans la note finale',
    )

    # Ancien champ — kept nullable pour backward compat, remplacé par les deux ci-dessous
    personnalite_ia = models.CharField(
        max_length=20, choices=PERSONNALITE_CHOICES,
        null=True, blank=True,
    )

    # Nouveau double axe IA
    style_questionnement = models.CharField(
        max_length=20, choices=STYLE_QUESTIONNEMENT_CHOICES, default='mentor',
        verbose_name='Style de questionnement',
    )
    style_notation = models.CharField(
        max_length=20, choices=STYLE_NOTATION_CHOICES, default='juste',
        verbose_name='Style de notation',
    )
    ajustement_auto_stress = models.BooleanField(
        default=True,
        verbose_name='Ajustement automatique si stress détecté',
        help_text="Si actif, bascule vers Mentor/Indulgent quand l'étudiant est stressé",
    )

    consignes_ia = models.TextField(
        blank=True,
        help_text="Instructions libres pour l'IA (contexte, focus particulier...)",
    )

    mode_notation_groupe = models.CharField(
        max_length=20, choices=MODE_GROUPE_CHOICES, default='individuelle',
    )
    coefficient_groupe = models.FloatField(default=0.5)
    coefficient_individuel = models.FloatField(default=0.5)

    # ── Code d'accès étudiant (style Google Classroom) ──────────────
    code_acces = models.CharField(
        max_length=10, unique=True, blank=True,
        verbose_name="Code d'accès",
        help_text="Partagez ce code aux étudiants pour qu'ils rejoignent la session",
    )
    inscrits = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='sessions_inscrites',
        verbose_name='Étudiants inscrits',
        help_text='Étudiants ayant rejoint la session (via code ou ajout manuel)',
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_creation']
        verbose_name = 'Session de soutenance'
        verbose_name_plural = 'Sessions de soutenance'

    def save(self, *args, **kwargs):
        if not self.code_acces:
            self.code_acces = _generer_code_session()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.titre} ({self.get_langue_display()})'


class CritereNotation(models.Model):
    """Critère utilisé pour noter une session."""

    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name='criteres',
    )
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    coefficient = models.FloatField(default=1.0)
    est_personnalise = models.BooleanField(
        default=False,
        help_text='True si entré librement par le prof (sinon, critère prédéfini)',
    )
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'id']
        verbose_name = 'Critère de notation'
        verbose_name_plural = 'Critères de notation'

    def __str__(self) -> str:
        return f'{self.nom} (×{self.coefficient})'


class PassageEtudiant(models.Model):
    """Une passage : un étudiant ou un groupe qui soutient à un horaire donné."""

    TYPE_GROUPE_CHOICES = [
        ('monome', 'Monôme (1 étudiant)'),
        ('binome', 'Binôme (2 étudiants)'),
        ('groupe', 'Groupe (3+ étudiants)'),
    ]

    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('en_cours', 'En cours — présentation'),
        ('questions', 'Questions'),
        ('termine', 'Terminé — notation en cours'),
        ('note', 'Noté'),
    ]

    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, related_name='passages',
    )
    etudiants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='passages',
    )
    type_groupe = models.CharField(max_length=10, choices=TYPE_GROUPE_CHOICES, default='monome')
    ordre_passage = models.PositiveIntegerField(default=1)
    heure_prevue = models.DateTimeField()
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')

    fichier_pptx = models.FileField(upload_to='pptx/', blank=True, null=True)
    fichier_rapport = models.FileField(upload_to='rapports/', blank=True, null=True)
    enregistrement_video = models.FileField(upload_to='videos/', blank=True, null=True)
    fichier_demo_video = models.FileField(
        upload_to='demos/', blank=True, null=True,
        verbose_name='Vidéo de démonstration',
    )
    url_depot_github = models.URLField(
        blank=True, max_length=300,
        verbose_name='URL dépôt GitHub',
    )
    analyses_extra = models.JSONField(
        default=dict, blank=True,
        verbose_name='Analyses supplémentaires (vidéo + GitHub)',
        help_text='{"demo_video": {...}, "github": {...}}',
    )
    transcription = models.TextField(blank=True)
    transcriptions_par_etudiant = models.JSONField(
        default=dict, blank=True,
        verbose_name='Transcriptions par étudiant',
        help_text='{"<user_id>": "<texte>"} — renseigné si chaque étudiant se connecte depuis son propre appareil.',
    )
    donnees_posture = models.JSONField(default=dict, blank=True)
    syntheses_ia = models.JSONField(
        default=dict, blank=True,
        verbose_name='Synthèses IA par étudiant',
        help_text=(
            '{"<user_id>": {"synthese": "...", "ton_detecte": "...", '
            '"disfluences_detectees": "...", "coherence_corps_discours": "..."}} '
            '— renseigné après le pipeline de notation.'
        ),
    )

    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    rappel_envoye = models.BooleanField(
        default=False,
        verbose_name='Rappel 10 min envoyé',
        help_text='Vrai si le rappel email pré-passage a déjà été envoyé.',
    )

    class Meta:
        ordering = ['session', 'ordre_passage']
        verbose_name = 'Passage étudiant'
        verbose_name_plural = 'Passages étudiants'

    def __str__(self) -> str:
        noms = ', '.join(e.get_full_name() or e.username for e in self.etudiants.all())
        return f'#{self.ordre_passage} — {noms or "(vide)"} — {self.session.titre}'

    @property
    def noms_etudiants(self) -> str:
        return ', '.join(e.get_full_name() or e.username for e in self.etudiants.all())
