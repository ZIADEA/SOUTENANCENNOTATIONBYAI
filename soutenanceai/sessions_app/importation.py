"""
Parsing et matching de listes d'étudiants depuis CSV, XLSX, PDF, TXT ou image.

Flux :
  fichier → parse_fichier() → list[dict{nom, prenom, groupe}]
           → matcher_groupes() → list[GroupeImport]
"""

from __future__ import annotations

import csv
import io
import json
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# Normalisation des noms
# ──────────────────────────────────────────────────────────────────────────────

def normaliser(s: str) -> str:
    """Minuscules + suppression des accents + strip + colle les chiffres aux lettres.

    Exemple : "Etudiant 1" → "etudiant1", "DUPONT Alice" → "dupont alice"
    Cela permet de matcher "Etudiant 1" avec "Etudiant1".
    """
    import re
    if not s:
        return ''
    s = s.lower().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    # Supprimer les espaces entre une lettre et un chiffre (et inversement)
    # "etudiant 1" → "etudiant1", "td 2b" → "td2b"
    s = re.sub(r'([a-z])\s+(\d)', r'\1\2', s)
    s = re.sub(r'(\d)\s+([a-z])', r'\1\2', s)
    return s


# ──────────────────────────────────────────────────────────────────────────────
# Détection automatique des colonnes
# ──────────────────────────────────────────────────────────────────────────────

_NOM_ALIAS     = ['nom', 'name', 'last_name', 'lastname', 'family_name',
                  'surname', 'nom_etudiant', 'nometudiant']
_PRENOM_ALIAS  = ['prenom', 'prenom', 'first_name', 'firstname',
                  'given_name', 'prenom_etudiant', 'prenomd']
_GROUPE_ALIAS  = ['groupe', 'group', 'equipe', 'team', 'groupe_num',
                  'group_id', 'td', 'tp', 'numero_groupe', 'groupetd',
                  'groupe_td', 'num_groupe']


def _detecter_colonnes(headers: list[str]) -> dict:
    """Retourne {'nom': col_reelle, 'prenom': col_reelle, 'groupe': col_reelle}."""
    norm_map = {normaliser(h): h for h in headers if h}
    result: dict[str, str] = {}
    for key, aliases in [('nom', _NOM_ALIAS), ('prenom', _PRENOM_ALIAS),
                          ('groupe', _GROUPE_ALIAS)]:
        for alias in aliases:
            if alias in norm_map:
                result[key] = norm_map[alias]
                break
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Parseurs
# ──────────────────────────────────────────────────────────────────────────────

def _lire_csv_txt(content: bytes) -> list[dict]:
    """Parse un fichier CSV ou TXT (délimiteur auto-détecté)."""
    for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            texte = content.decode(enc)
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        raise ValueError("Encodage non reconnu.")

    # Détection du délimiteur
    sample = texte[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel  # fallback virgule

    reader = csv.DictReader(io.StringIO(texte), dialect=dialect)
    rows = list(reader)
    if not rows:
        return []
    return rows


def _lire_xlsx(content: bytes) -> list[dict]:
    """Parse un fichier XLSX (première feuille)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.values)
    wb.close()
    if not rows:
        return []
    # Première ligne = en-têtes
    headers = [str(h).strip() if h is not None else f'col{i}'
               for i, h in enumerate(rows[0])]
    result = []
    for row in rows[1:]:
        if not any(v is not None for v in row):
            continue
        d = {headers[i]: (str(v).strip() if v is not None else '')
             for i, v in enumerate(row) if i < len(headers)}
        result.append(d)
    return result


def _lire_pdf(content: bytes) -> list[dict]:
    """Extrait les tableaux d'un PDF texte via pdfplumber."""
    import pdfplumber
    rows: list[list] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if table:
                    rows.extend(table)
    if not rows:
        raise ValueError(
            "Aucun tableau trouvé dans le PDF. "
            "Si c'est un PDF scanné, utilisez le format Image."
        )
    headers = [str(h).strip() if h else f'col{i}' for i, h in enumerate(rows[0])]
    result = []
    for row in rows[1:]:
        if not any(row):
            continue
        d = {headers[i]: (str(v).strip() if v else '')
             for i, v in enumerate(row) if i < len(headers)}
        result.append(d)
    return result


def _lire_image_claude(content: bytes, media_type: str, api_key: str = '') -> list[dict]:
    """OCR via Claude Vision → retourne une liste de dicts {nom, prenom, groupe}."""
    import base64
    import anthropic
    from django.conf import settings as django_settings

    b64 = base64.standard_b64encode(content).decode('utf-8')

    # Priorité : clé passée en paramètre → sinon settings Django → sinon variable d'env
    key = api_key or getattr(django_settings, 'ANTHROPIC_API_KEY', '') or ''
    if not key:
        raise ValueError(
            "Clé API Anthropic introuvable. "
            "Vérifiez ANTHROPIC_API_KEY dans le fichier .env."
        )
    client = anthropic.Anthropic(api_key=key)

    prompt = (
        "Tu es un assistant spécialisé dans la lecture de listes d'étudiants "
        "(manuscrites, imprimées ou sous forme de tableau).\n\n"
        "Extrais TOUS les étudiants visibles dans cette image.\n"
        "Retourne UNIQUEMENT un objet JSON valide, sans texte autour :\n"
        '{"etudiants": [{"nom": "...", "prenom": "...", "groupe": "..."}, ...]}\n\n'
        "Règles importantes :\n"
        "1. Si le document a une structure par colonnes (ex: Groupe 1 | Groupe 2), "
        "   chaque colonne est un groupe différent. Utilise le label de la colonne "
        "   comme valeur de 'groupe' (ex: 'Groupe 1', 'G1', 'TD2'...).\n"
        "2. Si les étudiants sont listés sous un titre de groupe (ex: '-- Groupe A --' "
        "   suivi de noms), tous les noms en dessous appartiennent à ce groupe.\n"
        "3. Si aucun groupe n'est mentionné, mets \"\" pour groupe.\n"
        "4. Si le nom complet est en un seul bloc (ex: 'DUPONT Alice'), "
        "   le prénom est généralement en dernier ou en minuscules/majuscule initiale, "
        "   et le nom en MAJUSCULES. Sépare-les du mieux possible.\n"
        "5. Ignore les titres de page, sous-titres, numéros de ligne et "
        "   toute ligne qui n'est pas un étudiant.\n"
        "6. Respecte l'orthographe exacte des noms tels qu'ils apparaissent "
        "   (majuscules, accents...).\n"
        "7. Si un groupe n'a pas d'étiquette (liste simple), mets \"\" pour groupe.\n\n"
        "Retourne UNIQUEMENT le JSON. Aucun commentaire, aucune explication."
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )

    texte = response.content[0].text.strip()
    # Nettoyer les balises markdown si présentes
    if texte.startswith('```'):
        parts = texte.split('```')
        texte = parts[1].lstrip('json').strip() if len(parts) > 1 else texte

    try:
        data = json.loads(texte)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Claude Vision n'a pas renvoyé un JSON valide : {exc}\n"
            f"Réponse brute : {texte[:200]}"
        ) from exc

    return data.get('etudiants', [])


# ──────────────────────────────────────────────────────────────────────────────
# Normalisation des lignes brutes → {nom, prenom, groupe}
# ──────────────────────────────────────────────────────────────────────────────

def _normaliser_lignes(rows: list[dict]) -> list[dict]:
    """
    Détecte les colonnes nom/prenom/groupe et retourne des dicts standardisés.
    Lève ValueError si les colonnes nom/prénom ne sont pas trouvées.
    """
    if not rows:
        return []

    headers = list(rows[0].keys())
    cols = _detecter_colonnes(headers)

    # Fallback : si une seule colonne, tenter de la splitter
    if 'nom' not in cols and 'prenom' not in cols and len(headers) >= 1:
        # Essayer de trouver une colonne "nom_complet" ou similaire
        for h in headers:
            if normaliser(h) in ('nom_complet', 'etudiant', 'eleve', 'student', 'fullname',
                                  'nom prenom', 'prenom nom'):
                cols['_fullname'] = h
                break

    if 'nom' not in cols and 'prenom' not in cols and '_fullname' not in cols:
        # Dernière tentative : prendre les deux premières colonnes non vides
        non_vides = [h for h in headers if h.strip()]
        if len(non_vides) >= 2:
            cols['nom']    = non_vides[0]
            cols['prenom'] = non_vides[1]
        elif len(non_vides) == 1:
            cols['_fullname'] = non_vides[0]
        else:
            raise ValueError(
                f"Colonnes nom/prénom introuvables. "
                f"En-têtes détectés : {headers}. "
                "Attendu : nom, prenom (ou last_name, first_name...)"
            )

    result = []
    for row in rows:
        if '_fullname' in cols:
            val = (row.get(cols['_fullname']) or '').strip()
            parts = val.split(None, 1)
            nom    = parts[0] if parts else ''
            prenom = parts[1] if len(parts) > 1 else ''
        else:
            nom    = (row.get(cols.get('nom', ''), '') or '').strip()
            prenom = (row.get(cols.get('prenom', ''), '') or '').strip()

        groupe = (row.get(cols.get('groupe', ''), '') or '').strip()

        if not nom and not prenom:
            continue
        result.append({'nom': nom, 'prenom': prenom, 'groupe': groupe})

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Point d'entrée principal du parseur
# ──────────────────────────────────────────────────────────────────────────────

def parse_fichier(
    content: bytes,
    filename: str,
    api_key: str = '',
) -> list[dict]:
    """
    Parse un fichier et retourne une liste de dicts {nom, prenom, groupe}.
    Accepte CSV, TXT, XLSX, PDF, PNG, JPG, JPEG, WEBP, GIF.
    """
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    IMG_TYPES = {
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'webp': 'image/webp',
        'gif': 'image/gif',
    }

    if ext in ('csv', 'txt'):
        rows = _lire_csv_txt(content)
    elif ext == 'xlsx':
        rows = _lire_xlsx(content)
    elif ext == 'pdf':
        # Essayer texte d'abord, puis OCR si ça échoue
        try:
            rows = _lire_pdf(content)
            # Vérifier qu'on a bien trouvé quelque chose d'utile
            if not rows:
                raise ValueError("PDF vide")
        except ValueError:
            if api_key:
                return _lire_image_claude(content, 'application/pdf', api_key)
            raise
    elif ext in IMG_TYPES:
        if not api_key:
            raise ValueError("Clé API Anthropic requise pour l'analyse d'image.")
        return _lire_image_claude(content, IMG_TYPES[ext], api_key)
    else:
        raise ValueError(
            f"Format '{ext}' non supporté. "
            "Formats acceptés : CSV, XLSX, PDF, TXT, PNG, JPG, JPEG, WEBP, GIF."
        )

    return _normaliser_lignes(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Matching étudiant
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MatchEtudiant:
    """Résultat du matching d'un étudiant importé."""
    nom_import: str
    prenom_import: str
    user: object = None          # instance User Django ou None
    statut: str = 'non_trouve'   # 'exact' | 'fuzzy' | 'non_trouve'
    score: float = 0.0


def _variantes_cible(nom: str, prenom: str) -> list[str]:
    """
    Génère toutes les formes normalisées d'un nom importé pour le matching.
    Ex : "Etudiant 1" → ["etudiant1", "1etudiant", "etudiant1 etudiant1", ...]
    """
    n = normaliser(nom)
    p = normaliser(prenom)
    cibles = set()

    # Combinaisons nom+prenom dans les deux ordres
    cibles.add(f"{n} {p}".strip())
    cibles.add(f"{p} {n}".strip())
    cibles.add(f"{n}{p}")   # sans espace (colle les deux parties)
    cibles.add(f"{p}{n}")

    # Cas où prénom=nom (comptes test style "ETUDIANT1 ETUDIANT1")
    # → on génère aussi "n n" et "p p"
    cibles.add(f"{n} {n}")
    cibles.add(f"{p} {p}")

    # Concaténation sans espace doublée
    np = f"{n}{p}"
    cibles.add(f"{np} {np}")

    return [c for c in cibles if c]


def _matcher_un(nom: str, prenom: str, inscrits) -> MatchEtudiant:
    """Tente de faire correspondre nom+prenom à un inscrit."""
    cibles = _variantes_cible(nom, prenom)

    # 1. Correspondance exacte (toutes variantes)
    for e in inscrits:
        refs = [
            normaliser(f"{e.last_name} {e.first_name}"),
            normaliser(f"{e.first_name} {e.last_name}"),
            normaliser(e.last_name),
            normaliser(e.first_name),
        ]
        if any(r == c for r in refs for c in cibles):
            return MatchEtudiant(nom, prenom, user=e, statut='exact', score=1.0)

    # 2. Correspondance fuzzy — tester toutes les variantes, garder le meilleur score
    best_score = 0.0
    best_user  = None
    for e in inscrits:
        refs_e = [
            normaliser(f"{e.last_name} {e.first_name}"),
            normaliser(f"{e.first_name} {e.last_name}"),
        ]
        for cible in cibles:
            for ref in refs_e:
                score = SequenceMatcher(None, cible, ref).ratio()
                if score > best_score:
                    best_score = score
                    best_user  = e

    # Seuil abaissé à 0.72 pour tolérer les variations d'espacement/casse
    if best_score >= 0.72:
        return MatchEtudiant(nom, prenom, user=best_user, statut='fuzzy', score=round(best_score, 2))

    return MatchEtudiant(nom, prenom, user=None, statut='non_trouve', score=0.0)


# ──────────────────────────────────────────────────────────────────────────────
# Groupage et validation
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class GroupeImport:
    """Un groupe prêt à devenir un PassageEtudiant."""
    label: str                           # ex: "G1", "Solo", "Alice+Bob"
    membres: list[MatchEtudiant] = field(default_factory=list)
    valide: bool = False                 # True si tous les membres sont trouvés
    raison_invalide: str = ''
    type_groupe: str = 'monome'          # 'monome' | 'binome' | 'groupe'


def matcher_groupes(lignes: list[dict], inscrits) -> list[GroupeImport]:
    """
    Prend la liste normalisée {nom, prenom, groupe} et les inscrits Django.
    Retourne une liste de GroupeImport avec statut de matching.
    """
    inscrits_list = list(inscrits)

    # Grouper par label de groupe (vide = passage individuel)
    groupes_raw: dict[str, list[dict]] = {}
    compteur_solo = 0
    for ligne in lignes:
        key = ligne['groupe'] or None
        if key is None:
            compteur_solo += 1
            key = f'__solo_{compteur_solo}'
        if key not in groupes_raw:
            groupes_raw[key] = []
        groupes_raw[key].append(ligne)

    resultats: list[GroupeImport] = []
    for key, membres_raw in groupes_raw.items():
        label = key if not key.startswith('__solo_') else 'Individuel'
        matches = [_matcher_un(m['nom'], m['prenom'], inscrits_list) for m in membres_raw]

        n = len(matches)
        type_groupe = 'monome' if n == 1 else ('binome' if n == 2 else 'groupe')

        # Groupe valide seulement si TOUS les membres sont trouvés
        non_trouves = [m for m in matches if m.statut == 'non_trouve']
        if non_trouves:
            noms_manquants = ', '.join(
                f"{m.prenom_import} {m.nom_import}" for m in non_trouves
            )
            raison = f"Membre(s) non inscrit(s) dans l'application : {noms_manquants}"
            groupe = GroupeImport(
                label=label, membres=matches,
                valide=False, raison_invalide=raison, type_groupe=type_groupe,
            )
        else:
            groupe = GroupeImport(
                label=label, membres=matches,
                valide=True, type_groupe=type_groupe,
            )

        resultats.append(groupe)

    return resultats


def groupes_to_json(groupes: list[GroupeImport]) -> list[dict]:
    """Sérialise les groupes pour le stockage en session Django."""
    return [
        {
            'label': g.label,
            'type_groupe': g.type_groupe,
            'valide': g.valide,
            'raison_invalide': g.raison_invalide,
            'membres': [
                {
                    'nom': m.nom_import,
                    'prenom': m.prenom_import,
                    'user_id': m.user.id if m.user else None,
                    'statut': m.statut,
                    'score': m.score,
                    'display': m.user.get_full_name() if m.user else f"{m.prenom_import} {m.nom_import}",
                }
                for m in g.membres
            ],
        }
        for g in groupes
    ]
