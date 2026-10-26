# -*- coding: utf-8 -*-
"""
Le relais vers les frères : la fiche de synthèse, par courriel, par WhatsApp,
et toujours dans le tableau de bord.

Rien ne se perd : même sans SMTP ni WhatsApp, la fiche est consignée dans la
table ``notifications`` avec son motif. C'est le principe T2 du cahier des
charges, et il n'est jamais négociable.
"""
from __future__ import annotations

import logging

from . import config, metier
from .channels import emailer, whatsapp

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Destinataires
# ---------------------------------------------------------------------------
def destinataires(db) -> dict:
    """Adresses de courriel et numéros WhatsApp des frères hôteliers."""
    bruts = config.parametre(db, "hoteliers_whatsapp", "").replace(";", ",")
    numeros = []
    for morceau in bruts.split(","):
        numero = whatsapp.normaliser_numero(morceau)
        if len(numero) >= 10 and numero not in numeros:
            numeros.append(numero)
    return {
        "emails": emailer.destinataires(config.parametre(db, "hoteliers_emails", "")),
        "whatsapp": numeros,
    }


# ---------------------------------------------------------------------------
# La fiche de synthèse
# ---------------------------------------------------------------------------
def _composition(dem) -> str:
    n = int(dem.get("nb_personnes") or 1)
    texte = f"{n} personne" + ("s" if n > 1 else "")
    hommes, femmes = dem.get("nb_hommes"), dem.get("nb_femmes")
    if hommes or femmes:
        texte += f" ({int(hommes or 0)} hommes, {int(femmes or 0)} femmes)"
    return texte


def _besoins(dem) -> str:
    morceaux = []
    if dem.get("regime_alimentaire"):
        morceaux.append("régime : " + dem["regime_alimentaire"])
    if dem.get("accessibilite"):
        morceaux.append("accessibilité : " + dem["accessibilite"])
    if dem.get("participation_offices"):
        morceaux.append("offices : " + dem["participation_offices"])
    if dem.get("premiere_visite"):
        morceaux.append("première visite")
    if dem.get("besoin_note"):
        morceaux.append(dem["besoin_note"])
    return "; ".join(morceaux) if morceaux else "aucun"


def _periode(dem) -> str:
    if not dem.get("date_arrivee"):
        return "à préciser"
    if not dem.get("date_depart"):
        return f"à partir du {metier.format_date(dem['date_arrivee'])}"
    return (f"du {metier.format_date(dem['date_arrivee'])} au "
            f"{metier.format_date(dem['date_depart'])} — "
            f"{metier.nuits(dem['date_arrivee'], dem['date_depart'])} nuits")


def composer_fiche(db, dem):
    """Renvoie ``(sujet, corps)`` — la fiche que lisent les frères."""
    if not dem:
        return "", ""
    hote = f"{dem.get('prenom', '')} {dem.get('nom', '')}".strip() or "hôte non identifié"
    dispo = metier.verifier_disponibilite(db, dem.get("date_arrivee"),
                                           dem.get("date_depart"),
                                           dem.get("nb_personnes") or 1)
    sujet = (f"[Hôtellerie] {dem.get('reference') or ''} — {hote} — "
             f"{metier.format_date(dem.get('date_arrivee'))} → "
             f"{metier.format_date(dem.get('date_depart'))}")
    lignes = [
        f"DEMANDE DE SÉJOUR — {dem.get('reference') or 'sans référence'}",
        "",
        f"Hôte        : {hote}",
        f"Provenance  : {dem.get('provenance') or 'à préciser'}",
        f"Téléphone   : {whatsapp.afficher_numero(dem.get('telephone')) or 'non communiqué'}",
        f"Courriel    : {dem.get('email') or 'non communiqué'}",
        f"Nature      : {metier.nature(dem.get('type_sejour'))}",
        f"Période     : {_periode(dem)}",
        f"Composition : {_composition(dem)}",
        f"Besoins     : {_besoins(dem)}",
        f"Reçue le    : {dem.get('cree_le') or ''}",
        f"Source      : {dem.get('source') or 'agent'}",
    ]
    if dem.get("message"):
        lignes += ["", "Message de l'hôte :", "  " + str(dem["message"]).replace("\n", "\n  ")]
    lignes += [
        "",
        "DISPONIBILITÉ SUR LA PÉRIODE",
        f"  Chambres libres : {dispo['nb_chambres_libres']} / {dispo['nb_chambres_totales']}",
        f"  Capacité libre  : {dispo['capacite_libre']} place(s) pour "
        f"{dem.get('nb_personnes') or 1} personne(s)",
        f"  Verdict         : {'suffisant' if dispo['disponible'] else 'insuffisant ou à vérifier'}"
        + (f" ({dispo['motif']})" if dispo.get("motif") else ""),
        "",
        "RAPPEL : l'agent n'a rien confirmé à l'hôte. Le discernement et la "
        "réponse appartiennent aux frères.",
    ]
    return sujet, "\n".join(lignes)


# ---------------------------------------------------------------------------
# Journal des transmissions
# ---------------------------------------------------------------------------
def _consigner(db, demande_id, canal, destinataire, sujet, statut, erreur="") -> None:
    try:
        db.executer(
            "INSERT INTO notifications (demande_id, canal, destinataire, sujet, statut, erreur) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (demande_id, canal, destinataire or "", (sujet or "")[:200], statut, (erreur or "")[:500]))
    except Exception as exc:
        log.warning("Notification non consignée : %s", exc)


def _statut(resultat) -> str:
    if resultat.get("ok"):
        return "envoye"
    return "ignore" if resultat.get("ignore") else "echoue"


def notifier_hoteliers(db, demande_id, motif: str = "nouvelle_demande") -> dict:
    """Transmet la fiche aux frères, par tous les canaux disponibles."""
    dem = metier.demande(db, demande_id)
    if not dem:
        return {"ok": False, "erreur": "demande inconnue"}
    sujet, corps = composer_fiche(db, dem)
    dest = destinataires(db)
    resultats = []

    _consigner(db, demande_id, "dashboard", "frères hôteliers", sujet, "envoye")
    resultats.append({"canal": "dashboard", "ok": True, "ignore": False, "erreur": ""})

    if dest["emails"]:
        if config.drapeau_parametre(db, "notifier_par_email", True):
            res = emailer.envoyer(db, dest["emails"], sujet, corps)
            _consigner(db, demande_id, "email", ", ".join(dest["emails"]), sujet,
                       _statut(res), res.get("erreur", ""))
        else:
            res = {"ok": False, "ignore": True, "erreur": "envoi par courriel désactivé"}
            _consigner(db, demande_id, "email", ", ".join(dest["emails"]), sujet, "ignore",
                       res["erreur"])
        resultats.append({"canal": "email", **res})
    else:
        _consigner(db, demande_id, "email", "", sujet, "ignore", "aucune adresse de frère configurée")
        resultats.append({"canal": "email", "ok": False, "ignore": True,
                          "erreur": "aucune adresse configurée"})

    if dest["whatsapp"] and config.drapeau_parametre(db, "notifier_par_whatsapp", True):
        for numero in dest["whatsapp"]:
            res = whatsapp.envoyer(db, numero, corps)
            _consigner(db, demande_id, "whatsapp", whatsapp.afficher_numero(numero), sujet,
                       _statut(res), res.get("erreur", ""))
            resultats.append({"canal": "whatsapp", "destinataire": numero, **res})

    db.journal("agent", "fiche_transmise", str(demande_id), motif)
    return {"ok": any(r.get("ok") for r in resultats), "resultats": resultats, "sujet": sujet}


# ---------------------------------------------------------------------------
# Alertes et relais
# ---------------------------------------------------------------------------
def _alerter(db, sujet, corps, conversation_id=None, demande_id=None) -> dict:
    dest = destinataires(db)
    _consigner(db, demande_id, "dashboard", "frères hôteliers", sujet, "envoye")
    resultats = []
    if dest["emails"]:
        res = emailer.envoyer(db, dest["emails"], sujet, corps)
        _consigner(db, demande_id, "email", ", ".join(dest["emails"]), sujet,
                   _statut(res), res.get("erreur", ""))
        resultats.append({"canal": "email", **res})
    for numero in dest["whatsapp"]:
        res = whatsapp.envoyer(db, numero, corps)
        _consigner(db, demande_id, "whatsapp", whatsapp.afficher_numero(numero), sujet,
                   _statut(res), res.get("erreur", ""))
        resultats.append({"canal": "whatsapp", **res})
    db.journal("agent", "alerte", str(conversation_id or demande_id or ""), sujet)
    return {"ok": any(r.get("ok") for r in resultats), "resultats": resultats}


def alerter_urgence(db, conversation_id, texte: str) -> dict:
    corps = (
        "URGENCE SIGNALÉE PAR UN HÔTE\n\n"
        f"Conversation : {conversation_id}\n"
        f"Message : {texte}\n\n"
        "L'agent a donné immédiatement les numéros de l'accueil et de l'hôtellerie, "
        "et a orienté vers les secours si nécessaire. Un frère doit prendre le relais."
    )
    return _alerter(db, "URGENCE — hôte à rappeler", corps, conversation_id)


def notifier_question(db, question: str, conversation_id=None) -> dict:
    corps = (
        "QUESTION SANS RÉPONSE DANS LA BASE DE CONNAISSANCES\n\n"
        f"Conversation : {conversation_id or '—'}\n"
        f"Question : {question}\n\n"
        "L'agent a dit honnêtement qu'il ne savait pas, et a renvoyé l'hôte vers "
        "l'hôtellerie. Il serait bon d'ajouter la réponse à la base de connaissances."
    )
    return _alerter(db, "Question d'un hôte à compléter", corps, conversation_id)


def signaler_relais(db, conversation_id, texte: str, partiel: bool = False,
                    demande_id=None) -> dict:
    corps = (
        "RELAIS HUMAIN DEMANDÉ\n\n"
        f"Conversation : {conversation_id}\n"
        f"Message : {texte}\n\n"
        + ("Le dossier est incomplet : l'agent a cessé d'insister et transmet ce "
           "qu'il a recueilli.\n" if partiel else
           "L'hôte souhaite parler à un père ou à un frère. L'agent s'est tu.\n")
        + "Un frère doit prendre le relais dans le tableau de bord."
    )
    return _alerter(db, "Relais humain — un hôte attend", corps, conversation_id, demande_id)
