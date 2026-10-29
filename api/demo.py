"""Démonstration publique Vercel, sans stockage durable ni canaux externes.

Ce point d'entrée n'est PAS un déploiement de production. Il ne donne accès
qu'aux données fictives et n'autorise de modification que dans le simulateur.
Chaque instance possède sa propre base temporaire, qui peut disparaître à tout
moment. Ne jamais y saisir de données personnelles ou de secrets.
"""
import os
import tempfile
import urllib.parse

# Utiliser une base isolée par processus et ne jamais ouvrir la base réelle.
os.environ["HOTELLERIE_DATA_DIR"] = tempfile.mkdtemp(prefix="hotellerie-demo-")

from hotellerie import config, seed, securite
from hotellerie.agent.engine import Agent
from hotellerie.channels import emailer, whatsapp
from hotellerie.db import Base
from hotellerie.web.server import Handler


def _parametre_demo(db, cle, defaut=""):
    """Ne jamais lire des identifiants de l'environnement de déploiement."""
    valeur = db.valeur("SELECT valeur FROM parametres WHERE cle = ?", (cle,))
    return str(valeur).strip() if valeur is not None and str(valeur).strip() else defaut


config.parametre = _parametre_demo


def _reseau_desactive(*args, **kwargs):
    raise OSError("Réseau externe désactivé dans la démonstration")


whatsapp._requete = _reseau_desactive
emailer.envoyer = lambda *args, **kwargs: {
    "ok": False, "ignore": True, "erreur": "Envoi désactivé dans la démonstration"
}
config.assurer_dossiers()
_db = Base(config.DB_PATH)
seed.initialiser(_db, demo=True, silencieux=True)
securite.creer_utilisateur(_db, "Équipe d’accueil (démo)", "demo", "ApercuTemporaire2026")
_session = securite.creer_session(_db, "demo", heures=24)
_utilisateur_demo = securite.session_valide(_db, _session)
_agent = Agent(_db)
_agent.repondre("demo-whatsapp", "Bonjour, je souhaite parler à un frère.",
                canal="whatsapp", telephone="2250700000000", nom_contact="Hôte de démonstration")


class handler(Handler):
    """Adaptateur HTTP pour Vercel ; à ne pas utiliser pour de vraies données."""
    db = _db
    agent = _agent

    def _dispatcher(self, methode):
        # La réécriture Vercel préserve le chemin public dans __route.
        url = urllib.parse.urlsplit(self.path)
        paires = urllib.parse.parse_qsl(url.query, keep_blank_values=True)
        route = next((valeur for cle, valeur in paires if cle == "__route"), None)
        if route is not None:
            query = urllib.parse.urlencode([(cle, valeur) for cle, valeur in paires if cle != "__route"])
            self.path = "/" + route.lstrip("/") + ("?" + query if query else "")
        elif url.path == "/api/demo":
            self.path = "/" + ("?" + url.query if url.query else "")
        super()._dispatcher(methode)

    def _utilisateur(self):
        # Ce compte public n'existe que dans ce serveur fictif. Il n'est pas
        # utilisé pour l'authentification du serveur de production.
        self._jeton = "session-demo-publique"
        return _utilisateur_demo

    def _utilisateur_silencieux(self):
        return _utilisateur_demo

    def _router(self):
        if self._chemin in ("/webhook/whatsapp", "/api/agent", "/connexion", "/deconnexion"):
            self._erreur(403, "Fonction désactivée dans la démonstration publique.")
            return
        if self._methode == "POST" and self._chemin != "/simulateur":
            self._erreur(403, "Démonstration en lecture seule : seul le simulateur est modifiable.")
            return
        super()._router()

    def _page(self, contenu, code=200):
        contenu = contenu.replace('<a href="/deconnexion">quitter</a>', 'démo publique')
        contenu = contenu.replace(
            '<main class="conteneur">',
            '<main class="conteneur"><div class="alerte alerte-info">'
            '<strong>Mode démonstration publique.</strong> Données fictives et temporaires, '
            'visibles par tous ; elles peuvent être réinitialisées à tout moment. '
            'Lecture seule sauf simulateur, aucun envoi externe. '
            'Ne saisissez pas de données personnelles ni de secrets.</div>', 1)
        super()._page(contenu, code)
