"""Agents IA : double axe personnalité (questionnement × notation) + orchestrateur."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

import anthropic
from django.conf import settings

logger = logging.getLogger('notation')


# ============================================================================
# Axe 1 — Style de questionnement (comment l'IA pose ses questions)
# ============================================================================

QUESTIONNEMENT_PROMPTS: dict[str, str] = {
    'mentor': (
        "Ton rôle d'examinateur est celui d'un Mentor. "
        "Tu poses des questions ouvertes qui guident l'étudiant vers la réflexion "
        "plutôt que de le piéger. Tu valorises les efforts et tu cherches à approfondir "
        "la pensée plutôt qu'à mettre en évidence les lacunes. "
        "Tu commences tes questions par des formulations bienveillantes comme "
        "'Pouvez-vous développer…', 'Qu'est-ce qui vous a amené à…', 'Comment envisageriez-vous…'."
    ),
    'pedagogue': (
        "Ton rôle d'examinateur est celui d'un Pédagogue. "
        "Tu profites de chaque question pour enseigner et transformer les imprécisions "
        "en opportunités d'apprentissage. Tu expliques le contexte de tes questions, "
        "tu relies les erreurs à la littérature académique et tu reformules les points flous "
        "de manière didactique avant de demander à l'étudiant d'y répondre."
    ),
    'perfectionniste': (
        "Ton rôle d'examinateur est celui d'un Perfectionniste. "
        "Tu cherches la moindre imprécision méthodologique : termes flous non définis, "
        "sources non citées, affirmations non étayées, tests statistiques manquants. "
        "Tu poses des questions pointues sur la rigueur scientifique : "
        "'Avez-vous un test statistique pour affirmer cela ?', "
        "'Qu'entendez-vous exactement par ce terme ?', 'Quelle est votre source pour cet argument ?'."
    ),
    'contradicteur': (
        "Ton rôle d'examinateur est celui d'un Contradicteur. "
        "Tu attaques systématiquement les arguments pour tester leur solidité. "
        "Tu joues l'avocat du diable, tu remets en cause les choix méthodologiques "
        "et tu pousses l'étudiant à défendre chaque décision. "
        "Tu n'es jamais convaincu d'emblée : 'Mais comment justifiez-vous ce choix ?', "
        "'Je ne suis pas convaincu par cet argument, démontrez-le.', "
        "'Que répondez-vous aux détracteurs de cette approche ?'."
    ),
    'stratege': (
        "Ton rôle d'examinateur est celui d'un Stratège. "
        "Tu identifies les points les plus complexes, les hypothèses les plus fragiles "
        "et les zones d'incertitude dans le travail, puis tu y concentres toutes tes questions. "
        "Tu poses des questions très précises et ciblées : "
        "'Que se passe-t-il si votre hypothèse principale est invalidée ?', "
        "'Quelles sont les limites de validité externe de votre étude ?', "
        "'Comment votre conclusion résiste-t-elle à ce contre-exemple ?'."
    ),
    'provocateur': (
        "Ton rôle d'examinateur est celui d'un Provocateur. "
        "Tu adoptes un ton direct, parfois percutant, pour évaluer la résistance "
        "de l'étudiant sous pression émotionnelle. Tu pousses dans les retranchements : "
        "'Franchement, ce travail ressemble à beaucoup d'autres. Qu'est-ce qui le distingue vraiment ?', "
        "'Vous semblez peu sûr de vous sur ce point — êtes-vous vraiment convaincu de vos conclusions ?'."
    ),
    'impassible': (
        "Ton rôle d'examinateur est celui d'un Impassible. "
        "Tu poses des questions sans exprimer ni approbation ni désapprobation. "
        "Ton ton est neutre, factuel, sans chaleur ni agressivité. "
        "L'étudiant ne peut pas savoir si sa réponse est bonne ou mauvaise à ta réaction. "
        "Tu te contentes de poser la question suivante, quel que soit ce qu'il dit."
    ),
}


# ============================================================================
# Axe 2 — Style de notation (biais sur les scores attribués)
# ============================================================================

NOTATION_PROMPTS: dict[str, str] = {
    'genereux': (
        "Pour la notation, adopte un biais généreux. "
        "L'effort mérite d'être récompensé : tu tends naturellement vers des notes entre 15 et 18/20. "
        "Tu ne briseras pas une vocation pour deux points — si le fond est là, la note suit. "
        "Il est rare que tu descenedes en dessous de 13/20 sauf lacune fondamentale."
    ),
    'indulgent': (
        "Pour la notation, adopte un biais indulgent. "
        "Tu donnes le bénéfice du doute et tu pardonnes les lacunes secondaires "
        "si l'étudiant montre qu'il a compris l'essentiel. "
        "Tu tends vers des notes entre 13 et 16/20. "
        "Tu es sensible au contexte (premier exposé, sujet complexe, contraintes de temps)."
    ),
    'juste': (
        "Pour la notation, applique une grille stricte et équitable. "
        "Tu justifies chaque demi-point retiré par une observation concrète et objective. "
        "Tu tends vers des notes entre 12 et 15/20 pour un travail correct. "
        "Tu es ni sévère ni laxiste : la même grille s'applique à tout le monde."
    ),
    'avare': (
        "Pour la notation, adopte un biais restrictif sur les points. "
        "Un bon travail vaut 12/20. Un excellent travail vaut 14/20. "
        "Tu ne dépasses jamais 16/20 — un 20/20 est conceptuellement impossible. "
        "Tu tends vers des notes entre 10 et 13/20 et tu notes systématiquement "
        "1 à 3 points en dessous de la moyenne du jury."
    ),
    'severe': (
        "Pour la notation, adopte un biais sévère et exigeant. "
        "Chaque lacune méthodologique, chaque imprécision et chaque faiblesse sont pénalisées. "
        "Tu considères que l'exigence est une marque de respect pour la discipline académique. "
        "Tu tends vers des notes entre 8 et 12/20, et les notes élevées sont réservées "
        "à des prestations véritablement exceptionnelles."
    ),
    'terroriste': (
        "Pour la notation, adopte un biais très bas pour établir un standard élevé. "
        "Tu notes en dessous de 10/20 sauf mérite exceptionnel et clairement démontré. "
        "Tu utilises la note comme un message sur la qualité attendue dans la discipline. "
        "Tu tends vers des notes entre 6 et 10/20, considérant qu'un 10/20 est déjà un satisfecit."
    ),
    'comptable': (
        "Pour la notation, décompose systématiquement en sous-critères précis : "
        "fond (contenu, rigueur), forme (clarté, structure, slides), oral (débit, assurance, pédagogie), "
        "bibliographie (qualité, pertinence des sources). "
        "Calcule une moyenne pondérée à la décimale près pour chaque critère principal. "
        "Justifie chaque sous-note par une observation factuelle."
    ),
}


LANGUE_LABELS = {
    'fr': 'français', 'en': 'anglais', 'ar': 'arabe / darija',
    'es': 'espagnol', 'de': 'allemand',
}


# ============================================================================
# Client Anthropic — initialisation paresseuse
# ============================================================================

_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY n'est pas configurée. Voir .env.example."
            )
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


# ============================================================================
# Contexte de notation
# ============================================================================

@dataclass
class ContexteNotation:
    """Données rassemblées pour qu'un agent puisse noter une soutenance."""
    transcription: str
    contenu_slides: str
    contenu_rapport: str
    consignes_prof: str
    criteres: list  # liste de dicts {nom, coefficient, description}
    langue: str
    nom_etudiant: str
    duree_prevue_min: int
    duree_reelle_min: float
    donnees_posture: dict
    style_questionnement: str   # remplace 'personnalite'
    style_notation: str         # nouveau
    type_groupe: str
    membres_groupe: list        # liste de noms
    # Liste de dicts {question, reponse} — session Q&R avec l'IA
    questions_reponses: list = None

    def _fmt_comportemental(self) -> str:
        """Formate les données comportementales (posture + expressions + prosodie)
        de façon lisible pour le prompt Claude.
        Retourne une chaîne vide si aucune donnée n'est disponible.
        """
        p = self.donnees_posture or {}
        if not p:
            return "(données comportementales non disponibles — présentation sans webcam ou sans mesures)"
        lignes = []
        if 'pourcentage_contact_visuel' in p:
            lignes.append(
                f"- Contact visuel avec la caméra : {p['pourcentage_contact_visuel']}%"
            )
        if 'inclinaison_tete_moyenne_deg' in p:
            lignes.append(
                f"- Inclinaison moyenne de la tête : {p['inclinaison_tete_moyenne_deg']}°"
            )
        if 'emotion_dominante' in p:
            lignes.append(f"- Émotion faciale dominante (détectée par IA) : {p['emotion_dominante']}")
        if p.get('expressions_moyennes_pct'):
            exprs = p['expressions_moyennes_pct']
            # N'afficher que les émotions > 5% pour la lisibilité
            exprs_txt = ', '.join(
                f"{k} {v}%" for k, v in sorted(exprs.items(), key=lambda x: -x[1])
                if v > 5.0
            )
            if exprs_txt:
                lignes.append(f"- Répartition des émotions observées : {exprs_txt}")
        if 'debit_mots_par_min' in p:
            debit = p['debit_mots_par_min']
            if debit < 100:
                interp_debit = "(très lent — manque de dynamisme ou nombreuses pauses)"
            elif debit < 130:
                interp_debit = "(rythme lent mais compréhensible)"
            elif debit < 160:
                interp_debit = "(rythme idéal pour une présentation académique)"
            elif debit < 190:
                interp_debit = "(rapide — attention à la compréhension du jury)"
            else:
                interp_debit = "(très rapide — signe probable de stress ou de manque de maîtrise)"
            lignes.append(f"- Débit de parole estimé : {debit} mots/min {interp_debit}")
        if 'ratio_silence_pct' in p:
            lignes.append(f"- Ratio de silence / pauses : {p['ratio_silence_pct']}%")
        if 'commentaire_prosodie' in p:
            lignes.append(f"- Rythme vocal : {p['commentaire_prosodie']}")
        if 'commentaire_intonation' in p:
            lignes.append(f"- Variation d'intonation (volume) : {p['commentaire_intonation']}")
        if 'commentaire_auto' in p:
            lignes.append(f"- Contact visuel — observation : {p['commentaire_auto']}")
        if 'nb_mesures' in p:
            lignes.append(
                f"  (basé sur {p['nb_mesures']} échantillons webcam "
                "— mesures réelles via face-api.js + Web Audio API)"
            )
        return '\n'.join(lignes) if lignes else "(aucune donnée comportementale exploitable)"

    def _fmt_questions_reponses(self) -> str:
        """Formate la session Q&R pour l'inclure dans le prompt."""
        qrs = self.questions_reponses or []
        if not qrs:
            return "(aucune session de questions-réponses enregistrée)"
        lignes = []
        for i, qr in enumerate(qrs, 1):
            q = qr.get('question', '').strip()
            r = qr.get('reponse', '').strip()
            if q:
                lignes.append(f"Q{i} : {q}")
                lignes.append(f"R{i} : {r if r else '(pas de réponse enregistrée)'}")
                lignes.append("")
        return '\n'.join(lignes).strip() or "(aucune session de questions-réponses enregistrée)"

    def to_prompt(self) -> str:
        criteres_txt = '\n'.join(
            f'- {c["nom"]} (coefficient {c["coefficient"]}): {c.get("description", "")}'
            for c in self.criteres
        )
        comportemental_txt = self._fmt_comportemental()
        qa_txt = self._fmt_questions_reponses()
        return f"""
ÉVALUATION D'UNE SOUTENANCE — étudiant : {self.nom_etudiant}

# Configuration
- Langue de présentation attendue : {LANGUE_LABELS.get(self.langue, self.langue)}
- Durée prévue : {self.duree_prevue_min} min — durée réelle : {self.duree_reelle_min:.1f} min
- Type : {self.type_groupe} (membres : {", ".join(self.membres_groupe) or self.nom_etudiant})

# Consignes du professeur
{self.consignes_prof or "(aucune consigne spécifique)"}

# Critères à évaluer
{criteres_txt}

# Transcription audio de la présentation
\"\"\"
{self.transcription or "(transcription indisponible)"}
\"\"\"

# Contenu extrait des slides PPTX
\"\"\"
{self.contenu_slides or "(slides non fournies)"}
\"\"\"

# Contenu extrait du rapport PDF
\"\"\"
{self.contenu_rapport or "(rapport non fourni)"}
\"\"\"

# Session de questions-réponses avec l'IA (IMPORTANT pour noter le critère « Réponses aux questions »)
# Questions posées par l'IA examinatrice + réponses de l'étudiant après la présentation :
\"\"\"
{qa_txt}
\"\"\"

# Données comportementales observées pendant la présentation
# (contact visuel, expressions faciales, prosodie — mesurées côté navigateur en temps réel)
{comportemental_txt}

# Grille d'analyse de la transcription — ce que tu dois évaluer dans le discours oral
En lisant la transcription, prête attention aux dimensions suivantes (signaux experts) :

AISANCE ORALE ET DISFLUENCES :
- Présence de "euh", "hmm", répétitions ("c'est-à-dire, c'est-à-dire"), phrases incomplètes
- Silences qui trahissent une hésitation vs. silences rhétoriques maîtrisés
- Débit homogène ou heurté

RIGUEUR DU DISCOURS SCIENTIFIQUE :
- Vocabulaire disciplinaire précis et bien utilisé (ou jargon mal maîtrisé)
- Affirmations sourcées ("selon X, 2022...") vs. formules vagues ("des études montrent")
- Distinction explicite corrélation / causalité
- Mention des limites du travail et pistes futures (signe de maturité critique)
- Formulations de doute appropriées ("pourrait suggérer") vs. sur-interprétation

STRUCTURE LOGIQUE :
- Connecteurs logiques présents (donc, ainsi, par conséquent, or, cependant...)
- Transitions entre les parties
- Capacité à synthétiser ("notre contribution principale est...")
- Clôture présente et structurée (ou bâclée)

AUTHENTICITÉ ET MAÎTRISE RÉELLE :
- Parle de ses propres données avec des détails concrets → implication réelle
- Reformule ses idées avec ses propres mots (compréhension) vs. récitation par cœur
- Sait pourquoi il a fait ses choix méthodologiques
- Cite ses tableaux/figures avec intention ou désigne vaguement ("là, ce truc")

# Ta tâche
Pour CHAQUE critère listé, attribue une note sur 20 et un commentaire JUSTIFICATIF précis.
Appuie-toi sur des exemples TIRÉS DU TEXTE (citation courte ou paraphrase).
Ta réponse doit être STRICTEMENT en JSON valide, au format suivant :

{{
  "notes": [
    {{"critere": "<nom exact du critère>", "note": <float entre 0 et 20>, "commentaire": "<2-4 phrases avec exemple du texte>"}}
  ],
  "synthese": "<bilan global 3-5 phrases>",
  "ton_detecte": "<calme|stresse|hesitant|assure|monotone|enthousiaste>",
  "disfluences_detectees": "<aucune|rares|moderees|frequentes>",
  "coherence_corps_discours": "<coherente|legere_tension|incoherence_notable>"
}}
""".strip()


# ============================================================================
# Agent unique : encapsule l'appel à Claude pour les deux styles
# ============================================================================

class AgentNotation:
    def __init__(self, style_questionnement: str = 'mentor',
                 style_notation: str = 'juste'):
        self.style_questionnement = (
            style_questionnement
            if style_questionnement in QUESTIONNEMENT_PROMPTS
            else 'mentor'
        )
        self.style_notation = (
            style_notation
            if style_notation in NOTATION_PROMPTS
            else 'juste'
        )

    def system_prompt(self) -> str:
        q = QUESTIONNEMENT_PROMPTS[self.style_questionnement]
        n = NOTATION_PROMPTS[self.style_notation]
        return (
            f"{q}\n\n"
            f"{n}\n\n"
            "TU DOIS RÉPONDRE UNIQUEMENT EN JSON VALIDE, sans texte autour, "
            "sans bloc markdown ``` autour."
        )

    def noter(self, ctx: ContexteNotation) -> dict:
        """Appelle Claude et retourne le dict des notes."""
        client = get_client()
        try:
            response = client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=4000,
                system=self.system_prompt(),
                messages=[{'role': 'user', 'content': ctx.to_prompt()}],
            )
            raw = response.content[0].text.strip()
            # Nettoyage : retirer un éventuel bloc markdown résiduel
            if raw.startswith('```'):
                raw = raw.strip('`')
                if raw.startswith('json'):
                    raw = raw[4:]
                raw = raw.strip()
            data = json.loads(raw)
            data['_style_questionnement'] = self.style_questionnement
            data['_style_notation'] = self.style_notation
            return data
        except json.JSONDecodeError as e:
            logger.error('Réponse Claude non-JSON : %s', raw[:500])
            return {'erreur': f'JSON invalide: {e}', 'brut': raw[:500]}
        except Exception as e:
            logger.exception('Erreur appel Claude')
            return {'erreur': str(e)}


# ============================================================================
# Orchestrateur : ajuste les styles si stress détecté (configurable)
# ============================================================================

class Orchestrateur:
    """Choisit/ajuste les deux styles selon le contexte de la présentation."""

    # Profils de questionnement qui basculent vers 'mentor' si stress détecté
    STYLES_AGRESSIFS_Q = {'contradicteur', 'provocateur', 'impassible'}
    # Profils de notation qui basculent vers 'indulgent' si stress détecté
    STYLES_SEVERES_N   = {'severe', 'terroriste', 'avare'}

    def __init__(self, style_questionnement: str, style_notation: str,
                 ajustement_auto: bool = True):
        self.sq = style_questionnement
        self.sn = style_notation
        self.ajustement_auto = ajustement_auto

    def detecter_ton(self, transcription: str) -> str:
        """Heuristique simple pour détecter le ton avant d'appeler l'IA."""
        if not transcription:
            return 'inconnu'
        t = transcription.lower()
        marqueurs_stress = ['euh', 'heu', 'hmm', '...', 'je ne sais pas', "je sais pas"]
        score_stress = sum(t.count(m) for m in marqueurs_stress)
        mots = max(len(t.split()), 1)
        ratio = score_stress / mots
        if ratio > 0.05:
            return 'stressé'
        if ratio > 0.02:
            return 'hésitant'
        return 'assuré'

    def choisir_styles(self, transcription: str) -> tuple[str, str]:
        """Retourne (style_questionnement, style_notation) potentiellement ajustés."""
        if not self.ajustement_auto:
            return self.sq, self.sn

        ton = self.detecter_ton(transcription)
        sq, sn = self.sq, self.sn

        if ton == 'stressé':
            if sq in self.STYLES_AGRESSIFS_Q:
                logger.info(
                    "Orchestrateur: stress détecté → questionnement %s → mentor", sq,
                )
                sq = 'mentor'
            if sn in self.STYLES_SEVERES_N:
                logger.info(
                    "Orchestrateur: stress détecté → notation %s → indulgent", sn,
                )
                sn = 'indulgent'

        return sq, sn

    def noter(self, ctx: ContexteNotation) -> dict:
        sq, sn = self.choisir_styles(ctx.transcription)
        ctx.style_questionnement = sq
        ctx.style_notation = sn
        agent = AgentNotation(sq, sn)
        return agent.noter(ctx)


# ============================================================================
# Génération de questions pour la session Q/R
# ============================================================================

def generer_questions(
    transcription: str, contenu_slides: str,
    contenu_rapport: str, langue: str,
    nb_questions: int,
    style_questionnement: str = 'mentor',
    consignes: str = '',
) -> list[str]:
    """Génère nb_questions pertinentes à poser à l'étudiant, dans sa langue.
    Le style_questionnement oriente la tonalité des questions sans modifier
    leur base (toujours tirées du matériel de l'étudiant).
    """
    client = get_client()
    langue_label = LANGUE_LABELS.get(langue, langue)
    q_style = QUESTIONNEMENT_PROMPTS.get(
        style_questionnement, QUESTIONNEMENT_PROMPTS['mentor'],
    )

    prompt = f"""
À partir du matériel ci-dessous, génère exactement {nb_questions} questions
pertinentes à poser à l'étudiant pendant la session de questions.
Les questions doivent être en {langue_label}.

Les questions sont TOUJOURS basées sur le contenu réel (transcription, slides, rapport).
{q_style.replace("Ton rôle d'examinateur est celui", "Adopte le style")}

Consignes du professeur : {consignes or "(aucune)"}

# Transcription
{transcription[:3000]}

# Slides
{contenu_slides[:2000]}

# Rapport
{contenu_rapport[:3000]}

Réponds UNIQUEMENT en JSON :
{{"questions": ["...", "...", ...]}}
""".strip()

    try:
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=1500,
            system="Tu génères des questions d'examen pertinentes. Réponds en JSON strict.",
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.strip('`')
            if raw.startswith('json'):
                raw = raw[4:]
            raw = raw.strip()
        data = json.loads(raw)
        return data.get('questions', [])[:nb_questions]
    except Exception as e:
        logger.exception('Erreur generation questions')
        return []


def evaluer_reponse(
    question: str, reponse: str, langue: str,
    style_questionnement: str = 'mentor',
) -> dict:
    """Évalue la réponse d'un étudiant à une question."""
    client = get_client()
    system = QUESTIONNEMENT_PROMPTS.get(
        style_questionnement, QUESTIONNEMENT_PROMPTS['mentor'],
    )
    prompt = f"""
Question posée : "{question}"
Réponse de l'étudiant : "{reponse}"

Évalue cette réponse sur 20 et donne un court commentaire (2-3 phrases).
Réponds en JSON :
{{"note": <0-20>, "commentaire": "..."}}
""".strip()
    try:
        resp = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=500,
            system=system + " Réponds en JSON strict.",
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = resp.content[0].text.strip().strip('`')
        if raw.startswith('json'):
            raw = raw[4:].strip()
        return json.loads(raw)
    except Exception as e:
        logger.exception('Erreur eval réponse')
        return {'note': 10, 'commentaire': f'(évaluation indisponible : {e})'}


# ============================================================================
# Évaluation vidéo de démonstration (Groq Vision → Claude fallback)
# ============================================================================

def evaluer_demo_video(
    frames_b64: list[str],
    instructions: str,
    langue: str = 'fr',
) -> dict:
    """Analyse des frames d'une vidéo de démonstration.
    Essaie Groq llama-3.2-11b-vision d'abord (gratuit), puis Claude (payant).
    Retourne : {"note": float, "commentaire": str, "points_forts": [...], "points_faibles": [...]}
    """
    if not frames_b64:
        return {'note': 10, 'commentaire': 'Aucune frame extraite de la vidéo.', 'points_forts': [], 'points_faibles': []}

    langue_label = LANGUE_LABELS.get(langue, 'français')
    nb = len(frames_b64)
    prompt_texte = f"""Tu es un examinateur académique qui analyse une démonstration vidéo d'un étudiant.

Consignes du professeur : {instructions or 'Évaluer la qualité de la démonstration.'}

Tu disposes de {nb} captures d'écran prises à intervalles réguliers de la vidéo.
Analyse ces captures et évalue la démonstration sur 20.

Réponds UNIQUEMENT en JSON valide dans la langue {langue_label} :
{{
  "note": <0-20>,
  "commentaire": "paragraphe d'évaluation globale (5-8 phrases)",
  "points_forts": ["point 1", "point 2", ...],
  "points_faibles": ["point 1", "point 2", ...]
}}"""

    # Construction du contenu multimodal (texte + images)
    contenu_images = [{'type': 'text', 'text': prompt_texte}]
    for b64 in frames_b64:
        contenu_images.append({
            'type': 'image_url',
            'image_url': {'url': f'data:image/jpeg;base64,{b64}'},
        })

    # ── Tentative 1 : Groq llama-3.2-11b-vision (cheap / gratuit) ─────────
    if settings.GROQ_API_KEY:
        try:
            from groq import Groq, RateLimitError
            gclient = Groq(api_key=settings.GROQ_API_KEY)
            resp = gclient.chat.completions.create(
                model='llama-3.2-11b-vision-preview',
                messages=[{'role': 'user', 'content': contenu_images}],
                max_tokens=1500,
                temperature=0.3,
            )
            raw = resp.choices[0].message.content.strip().strip('`')
            if raw.startswith('json'):
                raw = raw[4:].strip()
            result = json.loads(raw)
            logger.info('[evaluer_demo_video] Groq OK — note %.1f', result.get('note', 0))
            return result
        except RateLimitError:
            logger.warning('[evaluer_demo_video] Groq 429 — fallback Claude')
        except Exception as exc:
            logger.warning('[evaluer_demo_video] Groq echec (%s) — fallback Claude', exc)

    # ── Tentative 2 : Claude (vision via anthropic SDK) ─────────────────────
    try:
        client = get_client()
        # Construire le contenu pour Anthropic (format différent de OpenAI)
        content_anthropic: list = [{'type': 'text', 'text': prompt_texte}]
        for b64 in frames_b64:
            content_anthropic.append({
                'type': 'image',
                'source': {
                    'type': 'base64',
                    'media_type': 'image/jpeg',
                    'data': b64,
                },
            })
        resp = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=1500,
            messages=[{'role': 'user', 'content': content_anthropic}],
        )
        raw = resp.content[0].text.strip().strip('`')
        if raw.startswith('json'):
            raw = raw[4:].strip()
        result = json.loads(raw)
        logger.info('[evaluer_demo_video] Claude OK — note %.1f', result.get('note', 0))
        return result
    except Exception as exc:
        logger.exception('[evaluer_demo_video] Claude echec')
        return {
            'note': 10,
            'commentaire': f'Évaluation indisponible ({exc}).',
            'points_forts': [],
            'points_faibles': [],
        }


# ============================================================================
# Évaluation dépôt GitHub (Claude — analyse code + README + structure)
# ============================================================================

def evaluer_depot_github(
    repo_data: dict,
    criteres: str,
    langue: str = 'fr',
) -> dict:
    """Analyse un dépôt GitHub à partir des données fetched par fetch_github_repo().
    Retourne : {"note": float, "commentaire": str, "points_forts": [...], "points_faibles": [...]}
    """
    if 'erreur' in repo_data:
        return {
            'note': 0,
            'commentaire': f"Impossible d'analyser le dépôt : {repo_data['erreur']}",
            'points_forts': [],
            'points_faibles': [],
        }

    langue_label = LANGUE_LABELS.get(langue, 'français')
    langages_str = ', '.join(f"{l} ({p}%)" for l, p in repo_data.get('langages', {}).items())
    structure_str = '\n'.join(repo_data.get('structure', []))
    fichiers_str = '\n\n'.join(
        f"--- {f['nom']} ---\n{f['contenu']}"
        for f in repo_data.get('fichiers_principaux', [])
    )

    prompt = f"""Tu es un examinateur académique qui évalue le dépôt GitHub d'un étudiant.

Informations sur le dépôt :
- Nom : {repo_data.get('nom', '')}
- Description : {repo_data.get('description', '(aucune)')}
- Langages : {langages_str or '(inconnus)'}
- Nombre de commits : {repo_data.get('nb_commits', 0)}
- Date création : {repo_data.get('date_creation', '')} | Dernier push : {repo_data.get('date_dernier_push', '')}

Structure du projet :
{structure_str or '(non disponible)'}

README :
{repo_data.get('readme', '(absent)')}

Extraits du code source :
{fichiers_str or '(non disponible)'}

Critères d'évaluation du professeur :
{criteres or 'Évaluer la qualité générale du code, la documentation, la structure et l\'historique des commits.'}

Évalue ce dépôt sur 20 en {langue_label}. Réponds UNIQUEMENT en JSON valide :
{{
  "note": <0-20>,
  "commentaire": "évaluation détaillée (5-8 phrases)",
  "points_forts": ["point 1", "point 2", ...],
  "points_faibles": ["point 1", "point 2", ...]
}}"""

    try:
        client = get_client()
        resp = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=1500,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = resp.content[0].text.strip().strip('`')
        if raw.startswith('json'):
            raw = raw[4:].strip()
        result = json.loads(raw)
        logger.info('[evaluer_depot_github] OK — note %.1f', result.get('note', 0))
        return result
    except Exception as exc:
        logger.exception('[evaluer_depot_github] Erreur')
        return {
            'note': 0,
            'commentaire': f'Évaluation GitHub indisponible ({exc}).',
            'points_forts': [],
            'points_faibles': [],
        }
