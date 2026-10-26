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
        "version": config.parametre(db, "wa_api_version", "v21.0"),
        "numero_test": normaliser_numero(config.parametre(db, "wa_numero_test", "")),
        "site_url": config.parametre(db, "site_url", "").rstrip("/"),
    }


def _base(db) -> str:
    version = configuration(db)["version"] or "v21.0"
    if not version.startswith("v"):
        version = "v" + version
    return f"https://graph.facebook.com/{version}"


def _requete(url: str, token: str, corps=None, delai: int = 20):
    donnees = None
    entetes = {"Authorization": f"Bearer {token}"}
    if corps is not None:
        donnees = json.dumps(corps).encode("utf-8")
        entetes["Content-Type"] = "application/json"
    requete = urllib.request.Request(url, data=donnees, headers=entetes,
                                     method="POST" if corps is not None else "GET")
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return json.loads(reponse.read().decode("utf-8") or "{}")


def _erreur_http(exc) -> dict:
    """Extrait le code et le message d'une erreur Meta, sans jamais lever."""
    code, message, detail = None, str(exc)[:300], ""
    try:
        charge = json.loads(exc.read().decode("utf-8", "ignore") or "{}")
        erreur = charge.get("error") or {}
        code = erreur.get("code")
        message = erreur.get("message") or message
        detail = erreur.get("error_data", {}).get("details") or ""
    except Exception:
        pass
    return {"code": code, "message": message, "detail": detail,
            "conseil": expliquer_erreur(code, message)}


# ---------------------------------------------------------------------------
# Traduction des erreurs Meta en français utile
# ---------------------------------------------------------------------------
CONSEILS = {
    190: "Jeton invalide ou expiré. Générez un jeton permanent (utilisateur "
         "système) dans Meta, puis recollez-le ici.",
    100: "Paramètre invalide : vérifiez l'identifiant du numéro (phone_number_id) "
         "et la version de l'API (v21.0 par exemple).",
    131030: "Ce numéro n'est pas autorisé à recevoir des messages. En mode test "
            "Meta, ajoutez-le dans « Destinataires de test » de votre application.",
    131047: "La fenêtre de 24 heures est fermée : l'hôte doit écrire en premier. "
            "Demandez-lui d'envoyer « Bonjour » au numéro WhatsApp Business.",
    131026: "Ce numéro n'a pas WhatsApp, ou ne peut pas recevoir de message.",
    131042: "Problème de facturation : une méthode de paiement doit être "
            "enregistrée sur le compte WhatsApp Business.",
    131000: "Erreur inconnue côté Meta. Réessayez ; le message reste dans la file.",
    133010: "Le compte n'est pas enregistré ou le numéro n'est pas vérifié.",
    368: "Compte temporairement restreint par Meta. Consultez la qualité du compte.",
    80007: "Limite de débit atteinte. Patientez quelques minutes ; la file "
           "rejouera l'envoi.",
}


def expliquer_erreur(code, message: str = "") -> str:
    try:
        code = int(code)
    except (TypeError, ValueError):
        return message or "Erreur inconnue."
    return CONSEILS.get(code, f"Erreur Meta {code} : {message or 'sans détail.'}")


# ---------------------------------------------------------------------------
# File d'attente locale
# ---------------------------------------------------------------------------
def _consigner(db, numero, texte, demande_id=None, conversation_id="") -> int:
    try:
        return int(db.executer(
            "INSERT INTO envois (demande_id, conversation_id, numero, corps) "
            "VALUES (?, ?, ?, ?)", (demande_id, conversation_id or "", numero or "",
                                    texte or "")))
    except Exception:
        return 0


def _clore(db, identifiant, statut, erreur="") -> None:
    if not identifiant:
        return
    try:
        db.executer(
            "UPDATE envois SET statut = ?, erreur = ?, envoye_le = CASE WHEN ? = 'envoye' "
            "THEN datetime('now','localtime') ELSE envoye_le END WHERE id = ?",
            (statut, (erreur or "")[:500], statut, identifiant))
    except Exception:
        pass


def file_attente(db, limite: int = 20) -> list:
    return db.lignes(
        "SELECT * FROM envois WHERE statut IN ('en_attente', 'echoue') "
        "ORDER BY id LIMIT ?", (int(limite),))


def derniers_envois(db, limite: int = 12) -> list:
    return db.lignes("SELECT * FROM envois ORDER BY id DESC LIMIT ?", (int(limite),))


def rejouer(db, limite: int = 20) -> dict:
    """Tente de renvoyer ce qui attend. Ne lève jamais."""
    conf = configuration(db)
    if not conf["token"] or not conf["phone_number_id"]:
        return {"ok": False, "envoyes": 0, "restants": len(file_attente(db, limite)),
                "erreur": "WhatsApp n'est pas encore configuré : rien n'a pu partir."}
    envoyes, echecs = 0, 0
    for envoi in file_attente(db, limite):
        db.executer("UPDATE envois SET tentatives = tentatives + 1 WHERE id = ?", (envoi["id"],))
        resultat = _expedier(db, conf, envoi["numero"], envoi["corps"])
        if resultat["ok"]:
            _clore(db, envoi["id"], "envoye")
            envoyes += 1
        else:
            _clore(db, envoi["id"], "echoue", resultat.get("erreur", ""))
            echecs += 1
    return {"ok": envoyes > 0, "envoyes": envoyes, "echecs": echecs,
            "restants": len(file_attente(db, 200)),
            "erreur": "" if envoyes or not echecs else "Aucun envoi n'a abouti."}


# ---------------------------------------------------------------------------
# Envoi
# ---------------------------------------------------------------------------
def _expedier(db, conf, destinataire, texte, delai: int = 20) -> dict:
    """Appel réseau seul. Ne consigne rien, ne lève rien."""
    if not destinataire:
        return {"ok": False, "ignore": False, "morceaux": 0, "erreur": "numéro vide"}
    url = f"{_base(db)}/{conf['phone_number_id']}/messages"
    morceaux = decouper(texte)
    envoyes = 0
    try:
        for morceau in morceaux:
            _requete(url, conf["token"], {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": destinataire,
                "type": "text",
                "text": {"preview_url": False, "body": morceau},
            }, delai)
            envoyes += 1
        return {"ok": True, "ignore": False, "morceaux": envoyes, "erreur": ""}
    except urllib.error.HTTPError as exc:
        information = _erreur_http(exc)
        log.warning("WhatsApp HTTP %s : %s", exc.code, information["message"])
        return {"ok": False, "ignore": False, "morceaux": envoyes,
                "erreur": information["conseil"], "code": information["code"],
                "detail": information["message"]}
    except Exception as exc:
        log.warning("WhatsApp : %s", exc)
        return {"ok": False, "ignore": False, "morceaux": envoyes,
                "erreur": f"Réseau indisponible : {str(exc)[:200]}"}


def envoyer(db, numero: str, texte: str, apercu: bool = False,
            demande_id=None, conversation_id: str = "") -> dict:
    """Envoie un message et le consigne dans la file locale.

    Rien ne se perd : si WhatsApp n'est pas configuré ou si le réseau manque,
    le message reste ``en_attente`` et ``run.py whatsapp --rejouer`` le
    reprendra. C'est le principe T2 du cahier des charges.
    """
    conf = configuration(db)
    destinataire = normaliser_numero(numero)
    identifiant = _consigner(db, destinataire, texte, demande_id, conversation_id)

    if not conf["token"] or not conf["phone_number_id"]:
        return {"ok": False, "ignore": True, "morceaux": 0, "envoi_id": identifiant,
                "erreur": "WhatsApp non configuré (jeton ou identifiant du numéro absent) : "
                          "le message reste dans la file d'attente."}
    if apercu:
        return {"ok": True, "ignore": True, "morceaux": 0, "envoi_id": identifiant,
                "erreur": "mode aperçu : rien n'a été envoyé"}
    if not destinataire:
        _clore(db, identifiant, "echoue", "numéro vide")
        return {"ok": False, "ignore": False, "morceaux": 0, "envoi_id": identifiant,
                "erreur": "numéro vide"}

    resultat = _expedier(db, conf, destinataire, texte)
    resultat["envoi_id"] = identifiant
    if resultat["ok"]:
        _clore(db, identifiant, "envoye")
    else:
        _clore(db, identifiant, "echoue", resultat.get("erreur", ""))
    return resultat


# ---------------------------------------------------------------------------
# Diagnostic du compte WhatsApp Business
# ---------------------------------------------------------------------------
def verifier_compte(db) -> dict:
    """Interroge Meta sur le numéro configuré. Ne lève jamais."""
    conf = configuration(db)
    if not conf["token"] or not conf["phone_number_id"]:
        return {"ok": False, "code": None,
                "erreur": "Jeton ou identifiant du numéro absent : renseignez-les d'abord.",
                "conseil": "Ces deux valeurs se trouvent dans Meta, « WhatsApp → API Setup »."}
    url = (f"{_base(db)}/{conf['phone_number_id']}?fields=display_phone_number,"
           "verified_name,quality_rating,platform_type,code_verification_status")
    try:
        donnees = _requete(url, conf["token"], delai=15)
        return {"ok": True, "code": None, "erreur": "", "conseil": "",
                "compte": donnees}
    except urllib.error.HTTPError as exc:
        information = _erreur_http(exc)
        return {"ok": False, "code": information["code"],
                "erreur": information["message"], "conseil": information["conseil"],
                "detail": information["detail"]}
    except Exception as exc:
        return {"ok": False, "code": None, "erreur": str(exc)[:200],
                "conseil": "Le serveur n'a pas pu joindre graph.facebook.com : "
                           "vérifiez la connexion Internet de la maison."}


def diagnostic(db, numero: str = "") -> dict:
    """Ce qu'il faut savoir avant d'annoncer « WhatsApp est branché »."""
    conf = configuration(db)
    numero = normaliser_numero(numero or conf["numero_test"])
    etapes = []

    def etape(nom, ok, detail):
        etapes.append({"etape": nom, "ok": bool(ok), "detail": detail})

    etape("Jeton d'accès", bool(conf["token"]),
          "présent" if conf["token"] else "absent — Meta, « WhatsApp → API Setup », jeton permanent")
    etape("Identifiant du numéro (phone_number_id)", bool(conf["phone_number_id"]),
          conf["phone_number_id"] or "absent")
    etape("Jeton de vérification du webhook", bool(conf["verify_token"]),
          conf["verify_token"] or "absent")
    etape("Secret de l'application (signature)", bool(conf["app_secret"]),
          "présent" if conf["app_secret"] else
          "facultatif, mais recommandé : sans lui, n'importe qui peut simuler un message")
    etape("Adresse publique du webhook", bool(conf["site_url"]),
          (conf["site_url"] + "/webhook/whatsapp") if conf["site_url"]
          else "non renseignée — Meta exige une adresse HTTPS publique")
    etape("Numéro d'essai", bool(numero),
          afficher_numero(numero) if numero else "non renseigné")

    compte = None
    if conf["token"] and conf["phone_number_id"]:
        resultat = verifier_compte(db)
        compte = resultat.get("compte")
        etape("Compte joint chez Meta", resultat["ok"],
              (resultat["conseil"] if not resultat["ok"]
               else (compte or {}).get("display_phone_number", "compte joint")))
    pret = all(e["ok"] for e in etapes if e["etape"] != "Secret de l'application (signature)")
    return {"pret": pret, "etapes": etapes, "compte": compte,
            "numero": numero, "file": len(file_attente(db, 200))}
