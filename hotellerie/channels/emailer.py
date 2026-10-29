# -*- coding: utf-8 -*-
"""Courriel (SMTP), sans dépendance : ``smtplib`` et ``email`` suffisent."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

from .. import config

log = logging.getLogger(__name__)


def configuration(db) -> dict:
    return {
        "hote": config.parametre(db, "smtp_hote", ""),
        "port": config.entier_parametre(db, "smtp_port", 587),
        "utilisateur": config.parametre(db, "smtp_utilisateur", ""),
        "mot_de_passe": config.parametre(db, "smtp_mot_de_passe", ""),
        "expediteur": (config.parametre(db, "smtp_expediteur", "")
                       or config.parametre(db, "smtp_utilisateur", "")),
        "tls": config.drapeau_parametre(db, "smtp_tls", True),
        "delai": config.entier_parametre(db, "smtp_delai", 20),
    }


def destinataires(valeur) -> list:
    if isinstance(valeur, (list, tuple)):
        brut = list(valeur)
    else:
        brut = (valeur or "").replace(";", ",").split(",")
    return [x.strip() for x in brut if x and "@" in x]


def envoyer(db, adresses, sujet: str, corps_texte: str, corps_html: str = "") -> dict:
    """Envoie un courriel; ne lève jamais, renvoie un motif en cas d'échec."""
    conf = configuration(db)
    liste = destinataires(adresses)
    if not liste:
        return {"ok": False, "ignore": True, "erreur": "aucun destinataire"}
    if not conf["hote"]:
        return {"ok": False, "ignore": True, "erreur": "SMTP non configuré (serveur absent)"}
    expediteur = conf["expediteur"] or "hotellerie@localhost"
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = Header(sujet, "utf-8")
        message["From"] = formataddr((str(Header(config.NOM_MAISON, "utf-8")), expediteur))
        message["To"] = ", ".join(liste)
        message["Date"] = formatdate(localtime=True)
        message.attach(MIMEText(corps_texte, "plain", "utf-8"))
        message.attach(MIMEText(corps_html or _html(corps_texte), "html", "utf-8"))

        contexte = ssl.create_default_context()
        if conf["port"] == 465:
            serveur = smtplib.SMTP_SSL(conf["hote"], conf["port"], timeout=conf["delai"],
                                       context=contexte)
        else:
            serveur = smtplib.SMTP(conf["hote"], conf["port"], timeout=conf["delai"])
        try:
            serveur.ehlo()
            if conf["tls"] and conf["port"] != 465:
                serveur.starttls(context=contexte)
                serveur.ehlo()
            if conf["utilisateur"]:
                serveur.login(conf["utilisateur"], conf["mot_de_passe"])
            serveur.sendmail(expediteur, liste, message.as_string())
        finally:
            try:
                serveur.quit()
            except Exception:
                pass
        return {"ok": True, "ignore": False, "erreur": ""}
    except Exception as exc:
        log.warning("Courriel : %s", exc)
        return {"ok": False, "ignore": False, "erreur": str(exc)[:300]}


def _html(texte: str) -> str:
    import html
    return ("<html><body style=\"font-family: Georgia, serif; line-height: 1.6; color: #222\">"
            "<pre style=\"white-space: pre-wrap; font-family: inherit\">"
            + html.escape(texte or "") + "</pre></body></html>")
