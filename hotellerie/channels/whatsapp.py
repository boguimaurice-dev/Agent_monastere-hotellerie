# -*- coding: utf-8 -*-
"""
WhatsApp Cloud API (Meta) : normalisation des numéros, webhook, envoi.

Rien n'est obligatoire : sans jeton, ``envoyer`` ne lève jamais et renvoie un
motif lisible, que le tableau de bord affiche. Une demande ne se perd jamais
à cause d'une configuration absente.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

from .. import config

log = logging.getLogger(__name__)

API = "https://graph.facebook.com/v21.0"
LIMITE_CARACTERES = 1500
PAYS = "225"


# ---------------------------------------------------------------------------
# Numéros
# ---------------------------------------------------------------------------
def normaliser_numero(numero: str) -> str:
    """Renvoie un numéro international sans « + », prêt pour l'API."""
    n = re.sub(r"\D", "", numero or "")
    if n.startswith("00"):
        n = n[2:]
    if n.startswith(PAYS):
        return n
    if len(n) == 10 and n.startswith("0"):
        return PAYS + n
    if len(n) == 8:
        return PAYS + n
    return n


def afficher_numero(numero: str) -> str:
    """« 2250797008052 » → « +225 07 97 00 80 52 »."""
    n = normaliser_numero(numero)
    if not n:
        return ""
    if n.startswith(PAYS) and len(n) == 13:
        reste = n[len(PAYS):]
        groupes = " ".join(reste[i:i + 2] for i in range(0, len(reste), 2))
        return f"+{PAYS} {groupes}"
    return "+" + n


# ---------------------------------------------------------------------------
# Webhook entrant
# ---------------------------------------------------------------------------
def extraire_messages(charge) -> list:
    """Aplatit la charge Meta en une liste simple de messages."""
    resultat = []
    charge = charge or {}
    for entree in charge.get("entry", []) or []:
        for changement in entree.get("changes", []) or []:
            valeur = changement.get("value") or {}
            noms = {}
            for contact in valeur.get("contacts", []) or []:
                identifiant = contact.get("wa_id") or contact.get("user_id") or ""
                noms[identifiant] = ((contact.get("profile") or {}).get("name") or "")
            for message in valeur.get("messages", []) or []:
                brut = message.get("from") or ""
                type_message = message.get("type") or "text"
                texte = ""
                if type_message == "text":
                    texte = ((message.get("text") or {}).get("body") or "")
                elif type_message == "button":
                    texte = ((message.get("button") or {}).get("text") or "")
                elif type_message == "interactive":
                    interactif = message.get("interactive") or {}
                    texte = (((interactif.get("button_reply") or {}).get("title"))
                             or ((interactif.get("list_reply") or {}).get("title")) or "")
                resultat.append({
                    "de": normaliser_numero(brut),
                    "brut": brut,
                    "id": message.get("id") or "",
                    "type": type_message,
                    "texte": texte,
                    "horodatage": message.get("timestamp") or "",
                    "nom": noms.get(brut, ""),
                })
    return resultat


def verifier_webhook(query, jeton: str = ""):
    """Poignée de main Meta : ``(ok, challenge)``."""
    def premier(cle):
        valeur = (query or {}).get(cle)
        if isinstance(valeur, (list, tuple)):
            return valeur[0] if valeur else ""
        return valeur or ""

    attendu = (jeton or config.env("wa_verify_token")
               or config.VERIFY_TOKEN_DEFAUT)
    if premier("hub.mode") != "subscribe":
        return False, ""
    if premier("hub.verify_token") != attendu:
        return False, ""
    return True, str(premier("hub.challenge"))


# ---------------------------------------------------------------------------
# Découpage
# ---------------------------------------------------------------------------
def decouper(texte: str, limite: int = LIMITE_CARACTERES) -> list:
    """Découpe un message long sans couper un mot, avec numérotation (1/2)."""
    texte = (texte or "").strip()
    if not texte:
        return []
    if len(texte) <= limite:
        return [texte]
    morceaux = []
    reste = texte
    while reste:
        if len(reste) <= limite:
            morceaux.append(reste.strip())
            break
        coupe = reste.rfind("\n\n", 0, limite)
        if coupe < limite // 2:
            coupe = reste.rfind(". ", 0, limite)
        if coupe < limite // 2:
            coupe = reste.rfind(" ", 0, limite)
        if coupe <= 0:
            coupe = limite
        morceaux.append(reste[:coupe + 1].strip())
        reste = reste[coupe + 1:].lstrip()
    if len(morceaux) > 1:
        total = len(morceaux)
        morceaux = [f"{m} ({i}/{total})" for i, m in enumerate(morceaux, 1)]
    return morceaux


# ---------------------------------------------------------------------------
# Envoi
# ---------------------------------------------------------------------------
def configuration(db) -> dict:
    return {
        "token": config.parametre(db, "wa_token", ""),
        "phone_number_id": config.parametre(db, "wa_phone_number_id", ""),
        "verify_token": config.parametre(db, "wa_verify_token", config.VERIFY_TOKEN_DEFAUT),
        "app_secret": config.parametre(db, "wa_app_secret", ""),
    }


def _poster(url: str, corps: dict, token: str, delai: int = 20):
    requete = urllib.request.Request(
        url, data=json.dumps(corps).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return json.loads(reponse.read().decode("utf-8") or "{}")


def envoyer(db, numero: str, texte: str, apercu: bool = False) -> dict:
    """Envoie un message; renvoie ``{ok, morceaux, erreur, ignore}``."""
    conf = configuration(db)
    destinataire = normaliser_numero(numero)
    if not conf["token"] or not conf["phone_number_id"]:
        return {"ok": False, "ignore": True, "morceaux": 0,
                "erreur": "WhatsApp non configuré (jeton ou identifiant du numéro absent)"}
    if apercu:
        return {"ok": True, "ignore": True, "morceaux": 0, "erreur": "mode aperçu"}
    if not destinataire:
        return {"ok": False, "ignore": False, "morceaux": 0, "erreur": "numéro vide"}
    url = f"{API}/{conf['phone_number_id']}/messages"
    morceaux = decouper(texte)
    envoyes = 0
    try:
        for morceau in morceaux:
            _poster(url, {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": destinataire,
                "type": "text",
                "text": {"preview_url": False, "body": morceau},
            }, conf["token"])
            envoyes += 1
        return {"ok": True, "ignore": False, "morceaux": envoyes, "erreur": ""}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:300]
        log.warning("WhatsApp HTTP %s : %s", exc.code, detail)
        return {"ok": False, "ignore": False, "morceaux": envoyes, "erreur": f"HTTP {exc.code} : {detail}"}
    except Exception as exc:
        log.warning("WhatsApp : %s", exc)
        return {"ok": False, "ignore": False, "morceaux": envoyes, "erreur": str(exc)[:300]}
