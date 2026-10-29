"""Vérifie les garanties de la démonstration serverless, sans contacter Vercel."""
import os
import re
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request


class DemoVercel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        code = ("from http.server import ThreadingHTTPServer; "
                "from api.demo import handler; "
                f"ThreadingHTTPServer(('127.0.0.1', {cls.port}), handler).serve_forever()")
        cls.serveur = subprocess.Popen([sys.executable, "-c", code], env=os.environ.copy(),
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f"http://127.0.0.1:{cls.port}/api/demo?__route="
        for _ in range(100):
            if cls.serveur.poll() is not None:
                raise RuntimeError("Le serveur de démonstration s'est arrêté")
            try:
                urllib.request.urlopen(cls.base + "tableau-de-bord", timeout=1).close()
                break
            except OSError:
                time.sleep(0.05)
        else:
            cls.serveur.terminate()
            cls.serveur.wait(timeout=5)
            raise RuntimeError("Le serveur de démonstration n'a pas démarré")

    @classmethod
    def tearDownClass(cls):
        cls.serveur.terminate()
        cls.serveur.wait(timeout=5)

    def test_navigation_et_simulateur(self):
        with urllib.request.urlopen(self.base + "tableau-de-bord") as reponse:
            contenu = reponse.read().decode("utf-8")
        self.assertIn("Mode démonstration publique", contenu)
        self.assertIn("Ne saisissez pas de données personnelles ni de secrets", contenu)
        self.assertIn("Chaque hôte est une rencontre", contenu)
        with urllib.request.urlopen(self.base + "simulateur") as reponse:
            contenu = reponse.read().decode("utf-8")
        csrf = re.search(r'name="csrf" value="([^"]+)"', contenu).group(1)
        cid = re.search(r'name="cid" value="([^"]+)"', contenu).group(1)
        donnees = urllib.parse.urlencode({"csrf": csrf, "cid": cid, "message": "Bonjour"}).encode()
        # Le serveur local ne fait pas lui-même les réécritures Vercel, donc
        # ne pas suivre la redirection ici : vérifier la page par sa route.
        class SansRedirection(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        ouvreur = urllib.request.build_opener(SansRedirection)
        with self.assertRaises(urllib.error.HTTPError) as contexte:
            ouvreur.open(self.base + "simulateur", data=donnees)
        self.assertEqual(contexte.exception.code, 303)
        with urllib.request.urlopen(self.base + "simulateur&cid=" + cid) as reponse:
            self.assertIn("Pax.", reponse.read().decode("utf-8"))

    def test_configuration_et_canaux_fermes(self):
        for chemin, corps in (("parametres", b"smtp_hote=exemple"),
                               ("whatsapp/enregistrer", b"wa_token=exemple"),
                               ("webhook/whatsapp", b"{}"), ("api/agent", b"{}")):
            with self.subTest(chemin=chemin), self.assertRaises(urllib.error.HTTPError) as contexte:
                urllib.request.urlopen(self.base + chemin, data=corps)
            self.assertEqual(contexte.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
