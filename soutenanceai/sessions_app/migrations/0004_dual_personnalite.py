"""Migration 0004 : double axe personnalité IA (questionnement + notation).

- Ajoute style_questionnement, style_notation, ajustement_auto_stress
- Rend personnalite_ia nullable (rétrocompatibilité)
- RunPython : mappe les anciennes valeurs vers les nouveaux champs
"""
from django.db import migrations, models


def migrer_personnalites(apps, schema_editor):
    """Mappe l'ancien champ unique vers les deux nouveaux axes."""
    Session = apps.get_model('sessions_app', 'Session')

    mapping_q = {
        'neutre':    'impassible',
        'severe':    'contradicteur',
        'empathique': 'mentor',
        'gentil':    'pedagogue',
    }
    mapping_n = {
        'neutre':    'juste',
        'severe':    'severe',
        'empathique': 'indulgent',
        'gentil':    'genereux',
    }

    for s in Session.objects.all():
        old = s.personnalite_ia or 'neutre'
        s.style_questionnement = mapping_q.get(old, 'mentor')
        s.style_notation = mapping_n.get(old, 'juste')
        s.save(update_fields=['style_questionnement', 'style_notation'])


class Migration(migrations.Migration):

    dependencies = [
        ('sessions_app', '0003_add_classe'),
    ]

    operations = [
        # 1. Rendre personnalite_ia nullable
        migrations.AlterField(
            model_name='session',
            name='personnalite_ia',
            field=models.CharField(
                blank=True, null=True, max_length=20,
                choices=[
                    ('neutre', 'Neutre — évaluation objective'),
                    ('severe', 'Sévère — exigeant'),
                    ('empathique', 'Empathique — bienveillant'),
                    ('gentil', 'Gentil — encourageant'),
                ],
            ),
        ),
        # 2. Ajouter les nouveaux champs
        migrations.AddField(
            model_name='session',
            name='style_questionnement',
            field=models.CharField(
                max_length=20, default='mentor',
                verbose_name='Style de questionnement',
                choices=[
                    ('mentor',          'Le Mentor — Questions ouvertes et guidantes'),
                    ('pedagogue',       'Le Pédagogue — Explique et enseigne'),
                    ('perfectionniste', 'Le Perfectionniste — Traque les imprécisions'),
                    ('contradicteur',   'Le Contradicteur — Contre-argumente et teste'),
                    ('stratege',        'Le Stratège — Questions précises et ciblées'),
                    ('provocateur',     'Le Provocateur — Pousse dans les retranchements'),
                    ('impassible',      "L'Impassible — Neutre, aucune réaction"),
                ],
            ),
        ),
        migrations.AddField(
            model_name='session',
            name='style_notation',
            field=models.CharField(
                max_length=20, default='juste',
                verbose_name='Style de notation',
                choices=[
                    ('genereux',   "Le Généreux — ≈ 15-18/20, valorise l'effort"),
                    ('indulgent',  "L'Indulgent — ≈ 13-16/20, bénéfice du doute"),
                    ('juste',      'Le Juste — ≈ 12-15/20, grille stricte et équitable'),
                    ('avare',      "L'Avare de points — ≈ 10-13/20"),
                    ('severe',     'Le Sévère — ≈ 8-12/20, punit les lacunes'),
                    ('terroriste', 'Le Terroriste — ≤ 10/20, note comme sanction'),
                    ('comptable',  'Le Comptable — Calcule à la décimale'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='session',
            name='ajustement_auto_stress',
            field=models.BooleanField(
                default=True,
                verbose_name='Ajustement automatique si stress détecté',
                help_text="Si actif, bascule vers Mentor/Indulgent quand l'étudiant est stressé",
            ),
        ),
        # 3. Mapper les anciennes valeurs
        migrations.RunPython(migrer_personnalites, migrations.RunPython.noop),
    ]
