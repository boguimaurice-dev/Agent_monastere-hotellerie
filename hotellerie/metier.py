# -*- coding: utf-8 -*-
"""
Le métier de l'hôtellerie : demandes, disponibilités, occupation.

Ce module est entièrement déterministe. Aucun modèle de langage n'intervient
ici : une chambre est libre ou elle ne l'est pas, et le calcul doit pouvoir
être refait à la main par un frère.
"""
from __future__ import annotations

import calendar
import datetime as dt

# ---------------------------------------------------------------------------
# Natures de séjour
# ---------------------------------------------------------------------------
NATURES = {
    "retraite": "Retraite spirituelle individuelle",
    "repos": "Temps de repos",
    "couple": "Couple",
    "groupe": "Groupe ou session",
    "travail": "Mission de travail",
    "discernement": "Discernement vocationnel",
    "autre": "Autre",
}

STATUTS = {
    "en_attente": "En attente de discernement",
    "acceptee": "Acceptée par les frères",
    "confirmee": "Confirmée — chambre attribuée",
    "refusee": "Refusée",
    "annulee": "Annulée par l'hôte",
    "sejour_termine": "Séjour terminé",
}

STATUTS_OCCUPANTS = ("acceptee", "confirmee")


def nature(code: str) -> str:
    return NATURES.get((code or "autre").strip().lower(), NATURES["autre"])


def libelle_statut(code: str) -> str:
    return STATUTS.get((code or "").strip().lower(), code or "—")


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
def aujourdhui() -> dt.date:
    return dt.date.today()


def iso(valeur) -> str:
    """Renvoie une date ISO (AAAA-MM-JJ) ou une chaîne vide."""
    if not valeur:
        return ""
    if isinstance(valeur, dt.date):
        return valeur.isoformat()
    return str(valeur)[:10]


def lire_date(valeur):
    try:
        return dt.date.fromisoformat(str(valeur)[:10])
    except (TypeError, ValueError):
        return None


def nuits(arrivee, depart) -> int:
    a, d = lire_date(arrivee), lire_date(depart)
    if not a or not d or d <= a:
        return 0
    return (d - a).days


def format_date(valeur, long: bool = False) -> str:
    d = lire_date(valeur)
    if not d:
        return "—"
    return d.strftime("%d/%m/%Y")


def format_date_longue(valeur) -> str:
    """« 12 octobre 2026 » — sans zéro initial, pour une lecture naturelle."""
    d = lire_date(valeur)
    if not d:
        return "—"
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre"]
    return f"{d.day} {mois[d.month - 1]} {d.year}"


# ---------------------------------------------------------------------------
# Chambres
# ---------------------------------------------------------------------------
def chambres(db, actives_only: bool = True) -> list:
    sql = "SELECT * FROM chambres"
    if actives_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY id"
    return db.lignes(sql)


def chambre(db, identifiant):
    if not identifiant:
        return None
    return db.ligne("SELECT * FROM chambres WHERE id = ?", (int(identifiant),))


def enregistrer_chambre(db, donnees: dict) -> int:
    identifiant = donnees.get("id")
    champs = (
        (donnees.get("nom") or "Chambre").strip(),
        max(1, int(donnees.get("capacite") or 1)),
        (donnees.get("type") or "individuelle").strip(),
        (donnees.get("aile") or "").strip(),
        1 if str(donnees.get("pmr") or "0") in ("1", "on", "true", "oui") else 0,
        (donnees.get("note") or "").strip(),
        1 if str(donnees.get("active", 1)) not in ("0", "", "false", "False") else 0,
    )
    if identifiant:
        db.executer("UPDATE chambres SET nom=?, capacite=?, type=?, aile=?, pmr=?, note=?, active=? "
                    "WHERE id=?", champs + (int(identifiant),))
        return int(identifiant)
    return int(db.executer("INSERT INTO chambres (nom, capacite, type, aile, pmr, note, active) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?)", champs))


def supprimer_chambre(db, identifiant) -> None:
    """On désactive plutôt que de supprimer : l'historique doit rester lisible."""
    db.executer("UPDATE chambres SET active = 0 WHERE id = ?", (int(identifiant),))


# ---------------------------------------------------------------------------
# Demandes
# ---------------------------------------------------------------------------
def reference(db) -> str:
    annee = aujourdhui().year
    prefixe = f"H-{annee}-"
    dernier = db.valeur(
        "SELECT MAX(CAST(SUBSTR(reference, ?) AS INTEGER)) FROM demandes WHERE reference LIKE ?",
        (len(prefixe) + 1, prefixe + "%"), defaut=0) or 0
    # On vérifie l'unicité : une référence ne se réutilise jamais.
    for _ in range(1000):
        dernier += 1
        candidate = f"{prefixe}{dernier:04d}"
        if not db.ligne("SELECT 1 FROM demandes WHERE reference = ?", (candidate,)):
            return candidate
    return f"{prefixe}{dt.datetime.now().strftime('%H%M%S')}"


CHAMPS_DEMANDE = (
    "nom", "prenom", "provenance", "telephone", "email", "type_sejour",
    "date_arrivee", "date_depart", "nb_personnes", "nb_hommes", "nb_femmes",
    "regime_alimentaire", "accessibilite", "participation_offices",
    "premiere_visite", "besoin_note", "message", "conversation_id", "source",
)


def creer_demande(db, donnees: dict) -> int:
    d = dict(donnees or {})
    champs = {c: d.get(c) for c in CHAMPS_DEMANDE}
    champs["nom"] = (champs.get("nom") or "").strip()
    champs["prenom"] = (champs.get("prenom") or "").strip()
    champs["provenance"] = (champs.get("provenance") or "").strip()
    champs["type_sejour"] = (champs.get("type_sejour") or "autre").strip().lower()
    champs["date_arrivee"] = iso(champs.get("date_arrivee")) or None
    champs["date_depart"] = iso(champs.get("date_depart")) or None
    for cle in ("nb_personnes",):
        try:
            champs[cle] = max(1, int(champs.get(cle) or 1))
        except (TypeError, ValueError):
            champs[cle] = 1
    for cle in ("nb_hommes", "nb_femmes", "premiere_visite"):
        if champs.get(cle) in ("", "None"):
            champs[cle] = None
        elif champs.get(cle) is not None:
            try:
                champs[cle] = int(champs[cle])
            except (TypeError, ValueError):
                champs[cle] = None
    for cle in ("telephone", "email", "regime_alimentaire", "accessibilite",
                "participation_offices", "besoin_note", "message", "conversation_id", "source"):
        champs[cle] = (champs.get(cle) or "") if champs.get(cle) is not None else ""
    champs["source"] = champs["source"] or "agent"

    identifiant = db.executer(
        "INSERT INTO demandes (reference, nom, prenom, provenance, telephone, email, "
        "type_sejour, date_arrivee, date_depart, nb_personnes, nb_hommes, nb_femmes, "
        "regime_alimentaire, accessibilite, participation_offices, premiere_visite, "
        "besoin_note, message, conversation_id, source, statut) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'en_attente')",
        (reference(db), champs["nom"], champs["prenom"], champs["provenance"],
         champs["telephone"], champs["email"], champs["type_sejour"],
         champs["date_arrivee"], champs["date_depart"], champs["nb_personnes"],
         champs["nb_hommes"], champs["nb_femmes"], champs["regime_alimentaire"],
         champs["accessibilite"], champs["participation_offices"],
         champs["premiere_visite"], champs["besoin_note"], champs["message"],
         champs["conversation_id"], champs["source"]))
    if champs.get("conversation_id"):
        db.executer("UPDATE conversations SET demande_id = ? WHERE id = ?",
                    (identifiant, champs["conversation_id"]))
    db.journal(champs.get("source") or "agent", "demande_creee",
               str(identifiant), f"{champs['prenom']} {champs['nom']}".strip())
    return int(identifiant)


def demande(db, identifiant):
    if not identifiant:
        return None
    return db.ligne("SELECT * FROM demandes WHERE id = ?", (int(identifiant),))


def par_reference(db, ref: str):
    return db.ligne("SELECT * FROM demandes WHERE reference = ?", (ref,))


def mettre_a_jour(db, identifiant, champs: dict) -> None:
    autorises = [c for c in (set(CHAMPS_DEMANDE) | {"statut", "chambre_id", "notes_internes",
                             "decision_le", "decide_par"}) if c in champs]
    if not autorises:
        return
    morceaux = ", ".join(f"{c} = ?" for c in autorises)
    valeurs = [champs[c] for c in autorises]
    valeurs.append(int(identifiant))
    db.executer(f"UPDATE demandes SET {morceaux}, maj_le = datetime('now','localtime') "
                "WHERE id = ?", valeurs)


def changer_statut(db, identifiant, statut: str, acteur: str = "") -> None:
    if statut not in STATUTS:
        return
    db.executer(
        "UPDATE demandes SET statut = ?, decision_le = datetime('now','localtime'), "
        "decide_par = ?, maj_le = datetime('now','localtime') WHERE id = ?",
        (statut, acteur or "", int(identifiant)))
    db.journal(acteur or "systeme", "statut_change", str(identifiant), statut)


def attribuer_chambre(db, identifiant, chambre_id, acteur: str = "") -> None:
    if chambre_id in (None, "", "0"):
        db.executer("UPDATE demandes SET chambre_id = NULL WHERE id = ?", (int(identifiant),))
    else:
        db.executer("UPDATE demandes SET chambre_id = ? WHERE id = ?",
                    (int(chambre_id), int(identifiant)))
        db.executer("UPDATE demandes SET statut = 'confirmee', decision_le = datetime('now','localtime'), "
                    "decide_par = ? WHERE id = ?", (acteur or "", int(identifiant)))
    db.journal(acteur or "systeme", "chambre_attribuee", str(identifiant), str(chambre_id or ""))


def supprimer_demande(db, identifiant) -> None:
    db.executer("DELETE FROM demandes WHERE id = ?", (int(identifiant),))
    db.journal("systeme", "demande_supprimee", str(identifiant))


def demandes(db, statut: str = "", recherche: str = "", limite: int = 200) -> list:
    sql = "SELECT * FROM demandes WHERE 1 = 1"
    params = []
    if statut:
        sql += " AND statut = ?"
        params.append(statut)
    if recherche:
        sql += (" AND (nom LIKE ? OR prenom LIKE ? OR reference LIKE ? OR provenance LIKE ? "
                "OR telephone LIKE ? OR email LIKE ?)")
        motif = f"%{recherche}%"
        params.extend([motif] * 6)
    sql += " ORDER BY cree_le DESC, id DESC LIMIT ?"
    params.append(int(limite))
    return db.lignes(sql, params)


# ---------------------------------------------------------------------------
# Disponibilités
# ---------------------------------------------------------------------------
def _chambres_occupees(db, arrivee: str, depart: str) -> dict:
    """Chambre → motif d'occupation sur la période (arrivée incluse, départ exclu)."""
    occupees = {}
    for ligne in db.lignes(
        "SELECT d.chambre_id, d.reference, d.date_arrivee, d.date_depart FROM demandes d "
        "WHERE d.statut IN ('acceptee', 'confirmee') AND d.chambre_id IS NOT NULL "
        "AND d.date_arrivee IS NOT NULL "
        "AND d.date_arrivee < ? "
        "AND COALESCE(d.date_depart, date(d.date_arrivee, '+1 day')) > ?",
        (depart, arrivee)):
        occupees[ligne["chambre_id"]] = f"séjour {ligne['reference'] or ''}".strip()
    for ligne in db.lignes(
        "SELECT chambre_id, motif FROM blocages WHERE date_debut < ? AND date_fin > ?",
        (depart, arrivee)):
        occupees.setdefault(ligne["chambre_id"], ligne["motif"] or "indisponible")
    return occupees


def verifier_disponibilite(db, arrivee, depart, nb_personnes: int = 1) -> dict:
    """Calcule ce que les frères doivent savoir avant de discerner.

    L'agent ne s'en sert jamais pour dire « il y a de la place » : la
    disponibilité est portée sur la fiche remise aux frères (voir notify.py).
    """
    arrivee_iso, depart_iso = iso(arrivee), iso(depart)
    actives = chambres(db, actives_only=True)
    resultat = {
        "disponible": False,
        "nb_chambres_libres": 0,
        "nb_chambres_totales": len(actives),
        "capacite_libre": 0,
        "capacite_totale": sum(int(c["capacite"] or 1) for c in actives),
        "chambres_libres": [],
        "chambres_occupees": [],
        "nuits": nuits(arrivee_iso, depart_iso),
        "motif": "",
    }
    if not arrivee_iso or not depart_iso:
        resultat["motif"] = "dates incomplètes"
        return resultat
    if depart_iso <= arrivee_iso:
        resultat["motif"] = "la date de départ doit suivre la date d'arrivée"
        return resultat
    try:
        nb_personnes = max(1, int(nb_personnes or 1))
    except (TypeError, ValueError):
        nb_personnes = 1
    occupees = _chambres_occupees(db, arrivee_iso, depart_iso)
    libres = []
    for c in actives:
        if c["id"] in occupees:
            resultat["chambres_occupees"].append({**c, "motif": occupees[c["id"]]})
        else:
            libres.append(c)
    resultat["chambres_libres"] = libres
    resultat["nb_chambres_libres"] = len(libres)
    resultat["capacite_libre"] = sum(int(c["capacite"] or 1) for c in libres)
    resultat["disponible"] = resultat["capacite_libre"] >= nb_personnes
    if not libres:
        resultat["motif"] = "aucune chambre libre sur la période"
    elif not resultat["disponible"]:
        resultat["motif"] = (f"capacité libre insuffisante "
                             f"({resultat['capacite_libre']} places pour {nb_personnes})")
    return resultat


# ---------------------------------------------------------------------------
# Blocages
# ---------------------------------------------------------------------------
def creer_blocage(db, chambre_id, debut, fin, motif: str = "") -> int:
    return int(db.executer(
        "INSERT INTO blocages (chambre_id, date_debut, date_fin, motif) VALUES (?, ?, ?, ?)",
        (int(chambre_id), iso(debut), iso(fin), (motif or "").strip())))


def supprimer_blocage(db, identifiant) -> None:
    db.executer("DELETE FROM blocages WHERE id = ?", (int(identifiant),))


def blocages(db) -> list:
    return db.lignes(
        "SELECT b.*, c.nom AS chambre_nom FROM blocages b "
        "LEFT JOIN chambres c ON c.id = b.chambre_id ORDER BY b.date_debut")


# ---------------------------------------------------------------------------
# Occupation et statistiques
# ---------------------------------------------------------------------------
def occupation_mois(db, annee: int, mois: int) -> dict:
    """Calendrier chambre × jour pour un mois donné."""
    premier = dt.date(annee, mois, 1)
    dernier = dt.date(annee, mois, calendar.monthrange(annee, mois)[1])
    liste_chambres = chambres(db)
    cases = {}

    for d in db.lignes(
        "SELECT d.*, c.nom AS chambre_nom FROM demandes d LEFT JOIN chambres c "
        "ON c.id = d.chambre_id WHERE d.statut IN ('acceptee', 'confirmee', 'en_attente') "
        "AND d.date_arrivee IS NOT NULL AND d.chambre_id IS NOT NULL "
        "AND d.date_arrivee <= ? AND COALESCE(d.date_depart, d.date_arrivee) >= ?",
        (dernier.isoformat(), premier.isoformat())):
        jour = max(lire_date(d["date_arrivee"]), premier)
        fin = min(lire_date(d["date_depart"]) or lire_date(d["date_arrivee"]), dernier)
        while jour < fin:
            cases[(jour.isoformat(), d["chambre_id"])] = {
                "type": "sejour", "reference": d["reference"], "demande_id": d["id"],
                "nom": f"{d['prenom']} {d['nom']}".strip(),
                "statut": d["statut"],
                "arrivee": iso(d["date_arrivee"]),
                "depart": iso(d["date_depart"]),
            }
            jour += dt.timedelta(days=1)

    for b in db.lignes(
        "SELECT * FROM blocages WHERE date_debut <= ? AND date_fin >= ?",
        (dernier.isoformat(), premier.isoformat())):
        jour = max(lire_date(b["date_debut"]), premier)
        fin = min(lire_date(b["date_fin"]), dernier)
        while jour < fin:
            cases[(jour.isoformat(), b["chambre_id"])] = {
                "type": "blocage", "motif": b["motif"], "blocage_id": b["id"]}
            jour += dt.timedelta(days=1)

    jours = [dt.date(annee, mois, j) for j in range(1, dernier.day + 1)]
    return {"annee": annee, "mois": mois, "premier": premier, "dernier": dernier,
            "chambres": liste_chambres, "jours": jours, "cases": cases}


def stats(db) -> dict:
    auj = aujourdhui().isoformat()
    return {
        "en_attente": int(db.valeur("SELECT COUNT(*) FROM demandes WHERE statut='en_attente'", defaut=0) or 0),
        "acceptees": int(db.valeur("SELECT COUNT(*) FROM demandes WHERE statut='acceptee'", defaut=0) or 0),
        "arrivees_jour": int(db.valeur(
            "SELECT COUNT(*) FROM demandes WHERE date_arrivee = ? "
            "AND statut IN ('acceptee', 'confirmee')", (auj,), defaut=0) or 0),
        "departs_jour": int(db.valeur(
            "SELECT COUNT(*) FROM demandes WHERE date_depart = ? "
            "AND statut IN ('acceptee', 'confirmee')", (auj,), defaut=0) or 0),
        "conversations_jour": int(db.valeur(
            "SELECT COUNT(*) FROM conversations WHERE substr(maj, 1, 10) = ?", (auj,), defaut=0) or 0),
        "humain_requis": int(db.valeur(
            "SELECT COUNT(*) FROM conversations WHERE humain_requis = 1", defaut=0) or 0),
        "notifications_echouees": int(db.valeur(
            "SELECT COUNT(*) FROM notifications WHERE statut IN ('echoue', 'ignore')", defaut=0) or 0),
        "chambres_actives": int(db.valeur(
            "SELECT COUNT(*) FROM chambres WHERE active = 1", defaut=0) or 0),
        "capacite_totale": int(db.valeur(
            "SELECT COALESCE(SUM(capacite), 0) FROM chambres WHERE active = 1", defaut=0) or 0),
        "demandes_total": int(db.valeur("SELECT COUNT(*) FROM demandes", defaut=0) or 0),
    }
