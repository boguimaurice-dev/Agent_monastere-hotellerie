#!/usr/bin/env python3
"""Aperçu local fictif, à ne jamais utiliser pour héberger de vraies données.

La base est temporaire et le compte de démonstration est public. L'intégration
iframe est autorisée uniquement dans ce serveur dédié à l'aperçu.
"""
import os
import sys
import tempfile
from pathlib import Path
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

with tempfile.TemporaryDirectory(prefix="hotellerie-apercu-") as dossier:
    port = int(os.environ.get("PORT", "8080"))
    # Ne pas importer les identifiants de l'environnement ou du fichier .env
    # dans cette démonstration publique.
    os.environ.clear()
    os.environ["HOTELLERIE_DATA_DIR"] = dossier
    from hotellerie import config, seed, securite
    os.environ.clear()  # config a pu lire un fichier .env local
    os.environ["HOTELLERIE_DATA_DIR"] = dossier
    from hotellerie.agent.engine import Agent
    from hotellerie.channels import emailer, whatsapp
    from hotellerie.db import Base
    from hotellerie.web.server import Handler

    # Même si un visiteur renseigne des paramètres, aucun message réel ne part.
    def reseau_desactive(*args, **kwargs):
        raise OSError("Réseau externe désactivé dans l'aperçu fictif")

    whatsapp._requete = reseau_desactive
    emailer.envoyer = lambda *args, **kwargs: {
        "ok": False, "ignore": True, "erreur": "Envoi désactivé dans l'aperçu fictif"
    }

    class ApercuHandler(Handler):
        # L'aperçu ne contient que des données fictives et reste public. Éviter
        # les cookies tiers, souvent bloqués lorsque l'aperçu est dans une iframe.
        # Le serveur normal conserve, lui, son authentification habituelle.
        session_demo = ""

        def _utilisateur(self):
            self._jeton = self.session_demo
            return securite.session_valide(self.db, self._jeton)

        def _utilisateur_silencieux(self):
            return securite.session_valide(self.db, self.session_demo)

        def _page(self, contenu, code=200):
            contenu = contenu.replace('<a href="/deconnexion">quitter</a>',
                                      '<span class="petit muted">Démo</span>')
            contenu = contenu.replace(
                '<main class="conteneur">',
                '<main class="conteneur"><div class="alerte alerte-info">'
                '<strong>Mode démonstration.</strong> Données fictives, '
                'aucun envoi externe. Ne saisissez pas de données personnelles.'
                '</div>', 1)
            super()._page(contenu, code)

        def send_header(self, keyword, value):
            if keyword.lower() == "x-frame-options":
                return
            if keyword.lower() == "content-security-policy":
                value = value.replace("frame-ancestors 'none'", "frame-ancestors *")
            super().send_header(keyword, value)

    config.assurer_dossiers()
    db = Base(config.DB_PATH)
    seed.initialiser(db, demo=True, silencieux=True)
    securite.creer_utilisateur(db, "Frère Hôtelier (démo)", "demo", "MaisonDemo2026")
    ApercuHandler.db = db
    ApercuHandler.agent = Agent(db)
    # Un échange fictif permet de découvrir le relais sans compte Meta.
    ApercuHandler.agent.repondre("demo-whatsapp", "Bonjour, je souhaite parler à un frère.",
                                canal="whatsapp", telephone="2250700000000",
                                nom_contact="Hôte de démonstration")
    ApercuHandler.session_demo = securite.creer_session(db, "demo", heures=24 * 365)
    serveur = ThreadingHTTPServer(("0.0.0.0", port), ApercuHandler)
    print("Aperçu fictif : accès direct, aucune donnée réelle ni envoi externe", flush=True)
    try:
        serveur.serve_forever()
    finally:
        serveur.server_close()
        db.fermer()
