# -*- coding: utf-8 -*-
"""
Amorçage de la base : chambres génériques, base de connaissances, paramètres.

Rien n'est jamais écrasé si cela existe déjà : ``initialiser`` peut être
relancé sans risque sur une base vivante.
"""
from __future__ import annotations

import datetime as dt

from . import config, knowledge, metier

CHAMBRES_DEFAUT = [
    # (nom, capacité, type, aile, pmr)
    ("Chambre 1", 2, "individuelle", "Aile Sainte-Marie", 0),
    ("Chambre 2", 2, "individuelle", "Aile Sainte-Marie", 0),
    ("Chambre 3", 2, "individuelle", "Aile Sainte-Marie", 0),
    ("Chambre 4", 2, "individuelle", "Aile Sainte-Marie", 1),
    ("Chambre 5", 2, "individuelle", "Aile Saint-Benoît", 0),
    ("Chambre 6", 2, "individuelle", "Aile Saint-Benoît", 0),
    ("Chambre 7", 2, "individuelle", "Aile Saint-Benoît", 0),
    ("Chambre 8", 2, "individuelle", "Aile Saint-Benoît", 0),
    ("Dortoir", 10, "dortoir", "Aile Saint-Benoît", 0),
]

PARAMETRES_DEFAUT = {
    "agent_actif": "1",
    "agent_heures_debut": "6",
    "agent_heures_fin": "21",
    "agent_delai_reponse": "",
    "wa_verify_token": config.VERIFY_TOKEN_DEFAUT,
    "wa_api_version": "v21.0",
    # Numéro d'essai du branchement WhatsApp (destinataire de test Meta).
    "wa_numero_test": "",
    "site_url": "",
    "hoteliers_emails": "",
    "hoteliers_whatsapp": "",
    "notifier_par_email": "1",
    "notifier_par_whatsapp": "1",
    "ia_active": "0",
    "ia_fournisseur": "openai",
    "ia_modele": "gpt-4o-mini",
    "ia_temperature": "0.4",
    "ia_delai": "20",
    "smtp_hote": "",
    "smtp_port": "587",
    "smtp_utilisateur": "",
    "smtp_mot_de_passe": "",
    "smtp_expediteur": "",
    "smtp_tls": "1",
    "api_ouverte": "0",
}


def _parametres(db) -> int:
    n = 0
    for cle, valeur in PARAMETRES_DEFAUT.items():
        if db.ligne("SELECT 1 FROM parametres WHERE cle = ?", (cle,)):
            continue
        db.executer("INSERT INTO parametres (cle, valeur) VALUES (?, ?)", (cle, valeur))
        n += 1
    return n


def _chambres(db) -> int:
    if db.valeur("SELECT COUNT(*) FROM chambres", defaut=0):
        return 0
    for nom, capacite, type_, aile, pmr in CHAMBRES_DEFAUT:
        db.executer(
            "INSERT INTO chambres (nom, capacite, type, aile, pmr) VALUES (?, ?, ?, ?, ?)",
            (nom, capacite, type_, aile, pmr))
    return len(CHAMBRES_DEFAUT)


def _demo(db) -> int:
    """Six demandes fictives, pour que le tableau de bord parle tout de suite."""
    if db.valeur("SELECT COUNT(*) FROM demandes", defaut=0):
        return 0
    auj = dt.date.today()
    jour = lambda n: (auj + dt.timedelta(days=n)).isoformat()
    modeles = [
        {"nom": "Kouassi", "prenom": "Jean", "provenance": "Abidjan",
         "telephone": "0701020304", "type_sejour": "retraite",
         "date_arrivee": jour(3), "date_depart": jour(6), "nb_personnes": 1,
         "statut": "en_attente"},
        {"nom": "Koffi", "prenom": "Aya", "provenance": "Yamoussoukro",
         "telephone": "0705060708", "type_sejour": "groupe",
         "date_arrivee": jour(9), "date_depart": jour(12), "nb_personnes": 12,
         "nb_hommes": 4, "nb_femmes": 8, "regime_alimentaire": "sans porc",
         "statut": "en_attente"},
        {"nom": "Traoré", "prenom": "Paul", "provenance": "Bouaké",
         "telephone": "0709101112", "type_sejour": "repos",
         "date_arrivee": jour(1), "date_depart": jour(4), "nb_personnes": 2,
         "statut": "acceptee"},
        {"nom": "Diomandé", "prenom": "Marie", "provenance": "Korhogo",
         "telephone": "0713141516", "type_sejour": "discernement",
         "date_arrivee": jour(20), "date_depart": jour(25), "nb_personnes": 1,
         "statut": "confirmee"},
        {"nom": "N'Guessan", "prenom": "Luc", "provenance": "Abidjan",
         "telephone": "0717181920", "type_sejour": "travail",
         "date_arrivee": jour(-10), "date_depart": jour(-6), "nb_personnes": 1,
         "statut": "sejour_termine"},
        {"nom": "Bamba", "prenom": "Fatou", "provenance": "Man",
         "telephone": "0721222324", "type_sejour": "couple",
         "date_arrivee": jour(30), "date_depart": jour(33), "nb_personnes": 2,
         "statut": "refusee"},
    ]
    n = 0
    for m in modeles:
        statut = m.pop("statut")
        identifiant = metier.creer_demande(db, {**m, "source": "demo"})
        db.executer("UPDATE demandes SET statut = ? WHERE id = ?", (statut, identifiant))
        n += 1
    # Une chambre attribuée, pour que le calendrier montre quelque chose.
    premiere = db.ligne("SELECT id FROM chambres ORDER BY id LIMIT 1")
    confirmee = db.ligne("SELECT id FROM demandes WHERE statut = 'confirmee' LIMIT 1")
    if premiere and confirmee:
        metier.attribuer_chambre(db, confirmee["id"], premiere["id"], acteur="demo")
    return n


def initialiser(db, demo: bool = False, silencieux: bool = False) -> dict:
    resultat = {"chambres": 0, "connaissances": 0, "parametres": 0, "demandes": 0}
    resultat["chambres"] = _chambres(db)
    resultat["parametres"] = _parametres(db)
    resultat["connaissances"] = knowledge.charger_graine(db, ecraser=False)
    if demo:
        resultat["demandes"] = _demo(db)
    db.journal("cli", "initialisation", "",
               f"chambres={resultat['chambres']} fiches={resultat['connaissances']}")
    if not silencieux:
        print(f"  Chambres créées          : {resultat['chambres']}")
        print(f"  Fiches de connaissance   : {resultat['connaissances']}")
        print(f"  Paramètres par défaut    : {resultat['parametres']}")
        if demo:
            print(f"  Demandes de démonstration: {resultat['demandes']}")
        manquantes = len(knowledge.fiches_a_completer(db))
        if manquantes:
            print(f"  Fiches à compléter       : {manquantes} (voir « Base de connaissances »)")
    return resultat
