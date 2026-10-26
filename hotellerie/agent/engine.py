# -*- coding: utf-8 -*-
"""
Le moteur de dialogue : la conduite de l'échange, une question à la fois.

Déterministe par construction (principe T4). Le module de langage, s'il est
activé, ne fait qu'habiller une réponse déjà juste : il n'ajoute aucun fait et
ne décide de rien.

Trois règles non négociables y sont inscrites :

1. on ne redemande jamais ce que l'hôte a déjà dit (P4) ;
2. on ne relance pas plus de deux fois, ensuite on transmet (FA-10) ;
3. on ne confirme jamais une réservation (P2) — on transmet aux frères.
"""
from __future__ import annotations

import json
import logging
import re

from .. import config, knowledge, metier, notify
from . import comprehension as C
from . import llm, prompts

log = logging.getLogger(__name__)

CHAMPS_ETAPE = {
    "identite": "nom",
    "provenance": "provenance",
    "periode": "date_depart",
    "personnes": "nb_personnes",
    "nature": "type_sejour",
    "besoins": "besoins_connus",
}


class Agent:
    """L'agent d'accueil d'un monastère : il recueille, il ne décide pas."""

    def __init__(self, db):
        self.db = db
        self.llm = llm.Moteur(db)

    # =====================================================================
    # Point d'entrée
    # =====================================================================
    def repondre(self, conversation_id: str, texte: str, canal: str = "whatsapp",
                 telephone: str = "", nom_contact: str = "") -> str:
        """Reçoit un message et renvoie la réponse (chaîne vide = silence)."""
        texte = (texte or "").strip()
        if not texte:
            return ""
        conv = self._conversation(conversation_id, canal, telephone, nom_contact)
        if conv.get("humain_requis"):
            self._consigner(conv["id"], "entrant", texte, canal)
            return ""
        if not config.drapeau_parametre(self.db, "agent_actif", True):
            self.db.executer("UPDATE conversations SET humain_requis = 1 WHERE id = ?", (conv["id"],))
            self._consigner(conv["id"], "entrant", texte, canal)
            self.db.journal("agent", "agent_inactif", conv["id"])
            return ""

        donnees = self._lire_donnees(conv)
        self._consigner(conv["id"], "entrant", texte, canal)
        reponse, etat = self._traiter(conv, donnees, texte, canal)
        self._enregistrer(conv, donnees, etat)
        if reponse:
            self._consigner(conv["id"], "sortant", reponse, canal)
        return reponse

    # =====================================================================
    # Conduite
    # =====================================================================
    def _traiter(self, conv, d: dict, texte: str, canal: str):
        etape = d.get("etape") or "accueil"
        demande = C.est_demande_sejour(texte)
        question = C.est_une_question(texte)

        # 1. L'urgence passe avant tout. On ne fait pas attendre.
        if C.est_urgence(texte):
            try:
                notify.alerter_urgence(self.db, conv["id"], texte)
            except Exception as exc:
                log.warning("Alerte urgence non transmise : %s", exc)
            return prompts.URGENCE, etape

        # 2. L'hôte demande un frère : l'agent se tait, pour de bon.
        if C.demande_humain(texte):
            d["humain_requis"] = 1
            d["etape"] = "relais"
            try:
                notify.signaler_relais(self.db, conv["id"], texte,
                                       demande_id=d.get("demande_id"))
            except Exception as exc:
                log.warning("Relais humain non transmis : %s", exc)
            return prompts.RELAIS_HUMAIN, "relais"

        # 3. Annulation d'une demande déjà transmise.
        if d.get("demande_id") and C.extraire_annulation(texte):
            metier.changer_statut(self.db, d["demande_id"], "annulee", "hote")
            return prompts.ANNULATION, "annule"

        # 4. Le récapitulatif attend une réponse claire.
        if etape == "recap":
            if C.est_confirmation(texte):
                return self._transmettre(conv, d)
            if C.est_negation(texte):
                d["etape"] = "correction"
                return prompts.RECAP_CORRECTION, "correction"
            # Une question pendant le récapitulatif mérite une réponse.
            if question and not demande:
                return (self._question(texte, conv) + "\n\n" + prompts.RECAP
                        .format(**self._recap(d))), "recap"
            d["etape"] = "correction"

        # 5. Après transmission, la porte reste ouverte.
        if etape in ("transmis", "annule"):
            if demande or (not question and self._a_des_infos(d)):
                d.clear()
                d.update({"etape": "accueil", "relances": 0, "humain_requis": 0})
                etape = "accueil"
            elif question:
                return self._question(texte, conv), etape
            else:
                return prompts.MERCI, etape

        # 6. Une question pure, au début de l'échange : on renseigne.
        if question and not demande and etape in ("accueil", "", "relais"):
            return self._question(texte, conv), etape

        # 7. On reçoit tout ce que l'hôte dit, sans rien redemander.
        self._fusionner(texte, d, ecraser=(etape == "correction"))
        if d.get("date_arrivee") and d.get("date_depart") \
                and d["date_depart"] <= d["date_arrivee"]:
            d["date_depart"] = None

        # Une salutation seule, sans aucune information : on accueille.
        if etape == "accueil" and not demande and not self._a_des_infos(d):
            if C.est_salutation(texte):
                return prompts.SALUTATION, "accueil"
            if re.search(r"\bmerci\b", C._preparer(texte)):
                return prompts.MERCI, "accueil"
            return prompts.PRECISION, "accueil"

        prochain, question_suivante = self._prochaine(d)

        # 8. Tout est là : on présente le récapitulatif.
        if prochain == "recap":
            d["etape"] = "recap"
            return prompts.RECAP.format(**self._recap(d)), "recap"

        # 9. Pas de progrès sur la question posée : relance, puis relais.
        if prochain == etape and etape in CHAMPS_ETAPE:
            if question:
                return (self._question(texte, conv) + "\n\n" + question_suivante), etape
            d["relances"] = int(d.get("relances") or 0) + 1
            if d["relances"] > 2:
                d["humain_requis"] = 1
                d["etape"] = "relais"
                self._relais_partiel(conv, d, texte)
                return prompts.RELAIS_PARTIEL, "relais"
            return prompts.RELANCES.get(prochain, question_suivante), etape

        # 10. On avance, sans jamais redemander ce qui est déjà donné.
        d["relances"] = 0
        d["etape"] = prochain
        return self._avec_reconnaissance(prochain, d, question_suivante), prochain

    # =====================================================================
    # Collecte
    # =====================================================================
    def _fusionner(self, texte: str, d: dict, ecraser: bool = False) -> None:
        etape = d.get("etape")

        if ecraser or not d.get("type_sejour"):
            nature = C.extraire_type_sejour(texte)
            if nature:
                d["type_sejour"] = nature

        if ecraser or not d.get("nom"):
            nom, prenom = C.extraire_identite(
                texte, attendu=(etape in ("identite", "correction") or ecraser))
            if nom:
                d["nom"] = nom
                d["prenom"] = prenom or d.get("prenom", "")

        if ecraser or not d.get("provenance"):
            provenance = C.extraire_provenance(
                texte, attendu=(etape in ("provenance", "correction") or ecraser))
            if provenance:
                d["provenance"] = provenance

        arrivee, depart, _ = C.extraire_dates(texte)
        if arrivee and (ecraser or not d.get("date_arrivee")):
            d["date_arrivee"] = arrivee
        if depart and (ecraser or not d.get("date_depart")):
            d["date_depart"] = depart

        if ecraser or not d.get("nb_personnes"):
            nombre = C.extraire_nombre_personnes(texte)
            if nombre:
                d["nb_personnes"] = nombre

        hommes, femmes = C.extraire_repartition(texte)
        if hommes or femmes:
            d["nb_hommes"] = hommes or None
            d["nb_femmes"] = femmes or None

        besoins = C.extraire_besoins(texte)
        if besoins["vide"]:
            d["regime"] = ""
            d["accessibilite"] = ""
            d["participation_offices"] = ""
            d["besoins_connus"] = True
        else:
            change = False
            for cle in ("regime", "accessibilite", "participation_offices"):
                if besoins[cle]:
                    d[cle] = besoins[cle]
                    change = True
            if besoins["premiere_visite"]:
                d["premiere_visite"] = True
                change = True
            if change:
                d["besoins_connus"] = True

        telephone = C.extraire_telephone(texte)
        if telephone:
            d["telephone"] = telephone
        courriel = C.extraire_email(texte)
        if courriel:
            d["email"] = courriel

        if not d.get("message") and len(texte) > 25:
            d["message"] = texte[:1000]

    def _prochaine(self, d: dict):
        """La prochaine question utile, dans l'ordre de la Règle."""
        if not d.get("nom"):
            return "identite", prompts.DEMANDE_NOM
        if not d.get("provenance"):
            return "provenance", prompts.DEMANDE_PROVENANCE
        if not d.get("date_arrivee") or not d.get("date_depart"):
            return "periode", prompts.DEMANDE_PERIODE
        if not d.get("nb_personnes"):
            return "personnes", prompts.DEMANDE_PERSONNES
        if not d.get("type_sejour"):
            return "nature", prompts.DEMANDE_NATURE
        if not d.get("besoins_connus"):
            return "besoins", prompts.DEMANDE_BESOINS
        return "recap", ""

    def _a_des_infos(self, d: dict) -> bool:
        return bool(d.get("nom") or d.get("provenance") or d.get("date_arrivee")
                    or d.get("nb_personnes"))

    def _avec_reconnaissance(self, prochain: str, d: dict, question: str) -> str:
        if prochain == "personnes" and d.get("date_arrivee") and d.get("date_depart"):
            nuits = metier.nuits(d["date_arrivee"], d["date_depart"])
            return (f"Du {metier.format_date_longue(d['date_arrivee'])} au "
                    f"{metier.format_date_longue(d['date_depart'])}, c'est noté — "
                    f"{nuits} nuits.\n\n{question}")
        if prochain == "besoins" and d.get("nb_personnes"):
            return "Bien noté.\n\n" + question
        if prochain == "besoins" and d.get("nom"):
            return f"Merci, {d.get('prenom') or d.get('nom')}.\n\n" + question
        return question

    # =====================================================================
    # Récapitulatif, transmission
    # =====================================================================
    def _recap(self, d: dict) -> dict:
        hote = f"{d.get('prenom', '')} {d.get('nom', '')}".strip() or "à préciser"
        if d.get("date_arrivee") and d.get("date_depart"):
            periode = (f"du {metier.format_date_longue(d['date_arrivee'])} au "
                       f"{metier.format_date_longue(d['date_depart'])} — "
                       f"{metier.nuits(d['date_arrivee'], d['date_depart'])} nuits")
        else:
            periode = "à préciser"
        n = int(d.get("nb_personnes") or 1)
        composition = f"{n} personne" + ("s" if n > 1 else "")
        if d.get("nb_hommes") or d.get("nb_femmes"):
            composition += (f" ({int(d.get('nb_hommes') or 0)} hommes, "
                            f"{int(d.get('nb_femmes') or 0)} femmes)")
        besoins = "; ".join(x for x in (d.get("regime"), d.get("accessibilite"),
                                         d.get("participation_offices")) if x)
        if d.get("premiere_visite"):
            besoins = (besoins + "; " if besoins else "") + "première visite"
        return {
            "hote": hote,
            "provenance": d.get("provenance") or "à préciser",
            "nature": metier.nature(d.get("type_sejour") or "autre"),
            "periode": periode,
            "composition": composition,
            "besoins": besoins or "aucun",
        }

    def _transmettre(self, conv, d: dict):
        donnees = self._demande_depuis(d, conv)
        identifiant = metier.creer_demande(self.db, donnees)
        d["demande_id"] = identifiant
        d["etape"] = "transmis"
        d["relances"] = 0
        try:
            notify.notifier_hoteliers(self.db, identifiant)
        except Exception as exc:  # jamais bloquant : la demande est en base
            log.warning("Fiche non transmise : %s", exc)
        dem = metier.demande(self.db, identifiant) or {}
        return prompts.TRANSMISSION.format(reference=dem.get("reference") or ""), "transmis"

    def _demande_depuis(self, d: dict, conv) -> dict:
        return {
            "nom": d.get("nom", ""),
            "prenom": d.get("prenom", ""),
            "provenance": d.get("provenance", ""),
            "telephone": d.get("telephone") or conv.get("telephone", "") or "",
            "email": d.get("email", ""),
            "type_sejour": d.get("type_sejour") or "autre",
            "date_arrivee": d.get("date_arrivee"),
            "date_depart": d.get("date_depart"),
            "nb_personnes": d.get("nb_personnes") or 1,
            "nb_hommes": d.get("nb_hommes"),
            "nb_femmes": d.get("nb_femmes"),
            "regime_alimentaire": d.get("regime", ""),
            "accessibilite": d.get("accessibilite", ""),
            "participation_offices": d.get("participation_offices", ""),
            "premiere_visite": d.get("premiere_visite"),
            "besoin_note": d.get("note", ""),
            "message": d.get("message", ""),
            "conversation_id": conv["id"],
            "source": conv.get("canal") or "agent",
        }

    def _relais_partiel(self, conv, d: dict, texte: str) -> None:
        """Deux relances suffisent : on transmet un dossier partiel, sans harceler."""
        identifiant = None
        if self._a_des_infos(d):
            try:
                identifiant = metier.creer_demande(self.db, self._demande_depuis(d, conv))
                d["demande_id"] = identifiant
            except Exception as exc:
                log.warning("Dossier partiel non créé : %s", exc)
        try:
            notify.signaler_relais(self.db, conv["id"], texte, partiel=True,
                                   demande_id=identifiant)
        except Exception as exc:
            log.warning("Relais partiel non transmis : %s", exc)

    # =====================================================================
    # Questions à la base de connaissances
    # =====================================================================
    def _question(self, texte: str, conv) -> str:
        fiches = knowledge.chercher(self.db, texte, limite=3)
        if fiches:
            reponse = knowledge.nettoyer_reponse(fiches[0].get("reponse", ""))
            if len(reponse) >= 30:
                finale = prompts.QUESTION_TROUVEE.format(reponse=reponse)
                if self.llm.disponible():
                    finale = self.llm.formuler(texte, finale, contexte="question pratique")
                self.db.journal("agent", "question_repondue", fiches[0].get("cle", ""),
                                conv.get("id", ""))
                return finale
        try:
            notify.notifier_question(self.db, texte, conv.get("id"))
        except Exception as exc:
            log.warning("Question non transmise : %s", exc)
        return prompts.QUESTION_INCONNUE

    # =====================================================================
    # Persistance
    # =====================================================================
    def _conversation(self, identifiant, canal, telephone, nom_contact):
        conv = self.db.ligne("SELECT * FROM conversations WHERE id = ?", (identifiant,))
        if not conv:
            self.db.executer(
                "INSERT INTO conversations (id, canal, telephone, nom_affiche) VALUES (?, ?, ?, ?)",
                (identifiant, canal or "whatsapp", telephone or "", nom_contact or ""))
            conv = self.db.ligne("SELECT * FROM conversations WHERE id = ?", (identifiant,))
        elif telephone and not conv.get("telephone"):
            self.db.executer("UPDATE conversations SET telephone = ? WHERE id = ?",
                             (telephone, identifiant))
            conv["telephone"] = telephone
        return conv

    def _lire_donnees(self, conv) -> dict:
        try:
            donnees = json.loads(conv.get("donnees") or "{}")
        except (ValueError, TypeError):
            donnees = {}
        if not isinstance(donnees, dict):
            donnees = {}
        donnees.setdefault("etape", conv.get("etat") or "accueil")
        donnees.setdefault("relances", int(conv.get("relances") or 0))
        donnees.setdefault("humain_requis", int(conv.get("humain_requis") or 0))
        return donnees

    def _enregistrer(self, conv, d: dict, etat: str) -> None:
        self.db.executer(
            "UPDATE conversations SET etat = ?, donnees = ?, relances = ?, humain_requis = ?, "
            "demande_id = COALESCE(?, demande_id), maj = datetime('now','localtime') WHERE id = ?",
            (etat or d.get("etape") or "accueil", json.dumps(d, ensure_ascii=False),
             int(d.get("relances") or 0), int(d.get("humain_requis") or 0),
             d.get("demande_id"), conv["id"]))
        if d.get("nom") and not conv.get("nom_affiche"):
            self.db.executer("UPDATE conversations SET nom_affiche = ? WHERE id = ?",
                             (f"{d.get('prenom', '')} {d['nom']}".strip(), conv["id"]))

    def _consigner(self, conversation_id, direction, corps, canal, intention="") -> None:
        try:
            self.db.executer(
                "INSERT INTO messages (conversation_id, direction, canal, corps, intention) "
                "VALUES (?, ?, ?, ?, ?)",
                (conversation_id, direction, canal or "", corps or "", intention or ""))
        except Exception as exc:
            log.warning("Message non consigné : %s", exc)
