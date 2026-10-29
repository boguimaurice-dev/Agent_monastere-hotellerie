"""Tests d'intégration locaux : aucune communication externe ni donnée réelle."""
import datetime as dt
import concurrent.futures
import hashlib
import hmac
import http.client
import json
import os
import subprocess
import sqlite3
import sys
import re
import tempfile
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from hotellerie import config, seed, securite, metier, notify
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
            self.assertGreater(base_cli.valeur('SELECT COUNT(*) FROM connaissances'), 0)
            self.assertGreater(base_cli.valeur('SELECT COUNT(*) FROM chambres'), 0)
        finally:
            base_cli.fermer()

    def test_creation_compte_initialise_les_donnees_et_ne_revele_pas_le_jeton(self):
        env = dict(os.environ, HOTELLERIE_DATA_DIR=str(Path(self.tmp.name) / 'premier-demarrage'),
                   wa_verify_token='secret-a-ne-pas-afficher')
        subprocess.run([sys.executable, 'run.py', 'utilisateur', '--login', 'hotel',
                        '--motdepasse', 'motdepasse-test'], env=env, check=True, capture_output=True)
        base_cli = Base(Path(env['HOTELLERIE_DATA_DIR']) / 'hotellerie.db')
        try:
            self.assertGreater(base_cli.valeur('SELECT COUNT(*) FROM connaissances'), 0)
            self.assertEqual(base_cli.valeur('SELECT COUNT(*) FROM chambres'), 9)
        finally:
            base_cli.fermer()
        sortie = subprocess.run([sys.executable, 'run.py', 'whatsapp'], env=env,
                                check=True, capture_output=True, text=True).stdout
        self.assertNotIn('secret-a-ne-pas-afficher', sortie)

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
        self.assertEqual(demandes[0]['telephone'], '2250700000000')
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
        with patch('hotellerie.channels.whatsapp._requete', side_effect=[{'messages': [{'id': 'wamid.test'}]}, OSError('réseau')]):
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

    def test_reponse_humaine_depuis_conversation_sans_dossier(self):
        cid = '2250700000000'
        agent = Handler.agent
        agent.repondre(cid, 'Bonjour', telephone=cid)
        self.login()
        page = self.request('GET', '/conversations/' + cid)[2]
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        payload = {'csrf': csrf, 'message': 'Bienvenue, je vous réponds.'}
        status, _, _ = self.request('POST', '/conversations/' + cid + '/repondre', payload)
        self.assertEqual(status, 303)
        self.assertEqual(self.db.valeur('SELECT COUNT(*) FROM envois'), 0)
        self.request('POST', '/conversations/' + cid + '/relais', {'csrf': csrf, 'action': 'prendre'})
        page = self.request('GET', '/conversations/' + cid)[2]
        self.assertIn('Envoyer à l’hôte'.replace('’', "'"), page)
        status, _, _ = self.request('POST', '/conversations/' + cid + '/repondre', payload)
        self.assertEqual(status, 303)
        self.assertEqual(self.db.valeur('SELECT COUNT(*) FROM envois'), 1)
        self.assertIn('en attente d&#x27;envoi', self.request('GET', '/conversations/' + cid)[2])
        self.assertEqual(agent.repondre(cid, 'Allô ?', telephone=cid), '')
        config.definir_parametre(self.db, 'wa_token', 'test')
        config.definir_parametre(self.db, 'wa_phone_number_id', 'id')
        with patch('hotellerie.channels.whatsapp._requete', return_value={'messages': [{'id': 'wamid.test'}]}):
            resultat = whatsapp.rejouer(self.db)
        self.assertEqual(resultat['envoyes'], 1)
        self.assertIn('accepté par WhatsApp', self.request('GET', '/conversations/' + cid)[2])

    def test_urgence_met_en_relais_et_notification_liee(self):
        cid = '2250700000000'
        response = Handler.agent.repondre(cid, "C'est urgent, mon frère est très malade", telephone=cid)
        self.assertIn('secours', response.lower())
        self.assertEqual(self.db.valeur('SELECT humain_requis FROM conversations WHERE id=?', (cid,)), 1)
        self.assertEqual(self.db.valeur('SELECT conversation_id FROM notifications WHERE canal=?', ('dashboard',)), cid)
        self.login()
        page = self.request('GET', '/notifications')[2]
        self.assertIn('/conversations/' + cid, page)
        self.assertIn('URGENCE', page)

    def test_attribution_bloque_chevauchements_et_debordement_mois(self):
        chambre = self.db.valeur('SELECT id FROM chambres ORDER BY id LIMIT 1')
        a = metier.creer_demande(self.db, {'nom': 'A', 'date_arrivee': '2030-12-30',
                                          'date_depart': '2031-01-03', 'nb_personnes': 1})
        b = metier.creer_demande(self.db, {'nom': 'B', 'date_arrivee': '2030-12-31',
                                          'date_depart': '2031-01-02', 'nb_personnes': 1})
        with self.assertRaises(ValueError):
            metier.changer_statut(self.db, b, 'confirmee')
        metier.attribuer_chambre(self.db, a, chambre)
        normal = metier.verifier_disponibilite(self.db, '2030-12-30', '2031-01-03', 1)
        propre = metier.verifier_disponibilite(self.db, '2030-12-30', '2031-01-03', 1,
                                               exclure_demande_id=a)
        self.assertNotIn(chambre, [c['id'] for c in normal['chambres_libres']])
        self.assertIn(chambre, [c['id'] for c in propre['chambres_libres']])
        with self.assertRaises(ValueError):
            metier.attribuer_chambre(self.db, b, chambre)
        with self.assertRaises(ValueError):
            metier.creer_blocage(self.db, chambre, '2030-12-31', '2031-01-01')
        self.assertIn(('2030-12-31', chambre), metier.occupation_mois(self.db, 2030, 12)['cases'])
        self.assertIn(('2031-01-01', chambre), metier.occupation_mois(self.db, 2031, 1)['cases'])
        self.assertEqual(self.db.valeur('SELECT statut FROM demandes WHERE id=?', (b,)), 'en_attente')
        metier.attribuer_chambre(self.db, a, 0)
        self.assertEqual(self.db.valeur('SELECT statut FROM demandes WHERE id=?', (a,)), 'en_attente')
        metier.attribuer_chambre(self.db, b, chambre)
        self.assertEqual(self.db.valeur('SELECT statut FROM demandes WHERE id=?', (b,)), 'confirmee')

    def test_attribution_rejette_dates_blocage_et_capacite(self):
        chambre = self.db.valeur('SELECT id FROM chambres ORDER BY id LIMIT 1')
        metier.creer_blocage(self.db, chambre, '2031-02-01', '2031-02-03')
        dem = metier.creer_demande(self.db, {'nom': 'A', 'date_arrivee': '2031-02-01',
                                             'date_depart': '2031-02-03', 'nb_personnes': 1})
        with self.assertRaises(ValueError):
            metier.attribuer_chambre(self.db, dem, chambre)
        dem2 = metier.creer_demande(self.db, {'nom': 'B', 'date_arrivee': '2031-03-01',
                                              'date_depart': '2031-03-03', 'nb_personnes': 100})
        with self.assertRaises(ValueError):
            metier.attribuer_chambre(self.db, dem2, chambre)
        with self.assertRaises(ValueError):
            metier.creer_blocage(self.db, chambre, '2031-03-04', '2031-03-03')

    def test_migration_notifications_ancienne_base(self):
        chemin = Path(self.tmp.name) / 'ancienne.db'
        conn = sqlite3.connect(chemin)
        conn.execute("CREATE TABLE notifications (id INTEGER PRIMARY KEY, demande_id INTEGER, canal TEXT NOT NULL, destinataire TEXT NOT NULL DEFAULT '', sujet TEXT NOT NULL DEFAULT '', statut TEXT NOT NULL DEFAULT 'envoye', erreur TEXT NOT NULL DEFAULT '', horodatage TEXT NOT NULL DEFAULT '')")
        conn.commit()
        conn.close()
        ancienne = Base(chemin)
        try:
            notify._alerter(ancienne, 'Test', 'Corps', conversation_id='test-conversation')
            self.assertEqual(ancienne.valeur('SELECT conversation_id FROM notifications'), 'test-conversation')
        finally:
            ancienne.fermer()

    def test_apres_transmission_annulation_et_nouveau_sejour(self):
        agent, cid = Handler.agent, 'api-client'
        arrivee = dt.date.today() + dt.timedelta(days=90)
        depart = arrivee + dt.timedelta(days=3)
        for texte in ('Je voudrais venir en retraite', 'Jean Kouassi', 'Abidjan',
                      f'{arrivee.isoformat()} au {depart.isoformat()}', 'seul', 'rien de particulier', 'oui'):
            response = agent.repondre(cid, texte, canal='api')
        self.assertNotIn('24', response)
        self.assertIsNotNone(self.db.valeur('SELECT demande_id FROM conversations WHERE id=?', (cid,)))
        agent.repondre(cid, 'Merci beaucoup', canal='api')
        self.assertEqual(self.db.valeur('SELECT etat FROM conversations WHERE id=?', (cid,)), 'transmis')
        response = agent.repondre(cid, 'Je voudrais annuler', canal='api')
        self.assertIn('retirée', response)
        self.assertEqual(self.db.valeur('SELECT statut FROM demandes'), 'annulee')
        self.assertEqual(self.db.valeur('SELECT etat FROM conversations WHERE id=?', (cid,)), 'annule')
        self.assertTrue(self.db.valeur("SELECT COUNT(*) FROM notifications WHERE sujet LIKE '%Annulation%'") > 0)
        agent.repondre(cid, 'Je voudrais venir en retraite', canal='api')
        self.assertIsNone(self.db.valeur('SELECT demande_id FROM conversations WHERE id=?', (cid,)))

    def test_modification_apres_transmission_est_remise_a_un_frere(self):
        agent, cid = Handler.agent, 'api-client'
        arrivee = dt.date.today() + dt.timedelta(days=90)
        depart = arrivee + dt.timedelta(days=3)
        for texte in ('Je voudrais venir en retraite', 'Jean Kouassi', 'Abidjan',
                      f'{arrivee.isoformat()} au {depart.isoformat()}', 'seul', 'rien de particulier', 'oui'):
            agent.repondre(cid, texte, canal='api')
        response = agent.repondre(cid, 'Je souhaite modifier les dates', canal='api')
        self.assertIn('frères', response.lower())
        self.assertEqual(self.db.valeur('SELECT humain_requis FROM conversations WHERE id=?', (cid,)), 1)
        self.assertEqual(self.db.valeur('SELECT date_arrivee FROM demandes'), arrivee.isoformat())

    def test_whatsapp_diagnostic_prudent_et_sans_secret_affiche(self):
        config.definir_parametre(self.db, 'wa_verify_token', 'jeton-secret-test')
        config.definir_parametre(self.db, 'wa_token', 'jeton-test')
        config.definir_parametre(self.db, 'wa_phone_number_id', '123')
        config.definir_parametre(self.db, 'site_url', 'http://localhost')
        with patch('hotellerie.channels.whatsapp.verifier_compte', return_value={'ok': True, 'compte': {}}):
            bilan = whatsapp.diagnostic(self.db)
        self.assertFalse(bilan['pret'])
        self.assertFalse(whatsapp.url_https_publique('http://localhost'))
        self.assertFalse(whatsapp.url_https_publique('https://127.0.0.1'))
        self.assertTrue(whatsapp.url_https_publique('https://exemple.org'))
        config.definir_parametre(self.db, 'wa_dernier_diagnostic', json.dumps({'type': 'essai',
                                 'etapes': [{'etape': 'Message envoyé', 'ok': True}]}))
        self.login()
        page = self.request('GET', '/whatsapp')[2]
        self.assertNotIn('jeton-secret-test', page)
        self.assertNotIn('WhatsApp est prêt', page)
        self.assertNotIn('2250151740187', page)

    def test_dates_ne_deviendront_pas_des_numeros_de_telephone(self):
        for texte in ('2030-12-01 au 2030-12-04', 'le 12 10 2027', '12/10/2027'):
            self.assertEqual(comprehension.extraire_telephone(texte), '')
        self.assertEqual(comprehension.extraire_telephone('Mon numéro : 07 47 52 05 57'), '0747520557')
        self.assertEqual(comprehension.extraire_telephone('2030-12-01, téléphone 07 47 52 05 57'), '0747520557')

    def test_reponse_meta_sans_identifiant_reste_incertaine(self):
        config.definir_parametre(self.db, 'wa_token', 'test')
        config.definir_parametre(self.db, 'wa_phone_number_id', 'id')
        with patch('hotellerie.channels.whatsapp._requete', return_value={}):
            result = whatsapp.envoyer(self.db, '0700000000', 'Bonjour')
        self.assertFalse(result['ok'])
        self.assertIn('incertaine', result['erreur'])
        self.assertEqual(self.db.valeur('SELECT statut FROM envois'), 'echoue')

    def test_numero_et_message_invalides_ne_sont_pas_en_files(self):
        for numero, texte in (('', 'Bonjour'), ('abc', 'Bonjour'), ('0700000000', '  ')):
            self.assertFalse(whatsapp.envoyer(self.db, numero, texte)['ok'])
        self.assertEqual(self.db.valeur('SELECT COUNT(*) FROM envois'), 0)

    def test_attributions_concurrentes_une_seule_confirmee(self):
        chambre = self.db.valeur('SELECT id FROM chambres ORDER BY id LIMIT 1')
        demandes = [metier.creer_demande(self.db, {'nom': str(n), 'date_arrivee': '2032-03-01',
                                                    'date_depart': '2032-03-03', 'nb_personnes': 1})
                    for n in range(2)]
        barriere = threading.Barrier(2)
        def attribuer(identifiant):
            barriere.wait()
            try:
                metier.attribuer_chambre(self.db, identifiant, chambre)
                return True
            except ValueError:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            resultats = list(pool.map(attribuer, demandes))
        self.assertEqual(sum(resultats), 1)
        self.assertEqual(self.db.valeur("SELECT COUNT(*) FROM demandes WHERE statut='confirmee'"), 1)

    def test_requete_trop_grande_rejetee_avant_lecture(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.putrequest('POST', '/webhook/whatsapp')
            conn.putheader('Content-Length', str(1024 * 1024 + 1))
            conn.endheaders()
            self.assertEqual(conn.getresponse().status, 413)
        finally:
            conn.close()

    def test_delai_valide_est_annonce_uniquement_si_configure(self):
        config.definir_parametre(self.db, 'agent_delai_reponse', 'deux jours ouvrés')
        agent, cid = Handler.agent, 'api-delai'
        arrivee = dt.date.today() + dt.timedelta(days=90)
        depart = arrivee + dt.timedelta(days=3)
        for texte in ('Je voudrais venir en retraite', 'Jean Kouassi', 'Abidjan',
                      f'{arrivee.isoformat()} au {depart.isoformat()}', 'seul', 'rien de particulier', 'oui'):
            reponse = agent.repondre(cid, texte, canal='api')
        self.assertIn('deux jours ouvrés', reponse)
        self.assertIn('indicatif', reponse)

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
