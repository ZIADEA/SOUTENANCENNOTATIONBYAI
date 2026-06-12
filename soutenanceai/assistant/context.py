"""Construction du contexte de données par rôle pour l'assistant IA.

Chaque utilisateur ne reçoit dans son contexte QUE ses propres données :
- visiteur anonyme : aucune donnée ;
- étudiant : ses classes, ses passages, ses notes ;
- professeur : ses classes, soutenances (paramètres), passages et notes de
  SES étudiants ;
- superadmin : statistiques globales.
"""
from __future__ import annotations

# Bornes pour garder un contexte compact (et un coût d'appel maîtrisé)
MAX_CLASSES = 6
MAX_SESSIONS = 8
MAX_PASSAGES = 40


def _fmt_notes_passage(passage, etudiant) -> str:
    """Notes d'un étudiant sur un passage : 'critère note/20' compactés."""
    from notation.models import NoteIA
    from notation.pipeline import calculer_note_globale

    notes = (
        NoteIA.objects.filter(passage=passage, etudiant=etudiant)
        .select_related('critere').order_by('critere__ordre')
    )
    if not notes.exists():
        return ''
    detail = ' ; '.join(f'{n.critere.nom} {n.note_finale:g}/20' for n in notes)
    globale = calculer_note_globale(passage, etudiant)
    globale_txt = f' — note globale {globale:.2f}/20' if globale is not None else ''
    return f' Notes : {detail}{globale_txt}.'


def _fmt_session(session, avec_code: bool = False) -> list[str]:
    """Paramètres d'une soutenance, sur quelques lignes compactes."""
    lignes = [
        f'  Soutenance « {session.titre} » : langue {session.get_langue_display()}, '
        f'{session.duree_presentation} min de présentation + {session.duree_questions} min '
        f'de questions ({session.nb_questions_max} questions IA max).',
        f'    Jury IA : questionnement « {session.get_style_questionnement_display()} », '
        f'notation « {session.get_style_notation_display()} », '
        f'anti-stress {"actif" if session.ajustement_auto_stress else "inactif"}.',
    ]
    criteres = ', '.join(
        f'{c.nom} (coef {c.coefficient:g})' for c in session.criteres.all()
    )
    if criteres:
        lignes.append(f'    Critères : {criteres}.')
    exigences = []
    if session.rapport_obligatoire:
        exigences.append(f'rapport PDF obligatoire (coef {session.coefficient_rapport:g})')
    if session.demo_video_requise:
        exigences.append(f'démo vidéo requise (coef {session.coefficient_demo_video:g})')
    if session.depot_github_requis:
        exigences.append(f'dépôt GitHub requis (coef {session.coefficient_github:g})')
    if exigences:
        lignes.append(f'    Exigences : {", ".join(exigences)}.')
    if avec_code:
        lignes.append(f'    Code d\'accès de la soutenance : {session.code_acces}.')
    return lignes


def contexte_professeur(user) -> str:
    lignes = [f'Tu parles au PROFESSEUR {user.get_full_name() or user.username}.', '']
    classes = user.classes_creees.prefetch_related('sessions__criteres', 'inscrits')[:MAX_CLASSES]
    if not classes:
        lignes.append("Ce professeur n'a pas encore créé de classe.")
    for classe in classes:
        lignes.append(
            f'Classe « {classe.nom} » — code d\'accès {classe.code_acces}, '
            f'{classe.inscrits.count()} étudiant(s) inscrit(s).'
        )
        for session in classe.sessions.all()[:MAX_SESSIONS]:
            lignes.extend(_fmt_session(session, avec_code=True))
            passages = session.passages.prefetch_related('etudiants')[:MAX_PASSAGES]
            for p in passages:
                heure = p.heure_prevue.strftime('%d/%m %H:%M') if p.heure_prevue else '—'
                ligne = (
                    f'    Passage #{p.ordre_passage} ({p.get_type_groupe_display()}) : '
                    f'{p.noms_etudiants or "(aucun étudiant)"} — {heure} — statut {p.get_statut_display()}.'
                )
                if p.statut == 'note':
                    for etu in p.etudiants.all():
                        notes_txt = _fmt_notes_passage(p, etu)
                        if notes_txt:
                            ligne += f' [{etu.get_full_name() or etu.username}]{notes_txt}'
                lignes.append(ligne)
        lignes.append('')
    return '\n'.join(lignes)


def contexte_etudiant(user) -> str:
    lignes = [f'Tu parles à l\'ÉTUDIANT {user.get_full_name() or user.username}.', '']
    classes = user.classes_inscrites.select_related('professeur')[:MAX_CLASSES]
    if not classes:
        lignes.append("Cet étudiant n'a encore rejoint aucune classe.")
    for classe in classes:
        prof = classe.professeur.get_full_name() or classe.professeur.username
        lignes.append(f'Classe « {classe.nom} » (professeur : {prof}).')
    lignes.append('')
    passages = (
        user.passages.select_related('session')
        .prefetch_related('etudiants').order_by('heure_prevue')[:MAX_PASSAGES]
    )
    if not passages:
        lignes.append('Aucun passage planifié pour le moment.')
    for p in passages:
        heure = p.heure_prevue.strftime('%d/%m/%Y %H:%M') if p.heure_prevue else 'non planifiée'
        lignes.append(
            f'Passage pour « {p.session.titre} » : heure prévue {heure}, '
            f'statut {p.get_statut_display()}.'
        )
        if p.statut == 'note':
            notes_txt = _fmt_notes_passage(p, user)
            if notes_txt:
                lignes.append(f' {notes_txt.strip()}')
    return '\n'.join(lignes)


def contexte_superadmin(user) -> str:
    from accounts.models import User
    from sessions_app.models import Classe, PassageEtudiant, Session

    return '\n'.join([
        f'Tu parles au SUPERADMIN {user.get_full_name() or user.username}.',
        '',
        'Statistiques globales de la plateforme :',
        f'- Professeurs : {User.objects.filter(role=User.ROLE_PROFESSEUR).count()}',
        f'- Étudiants : {User.objects.filter(role=User.ROLE_ETUDIANT).count()}',
        f'- Classes : {Classe.objects.count()}',
        f'- Soutenances : {Session.objects.count()}',
        f'- Passages : {PassageEtudiant.objects.count()} '
        f'(dont {PassageEtudiant.objects.filter(statut="note").count()} notés)',
    ])


def construire_contexte(user) -> str:
    """Retourne la section « Données de l'utilisateur » selon le rôle."""
    if not user.is_authenticated:
        return (
            'Tu parles à un VISITEUR non connecté (page publique). '
            'Tu ne disposes d\'aucune donnée personnelle : réponds sur le '
            'fonctionnement général de l\'application, ses fonctionnalités, '
            'son auteur, ses technologies. Invite-le à s\'inscrire (professeur) '
            'ou à utiliser un code de classe (étudiant) si pertinent.'
        )
    if user.is_superadmin:
        return contexte_superadmin(user)
    if user.is_professeur:
        return contexte_professeur(user)
    return contexte_etudiant(user)
