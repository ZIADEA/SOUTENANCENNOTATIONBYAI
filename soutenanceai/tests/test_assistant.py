"""Tests de l'assistant IA contextuel : endpoint chat + contextes par rôle."""
import json
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from assistant.context import construire_contexte
from notation.models import NoteIA


def _fake_reponse(texte: str) -> MagicMock:
    content = MagicMock()
    content.text = texte
    resp = MagicMock()
    resp.content = [content]
    return resp


# ============================================================================
# Endpoint /assistant/chat/
# ============================================================================

@pytest.mark.django_db
class TestChatEndpoint:

    URL = '/assistant/chat/'

    @patch('notation.agents.get_client')
    def test_visiteur_anonyme_recoit_une_reponse(self, mock_get_client, client, settings):
        settings.ANTHROPIC_API_KEY = 'test-key'
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_reponse('Bienvenue sur SoutenanceAI.')
        mock_get_client.return_value = mock_client

        resp = client.post(
            self.URL,
            data=json.dumps({'message': 'Comment fonctionne la notation ?'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.json()['reponse'] == 'Bienvenue sur SoutenanceAI.'

    @patch('notation.agents.get_client')
    def test_contexte_visiteur_dans_system_prompt(self, mock_get_client, client, settings):
        settings.ANTHROPIC_API_KEY = 'test-key'
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_reponse('ok')
        mock_get_client.return_value = mock_client

        client.post(self.URL, data=json.dumps({'message': 'Qui es-tu ?'}),
                    content_type='application/json')
        system = mock_client.messages.create.call_args[1]['system']
        assert 'VISITEUR' in system
        assert 'DJERI-ALASSANI' in system  # base de connaissances présente

    @patch('notation.agents.get_client')
    def test_historique_transmis(self, mock_get_client, client, settings):
        settings.ANTHROPIC_API_KEY = 'test-key'
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_reponse('ok')
        mock_get_client.return_value = mock_client

        client.post(self.URL, data=json.dumps({
            'message': 'Et ensuite ?',
            'history': [
                {'role': 'user', 'content': 'Bonjour'},
                {'role': 'assistant', 'content': 'Bonjour, je vous écoute.'},
            ],
        }), content_type='application/json')
        messages = mock_client.messages.create.call_args[1]['messages']
        assert len(messages) == 3
        assert messages[-1] == {'role': 'user', 'content': 'Et ensuite ?'}

    def test_message_vide_rejete(self, client, settings):
        settings.ANTHROPIC_API_KEY = 'test-key'
        resp = client.post(self.URL, data=json.dumps({'message': '  '}),
                           content_type='application/json')
        assert resp.status_code == 400

    def test_json_invalide_rejete(self, client, settings):
        settings.ANTHROPIC_API_KEY = 'test-key'
        resp = client.post(self.URL, data='pas du json', content_type='application/json')
        assert resp.status_code == 400

    def test_indisponible_sans_cle_api(self, client, settings):
        settings.ANTHROPIC_API_KEY = ''
        resp = client.post(self.URL, data=json.dumps({'message': 'test'}),
                           content_type='application/json')
        assert resp.status_code == 503

    def test_get_refuse(self, client):
        resp = client.get(self.URL)
        assert resp.status_code == 405


# ============================================================================
# Contextes par rôle
# ============================================================================

@pytest.mark.django_db
class TestContextes:

    def test_contexte_professeur_contient_ses_classes_et_parametres(
        self, prof_user, classe_obj, session_obj
    ):
        session_obj.classe = classe_obj
        session_obj.save()
        ctx = construire_contexte(prof_user)
        assert 'PROFESSEUR' in ctx
        assert classe_obj.nom in ctx
        assert classe_obj.code_acces in ctx
        assert session_obj.titre in ctx
        assert 'Mentor' in ctx          # style de questionnement paramétré
        assert 'coef' in ctx            # critères pondérés présents

    def test_contexte_professeur_contient_les_notes(
        self, prof_user, classe_obj, session_obj, passage_obj, etudiant_user
    ):
        session_obj.classe = classe_obj
        session_obj.save()
        passage_obj.statut = 'note'
        passage_obj.save()
        critere = session_obj.criteres.first()
        NoteIA.objects.create(
            passage=passage_obj, etudiant=etudiant_user, critere=critere,
            note_ia=14.5, note_finale=15.0, commentaire_ia='Bien.',
        )
        ctx = construire_contexte(prof_user)
        assert '15/20' in ctx
        assert 'note globale' in ctx

    def test_isolation_entre_professeurs(self, prof_user, prof_user2, classe_obj):
        from sessions_app.models import Classe
        autre = Classe.objects.create(professeur=prof_user2, nom='Classe Secrete X9')
        ctx = construire_contexte(prof_user)
        assert 'Classe Secrete X9' not in ctx
        assert autre.code_acces not in ctx

    def test_contexte_etudiant_contient_ses_passages(
        self, etudiant_user, classe_obj, passage_obj
    ):
        ctx = construire_contexte(etudiant_user)
        assert 'ÉTUDIANT' in ctx
        assert classe_obj.nom in ctx
        assert passage_obj.session.titre in ctx

    def test_contexte_superadmin_contient_les_stats(self, admin_user, prof_user):
        ctx = construire_contexte(admin_user)
        assert 'SUPERADMIN' in ctx
        assert 'Professeurs : 1' in ctx
