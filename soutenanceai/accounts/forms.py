"""Formulaires d'authentification & de gestion de comptes."""
from django import forms
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm

from .models import User


class ProfilEtudiantForm(forms.ModelForm):
    """Permet à l'étudiant de mettre à jour sa photo de profil (reconnaissance faciale)."""
    class Meta:
        model = User
        fields = ['photo_profil']
        widgets = {
            'photo_profil': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'image/*',
            }),
        }
        labels = {
            'photo_profil': 'Photo de profil',
        }
        help_texts = {
            'photo_profil': 'Photo nette de face (JPG/PNG). Utilisée pour vous identifier pendant la soutenance.',
        }


class LoginForm(forms.Form):
    username = forms.CharField(
        label='Identifiant',
        widget=forms.TextInput(attrs={'class': 'form-input', 'autofocus': True}),
    )
    password = forms.CharField(
        label='Mot de passe',
        widget=forms.PasswordInput(attrs={'class': 'form-input'}),
    )


class CreerCompteForm(UserCreationForm):
    """Formulaire générique de création (le rôle est forcé par la vue)."""

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'ex: etudiant@universite.fr'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        for fname in ('password1', 'password2'):
            self.fields[fname].widget.attrs.update({'class': 'form-input'})


class InscriptionProfesseurForm(UserCreationForm):
    """Formulaire d'auto-inscription pour les professeurs."""

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'username', 'sexe')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'ex: Pierre'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'ex: Martin'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'votre@universite.fr'}),
            'username': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'ex: pierre.martin'}),
            'sexe': forms.RadioSelect(attrs={'class': 'radio-inline'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['email'].required = True
        self.fields['sexe'].required = True
        self.fields['sexe'].label = 'Vous êtes'
        for fname in ('password1', 'password2'):
            self.fields[fname].widget.attrs.update({'class': 'form-input'})


class CreerProfesseurForm(UserCreationForm):
    """Formulaire de création d'un professeur par le superadmin (inclut le sexe)."""

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'sexe')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'sexe': forms.RadioSelect(attrs={'class': 'radio-inline'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['sexe'].required = True
        self.fields['sexe'].label = 'Sexe du professeur'
        for fname in ('password1', 'password2'):
            self.fields[fname].widget.attrs.update({'class': 'form-input'})


class ImportCSVForm(forms.Form):
    """Formulaire d'import en masse d'étudiants via CSV."""
    fichier_csv = forms.FileField(
        label='Fichier CSV',
        help_text='Colonnes requises : prenom, nom, email  —  UTF-8 ou UTF-8 BOM (Excel)',
        widget=forms.FileInput(attrs={'class': 'form-input', 'accept': '.csv,.txt'}),
    )


class ChangePasswordForm(PasswordChangeForm):
    """PasswordChangeForm avec classe CSS form-input sur tous les champs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-input'})
