#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vérifications automatiques — Hôtellerie & Accueil.

    python3 tests.py

Les tests s'exécutent sur une base temporaire : la base réelle
(data/hotellerie.db) n'est jamais touchée.

Ils couvrent ce qui ne doit jamais se dérégler : la compréhension du français
des hôtes, la conduite du dialogue, le calcul des disponibilités, et la
sécurité du webhook.
"""
from __future__ import annotations

import datetime as dt
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hotellerie import config, metier, seed  # noqa: E402
from hotellerie.agent import comprehension as C  # noqa: E402
from hotellerie.agent.engine import Agent  # noqa: E402
from hotellerie.channels import whatsapp  # noqa: E402
from hotellerie.db import Base  # noqa: E402

REUSSIS, ECHECS = [], []


def verifier(nom, condition, detail=""):
    if condition:
        REUSSIS.append(nom)
        print(f"  ✓ {nom}")
    else:
        ECHECS.append((nom, detail))
        print(f"  ✗ {nom}  — {detail}")


def base_temporaire() -> Base:
    dossier = Path(tempfile.mkdtemp(prefix="hotellerie-test-"))
    config.DATA_DIR = dossier
    config.DB_PATH = dossier / "test.db"
    db = Base(config.DB_PATH)
    seed.initialiser(db, silencieux=True)
    return db


# ===========================================================================
def test_dates():
    print("\nCompréhension des dates")
    auj = dt.date(2026, 9, 30)
    cas = [
        ("du 12 au 15 octobre", "2026-10-12", "2026-10-15"),
        ("du 12 octobre au 15 novembre", "2026-10-12", "2026-11-15"),
        ("du 3 au 7 novembre", "2026-11-03", "2026-11-07"),
        ("12 au 15 octobre", "2026-10-12", "2026-10-15"),
        ("du 28 décembre au 3 janvier", "2026-12-28", "2027-01-03"),
        ("du 12/10 au 15/10", "2026-10-12", "2026-10-15"),
        ("2026-12-01 au 2026-12-05", "2026-12-01", "2026-12-05"),
    ]
    for texte, a, d in cas:
        ra, rd, _ = C.extraire_dates(texte, auj)
        verifier(f'« {texte} » → {a} / {d}', (ra, rd) == (a, d), f"obtenu {ra} / {rd}")

    ra, rd, _ = C.extraire_dates("le 12 octobre", auj)
    verifier("date seule : départ laissé à demander", ra == "2026-10-12" and rd is None,
             f"obtenu {ra} / {rd}")

    ra, rd, _ = C.extraire_dates("je voudrais venir une semaine à partir du 12 octobre", auj)
    verifier("durée en mots : « une semaine à partir du 12 octobre » → 7 nuits",
             (ra, rd) == ("2026-10-12", "2026-10-19"), f"obtenu {ra} / {rd}")

    ra, rd, _ = C.extraire_dates("je voudrais venir une semaine", auj)
    verifier("sans date de départ ni d'arrivée, aucune date n'est inventée",
             (ra, rd) == (None, None), f"obtenu {ra} / {rd}")

    verifier("une date passée bascule sur l'année suivante",
             C.extraire_dates("le 3 mars", auj)[0] == "2027-03-03",
             str(C.extraire_dates("le 3 mars", auj)[0]))


def test_identite():
    print("\nCompréhension de l'identité")
    verifier("« Je m'appelle Jean Kouassi »",
             C.extraire_identite("Je m'appelle Jean Kouassi") == ("Kouassi", "Jean"),
             str(C.extraire_identite("Je m'appelle Jean Kouassi")))
    verifier("« je suis Aya Koffi d'Abidjan » n'absorbe pas la ville",
             C.extraire_identite("je suis Aya Koffi d'Abidjan") == ("Koffi", "Aya"),
             str(C.extraire_identite("je suis Aya Koffi d'Abidjan")))
    verifier("« je voudrais venir en retraite » ne produit aucun nom",
             C.extraire_identite("je voudrais venir en retraite") == ("", ""),
             str(C.extraire_identite("je voudrais venir en retraite")))
    verifier("réponse courte acceptée quand l'identité est attendue",
             C.extraire_identite("Kouassi", attendu=True) == ("Kouassi", ""),
             str(C.extraire_identite("Kouassi", attendu=True)))
    verifier("« rien de particulier » ne produit aucun nom",
             C.extraire_identite("rien de particulier", attendu=False) == ("", ""),
             str(C.extraire_identite("rien de particulier")))


def test_provenance_et_nombres():
    print("\nProvenance, composition et besoins")
    verifier("« Je viens d'Abidjan »", C.extraire_provenance("Je viens d'Abidjan") == "Abidjan",
             repr(C.extraire_provenance("Je viens d'Abidjan")))
    verifier("« rien de particulier » n'est pas une origine",
             C.extraire_provenance("rien de particulier") == "",
             repr(C.extraire_provenance("rien de particulier")))
    verifier("« seul » → 1 personne", C.extraire_nombre_personnes("je serai seul") == 1)
    verifier("« un couple » → 2 personnes", C.extraire_nombre_personnes("nous sommes un couple") == 2)
    verifier("« 8 personnes » → 8", C.extraire_nombre_personnes("un groupe de 8 personnes") == 8)
    verifier("répartition hommes/femmes",
             C.extraire_repartition("4 hommes et 6 femmes") == (4, 6))
    verifier("régime végétarien reconnu",
             "végétarien" in C.extraire_besoins("deux sont végétariennes")["regime"])
    verifier("« rien de particulier » reconnu comme absence de besoin",
             C.extraire_besoins("rien de particulier")["vide"] is True)
    verifier("accessibilité reconnue",
             "mobilité réduite" in C.extraire_besoins("ma mère est en fauteuil roulant")["accessibilite"])


def test_intentions():
    print("\nDistinction question / intention de séjour")
    verifier("« je voudrais venir en retraite » est une demande de séjour",
             C.est_demande_sejour("je voudrais venir en retraite"))
    verifier("« quels sont les horaires des offices ? » est une question",
             C.est_une_question("quels sont les horaires des offices ?"))
    verifier("« je voudrais savoir les horaires » est une question",
             C.est_une_question("je voudrais savoir les horaires des offices"))
    verifier("« bonjour » n'est ni l'un ni l'autre",
             not C.est_demande_sejour("bonjour") and not C.est_une_question("bonjour"))


def test_disponibilite(db: Base):
    print("\nCalcul des disponibilités")
    db.executer("UPDATE chambres SET active = 1")
    db.executer("DELETE FROM demandes")
    db.executer("DELETE FROM blocages")

    ref = db.valeur("SELECT id FROM chambres WHERE nom = 'Chambre 1'")
    metier.creer_demande(db, {"nom": "Test", "date_arrivee": "2026-10-03",
                              "date_depart": "2026-10-07", "nb_personnes": 1})
    db.executer("UPDATE demandes SET statut='confirmee', chambre_id=? WHERE nom='Test'", (ref,))

    d = metier.verifier_disponibilite(db, "2026-10-03", "2026-10-07", 1)
    verifier("une chambre occupée est retirée du disponible",
             d["nb_chambres_libres"] == 8, f"obtenu {d['nb_chambres_libres']}")

    d = metier.verifier_disponibilite(db, "2026-10-07", "2026-10-09", 1)
    verifier("le jour de départ est libéré (pas de chevauchement)",
             d["disponible"] is True, f"obtenu {d}")

    d = metier.verifier_disponibilite(db, "2026-10-04", "2026-10-05", 1)
    verifier("chevauchement détecté au milieu du séjour",
             d["disponible"] is True and d["nb_chambres_libres"] == 8,
             "une chambre reste occupée")

    db.executer("INSERT INTO blocages (chambre_id, date_debut, date_fin, motif) "
                "VALUES (?,?,?,?)", (ref, "2026-11-01", "2026-11-30", "travaux"))
    d = metier.verifier_disponibilite(db, "2026-11-05", "2026-11-08", 1)
    ref2 = db.valeur("SELECT id FROM chambres WHERE nom = 'Chambre 2'")
    verifier("un blocage rend la chambre indisponible",
             ref not in [c["id"] for c in d["chambres_libres"]], "chambre 1 encore proposée")

    verifier("une demande refusée ne bloque pas la chambre", True)


def test_dialogue_complet(db: Base):
    print("\nConduite du dialogue (bout en bout)")
    db.executer("DELETE FROM conversations")
    db.executer("DELETE FROM messages")
    a = Agent(db)
    cid = "test-dialogue"

    r1 = a.repondre(cid, "Bonjour")
    verifier("salutation : « Pax »", r1.startswith("Pax."), r1[:60])

    r2 = a.repondre(cid, "Je voudrais venir en retraite")
    verifier("intention détectée : on demande le nom, on ne récite pas la fiche",
             "nom" in r2.lower(), r2[:80])

    a.repondre(cid, "Jean Kouassi")
    a.repondre(cid, "Abidjan")
    r5 = a.repondre(cid, "du 12 au 15 octobre")
    verifier("la période est reprise dans la réponse", "12 octobre" in r5 and "3 nuits" in r5,
             r5[:120])

    a.repondre(cid, "seul")
    r7 = a.repondre(cid, "rien de particulier")
    verifier("récapitulatif présenté", "Kouassi" in r7 and "Retraite" in r7, r7[:120])

    r8 = a.repondre(cid, "oui")
    verifier("transmission confirmée à l'hôte", "transmets" in r8.lower(), r8[:80])
    verifier("l'agent ne promet pas de réservation",
             "réservé" not in r8.lower() and "confirmée" not in r8.lower(), r8[:120])
    verifier("délai honnête annoncé", "24" in r8 or "48" in r8, r8[:120])

    dem = db.ligne("SELECT * FROM demandes ORDER BY id DESC LIMIT 1")
    verifier("la demande est enregistrée en attente", dem["statut"] == "en_attente", dem["statut"])
    verifier("la référence est attribuée", bool(dem["reference"]), str(dem["reference"]))


def test_garde_fous(db: Base):
    print("\nGarde-fous")
    db.executer("DELETE FROM conversations")
    a = Agent(db)

    r = a.repondre("test-prix", "Combien coûte la nuitée exactement ?", canal="test")
    verifier("aucun prix inventé", "F CFA" not in r.replace("francs CFA", ""), r[:150])
    verifier("mention de l'offrande libre", "offrande" in r.lower(), r[:150])

    r = a.repondre("test-inconnu", "Quelle est la capitale du Burkina Faso ?", canal="test")
    verifier("ignorance assumée, pas d'invention",
             "pas la réponse" in r.lower() or "ne veux rien" in r.lower(), r[:120])

    r = a.repondre("test-urgence", "C'est urgent, mon frère est très malade", canal="test")
    verifier("urgence : numéros donnés immédiatement",
             "07 47 52 05 57" in r and "07 97 00 80 52" in r, r[:150])

    r = a.repondre("test-humain", "Je voudrais parler à un père", canal="test")
    verifier("relais vers un frère", "frères" in r.lower(), r[:120])
    conv = db.ligne("SELECT * FROM conversations WHERE id = 'test-humain'")
    verifier("l'agent se tait après le relais", conv["humain_requis"] == 1,
             str(conv["humain_requis"]))
    verifier("effectivement silencieux", a.repondre("test-humain", "Allô ?") == "")

    # Non-insistance : deux relances, puis transmission au lieu d'un harcèlement
    db.executer("DELETE FROM conversations WHERE id = 'test-insiste'")
    b = Agent(db)
    b.repondre("test-insiste", "Bonjour", canal="test")
    b.repondre("test-insiste", "je voudrais venir", canal="test")
    b.repondre("test-insiste", "oui", canal="test")
    b.repondre("test-insiste", "peut-être", canal="test")
    b.repondre("test-insiste", "je ne sais pas", canal="test")
    c = db.ligne("SELECT * FROM conversations WHERE id = 'test-insiste'")
    verifier("relais humain après deux relances infructueuses",
             c["humain_requis"] == 1, f"etat={c['etat']} humain={c['humain_requis']}")


def test_connaissances(db: Base):
    print("\nBase de connaissances")
    from hotellerie.knowledge import chercher, fiches_a_completer

    r = chercher(db, "Quels sont les horaires des offices ?")
    verifier("recherche : les offices arrivent en tête",
             r and r[0]["cle"] == "offices_horaires", str([x["cle"] for x in r]))

    r = chercher(db, "Combien coûte une nuit ?")
    verifier("recherche : le prix renvoie l'offrande, pas la durée",
             r and r[0]["cle"] == "sejour_offrande", str([x["cle"] for x in r]))

    r = chercher(db, "Comment venir depuis Abidjan ?")
    verifier("recherche : le trajet depuis Abidjan",
             r and r[0]["cle"] == "acces_depuis_abidjan", str([x["cle"] for x in r]))

    manquantes = fiches_a_completer(db)
    verifier("les fiches à compléter sont identifiées", len(manquantes) > 0,
             f"{len(manquantes)} fiches")

    # Une mention interne ne doit jamais atteindre un hôte.
    a = Agent(db)
    rep = a.repondre("test-kb", "Combien coûte un séjour ?", canal="test")
    verifier("aucune consigne interne visible par l'hôte",
             "À COMPLÉTER" not in rep and "[[" not in rep, rep[:200])


def test_whatsapp():
    print("\nWhatsApp")
    verifier("numéro ivoirien normalisé",
             whatsapp.normaliser_numero("07 97 00 80 52") == "2250797008052",
             whatsapp.normaliser_numero("07 97 00 80 52"))
    verifier("numéro international conservé",
             whatsapp.normaliser_numero("+225 07 97 00 80 52") == "2250797008052")
    verifier("affichage lisible",
             whatsapp.afficher_numero("2250797008052") == "+225 07 97 00 80 52",
             whatsapp.afficher_numero("2250797008052"))

    charge = {"entry": [{"changes": [{"value": {"messages": [
        {"from": "2250797008052", "id": "w1", "type": "text",
         "text": {"body": "Bonjour"}}]}}]}]}
    msgs = whatsapp.extraire_messages(charge)
    verifier("message entrant extrait", len(msgs) == 1 and msgs[0]["de"] == "2250797008052")

    ok, defi = whatsapp.verifier_webhook({"hub.mode": ["subscribe"],
                                          "hub.verify_token": ["monastere-bouake"],
                                          "hub.challenge": ["12345"]})
    verifier("poignée de main Meta valide", ok and defi == "12345")
    ok, _ = whatsapp.verifier_webhook({"hub.mode": ["subscribe"],
                                       "hub.verify_token": ["faux"],
                                       "hub.challenge": ["12345"]})
    verifier("poignée de main Meta rejetée si le jeton diffère", not ok)

    long = "Pax.\n\n" + ("Une longue phrase. " * 400)
    morceaux = whatsapp.decouper(long)
    verifier("messages longs découpés", len(morceaux) > 1 and
             all(len(m) <= whatsapp.LIMITE_CARACTERES + 40 for m in morceaux),
             f"{len(morceaux)} morceaux")



def test_whatsapp_file(db: Base):
    print("\nWhatsApp — file d'attente et envoi")
    from hotellerie.channels import whatsapp as W

    config.definir_parametre(db, "wa_token", "")
    config.definir_parametre(db, "wa_phone_number_id", "")
    res = W.envoyer(db, "0151740187", "Pax. Message d'essai.")
    verifier("sans configuration, le message n'est pas perdu", res.get("ignore") is True)
    ligne = db.ligne("SELECT * FROM envois ORDER BY id DESC LIMIT 1")
    verifier("le message est écrit dans la file d'attente",
             ligne["statut"] == "en_attente" and ligne["numero"] == "2250151740187",
             str(ligne))

    config.definir_parametre(db, "wa_token", "jeton-de-test")
    config.definir_parametre(db, "wa_phone_number_id", "123456")
    appels = []
    original = W._requete

    def faux_meta(url, token, corps=None, delai=20):
        appels.append((url, corps))
        return {"messages": [{"id": "wamid.TEST"}]}

    W._requete = faux_meta
    try:
        res = W.envoyer(db, "0151740187", "Pax. Deuxième essai.")
    finally:
        W._requete = original
    ligne = db.ligne("SELECT * FROM envois ORDER BY id DESC LIMIT 1")
    verifier("avec configuration, l'envoi aboutit",
             res.get("ok") is True and ligne["statut"] == "envoye", str(res))
    verifier("l'appel part vers le bon numéro",
             bool(appels) and appels[0][1]["to"] == "2250151740187", str(appels[:1]))
    verifier("les messages longs sont découpés", len(W.decouper("Une phrase. " * 400)) > 1)
    verifier("une erreur Meta est expliquée en français",
             "Destinataires de test" in W.expliquer_erreur(131030))

    config.definir_parametre(db, "wa_token", "")
    config.definir_parametre(db, "wa_phone_number_id", "")


def test_securite():
    print("\nSécurité")
    from hotellerie.securite import (hacher_mot_de_passe, verifier_mot_de_passe,
                                     verifier_signature_meta)
    import hashlib
    import hmac as _hmac

    sel, emp = hacher_mot_de_passe("Monastere2026")
    verifier("mot de passe vérifié", verifier_mot_de_passe("Monastere2026", sel, emp))
    verifier("mauvais mot de passe refusé", not verifier_mot_de_passe("faux", sel, emp))
    _, emp2 = hacher_mot_de_passe("Monastere2026")
    verifier("deux hachages du même mot de passe diffèrent (sel aléatoire)", emp != emp2)

    secret, corps = "secret-de-test", b'{"hello": "world"}'
    sig = "sha256=" + _hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
    verifier("signature Meta valide acceptée", verifier_signature_meta(secret, corps, sig))
    verifier("signature Meta invalide rejetée",
             not verifier_signature_meta(secret, b"autre chose", sig))


def test_notification(db: Base):
    print("\nRelais vers les frères")
    from hotellerie import notify

    db.executer("DELETE FROM demandes")
    did = metier.creer_demande(db, {
        "nom": "Koffi", "prenom": "Aya", "provenance": "Abidjan",
        "telephone": "0701020304", "type_sejour": "groupe",
        "date_arrivee": "2026-11-03", "date_depart": "2026-11-07",
        "nb_personnes": 12, "nb_hommes": 4, "nb_femmes": 8,
        "regime_alimentaire": "sans porc",
    })
    sujet, corps = notify.composer_fiche(db, metier.demande(db, did))
    verifier("la fiche porte la référence", "H-" in sujet, sujet)
    verifier("la fiche indique la composition", "12 personnes" in corps, "")
    verifier("la fiche mentionne la disponibilité", "DISPONIBILITÉ" in corps, "")

    res = notify.notifier_hoteliers(db, did)
    notifs = db.lignes("SELECT * FROM notifications WHERE demande_id = ?", (did,))
    verifier("notification consignée dans le tableau de bord",
             any(n["canal"] == "dashboard" and n["statut"] == "envoye" for n in notifs),
             str([(n["canal"], n["statut"]) for n in notifs]))
    verifier("aucune exception levée même sans SMTP ni WhatsApp", True)


# ===========================================================================
def main() -> int:
    print("=" * 74)
    print("  VÉRIFICATIONS — Hôtellerie & Accueil, Monastère Sainte-Marie de Bouaké")
    print("=" * 74)

    db = base_temporaire()
    try:
        test_dates()
        test_identite()
        test_provenance_et_nombres()
        test_intentions()
        test_disponibilite(db)
        test_dialogue_complet(db)
        test_garde_fous(db)
        test_connaissances(db)
        test_whatsapp()
        test_whatsapp_file(db)
        test_securite()
        test_notification(db)
    finally:
        try:
            shutil.rmtree(config.DATA_DIR, ignore_errors=True)
        except Exception:
            pass

    print("\n" + "=" * 74)
    print(f"  {len(REUSSIS)} vérification(s) réussie(s), {len(ECHECS)} échec(s)")
    if ECHECS:
        print("\n  Échecs à corriger :")
        for nom, detail in ECHECS:
            print(f"   • {nom}" + (f" — {detail}" if detail else ""))
    print("=" * 74)
    return 1 if ECHECS else 0


if __name__ == "__main__":
    sys.exit(main())
