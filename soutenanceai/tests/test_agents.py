"""Tests des agents IA : styles questionnement/notation, orchestrateur, questions."""
import json
from unittest.mock import MagicMock, patch

import pytest

from notation.agents import (
    NOTATION_PROMPTS,
    QUESTIONNEMENT_PROMPTS,
    AgentNotation,
    ContexteNotation,
    Orchestrateur,
    evaluer_reponse,
    generer_questions,
    get_client,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_claude_response(text: str) -> MagicMock:
    """Crée un faux objet de réponse Claude."""
    content = MagicMock()
    content.text = text
    resp = MagicMock()
    resp.content = [content]
    return resp


def _make_context(**kwargs) -> ContexteNotation:
    defaults = dict(
        transcription='Bonjour, je présente mon projet.',
        contenu_slides='Slide 1 : Introduction',
        contenu_rapport='Rapport : Résumé du projet.',
        consignes_prof='Focus sur la clarté.',
        criteres=[
            {'nom': 'Clarté', 'coefficient': 1.0, 'description': 'Clair et précis'},
            {'nom': 'Structure', 'coefficient': 2.0, 'description': 'Bien organisé'},
        ],
        langue='fr',
        nom_etudiant='Alice Dupont',
        duree_prevue_min=15,
        duree_reelle_min=14.5,
        donnees_posture={'pourcentage_contact_visuel': 75},
        style_questionnement='mentor',
        style_notation='juste',
        type_groupe='monome',
        membres_groupe=['Alice Dupont'],
    )
    defaults.update(kwargs)
    return ContexteNotation(**defaults)


# ============================================================================
# Styles (double axe questionnement × notation)
# ============================================================================

class TestStyles:

    def test_all_questionnement_styles_defined(self):
        for s in ('mentor', 'pedagogue', 'perfectionniste', 'contradicteur',
                  'stratege', 'provocateur', 'impassible'):
            assert s in QUESTIONNEMENT_PROMPTS
            assert len(QUESTIONNEMENT_PROMPTS[s]) > 20

    def test_all_notation_styles_defined(self):
        for s in ('genereux', 'indulgent', 'juste', 'avare',
                  'severe', 'terroriste', 'comptable'):
            assert s in NOTATION_PROMPTS
            assert len(NOTATION_PROMPTS[s]) > 20


# ============================================================================
# ContexteNotation
# ============================================================================

class TestContexteNotation:

    def test_to_prompt_contains_student_name(self):
        ctx = _make_context(nom_etudiant='Bob Martin')
        prompt = ctx.to_prompt()
        assert 'Bob Martin' in prompt

    def test_to_prompt_contains_criteria(self):
        ctx = _make_context()
        prompt = ctx.to_prompt()
        assert 'Clarté' in prompt
        assert 'Structure' in prompt

    def test_to_prompt_contains_transcription(self):
        ctx = _make_context(transcription='Voici ma transcription unique.')
        prompt = ctx.to_prompt()
        assert 'Voici ma transcription unique.' in prompt

    def test_to_prompt_handles_empty_transcription(self):
        ctx = _make_context(transcription='')
        prompt = ctx.to_prompt()
        assert 'transcription indisponible' in prompt

    def test_to_prompt_handles_empty_slides(self):
        ctx = _make_context(contenu_slides='')
        prompt = ctx.to_prompt()
        assert 'slides non fournies' in prompt

    def test_to_prompt_mentions_langue(self):
        ctx = _make_context(langue='en')
        prompt = ctx.to_prompt()
        assert 'nglais' in prompt  # Anglais / anglais

    def test_to_prompt_mentions_duration(self):
        ctx = _make_context(duree_prevue_min=20, duree_reelle_min=18.3)
        prompt = ctx.to_prompt()
        assert '20' in prompt

    def test_to_prompt_requests_json_output(self):
        ctx = _make_context()
        prompt = ctx.to_prompt()
        assert 'JSON' in prompt
        assert '"notes"' in prompt

    def test_to_prompt_includes_questions_reponses(self):
        ctx = _make_context(questions_reponses=[
            {'question': 'Pourquoi ce choix techno unique ?', 'reponse': 'Parce que performant.'},
        ])
        prompt = ctx.to_prompt()
        assert 'Pourquoi ce choix techno unique ?' in prompt
        assert 'Parce que performant.' in prompt


# ============================================================================
# AgentNotation
# ============================================================================

class TestAgentNotation:

    def test_init_defaults(self):
        agent = AgentNotation()
        assert agent.style_questionnement == 'mentor'
        assert agent.style_notation == 'juste'

    def test_init_valid_styles(self):
        agent = AgentNotation('contradicteur', 'severe')
        assert agent.style_questionnement == 'contradicteur'
        assert agent.style_notation == 'severe'

    def test_init_unknown_styles_fall_back_to_defaults(self):
        agent = AgentNotation('inexistant', 'inconnu')
        assert agent.style_questionnement == 'mentor'
        assert agent.style_notation == 'juste'

    def test_system_prompt_contains_json_instruction(self):
        agent = AgentNotation()
        assert 'JSON' in agent.system_prompt()

    def test_system_prompt_combines_both_styles(self):
        agent = AgentNotation('provocateur', 'terroriste')
        sp = agent.system_prompt()
        assert QUESTIONNEMENT_PROMPTS['provocateur'][:20] in sp
        assert NOTATION_PROMPTS['terroriste'][:20] in sp

    @patch('notation.agents.get_client')
    def test_noter_returns_parsed_dict(self, mock_get_client):
        response_data = {
            'notes': [
                {'critere': 'Clarté', 'note': 15.0, 'commentaire': 'Très clair.'},
                {'critere': 'Structure', 'note': 14.0, 'commentaire': 'Bien organisé.'},
            ],
            'synthese': 'Bonne prestation.',
            'ton_detecte': 'assure',
        }
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response(json.dumps(response_data))
        mock_get_client.return_value = mock_client

        agent = AgentNotation()
        result = agent.noter(_make_context())

        assert 'notes' in result
        assert len(result['notes']) == 2
        assert result['_style_questionnement'] == 'mentor'
        assert result['_style_notation'] == 'juste'

    @patch('notation.agents.get_client')
    def test_noter_cleans_markdown_code_block(self, mock_get_client):
        response_data = {'notes': [], 'synthese': 'OK', 'ton_detecte': 'calme'}
        raw = f'```json\n{json.dumps(response_data)}\n```'
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response(raw)
        mock_get_client.return_value = mock_client

        agent = AgentNotation()
        result = agent.noter(_make_context())
        assert 'notes' in result

    @patch('notation.agents.get_client')
    def test_noter_handles_json_decode_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response('pas du JSON valide !')
        mock_get_client.return_value = mock_client

        agent = AgentNotation()
        result = agent.noter(_make_context())
        assert 'erreur' in result

    @patch('notation.agents.get_client')
    def test_noter_handles_api_exception(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception('Network error')
        mock_get_client.return_value = mock_client

        agent = AgentNotation()
        result = agent.noter(_make_context())
        assert 'erreur' in result

    @patch('notation.agents.get_client')
    def test_noter_styles_used_in_system_prompt(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response(
            json.dumps({'notes': [], 'synthese': '', 'ton_detecte': 'calme'})
        )
        mock_get_client.return_value = mock_client

        agent = AgentNotation('perfectionniste', 'severe')
        agent.noter(_make_context())
        call_kwargs = mock_client.messages.create.call_args
        system_used = call_kwargs[1].get('system') or ''
        assert QUESTIONNEMENT_PROMPTS['perfectionniste'][:20] in system_used
        assert NOTATION_PROMPTS['severe'][:20] in system_used


# ============================================================================
# Orchestrateur
# ============================================================================

class TestOrchestrateur:

    def test_detecter_ton_assure_with_clean_transcription(self):
        orch = Orchestrateur('contradicteur', 'severe')
        assert orch.detecter_ton('Voici mon projet. Il est bien structuré.') == 'assuré'

    def test_detecter_ton_stresse_with_many_hesitations(self):
        orch = Orchestrateur('contradicteur', 'severe')
        t = 'euh euh heu je sais pas euh hmm je ne sais pas bien euh'
        assert orch.detecter_ton(t) == 'stressé'

    def test_detecter_ton_empty_returns_inconnu(self):
        orch = Orchestrateur('mentor', 'juste')
        assert orch.detecter_ton('') == 'inconnu'
        assert orch.detecter_ton(None) == 'inconnu'

    def test_stress_switches_aggressive_styles_to_soft(self):
        """Contradicteur + sévère deviennent mentor + indulgent si stress."""
        orch = Orchestrateur('contradicteur', 'severe', ajustement_auto=True)
        stressful = 'euh euh euh je sais pas euh heu heu hmm je ne sais pas vraiment euh'
        sq, sn = orch.choisir_styles(stressful)
        assert sq == 'mentor'
        assert sn == 'indulgent'

    def test_stress_does_not_switch_soft_styles(self):
        """Mentor + juste ne basculent pas même si stress détecté."""
        orch = Orchestrateur('mentor', 'juste', ajustement_auto=True)
        stressful = 'euh euh euh je sais pas euh heu heu hmm je ne sais pas vraiment euh'
        sq, sn = orch.choisir_styles(stressful)
        assert sq == 'mentor'
        assert sn == 'juste'

    def test_no_switch_when_ajustement_disabled(self):
        """Si ajustement_auto=False, aucun changement même en cas de stress."""
        orch = Orchestrateur('provocateur', 'terroriste', ajustement_auto=False)
        stressful = 'euh euh euh je sais pas euh heu heu hmm je ne sais pas vraiment euh'
        sq, sn = orch.choisir_styles(stressful)
        assert sq == 'provocateur'
        assert sn == 'terroriste'

    def test_calm_transcription_keeps_styles(self):
        orch = Orchestrateur('contradicteur', 'severe', ajustement_auto=True)
        calm = 'Mon projet utilise une architecture microservices robuste.'
        sq, sn = orch.choisir_styles(calm)
        assert sq == 'contradicteur'
        assert sn == 'severe'

    @patch('notation.agents.AgentNotation.noter')
    def test_noter_delegates_to_agent(self, mock_noter):
        mock_noter.return_value = {'notes': [], 'synthese': 'OK', 'ton_detecte': 'calme'}
        orch = Orchestrateur('mentor', 'juste')
        result = orch.noter(_make_context())
        mock_noter.assert_called_once()
        assert 'notes' in result

    @patch('notation.agents.AgentNotation.noter')
    def test_noter_updates_ctx_styles(self, mock_noter):
        """Le contexte reçoit les styles choisis (après éventuel ajustement)."""
        mock_noter.return_value = {'notes': [], 'synthese': '', 'ton_detecte': 'stresse'}
        orch = Orchestrateur('contradicteur', 'severe', ajustement_auto=True)
        ctx = _make_context(
            transcription='euh euh euh je sais pas euh heu heu hmm',
            style_questionnement='contradicteur',
            style_notation='severe',
        )
        orch.noter(ctx)
        assert ctx.style_questionnement == 'mentor'
        assert ctx.style_notation == 'indulgent'


# ============================================================================
# generer_questions
# ============================================================================

class TestGenererQuestions:

    @patch('notation.agents.get_client')
    def test_returns_questions_list(self, mock_get_client):
        questions = ['Q1 ?', 'Q2 ?', 'Q3 ?']
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response(
            json.dumps({'questions': questions})
        )
        mock_get_client.return_value = mock_client

        result = generer_questions(
            transcription='texte',
            contenu_slides='slides',
            contenu_rapport='rapport',
            langue='fr',
            nb_questions=3,
        )
        assert result == questions

    @patch('notation.agents.get_client')
    def test_respects_nb_questions_limit(self, mock_get_client):
        questions = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response(
            json.dumps({'questions': questions})
        )
        mock_get_client.return_value = mock_client

        result = generer_questions('t', 's', 'r', 'fr', nb_questions=2)
        assert len(result) <= 2

    @patch('notation.agents.get_client')
    def test_handles_api_exception_returns_empty(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception('timeout')
        mock_get_client.return_value = mock_client

        result = generer_questions('t', 's', 'r', 'fr', nb_questions=3)
        assert result == []

    @patch('notation.agents.get_client')
    def test_handles_invalid_json_returns_empty(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response('pas json')
        mock_get_client.return_value = mock_client

        result = generer_questions('t', 's', 'r', 'fr', nb_questions=3)
        assert result == []


# ============================================================================
# evaluer_reponse
# ============================================================================

class TestEvaluerReponse:

    @patch('notation.agents.get_client')
    def test_returns_note_and_commentaire(self, mock_get_client):
        eval_data = {'note': 14.0, 'commentaire': 'Réponse correcte.'}
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response(json.dumps(eval_data))
        mock_get_client.return_value = mock_client

        result = evaluer_reponse('Question ?', 'Réponse.', langue='fr')
        assert result['note'] == 14.0
        assert 'Réponse correcte.' in result['commentaire']

    @patch('notation.agents.get_client')
    def test_handles_exception_returns_default(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception('err')
        mock_get_client.return_value = mock_client

        result = evaluer_reponse('Q ?', 'R.', langue='fr')
        assert 'note' in result
        assert result['note'] == 10  # note par défaut

    @patch('notation.agents.get_client')
    def test_uses_style_system_prompt(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_claude_response(
            json.dumps({'note': 10.0, 'commentaire': 'OK'})
        )
        mock_get_client.return_value = mock_client

        evaluer_reponse('Q ?', 'R.', langue='fr', style_questionnement='pedagogue')
        call_kwargs = mock_client.messages.create.call_args
        system_used = call_kwargs[1].get('system') or ''
        assert QUESTIONNEMENT_PROMPTS['pedagogue'][:20] in system_used


# ============================================================================
# get_client
# ============================================================================

class TestGetClient:

    def test_raises_if_no_api_key(self, settings):
        import notation.agents as agents_module
        agents_module._client = None
        settings.ANTHROPIC_API_KEY = ''
        with pytest.raises(RuntimeError, match='ANTHROPIC_API_KEY'):
            get_client()

    @patch('anthropic.Anthropic')
    def test_returns_client_when_key_set(self, mock_anthropic, settings):
        import notation.agents as agents_module
        agents_module._client = None
        settings.ANTHROPIC_API_KEY = 'test-key-xxx'
        client = get_client()
        assert client is not None
        agents_module._client = None  # cleanup
