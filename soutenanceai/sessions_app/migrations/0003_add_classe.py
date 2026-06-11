"""Migration : ajout du modèle Classe + FK Session.classe + migration des données existantes."""
import secrets
import string

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def _generer_code(used):
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(secrets.choice(chars) for _ in range(8))
        if code not in used:
            return code


def migrer_sessions_vers_classes(apps, schema_editor):
    """Crée une Classe par professeur et rattache ses Sessions existantes."""
    Session = apps.get_model('sessions_app', 'Session')
    Classe = apps.get_model('sessions_app', 'Classe')

    used_codes = set()
    prof_ids = Session.objects.values_list('professeur_id', flat=True).distinct()

    for prof_id in prof_ids:
        sessions = Session.objects.filter(professeur_id=prof_id)
        if not sessions.exists():
            continue

        # Générer un code unique
        code = _generer_code(used_codes)
        used_codes.add(code)

        classe = Classe.objects.create(
            professeur_id=prof_id,
            nom='Ma première classe',
            code_acces=code,
        )

        # Rattacher les sessions + copier les inscrits
        for s in sessions:
            s.classe = classe
            s.save(update_fields=['classe'])
            for inscrit in s.inscrits.all():
                classe.inscrits.add(inscrit)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('sessions_app', '0002_add_code_acces_and_inscrits'),
    ]

    operations = [
        # 1. Créer la table Classe
        migrations.CreateModel(
            name='Classe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nom', models.CharField(max_length=255, verbose_name='Nom de la classe')),
                ('description', models.TextField(blank=True)),
                ('code_acces', models.CharField(
                    blank=True, max_length=10, unique=True,
                    help_text="Partagez ce code aux étudiants pour rejoindre la classe",
                    verbose_name="Code d'accès",
                )),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
                ('date_modification', models.DateTimeField(auto_now=True)),
                ('professeur', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='classes_creees',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('inscrits', models.ManyToManyField(
                    blank=True,
                    related_name='classes_inscrites',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Étudiants inscrits',
                )),
            ],
            options={
                'verbose_name': 'Classe',
                'verbose_name_plural': 'Classes',
                'ordering': ['-date_creation'],
            },
        ),

        # 2. Ajouter FK Session.classe (nullable pour l'instant)
        migrations.AddField(
            model_name='session',
            name='classe',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='sessions',
                to='sessions_app.classe',
                verbose_name='Classe parente',
            ),
        ),

        # 3. Migrer les données existantes
        migrations.RunPython(migrer_sessions_vers_classes, migrations.RunPython.noop),
    ]
