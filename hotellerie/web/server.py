# -*- coding: utf-8 -*-
"""
Le serveur du tableau de bord et des webhooks.

Tout repose sur ``http.server`` : aucune dépendance, un seul processus, une
seule base. Pensé pour une petite machine et une connexion intermittente.

Ce qui est protégé l'est réellement : sessions signées par un jeton aléatoire,
CSRF sur chaque formulaire, limitation des tentatives, en-têtes de sécurité,
échappement systématique des données affichées.
"""
from __future__ import annotations

import csv
import datetime as dt
import hmac
import io
import json
import logging
import re
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import config, knowledge, metier, notify, securite
from ..agent.engine import Agent
from ..channels import emailer, whatsapp
from . import vues
from .templates import esc

log = logging.getLogger(__name__)

COOKIE = "hotellerie_session"
LIMITE_CORPS = 1024 * 1024


class RequeteTropLongue(Exception):
    pass


def _maintenant() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Handler(BaseHTTPRequestHandler):
    """Un seul gestionnaire, un routeur explicite, aucune magie."""

    db = None          # injecté par demarrer()
    agent = None       # injecté par demarrer()
    server_version = "Hotellerie/" + config.VERSION
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------
    # Entrées
    # ------------------------------------------------------------------
    def do_GET(self):
        self._dispatcher("GET")

    def do_POST(self):
        self._dispatcher("POST")

    def do_HEAD(self):
        self._methode = "HEAD"
        self._repondre(200, b"", "text/plain")

    def log_message(self, format, *args):  # noqa: A002
        log.debug("%s — " + format, self.address_string(), *args)

    def _dispatcher(self, methode: str) -> None:
        self._methode = methode
        try:
            url = urllib.parse.urlsplit(self.path)
            chemin = url.path or "/"
            if len(chemin) > 1:
                chemin = chemin.rstrip("/")
            self._url = url
            self._chemin = chemin
            self._query = {k: v[-1] for k, v in
                           urllib.parse.parse_qs(url.query, keep_blank_values=True).items()}
            self._brut = self._lire_corps() if methode == "POST" else b""
            self._json = {}
            if methode == "POST":
                type_contenu = (self.headers.get("Content-Type") or "").lower()
                if "application/json" in type_contenu:
                    try:
                        charge = json.loads(self._brut.decode("utf-8") or "{}")
                        self._json = charge if isinstance(charge, dict) else {}
                    except ValueError:
                        self._json = {}
                    self._post = self._json
                else:
                    paires = urllib.parse.parse_qs(self._brut.decode("utf-8", "replace"),
                                                   keep_blank_values=True)
                    self._post = {k: v[-1] for k, v in paires.items()}
            else:
                self._post = {}
            self._router()
        except BrokenPipeError:
            pass
        except RequeteTropLongue:
            self.close_connection = True
            self._repondre(413, b"Requete trop volumineuse", "text/plain; charset=utf-8")
        except Exception:
            log.exception("Erreur pendant le traitement de %s", self.path)
            try:
                self._erreur(500, "Une erreur interne est survenue. Le journal contient le détail.")
            except Exception:
                pass

    def _lire_corps(self) -> bytes:
        try:
            longueur = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            longueur = 0
        if longueur <= 0:
            return b""
        if longueur > LIMITE_CORPS:
            raise RequeteTropLongue()
        return self.rfile.read(longueur)

    # ------------------------------------------------------------------
    # Réponses
    # ------------------------------------------------------------------
    def _repondre(self, code: int, corps: bytes, type_contenu: str = "text/html; charset=utf-8",
                  entetes=None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; "
                         "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                         "form-action 'self'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        for cle, valeur in (entetes or {}).items():
            self.send_header(cle, valeur)
        self.end_headers()
        if self._methode != "HEAD":
            self.wfile.write(corps)

    def _page(self, html: str, code: int = 200) -> None:
        self._repondre(code, html.encode("utf-8"))

    def _erreur(self, code: int, message: str) -> None:
        html = vues.page("Erreur", f"<h1>Erreur {code}</h1><p>{esc(message)}</p>",
                         utilisateur=self._utilisateur_silencieux())
        self._page(html, code)

    def _json_reponse(self, donnees, code: int = 200) -> None:
        self._repondre(code, json.dumps(donnees, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

    def _rediriger(self, destination: str) -> None:
        self._repondre(303, b"", "text/plain", {"Location": destination})

    def _flash(self, chemin: str, message: str = "", erreur: str = "") -> None:
        parametres = {}
        if message:
            parametres["message"] = message
        if erreur:
            parametres["erreur"] = erreur
        query = urllib.parse.urlencode(parametres)
        self._rediriger(chemin + (("?" + query) if query else ""))

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------
    def _cookies(self) -> dict:
        brut = self.headers.get("Cookie") or ""
        resultat = {}
        for morceau in brut.split(";"):
            if "=" in morceau:
                cle, valeur = morceau.split("=", 1)
                resultat[cle.strip()] = valeur.strip()
        return resultat

    def _utilisateur(self):
        self._jeton = self._cookies().get(COOKIE, "")
        self._utilisateur_cache = securite.session_valide(self.db, self._jeton)
        return self._utilisateur_cache

    def _utilisateur_silencieux(self):
        try:
            return securite.session_valide(self.db, self._cookies().get(COOKIE, ""))
        except Exception:
            return None

    def _csrf(self) -> str:
        return securite.jeton_csrf(getattr(self, "_jeton", ""))

    def _poser_cookie(self, jeton: str) -> None:
        securise = (self.headers.get("X-Forwarded-Proto", "").lower() == "https"
                    or config.drapeau("HOTELLERIE_COOKIE_SECURE", False))
        valeur = (f"{COOKIE}={jeton}; Path=/; HttpOnly; SameSite=Lax"
                  + ("; Secure" if securise else ""))
        self._cookie_a_poser = valeur

    # ------------------------------------------------------------------
    # Routeur
    # ------------------------------------------------------------------
    def _router(self) -> None:
        chemin = self._chemin

        # --- routes publiques -----------------------------------------
        if chemin in ("/", ""):
            self._rediriger("/tableau-de-bord")
            return
        if chemin == "/sante":
            self._sante()
            return
        if chemin == "/connexion":
            self._route_connexion()
            return
        if chemin == "/deconnexion":
            securite.detruire_session(self.db, self._cookies().get(COOKIE, ""))
            self._repondre(303, b"", "text/plain",
                           {"Location": "/connexion",
                            "Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
            return
        if chemin == "/webhook/whatsapp":
            self._webhook()
            return
        if chemin == "/api/agent":
            self._api_agent()
            return

        # --- tout le reste exige un compte ----------------------------
        utilisateur = self._utilisateur()
        if not utilisateur:
            self._rediriger("/connexion")
            return
        if self._methode == "POST" and not securite.verifier_csrf(
                getattr(self, "_jeton", ""), self._post.get("csrf", "")):
            self._erreur(403, "Jeton de formulaire invalide ou expiré. Rechargez la page.")
            return

        if self._methode == "GET":
            self._route_get(utilisateur)
        else:
            self._route_post(utilisateur)

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------
    def _route_get(self, utilisateur) -> None:
        chemin = self._chemin
        message = self._query.get("message", "")
        erreur = self._query.get("erreur", "")
        db = self.db

        if chemin == "/tableau-de-bord":
            self._page(vues.tableau_de_bord(db, utilisateur, message, erreur))
            return

        if chemin == "/demandes":
            self._page(vues.demandes_liste(db, utilisateur,
                                           self._query.get("statut", ""),
                                           self._query.get("q", ""), message, erreur))
            return

        if chemin == "/demandes/nouveau":
            self._page(vues.demande_nouvelle(db, utilisateur, self._csrf(), message=message, erreur=erreur))
            return

        if chemin == "/demandes/export.csv":
            self._export_csv()
            return

        correspondance = __import__("re").match(r"^/demandes/(\d+)$", chemin)
        if correspondance:
            dem = metier.demande(db, int(correspondance.group(1)))
            if not dem:
                self._erreur(404, "Cette demande n'existe pas.")
                return
            self._page(vues.demande_detail(db, utilisateur, dem, self._csrf(), message, erreur))
            return

        if chemin == "/calendrier":
            aujourdhui = metier.aujourdhui()
            try:
                annee = int(self._query.get("annee") or aujourdhui.year)
                mois = int(self._query.get("mois") or aujourdhui.month)
            except ValueError:
                annee, mois = aujourdhui.year, aujourdhui.month
            mois = min(12, max(1, mois))
            self._page(vues.calendrier(db, utilisateur, annee, mois, self._csrf(), message, erreur))
            return

        if chemin == "/connaissances":
            self._page(vues.connaissances_liste(db, utilisateur, self._query.get("q", ""),
                                                self._query.get("manquantes") == "1",
                                                message, erreur))
            return

        if chemin == "/connaissances/nouvelle":
            self._page(vues.connaissance_fiche(db, utilisateur, None, self._csrf(), message, erreur))
            return

        if chemin == "/connaissances/export.json":
            donnees = json.dumps(knowledge.exporter(db), ensure_ascii=False, indent=2)
            self._repondre(200, donnees.encode("utf-8"), "application/json; charset=utf-8",
                           {"Content-Disposition": "attachment; filename=base_connaissances.json"})
            return

        correspondance = __import__("re").match(r"^/connaissances/(\d+)$", chemin)
        if correspondance:
            fiche = knowledge.fiche(db, int(correspondance.group(1)))
            if not fiche:
                self._erreur(404, "Cette fiche n'existe pas.")
                return
            self._page(vues.connaissance_fiche(db, utilisateur, fiche, self._csrf(), message, erreur))
            return

        if chemin == "/simulateur":
            cid = self._query.get("cid", "")
            if not re.fullmatch(r"sim-[0-9a-f]{8}", cid) or self._query.get("nouveau"):
                cid = "sim-" + secrets.token_hex(4)
            self._page(vues.simulateur(db, utilisateur, cid, self._csrf(), message, erreur))
            return

        if chemin == "/conversations":
            self._page(vues.conversations_liste(db, utilisateur, message, erreur))
            return

        correspondance = __import__("re").match(r"^/conversations/(.+)$", chemin)
        if correspondance:
            conv = db.ligne("SELECT * FROM conversations WHERE id = ?",
                            (urllib.parse.unquote(correspondance.group(1)),))
            if not conv:
                self._erreur(404, "Cet échange n'existe pas.")
                return
            self._page(vues.conversation_detail(db, utilisateur, conv, self._csrf(), message, erreur))
            return

        if chemin == "/notifications":
            self._page(vues.notifications_liste(db, utilisateur, message, erreur))
            return

        if chemin == "/journal":
            self._page(vues.journal_liste(db, utilisateur))
            return

        if chemin == "/parametres":
            self._page(vues.parametres(db, utilisateur, self._csrf(), message, erreur))
            return

        if chemin == "/whatsapp":
            self._page(vues.whatsapp_page(db, utilisateur, self._csrf(), message, erreur))
            return

        self._erreur(404, "Page introuvable.")

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------
    def _route_post(self, utilisateur) -> None:
        import re
        chemin = self._chemin
        acteur = utilisateur.get("login") or "web"
        db = self.db

        if chemin == "/demandes/nouveau":
            donnees = {cle: self._post.get(cle, "") for cle in
                       ("nom", "prenom", "provenance", "telephone", "email", "type_sejour",
                        "date_arrivee", "date_depart", "nb_personnes", "nb_hommes", "nb_femmes",
                        "regime_alimentaire", "accessibilite", "besoin_note", "message")}
            donnees["source"] = "saisie"
            if not donnees["nom"].strip():
                self._flash("/demandes/nouveau", erreur="Le nom est nécessaire.")
                return
            identifiant = metier.creer_demande(db, donnees)
            db.journal(acteur, "demande_saisie", str(identifiant), donnees["nom"])
            notify.notifier_hoteliers(db, identifiant, motif="saisie_manuelle")
            self._flash(f"/demandes/{identifiant}", message="Demande enregistrée et transmise aux frères.")
            return

        correspondance = re.match(r"^/demandes/(\d+)/(statut|chambre|notes|repondre|notifier|supprimer)$", chemin)
        if correspondance:
            identifiant = int(correspondance.group(1))
            action = correspondance.group(2)
            dem = metier.demande(db, identifiant)
            if not dem:
                self._erreur(404, "Cette demande n'existe pas.")
                return
            if action == "statut":
                statut = self._post.get("statut", "")
                try:
                    metier.changer_statut(db, identifiant, statut, acteur)
                    self._flash(f"/demandes/{identifiant}", message="Décision enregistrée.")
                except ValueError as exc:
                    self._flash(f"/demandes/{identifiant}", erreur=str(exc))
                return
            if action == "chambre":
                try:
                    chambre_id = self._post.get("chambre_id") or 0
                    metier.attribuer_chambre(db, identifiant, chambre_id, acteur)
                    self._flash(f"/demandes/{identifiant}", message=("Chambre attribuée." if str(chambre_id) != "0" else "Attribution retirée."))
                except ValueError as exc:
                    self._flash(f"/demandes/{identifiant}", erreur=str(exc))
                return
            if action == "notes":
                metier.mettre_a_jour(db, identifiant, {"notes_internes": self._post.get("notes_internes", "")})
                db.journal(acteur, "notes_modifiees", str(identifiant))
                self._flash(f"/demandes/{identifiant}", message="Notes enregistrées.")
                return
            if action == "repondre":
                self._repondre_hote(acteur, dem)
                return
            if action == "notifier":
                notify.notifier_hoteliers(db, identifiant, motif="renvoi_manuel")
                db.journal(acteur, "fiche_renvoyee", str(identifiant))
                self._flash(f"/demandes/{identifiant}", message="Fiche retransmise aux frères.")
                return
            if action == "supprimer":
                metier.supprimer_demande(db, identifiant)
                db.journal(acteur, "demande_supprimee", str(identifiant))
                self._flash("/demandes", message="Demande supprimée.")
                return

        if chemin == "/chambres":
            metier.enregistrer_chambre(db, self._post)
            db.journal(acteur, "chambre_enregistree", self._post.get("nom", ""))
            self._flash("/calendrier", message="Chambre enregistrée.")
            return

        if chemin == "/blocages":
            if self._post.get("chambre_id") and self._post.get("date_debut") and self._post.get("date_fin"):
                try:
                    metier.creer_blocage(db, self._post["chambre_id"], self._post["date_debut"],
                                         self._post["date_fin"], self._post.get("motif", ""))
                    db.journal(acteur, "blocage_cree", self._post.get("chambre_id", ""))
                    self._flash("/calendrier", message="Indisponibilité enregistrée.")
                except ValueError as exc:
                    self._flash("/calendrier", erreur=str(exc))
            else:
                self._flash("/calendrier", erreur="Chambre et dates nécessaires.")
            return

        correspondance = re.match(r"^/blocages/(\d+)/supprimer$", chemin)
        if correspondance:
            metier.supprimer_blocage(db, int(correspondance.group(1)))
            self._flash("/calendrier", message="Indisponibilité retirée.")
            return

        correspondance = re.match(r"^/connaissances/(nouvelle|\d+)(/supprimer)?$", chemin)
        if correspondance:
            if correspondance.group(2):
                knowledge.supprimer(db, int(correspondance.group(1)))
                db.journal(acteur, "fiche_supprimee", correspondance.group(1))
                self._flash("/connaissances", message="Fiche supprimée.")
                return
            identifiant = None if correspondance.group(1) == "nouvelle" else int(correspondance.group(1))
            donnees = {
                "id": identifiant,
                "cle": self._post.get("cle", ""),
                "categorie": self._post.get("categorie", "divers"),
                "question": self._post.get("question", ""),
                "mots_cles": self._post.get("mots_cles", ""),
                "reponse": self._post.get("reponse", ""),
                "priorite": self._post.get("priorite", 5),
                "active": 1 if self._post.get("active") else (0 if identifiant else 1),
            }
            if not donnees["question"].strip():
                self._flash(f"/connaissances/{identifiant or 'nouvelle'}", erreur="La question est nécessaire.")
                return
            existait = bool(donnees["cle"].strip()) and bool(knowledge.fiche(db, donnees["cle"].strip()))
            knowledge.enregistrer(db, donnees)
            db.journal(acteur, "fiche_enregistree", donnees["cle"])
            if identifiant is None and existait:
                self._flash("/connaissances",
                            message="Cette clé existait déjà : la fiche a été mise à jour, sans doublon.")
            else:
                self._flash("/connaissances", message="Fiche enregistrée.")
            return

        if chemin == "/simulateur":
            cid = (self._post.get("cid") or "").strip()
            if not re.fullmatch(r"sim-[0-9a-f]{8}", cid):
                self._erreur(400, "Identifiant de simulation invalide.")
                return
            texte = (self._post.get("message") or "").strip()
            if texte:
                self.agent.repondre(cid, texte, canal="terminal")
            self._rediriger("/simulateur?cid=" + urllib.parse.quote(cid))
            return

        correspondance = re.match(r"^/conversations/(.+)/(relais|repondre)$", chemin)
        if correspondance:
            conversation = urllib.parse.unquote(correspondance.group(1))
            if correspondance.group(2) == "repondre":
                self._repondre_conversation(acteur, conversation)
                return
            prendre = self._post.get("action") != "rendre"
            # Même verrou que le moteur pour éviter une réponse simultanée
            # pendant la bascule de relais.
            with self.agent._verrou:
                self._basculer_relais(db, acteur, conversation, prendre)
            return

        if chemin == "/parametres":
            for cle in vues.PARAMETRES_CLEFS:
                if cle not in self._post:
                    continue
                valeur = self._post.get(cle, "")
                if cle in vues.PARAMETRES_SECRETS and valeur == vues.MASQUE:
                    continue
                config.definir_parametre(db, cle, valeur)
            if any(cle.startswith("wa_") for cle in self._post):
                config.definir_parametre(db, "wa_dernier_diagnostic", "")
            db.journal(acteur, "parametres_modifies", "")
            self._flash("/parametres", message="Paramètres enregistrés.")
            return

        if chemin.startswith("/whatsapp/"):
            action = chemin.rsplit("/", 1)[-1]

            if action == "enregistrer":
                for cle in vues.WHATSAPP_CLEFS:
                    if cle not in self._post:
                        continue
                    valeur = self._post.get(cle, "")
                    if cle in vues.WHATSAPP_SECRETS and valeur == vues.MASQUE:
                        continue
                    config.definir_parametre(db, cle, valeur.strip())
                config.definir_parametre(db, "wa_dernier_diagnostic", "")
                db.journal(acteur, "whatsapp_parametres", "")
                self._flash("/whatsapp", message="Réglages WhatsApp enregistrés.")
                return

            if action == "verifier":
                releve = whatsapp.diagnostic(db)
                releve["horodatage"] = _maintenant()
                releve["type"] = "configuration"
                config.definir_parametre(db, "wa_dernier_diagnostic",
                                         json.dumps(releve, ensure_ascii=False))
                db.journal(acteur, "whatsapp_diagnostic", "",
                           "pret" if releve.get("pret") else "incomplet")
                if releve.get("pret"):
                    self._flash("/whatsapp", message="Contrôles préalables satisfaits. Testez maintenant le webhook et un échange réel.")
                else:
                    self._flash("/whatsapp",
                                erreur="Le diagnostic n'est pas encore complet : lisez le relevé ci-dessous.")
                return

            if action == "tester":
                numero = (self._post.get("numero") or "").strip()
                texte = (self._post.get("message") or "").strip()
                if not texte:
                    self._flash("/whatsapp", erreur="Le message d'essai est vide.")
                    return
                resultat = whatsapp.envoyer(db, numero, texte)
                config.definir_parametre(db, "wa_dernier_diagnostic", json.dumps({
                    "horodatage": _maintenant(),
                    "type": "essai",
                    "etapes": [{
                        "etape": "Message d'essai vers " + (whatsapp.afficher_numero(numero) or "—"),
                        "ok": bool(resultat.get("ok")),
                        "detail": ("parti" if resultat.get("ok")
                                   else (resultat.get("erreur") or "envoi impossible")),
                    }],
                    "compte": None,
                }, ensure_ascii=False))
                db.journal(acteur, "whatsapp_essai", whatsapp.normaliser_numero(numero),
                           "envoye" if resultat.get("ok") else (resultat.get("erreur") or "")[:200])
                if resultat.get("ok"):
                    self._flash("/whatsapp", message="Message d'essai envoyé. Vérifiez votre téléphone.")
                else:
                    self._flash("/whatsapp", erreur=resultat.get("erreur") or "Envoi impossible.")
                return

            if action == "rejouer":
                resultat = whatsapp.rejouer(db)
                db.journal(acteur, "whatsapp_rejeu", str(resultat.get("envoyes", 0)),
                           f"restants={resultat.get('restants', 0)}")
                if resultat.get("envoyes"):
                    self._flash("/whatsapp",
                                message=f"{resultat['envoyes']} message(s) envoyé(s), "
                                        f"{resultat.get('restants', 0)} encore en attente.")
                else:
                    self._flash("/whatsapp",
                                erreur=resultat.get("erreur") or "Aucun message n'a pu partir.")
                return

        self._erreur(404, "Action inconnue.")

    def _basculer_relais(self, db, acteur, conversation, prendre):
        conv = db.ligne("SELECT donnees, etat FROM conversations WHERE id = ?", (conversation,))
        if not conv:
            self._erreur(404, "Conversation introuvable.")
            return
        try:
            donnees = json.loads(conv["donnees"] or "{}")
            if not isinstance(donnees, dict):
                donnees = {}
        except (ValueError, TypeError):
            donnees = {}
        donnees["humain_requis"] = int(prendre)
        if not prendre and donnees.get("etape") == "relais":
            donnees["etape"] = "accueil"
            donnees["relances"] = 0
        db.executer("UPDATE conversations SET humain_requis = ?, donnees = ?, etat = ? WHERE id = ?",
                    (int(prendre), json.dumps(donnees, ensure_ascii=False),
                     donnees.get("etape", conv["etat"]), conversation))
        db.journal(acteur, "relais_humain" if prendre else "relais_rendu", conversation)
        self._flash("/conversations/" + urllib.parse.quote(conversation, safe=""),
                    message="Vous avez la main. L'agent se tait." if prendre
                    else "La parole est rendue à l'agent.")

    def _repondre_conversation(self, acteur, conversation):
        db = self.db
        chemin = "/conversations/" + urllib.parse.quote(conversation, safe="")
        texte = (self._post.get("message") or "").strip()
        if not texte or len(texte) > 4000:
            self._flash(chemin, erreur="Le message doit contenir entre 1 et 4 000 caractères.")
            return
        with self.agent._verrou:
            conv = db.ligne("SELECT * FROM conversations WHERE id = ?", (conversation,))
            if not conv:
                self._erreur(404, "Conversation introuvable.")
                return
            if conv["canal"] != "whatsapp" or not conv.get("telephone"):
                self._flash(chemin, erreur="La réponse directe est réservée aux échanges WhatsApp avec numéro connu.")
                return
            if not conv["humain_requis"]:
                self._flash(chemin, erreur="Prenez d'abord le relais pour éviter deux réponses simultanées.")
                return
            resultat = whatsapp.envoyer(db, conv["telephone"], texte,
                                        demande_id=conv.get("demande_id"), conversation_id=conversation)
            envoi_id = resultat.get("envoi_id") or 0
            if envoi_id:
                db.executer("INSERT INTO messages (conversation_id, direction, canal, corps, meta) "
                            "VALUES (?, 'sortant', 'whatsapp', ?, ?)",
                            (conversation, texte, json.dumps({"auteur": acteur, "envoi_id": envoi_id})))
                db.executer("UPDATE conversations SET maj = datetime('now','localtime') WHERE id = ?",
                            (conversation,))
            db.journal(acteur, "reponse_conversation", conversation,
                       "accepte_meta" if resultat.get("ok") else "non_envoye")
        if resultat.get("ok"):
            self._flash(chemin, message="Message accepté par WhatsApp. Vérifiez sa réception auprès de l'hôte.")
        elif envoi_id:
            self._flash(chemin, erreur="Message non envoyé. Il reste dans la file WhatsApp : "
                        + (resultat.get("erreur") or "envoi impossible"))
        else:
            self._flash(chemin, erreur="Message non enregistré ni envoyé : "
                        + (resultat.get("erreur") or "envoi impossible"))

    def _repondre_hote(self, acteur: str, dem) -> None:
        db = self.db
        texte = (self._post.get("message") or "").strip()
        if not texte:
            self._flash(f"/demandes/{dem['id']}", erreur="Le message est vide.")
            return
        sujet = f"Votre demande {dem.get('reference') or ''} — Hôtellerie du monastère"
        conf_wa = whatsapp.configuration(db)
        whatsapp_pret = bool(conf_wa.get("token") and conf_wa.get("phone_number_id"))
        if dem.get("telephone") and whatsapp_pret:
            resultat = whatsapp.envoyer(db, dem["telephone"], texte, demande_id=dem["id"],
                                        conversation_id=dem.get("conversation_id") or "")
            canal, destinataire = "whatsapp", whatsapp.afficher_numero(dem["telephone"])
        elif dem.get("email"):
            # Sans WhatsApp configuré, le courriel reste un canal réel : on ne
            # laisse pas une réponse en suspens faute de jeton Meta.
            resultat = emailer.envoyer(db, dem["email"], sujet, texte)
            canal, destinataire = "email", dem["email"]
        elif dem.get("telephone"):
            resultat = whatsapp.envoyer(db, dem["telephone"], texte, demande_id=dem["id"],
                                        conversation_id=dem.get("conversation_id") or "")
            canal, destinataire = "whatsapp", whatsapp.afficher_numero(dem["telephone"])
        else:
            resultat = {"ok": False, "ignore": True, "erreur": "aucun contact pour cet hôte"}
            canal, destinataire = "dashboard", ""
        statut = "envoye" if resultat.get("ok") else ("ignore" if resultat.get("ignore") else "echoue")
        db.executer(
            "INSERT INTO notifications (demande_id, canal, destinataire, sujet, statut, erreur) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (dem["id"], canal, destinataire, "Réponse de la maison", statut,
             resultat.get("erreur", "")))
        envoi_id = resultat.get("envoi_id") or 0
        if dem.get("conversation_id") and (resultat.get("ok") or envoi_id):
            meta = {"auteur": acteur}
            if envoi_id:
                meta["envoi_id"] = envoi_id
            else:
                meta["statut"] = "envoye"
            db.executer(
                "INSERT INTO messages (conversation_id, direction, canal, corps, meta) VALUES (?, 'sortant', ?, ?, ?)",
                (dem["conversation_id"], canal, texte, json.dumps(meta)))
        db.journal(acteur, "reponse_hote", str(dem["id"]), statut)
        if statut == "envoye":
            self._flash(f"/demandes/{dem['id']}", message="Réponse envoyée à l'hôte.")
        else:
            self._flash(f"/demandes/{dem['id']}",
                        erreur=f"Réponse non envoyée ({resultat.get('erreur') or 'canal indisponible'}). "
                               "Elle reste consignée dans les notifications.")

    # ------------------------------------------------------------------
    # Connexion
    # ------------------------------------------------------------------
    def _route_connexion(self) -> None:
        db = self.db
        ip = self.client_address[0] if self.client_address else ""
        if self._methode == "POST":
            login = (self._post.get("login") or "").strip().lower()
            motdepasse = self._post.get("motdepasse") or ""
            if securite.connexion_bloquee(db, login, ip):
                self._page(vues.connexion(
                    erreur="Trop de tentatives. Patientez quinze minutes avant de réessayer."), 429)
                return
            utilisateur = securite.authentifier(db, login, motdepasse, ip)
            if not utilisateur:
                db.journal("web", "connexion_echouee", login, ip)
                self._page(vues.connexion(erreur="Identifiant ou mot de passe incorrect."), 401)
                return
            jeton = securite.creer_session(db, utilisateur["login"], ip,
                                           self.headers.get("User-Agent", ""))
            db.journal(utilisateur["login"], "connexion", "", ip)
            self._poser_cookie(jeton)
            self._repondre(303, b"", "text/plain", {
                "Location": "/tableau-de-bord",
                "Set-Cookie": self._cookie_a_poser,
            })
            return
        if self._utilisateur_silencieux():
            self._rediriger("/tableau-de-bord")
            return
        self._page(vues.connexion(self._query.get("message", ""), self._query.get("erreur", "")))

    # ------------------------------------------------------------------
    # Webhook WhatsApp
    # ------------------------------------------------------------------
    def _webhook(self) -> None:
        db = self.db
        if self._methode == "GET":
            jeton = config.parametre(db, "wa_verify_token", config.VERIFY_TOKEN_DEFAUT)
            ok, defi = whatsapp.verifier_webhook(self._query, jeton)
            if ok:
                self._repondre(200, defi.encode("utf-8"), "text/plain; charset=utf-8")
            else:
                log.warning("Webhook : jeton de vérification refusé (%s)", self.client_address[0])
                self._repondre(403, b"Jeton de verification invalide", "text/plain; charset=utf-8")
            return

        secret = config.parametre(db, "wa_app_secret", "")
        signature = self.headers.get("X-Hub-Signature-256", "")
        if not secret or not securite.verifier_signature_meta(secret, self._brut, signature):
            log.warning("Webhook : signature invalide")
            self._repondre(403, b"Signature invalide", "text/plain; charset=utf-8")
            return
        try:
            charge = json.loads(self._brut.decode("utf-8") or "{}")
        except ValueError:
            charge = {}
        for message in whatsapp.extraire_messages(charge):
            identifiant = message.get("id")
            if not message.get("de") or not identifiant:
                continue
            if not db.reserver_message_webhook(identifiant):
                continue
            try:
                if not message.get("texte"):
                    reponse = ("Pax. Je ne peux pas ouvrir les messages vocaux ni les images. "
                               "Écrivez-moi quelques mots, ou appelez l'hôtellerie au "
                               + config.TEL_HOTELLERIE + ".")
                else:
                    reponse = self.agent.repondre(message["de"], message["texte"], canal="whatsapp",
                                                  telephone=message["de"],
                                                  nom_contact=message.get("nom", ""))
                if reponse:
                    whatsapp.envoyer(db, message["de"], reponse,
                                     conversation_id=message["de"])
            except Exception:
                db.executer("DELETE FROM webhook_messages WHERE message_id = ?", (identifiant,))
                raise
        self._repondre(200, b"ok", "text/plain; charset=utf-8")

    # ------------------------------------------------------------------
    # API JSON
    # ------------------------------------------------------------------
    def _api_agent(self) -> None:
        db = self.db
        cle = config.parametre(db, "api_cle", "") or config.env("HOTELLERIE_API_CLE")
        if cle:
            fournie = self.headers.get("X-API-Key") or ""
            if not hmac.compare_digest(str(fournie), str(cle)):
                self._json_reponse({"erreur": "clé d'API invalide"}, 403)
                return
        elif not config.drapeau_parametre(db, "api_ouverte", False):
            self._json_reponse({"erreur": "API fermée : renseignez une clé dans Paramètres."}, 403)
            return
        if self._methode != "POST":
            self._json_reponse({"erreur": "Utilisez POST."}, 405)
            return
        message = str(self._json.get("message") or self._post.get("message") or "").strip()
        de = str(self._json.get("de") or self._post.get("de") or "").strip()
        if not message:
            self._json_reponse({"erreur": "Le champ « message » est requis."}, 400)
            return
        conversation = str(self._json.get("conversation") or "").strip()
        if conversation and not re.fullmatch(r"api-[a-zA-Z0-9_-]{1,80}", conversation):
            self._json_reponse({"erreur": "Identifiant de conversation invalide."}, 400)
            return
        if not conversation:
            conversation = "api-" + (whatsapp.normaliser_numero(de) or secrets.token_hex(16))
        reponse = self.agent.repondre(conversation, message, canal="api", telephone=de)
        self._json_reponse({"reponse": reponse, "conversation": conversation, "canal": "api"})

    # ------------------------------------------------------------------
    # Santé et export
    # ------------------------------------------------------------------
    def _sante(self) -> None:
        db = self.db
        base_ok = True
        try:
            db.valeur("SELECT 1")
        except Exception:
            base_ok = False
        self._json_reponse({
            "etat": "ok" if base_ok else "degrade",
            "heure": _maintenant(),
            "version": config.VERSION,
            "agent_actif": config.drapeau_parametre(db, "agent_actif", True),
            "whatsapp_configure": bool(config.parametre(db, "wa_token", "")
                                       and config.parametre(db, "wa_phone_number_id", "")),
            "courriel_configure": bool(config.parametre(db, "smtp_hote", "")),
            "base": "ok" if base_ok else "erreur",
        })

    def _export_csv(self) -> None:
        lignes = metier.demandes(self.db, limite=10000)
        colonnes = ["reference", "statut", "nom", "prenom", "provenance", "telephone", "email",
                    "type_sejour", "date_arrivee", "date_depart", "nb_personnes", "nb_hommes",
                    "nb_femmes", "regime_alimentaire", "accessibilite", "besoin_note", "cree_le"]
        sortie = io.StringIO()
        sortie.write("\ufeff")
        writer = csv.writer(sortie, delimiter=";")
        writer.writerow(["Référence", "Statut", "Nom", "Prénom", "Provenance", "Téléphone",
                         "Courriel", "Nature", "Arrivée", "Départ", "Personnes", "Hommes",
                         "Femmes", "Régime", "Accessibilité", "Remarque", "Reçue le"])
        for d in lignes:
            writer.writerow(["" if d.get(c) is None else d.get(c) for c in colonnes])
        self._repondre(200, sortie.getvalue().encode("utf-8"), "text/csv; charset=utf-8", {
            "Content-Disposition": "attachment; filename=demandes.csv"})


# ---------------------------------------------------------------------------
# Démarrage
# ---------------------------------------------------------------------------
def demarrer(db, hote: str = "0.0.0.0", port: int = 8080, ouvrir: bool = False):
    """Lance le serveur et ne rend la main qu'à l'arrêt."""
    config.assurer_dossiers()
    Handler.db = db
    Handler.agent = Agent(db)
    try:
        serveur = ThreadingHTTPServer((hote, port), Handler)
    except OSError as exc:
        print(f"Impossible d'écouter sur {hote}:{port} — {exc}")
        print("Le port est peut-être déjà pris. Essayez : python3 run.py servir --port 8081")
        return None
    serveur.daemon_threads = True
    affichage = "127.0.0.1" if hote in ("0.0.0.0", "", None) else hote
    url = f"http://{affichage}:{port}"
    print("")
    print("  Hôtellerie & Accueil — Monastère Sainte-Marie de Bouaké")
    print(f"  Tableau de bord : {url}")
    print(f"  Santé technique : {url}/sante")
    if not db.valeur("SELECT COUNT(*) FROM utilisateurs", defaut=0):
        print("")
        print("  Aucun compte n'existe encore. Créez le premier :")
        print('    python3 run.py utilisateur --login hotelier --nom "Frère hôtelier"')
    print("  Ctrl+C pour arrêter.")
    print("")
    if ouvrir:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        serveur.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")
    finally:
        serveur.server_close()
    return serveur
