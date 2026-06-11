"""Validation empirique preliminaire des styles de notation.

Protocole : transcription FIXE (qualite moyenne, hesitations moderees),
questionnement fixe ('mentor'), ajustement anti-stress DESACTIVE.
On fait varier le style de notation sur les 7 profils, 3 repetitions chacun,
et on mesure la moyenne ponderee des notes par critere.

Usage : .venv\\Scripts\\python.exe _validation_styles.py
Sortie : _validation_styles_resultats.json + tableau console
"""
import json
import os
import statistics
import sys
import time

import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'soutenanceai.settings')
django.setup()

from notation.agents import AgentNotation, ContexteNotation, NOTATION_PROMPTS

TRANSCRIPTION = """Bonjour, je vais vous presenter mon projet de fin de module
qui porte sur la prediction de la consommation energetique d'un batiment
universitaire a partir de donnees de capteurs. Euh, donc le contexte c'est que
le batiment consomme beaucoup et que la facture augmente chaque annee. Notre
objectif etait de construire un modele capable de predire la consommation a
24 heures, pour permettre euh d'optimiser le chauffage. Nous avons collecte
six mois de donnees : temperature interieure et exterieure, occupation des
salles, et consommation electrique au pas de quinze minutes. Apres un
nettoyage des valeurs aberrantes, nous avons compare trois approches : une
regression lineaire comme reference, une foret aleatoire, et un reseau LSTM.
La foret aleatoire obtient une erreur moyenne absolue de 4,2 kilowattheures,
contre 5,8 pour la regression et 4,5 pour le LSTM, qui demandait pourtant
beaucoup plus de temps d'entrainement. Donc euh nous avons retenu la foret
aleatoire pour le deploiement. Les limites de notre travail : six mois de
donnees seulement, donc pas de saisonnalite complete, et l'occupation des
salles est estimee a partir des emplois du temps, pas mesuree. En perspective,
nous voudrions integrer les donnees meteo de prevision et tester sur un
deuxieme batiment. Merci de votre attention."""

SLIDES = """SLIDE 1: Prediction de consommation energetique - contexte
SLIDE 2: Donnees : 6 mois, capteurs 15 min, 4 variables
SLIDE 3: Methodologie : regression / random forest / LSTM
SLIDE 4: Resultats : MAE 4,2 kWh (RF) vs 5,8 (reg.) vs 4,5 (LSTM)
SLIDE 5: Limites et perspectives"""

CRITERES = [
    {'nom': "Clarte de l'expression", 'coefficient': 1.0, 'description': ''},
    {'nom': 'Structure de la presentation', 'coefficient': 2.0, 'description': ''},
    {'nom': 'Maitrise du sujet', 'coefficient': 3.0, 'description': ''},
]

STYLES = ['genereux', 'indulgent', 'juste', 'avare', 'severe', 'terroriste', 'comptable']
REPETITIONS = 3


def moyenne_ponderee(notes: list[dict]) -> float | None:
    total, poids = 0.0, 0.0
    for n in notes:
        critere = next((c for c in CRITERES if c['nom'] == n.get('critere')), None)
        coef = critere['coefficient'] if critere else 1.0
        try:
            total += float(n['note']) * coef
            poids += coef
        except (KeyError, TypeError, ValueError):
            continue
    return round(total / poids, 2) if poids else None


def main():
    resultats: dict[str, list[float]] = {s: [] for s in STYLES}
    total_calls = len(STYLES) * REPETITIONS
    call = 0

    for style in STYLES:
        agent = AgentNotation(style_questionnement='mentor', style_notation=style)
        for rep in range(REPETITIONS):
            call += 1
            ctx = ContexteNotation(
                transcription=TRANSCRIPTION,
                contenu_slides=SLIDES,
                contenu_rapport='(rapport non fourni)',
                consignes_prof='',
                criteres=CRITERES,
                langue='fr',
                nom_etudiant='Etudiant Test',
                duree_prevue_min=15,
                duree_reelle_min=13.5,
                donnees_posture={'pourcentage_contact_visuel': 62.0,
                                 'inclinaison_tete_moyenne_deg': 4.1,
                                 'nb_mesures': 180},
                style_questionnement='mentor',
                style_notation=style,
                type_groupe='monome',
                membres_groupe=['Etudiant Test'],
                questions_reponses=[],
            )
            t0 = time.time()
            data = agent.noter(ctx)
            dt = time.time() - t0
            note = moyenne_ponderee(data.get('notes', []))
            print(f'[{call}/{total_calls}] {style:11s} rep{rep + 1} -> '
                  f'{note if note is not None else "ERREUR"} ({dt:.1f}s)', flush=True)
            if note is not None:
                resultats[style].append(note)
            time.sleep(1)

    print('\n=== SYNTHESE (moyenne ponderee /20, n=3) ===')
    synthese = {}
    for style in STYLES:
        vals = resultats[style]
        if vals:
            m = round(statistics.mean(vals), 2)
            e = round(statistics.stdev(vals), 2) if len(vals) > 1 else 0.0
            synthese[style] = {'moyenne': m, 'ecart_type': e, 'notes': vals}
            print(f'  {style:11s} : {m:5.2f}  (sigma={e:.2f})  {vals}')
        else:
            synthese[style] = {'moyenne': None, 'notes': []}

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       '_validation_styles_resultats.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(synthese, f, indent=2, ensure_ascii=False)
    print(f'\nResultats -> {out}')


if __name__ == '__main__':
    main()
