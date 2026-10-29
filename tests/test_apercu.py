"""L'aperçu est public, isolé et fonctionne sans cookies dans une iframe."""
import os
import re
import socket
import subprocess
import sys
import time
import unittest
import urllib.parse
import urllib.request


class Apercu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        env = dict(os.environ, PORT=str(cls.port))
        cls.serveur = subprocess.Popen(
            [sys.executable, "deploiement/apercu_demo.py"], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(100):
            if cls.serveur.poll() is not None:
                raise RuntimeError("Le serveur d'aperçu s'est arrêté au démarrage")
            try:
                with urllib.request.urlopen(cls.base + "/sante", timeout=1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            cls.serveur.terminate()
            cls.serveur.wait(timeout=5)
            raise RuntimeError("Le serveur d'aperçu n'a pas démarré")

    @classmethod
    def tearDownClass(cls):
        cls.serveur.terminate()
        cls.serveur.wait(timeout=5)

    def test_tableau_et_simulateur_sans_cookie(self):
        with urllib.request.urlopen(self.base + "/", timeout=5) as reponse:
            contenu = reponse.read().decode("utf-8")
            self.assertEqual(reponse.status, 200)
            self.assertIn("Tableau de bord", contenu)
            self.assertIn("Mode démonstration", contenu)
            self.assertIn("Ne saisissez pas de données personnelles", contenu)
            self.assertIsNone(reponse.headers.get("X-Frame-Options"))
        with urllib.request.urlopen(self.base + "/simulateur", timeout=5) as reponse:
            contenu = reponse.read().decode("utf-8")
        csrf = re.search(r'name="csrf" value="([^"]+)"', contenu).group(1)
        cid = re.search(r'name="cid" value="([^"]+)"', contenu).group(1)
        donnees = urllib.parse.urlencode({"csrf": csrf, "cid": cid, "message": "Bonjour"}).encode()
        with urllib.request.urlopen(self.base + "/simulateur", data=donnees, timeout=5) as reponse:
            self.assertIn("Pax.", reponse.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
