"""Tests d'intégration locaux : aucune communication externe ni donnée réelle."""
import datetime as dt
import hashlib
import hmac
import http.client
import json
import os
import subprocess
import sys
import re
import tempfile
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from hotellerie import config, seed, securite
from hotellerie.agent.engine import Agent
from hotellerie.agent import comprehension
from hotellerie.channels import whatsapp
from hotellerie.db import Base
from hotellerie.web.server import Handler


class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Base(Path(self.tmp.name) / 'test.db')
        seed.initialiser(self.db, silencieux=True)
        securite.creer_utilisateur(self.db, 'Hôtelier', 'test', 'motdepasse-test')
        Handler.db = self.db
        Handler.agent = Agent(self.db)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ''

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.db.fermer()
        self.tmp.cleanup()

    def request(self, method, path, data=None, headers=None):
        headers = dict(headers or {})
        if self.cookie:
            headers['Cookie'] = self.cookie
        if isinstance(data, dict):
            data = urllib.parse.urlencode(data).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request(method, path, body=data, headers=headers)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read().decode()
        finally:
            conn.close()

    def login(self):
        status, headers, _ = self.request('POST', '/connexion',
                                           {'login': 'test', 'motdepasse': 'motdepasse-test'})
        self.assertEqual(status, 303)
        self.cookie = headers['Set-Cookie'].split(';', 1)[0]

    def test_simulation_isolee_et_dates_separees(self):
        agent = Handler.agent
        arrivee = dt.date.today() + dt.timedelta(days=30)
        depart = arrivee + dt.timedelta(days=3)
        count = self.db.valeur('SELECT COUNT(*) FROM demandes')
        with patch('hotellerie.agent.engine.notify.notifier_hoteliers') as notif:
            for texte in ('Je voudrais venir en retraite', 'Jean Kouassi', 'Abidjan',
                          arrivee.isoformat(), depart.isoformat(), 'seul', 'rien de particulier'):
                reponse = agent.repondre('sim-12345678', texte, canal='terminal')
            self.assertIn('3 nuits', reponse)
            reponse = agent.repondre('sim-12345678', 'oui', canal='terminal')
            self.assertIn('Simulation', reponse)
            self.assertEqual(self.db.valeur('SELECT COUNT(*) FROM demandes'), count)
            notif.assert_not_called()
        self.assertEqual(comprehension.extraire_dates('12 octobre 2032', dt.date(2026, 1, 1))[0], '2032-10-12')
        self.assertIsNone(comprehension.extraire_dates('12 octobre 2020', dt.date(2026, 1, 1))[0])
        self.assertIsNone(comprehension.extraire_dates('29/02/2027', dt.date(2026, 1, 1))[0])

    def test_commande_terminal_ne_cree_pas_de_dossier_reel(self):
        env = dict(os.environ, HOTELLERIE_DATA_DIR=self.tmp.name)
        echange = ('Je voudrais venir en retraite\nJean Kouassi\nAbidjan\n'
                   '2035-12-01 au 2035-12-04\nseul\nrien de particulier\noui\nquitter\n')
        result = subprocess.run([sys.executable, 'run.py', 'tester'], input=echange,
                                text=True, capture_output=True, env=env, check=True)
        self.assertIn('Simulation terminée', result.stdout)
        base_cli = Base(Path(self.tmp.name) / 'hotellerie.db')
        try:
            self.assertEqual(base_cli.valeur('SELECT COUNT(*) FROM demandes'), 0)
            self.assertEqual(base_cli.valeur('SELECT COUNT(*) FROM notifications'), 0)
            self.assertEqual(base_cli.valeur('SELECT COUNT(*) FROM envois'), 0)
        finally:
            base_cli.fermer()

    def test_question_pendant_collecte_ne_devient_pas_un_nom(self):
        agent = Handler.agent
        agent.repondre('sim-12345678', 'Je souhaite venir', canal='terminal')
        reponse = agent.repondre('sim-12345678', 'Quels sont les horaires des offices ?', canal='terminal')
        self.assertIn('nom', reponse.lower())
        donnees = json.loads(self.db.valeur("SELECT donnees FROM conversations WHERE id='sim-12345678'"))
        self.assertFalse(donnees.get('nom'))
        agent.repondre('sim-12345678', 'Jean Kouassi', canal='terminal')
        donnees = json.loads(self.db.valeur("SELECT donnees FROM conversations WHERE id='sim-12345678'"))
        self.assertEqual(donnees.get('nom'), 'Kouassi')

    def test_correction_recap_sans_corrompre_identite(self):
        agent = Handler.agent
        arrivee = dt.date.today() + dt.timedelta(days=30)
        depart = arrivee + dt.timedelta(days=3)
        nouveau = arrivee + dt.timedelta(days=6)
        for texte in ('Je voudrais venir en retraite', 'Jean Kouassi', 'Abidjan',
                      f'{arrivee.isoformat()} au {depart.isoformat()}', 'seul', 'rien de particulier', 'non'):
            agent.repondre('sim-12345678', texte, canal='terminal')
        question = agent.repondre('sim-12345678', nouveau.isoformat(), canal='terminal')
        self.assertIn("arrivée ou de départ", question)
        recap = agent.repondre('sim-12345678', 'départ le ' + nouveau.isoformat(), canal='terminal')
        self.assertIn('Jean Kouassi', recap)
        self.assertIn('6 nuits', recap)

    def test_webhook_demande_complete_et_confirmation_non_rejouee(self):
        config.definir_parametre(self.db, 'wa_app_secret', 'secret-test')
        arrivee = dt.date.today() + dt.timedelta(days=40)
        depart = arrivee + dt.timedelta(days=2)
        textes = ['Je voudrais venir en retraite', 'Jean Kouassi', 'Abidjan',
                  f'{arrivee.isoformat()} au {depart.isoformat()}', 'seul', 'rien de particulier', 'oui']
        for i, texte in enumerate(textes):
            payload = json.dumps({'entry': [{'changes': [{'value': {'messages': [
                {'id': 'wamid.' + str(i), 'from': '2250700000000', 'type': 'text',
                 'text': {'body': texte}}]}}]}]}).encode()
            signature = 'sha256=' + hmac.new(b'secret-test', payload, hashlib.sha256).hexdigest()
            headers = {'Content-Type': 'application/json', 'X-Hub-Signature-256': signature}
            self.assertEqual(self.request('POST', '/webhook/whatsapp', payload, headers)[0], 200)
        self.assertEqual(self.request('POST', '/webhook/whatsapp', payload, headers)[0], 200)
        demandes = self.db.lignes('SELECT * FROM demandes')
        self.assertEqual(len(demandes), 1)
        self.assertEqual(demandes[0]['statut'], 'en_attente')
        self.assertEqual(demandes[0]['date_arrivee'], arrivee.isoformat())
        self.assertEqual(demandes[0]['date_depart'], depart.isoformat())
        self.assertEqual(self.db.valeur('SELECT COUNT(*) FROM envois'), len(textes))

    def test_backup_et_replay_partiel(self):
        dest = Path(self.tmp.name) / 'copie.db'
        self.db.sauvegarder(dest)
        copie = Base(dest)
        try:
            self.assertEqual(copie.valeur('SELECT COUNT(*) FROM connaissances'),
                             self.db.valeur('SELECT COUNT(*) FROM connaissances'))
        finally:
            copie.fermer()
        config.definir_parametre(self.db, 'wa_token', 'test')
        config.definir_parametre(self.db, 'wa_phone_number_id', 'id')
        with patch('hotellerie.channels.whatsapp._requete', side_effect=[{}, OSError('réseau')]):
            result = whatsapp.envoyer(self.db, '0700000000', 'Premier. ' * 400)
        self.assertFalse(result['ok'])
        self.assertGreater(result['morceaux'], 0)
        envoi = self.db.ligne('SELECT * FROM envois')
        self.assertNotIn('(1/', envoi['corps'])
        self.assertEqual(envoi['statut'], 'echoue')

    def test_http_connexion_csrf_simulateur_et_pages(self):
        self.assertEqual(self.request('GET', '/demandes')[0], 303)
        self.login()
        for path in ('/tableau-de-bord', '/demandes', '/calendrier', '/connaissances',
                     '/conversations', '/notifications', '/journal', '/parametres', '/whatsapp', '/simulateur'):
            self.assertEqual(self.request('GET', path)[0], 200, path)
        status, _, page = self.request('GET', '/simulateur')
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        cid = re.search(r'name="cid" value="([^"]+)"', page).group(1)
        self.assertEqual(self.request('POST', '/simulateur', {'cid': cid, 'message': 'Bonjour'})[0], 403)
        self.assertEqual(self.request('POST', '/simulateur', {'csrf': csrf, 'cid': '2250700000000', 'message': 'Bonjour'})[0], 400)
        self.assertEqual(self.request('POST', '/simulateur', {'csrf': csrf, 'cid': cid, 'message': 'Bonjour'})[0], 303)
        self.assertIn('Pax.', self.request('GET', '/simulateur?cid=' + cid)[2])

    def test_webhook_signature_et_doublon(self):
        payload = json.dumps({'entry': [{'changes': [{'value': {'messages': [
            {'id': 'wamid.1', 'from': '2250700000000', 'type': 'text', 'text': {'body': 'Bonjour'}}]}}]}]}).encode()
        self.assertEqual(self.request('POST', '/webhook/whatsapp', payload)[0], 403)
        config.definir_parametre(self.db, 'wa_app_secret', 'secret-test')
        signature = 'sha256=' + hmac.new(b'secret-test', payload, hashlib.sha256).hexdigest()
        headers = {'Content-Type': 'application/json', 'X-Hub-Signature-256': signature}
        self.assertEqual(self.request('POST', '/webhook/whatsapp', payload)[0], 403)
        self.assertEqual(self.request('POST', '/webhook/whatsapp', payload, headers)[0], 200)
        self.assertEqual(self.request('POST', '/webhook/whatsapp', payload, headers)[0], 200)
        self.assertEqual(self.db.valeur("SELECT COUNT(*) FROM messages WHERE direction='entrant'"), 1)
        self.assertEqual(self.db.valeur('SELECT COUNT(*) FROM envois'), 1)

    def test_relais_humain_rendu(self):
        agent = Handler.agent
        agent.repondre('2250700000000', 'Je voudrais parler à un père')
        self.assertEqual(agent.repondre('2250700000000', 'bonjour'), '')
        self.login()
        page = self.request('GET', '/conversations/2250700000000')[2]
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        status, _, _ = self.request('POST', '/conversations/2250700000000/relais',
                                    {'csrf': csrf, 'action': 'rendre'})
        self.assertEqual(status, 303)
        self.assertTrue(agent.repondre('2250700000000', 'Bonjour'))
        self.assertTrue(agent.repondre('2250700000000', 'Bonjour'))
        self.assertEqual(self.db.valeur("SELECT humain_requis FROM conversations WHERE id='2250700000000'"), 0)

    def test_api_reutilisation_et_apercu_sans_file(self):
        config.definir_parametre(self.db, 'api_cle', 'abc-secret')
        headers = {'Content-Type': 'application/json', 'X-API-Key': 'abc-secret'}
        payload = json.dumps({'message': 'Bonjour'}).encode()
        self.assertEqual(self.request('POST', '/api/agent', payload)[0], 403)
        status, _, body = self.request('POST', '/api/agent', payload, headers)
        self.assertEqual(status, 200)
        cid = json.loads(body)['conversation']
        payload = json.dumps({'message': 'Je voudrais venir en retraite', 'conversation': cid}).encode()
        status, _, body = self.request('POST', '/api/agent', payload, headers)
        self.assertIn('nom', json.loads(body)['reponse'].lower())
        before = self.db.valeur('SELECT COUNT(*) FROM envois')
        whatsapp.envoyer(self.db, '0700000000', 'Essai', apercu=True)
        self.assertEqual(self.db.valeur('SELECT COUNT(*) FROM envois'), before)


if __name__ == '__main__':
    unittest.main()
