"""Formulaires pour la création/édition de classes, sessions et passages."""
import random as _random

from django import forms
from django.utils import timezone

from accounts.models import User

from .models import Classe, PassageEtudiant, Session


class SessionForm(forms.ModelForm):
    class Meta:
        model = Session
        fields = [
            'titre', 'description',
            'langue', 'duree_presentation', 'duree_questions', 'nb_questions_max',
            'rapport_obligatoire', 'coefficient_rapport',
            'demo_video_requise', 'demo_video_instructions', 'coefficient_demo_video',
            'depot_github_requis', 'criteres_github', 'coefficient_github',
            'style_questionnement', 'style_notation', 'ajustement_auto_stress', 'consignes_ia',
            'mode_notation_groupe', 'coefficient_groupe', 'coefficient_individuel',
        ]
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'langue': forms.Select(attrs={'class': 'form-input'}),
            'duree_presentation': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
            'duree_questions': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
            'nb_questions_max': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
            'coefficient_rapport': forms.NumberInput(attrs={'class': 'form-input', 'step': 0.1}),
            'demo_video_requise': forms.CheckboxInput(),
            'demo_video_instructions': forms.Textarea(attrs={
                'class': 'form-input', 'rows': 2,
                'placeholder': "Ex : Montrez votre robot éviter un obstacle (30 sec max).",
            }),
            'coefficient_demo_video': forms.NumberInput(attrs={'class': 'form-input', 'step': 0.1, 'min': 0}),
            'depot_github_requis': forms.CheckboxInput(),
            'criteres_github': forms.Textarea(attrs={
                'class': 'form-input', 'rows': 2,
                'placeholder': "Ex : Code propre, README détaillé, tests unitaires, commits réguliers.",
            }),
            'coefficient_github': forms.NumberInput(attrs={'class': 'form-input', 'step': 0.1, 'min': 0}),
            'style_questionnement': forms.RadioSelect(),
            'style_notation': forms.RadioSelect(),
            'ajustement_auto_stress': forms.CheckboxInput(),
            'consignes_ia': forms.Textarea(attrs={'class': 'form-input', 'rows': 4,
                                                  'placeholder': "Ex : focus sur la rigueur scientifique, public non technique..."}),
            'mode_notation_groupe': forms.RadioSelect(),
            'coefficient_groupe': forms.NumberInput(attrs={'class': 'form-input', 'step': 0.05, 'min': 0, 'max': 1}),
            'coefficient_individuel': forms.NumberInput(attrs={'class': 'form-input', 'step': 0.05, 'min': 0, 'max': 1}),
        }


class PassageForm(forms.ModelForm):
    etudiants = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(role='etudiant'),
        widget=forms.SelectMultiple(attrs={'class': 'form-input', 'size': 6}),
        label='Étudiant(s)',
    )

    class Meta:
        model = PassageEtudiant
        fields = ['etudiants', 'type_groupe', 'ordre_passage', 'heure_prevue']
        widgets = {
            'type_groupe': forms.Select(attrs={'class': 'form-input'}),
            'ordre_passage': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
            'heure_prevue': forms.DateTimeInput(
                attrs={'class': 'form-input', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, professeur=None, **kwargs):
        super().__init__(*args, **kwargs)
        # On limite aux étudiants créés par ce prof (sauf superadmin)
        if professeur and not professeur.is_superuser:
            self.fields['etudiants'].queryset = User.objects.filter(
                role='etudiant', cree_par=professeur,
            )
        self.fields['heure_prevue'].input_formats = ['%Y-%m-%dT%H:%M']
        if not self.instance.pk:
            self.fields['heure_prevue'].initial = timezone.now()


class RejoindreSessionForm(forms.Form):
    """Formulaire pour qu'un nouvel étudiant rejoigne une session via code."""
    prenom = forms.CharField(
        max_length=50, label='Prénom',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Votre prénom', 'autofocus': True}),
    )
    nom = forms.CharField(
        max_length=50, label='Nom',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Votre nom'}),
    )
    email = forms.EmailField(
        required=False, label='Email (optionnel)',
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'votre@email.fr'}),
    )
    password = forms.CharField(
        label='Mot de passe', min_length=6,
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Choisissez un mot de passe (6 caractères min.)'}),
    )
    password2 = forms.CharField(
        label='Confirmer le mot de passe',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Répétez le mot de passe'}),
    )

    def clean(self):
        data = super().clean()
        if data.get('password') and data.get('password2'):
            if data['password'] != data['password2']:
                raise forms.ValidationError('Les deux mots de passe ne correspondent pas.')
        return data


class PlanifierPassageForm(forms.Form):
    """Formulaire utilisé par le prof pour affecter des inscrits à un passage."""
    etudiants = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple(),
        label='Étudiant(s) à planifier',
        help_text='Sélectionnez 1 (monôme), 2 (binôme) ou plusieurs (groupe)',
    )
    ordre_passage = forms.IntegerField(
        min_value=1, label='Numéro de passage',
        widget=forms.NumberInput(attrs={'class': 'form-input', 'style': 'width:80px', 'min': 1}),
    )
    heure_prevue = forms.DateTimeField(
        label='Heure prévue',
        widget=forms.DateTimeInput(
            attrs={'class': 'form-input', 'type': 'datetime-local'},
            format='%Y-%m-%dT%H:%M',
        ),
        input_formats=['%Y-%m-%dT%H:%M'],
    )

    def __init__(self, *args, session=None, exclude_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        if session:
            # Priorité : inscrits de la Classe parente (nouveau flux)
            # Fallback : inscrits directs de la session (ancien flux)
            if session.classe:
                qs = session.classe.inscrits.filter(role='etudiant')
            else:
                qs = session.inscrits.filter(role='etudiant')
            # Exclure les étudiants déjà planifiés
            if exclude_ids:
                qs = qs.exclude(id__in=exclude_ids)
            self.fields['etudiants'].queryset = qs.order_by('last_name', 'first_name')
        from django.utils import timezone
        self.fields['heure_prevue'].initial = timezone.now().strftime('%Y-%m-%dT%H:%M')


class UploadFichiersForm(forms.ModelForm):
    """Formulaire pour que l'étudiant dépose ses fichiers avant la soutenance."""
    class Meta:
        model = PassageEtudiant
        fields = ['fichier_pptx', 'fichier_rapport', 'fichier_demo_video', 'url_depot_github']
        widgets = {
            'fichier_pptx': forms.FileInput(attrs={'class': 'form-input', 'accept': '.pptx,.pdf'}),
            'fichier_rapport': forms.FileInput(attrs={'class': 'form-input', 'accept': '.pdf'}),
            'fichier_demo_video': forms.FileInput(attrs={
                'class': 'form-input', 'accept': 'video/*,.mp4,.webm,.mov,.avi',
            }),
            'url_depot_github': forms.URLInput(attrs={
                'class': 'form-input',
                'placeholder': 'https://github.com/votre-compte/votre-repo',
            }),
        }


class ClasseForm(forms.ModelForm):
    """Créer / éditer une Classe."""
    class Meta:
        model = Classe
        fields = ['nom', 'description']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Ex : Licence 3 IATD-SI 2025',
                'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-input', 'rows': 3,
                'placeholder': 'Description optionnelle (promotion, module…)',
            }),
        }


class RejoindreClasseForm(forms.Form):
    """Formulaire pour qu'un nouvel étudiant rejoigne une Classe via son code."""
    prenom = forms.CharField(
        max_length=50, label='Prénom',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Votre prénom', 'autofocus': True}),
    )
    nom = forms.CharField(
        max_length=50, label='Nom',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Votre nom'}),
    )
    username = forms.CharField(
        max_length=150, label='Identifiant de connexion',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'ex: prenom.nom  (lettres, chiffres, . - _)',
        }),
        help_text='150 caractères max. Lettres, chiffres et les caractères . @ + - _ uniquement.',
    )
    email = forms.EmailField(
        required=False, label='Email (optionnel)',
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'votre@email.fr'}),
    )
    password = forms.CharField(
        label='Mot de passe', min_length=6,
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Choisissez un mot de passe (6 car. min.)'}),
    )
    password2 = forms.CharField(
        label='Confirmer le mot de passe',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Répétez le mot de passe'}),
    )

    def clean_username(self):
        from django.contrib.auth.validators import UnicodeUsernameValidator
        username = self.cleaned_data.get('username', '').strip()
        UnicodeUsernameValidator()(username)  # lettres/chiffres/@.+-_ uniquement
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Cet identifiant est déjà pris. Choisissez-en un autre.")
        return username

    def clean(self):
        data = super().clean()
        if data.get('password') and data.get('password2'):
            if data['password'] != data['password2']:
                raise forms.ValidationError('Les deux mots de passe ne correspondent pas.')
        return data


class PlanifierAutoForm(forms.Form):
    """Formulaire d'auto-planification : génère tous les créneaux en un clic."""
    date_passage = forms.DateField(
        label='Date',
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
    )
    heure_debut = forms.TimeField(
        label='Heure de début',
        widget=forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
    )
    duree_minutes = forms.IntegerField(
        label='Durée par passage (minutes)', min_value=1, initial=15,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
    )
    pause_minutes = forms.IntegerField(
        label='Pause entre passages (minutes)', min_value=0, initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
    )
    ordre = forms.ChoiceField(
        label='Ordre de passage',
        choices=[('alpha', 'Ordre alphabétique'), ('random', 'Aléatoire (tirage au sort)')],
        widget=forms.RadioSelect(),
    )
    type_groupe = forms.ChoiceField(
        label='Type de groupe',
        choices=PassageEtudiant.TYPE_GROUPE_CHOICES,
        widget=forms.RadioSelect(),
        initial='monome',
    )


class ImportGroupesForm(forms.Form):
    """Formulaire d'import d'une liste d'étudiants/groupes depuis un fichier."""
    fichier = forms.FileField(
        label='Fichier (CSV, XLSX, PDF, TXT, image)',
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': '.csv,.xlsx,.pdf,.txt,.png,.jpg,.jpeg,.webp,.gif',
        }),
        help_text='Colonnes attendues : nom, prenom (et optionnellement : groupe)',
    )
    heure_debut = forms.DateTimeField(
        label='Heure du 1er passage',
        widget=forms.DateTimeInput(
            attrs={'class': 'form-input', 'type': 'datetime-local'},
            format='%Y-%m-%dT%H:%M',
        ),
        input_formats=['%Y-%m-%dT%H:%M'],
    )
    pause_minutes = forms.IntegerField(
        label='Pause entre créneaux (min)',
        min_value=0, initial=5,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'style': 'width:80px'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.utils import timezone
        self.fields['heure_debut'].initial = timezone.now().strftime('%Y-%m-%dT%H:%M')
