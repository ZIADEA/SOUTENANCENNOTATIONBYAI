"""Modèle utilisateur custom avec rôles."""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Utilisateur de SoutenanceAI avec 3 rôles possibles."""

    ROLE_SUPERADMIN = 'superadmin'
    ROLE_PROFESSEUR = 'professeur'
    ROLE_ETUDIANT = 'etudiant'

    ROLE_CHOICES = [
        (ROLE_SUPERADMIN, 'Super-administrateur'),
        (ROLE_PROFESSEUR, 'Professeur'),
        (ROLE_ETUDIANT, 'Étudiant'),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_ETUDIANT,
        verbose_name='Rôle',
    )

    SEXE_CHOICES = [('H', 'Homme'), ('F', 'Femme')]
    sexe = models.CharField(
        max_length=1,
        choices=SEXE_CHOICES,
        blank=True,
        default='',
        verbose_name='Sexe',
        help_text='Utilisé pour choisir l\'avatar du professeur dans la salle.',
    )

    # Le prof qui a créé ce compte (pour les étudiants)
    cree_par = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='comptes_crees',
    )
    photo_profil = models.ImageField(
        upload_to='photos_profil/',
        null=True, blank=True,
        verbose_name='Photo de profil',
        help_text='Photo nette de face — utilisée pour la reconnaissance faciale pendant la soutenance.',
    )

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'

    # -- Helpers ---------------------------------------------------------
    @property
    def is_superadmin(self) -> bool:
        return self.role == self.ROLE_SUPERADMIN or self.is_superuser

    @property
    def is_professeur(self) -> bool:
        return self.role == self.ROLE_PROFESSEUR

    @property
    def is_etudiant(self) -> bool:
        return self.role == self.ROLE_ETUDIANT

    def __str__(self) -> str:
        nom = self.get_full_name() or self.username
        return f'{nom} ({self.get_role_display()})'
