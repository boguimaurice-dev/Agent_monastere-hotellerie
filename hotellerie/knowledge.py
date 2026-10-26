# -*- coding: utf-8 -*-
"""
La base de connaissances : le « cerveau » de l'agent, et la parole de la maison.

Recherche lexicale pondérée, sans appel réseau, sans « embedding ». On sait
toujours pourquoi une fiche a été choisie — ce qu'une recherche vectorielle ne
permet pas. Les poids sont ceux du cahier des charges (§ 9.3).

Le mécanisme « À compléter » est essentiel : une information non publique
n'est jamais devinée. Elle reste entre crochets dans la fiche, le frère la voit
dans le tableau de bord, l'hôte ne la voit jamais.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from . import config

SEED_PATH = config.SEED_PATH

MARQUEUR_A_COMPLETER = "[[À COMPLÉTER"

# Mots vides : ils ne portent aucun sens pour le choix d'une fiche.
VIDES = {
    "le", "la", "les", "un", "une", "des", "de", "du", "au", "aux", "a",
    "et", "ou", "en", "dans", "sur", "sous", "pour", "par", "avec", "sans",
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses",
    "ce", "cet", "cette", "ces", "qui", "que", "quoi", "dont", "ou",
    "est", "sont", "etre", "etait", "ai", "as", "ont", "avoir", "faut",
    "se", "sa", "ne", "pas", "plus", "tres", "bien", "tout", "tous",
    "comment", "combien", "quand", "quel", "quelle", "quels", "quelles",
    "pourquoi", "pouvoir", "peut", "peux", "puis", "veux", "vouloir",
    "voudrais", "souhaite", "souhaiterais", "merci", "bonjour", "svp",
    "d", "l", "s", "n", "y", "c", "j", "m", "t", "qu",
}


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def normaliser(texte: str) -> str:
    """Minuscules, sans accents, sans ponctuation, apostrophes en espaces."""
    texte = (texte or "").lower()
    texte = unicodedata.normalize("NFD", texte)
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    texte = texte.replace("'", " ").replace("’", " ").replace("-", " ")
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


def mots(texte: str) -> list:
    return [m for m in normaliser(texte).split() if m]


def racine(mot: str) -> str:
    """Racine très légère : « offices » → « office », « horaires » → « horaire »."""
    if len(mot) > 3 and mot.endswith("s"):
        return mot[:-1]
    if len(mot) > 3 and mot.endswith("x"):
        return mot[:-1]
    return mot


def _significatifs(texte: str) -> set:
    return {racine(m) for m in mots(texte) if len(m) > 2 and m not in VIDES}


# ---------------------------------------------------------------------------
# Import de la graine
# ---------------------------------------------------------------------------
def charger_graine(db, ecraser: bool = False) -> int:
    """Importe ``base_connaissances.json`` dans la table ``connaissances``.

    Sans ``ecraser``, les fiches déjà présentes (et donc peut-être enrichies par
    les frères) ne sont jamais touchées. Renvoie le nombre de fiches traitées.
    """
    chemin = Path(SEED_PATH)
    if not chemin.exists():
        return 0
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except Exception:
        return 0
    return importer(db, donnees, ecraser=ecraser)


def importer(db, donnees, ecraser: bool = False) -> int:
    if isinstance(donnees, dict):
        donnees = donnees.get("fiches", [])
    total = 0
    for f in donnees or []:
        cle = (f.get("cle") or "").strip()
        if not cle:
            continue
        existe = db.ligne("SELECT id FROM connaissances WHERE cle = ?", (cle,))
        if existe and not ecraser:
            total += 1
            continue
        champs = (
            (f.get("categorie") or "divers").strip(),
            (f.get("question") or "").strip(),
            (f.get("mots_cles") or "").strip(),
            (f.get("reponse") or "").strip(),
            int(f.get("priorite") or 5),
            cle,
        )
        if existe:
            db.executer(
                "UPDATE connaissances SET categorie=?, question=?, mots_cles=?, reponse=?, "
                "priorite=?, maj_le=datetime('now','localtime') WHERE cle=?", champs)
        else:
            db.executer(
                "INSERT INTO connaissances (categorie, question, mots_cles, reponse, priorite, cle) "
                "VALUES (?, ?, ?, ?, ?, ?)", champs)
        total += 1
    return total


def exporter(db) -> list:
    """La base de connaissances sous forme de fichier transportable."""
    fiches = db.lignes(
        "SELECT cle, categorie, question, mots_cles, reponse, priorite, active "
        "FROM connaissances ORDER BY categorie, priorite DESC, cle")
    return fiches


# ---------------------------------------------------------------------------
# Recherche pondérée
# ---------------------------------------------------------------------------
def _score(fiche, requete_norm: str, requete_racines: set) -> float:
    score = 0.0
    liste_cles = [k.strip() for k in (fiche.get("mots_cles") or "").split(",") if k.strip()]
    for cle in liste_cles:
        cn = normaliser(cle)
        if not cn:
            continue
        if " " in cn:
            # Expression entière : signal le plus fort.
            if cn in requete_norm:
                score += 4.0
            elif all(racine(m) in requete_racines for m in cn.split() if m not in VIDES):
                score += 2.0
        elif racine(cn) in requete_racines:
            score += 3.0

    mots_question = _significatifs(fiche.get("question") or "")
    score += 2.0 * len(mots_question & requete_racines)

    mots_categorie = _significatifs((fiche.get("categorie") or "").replace("_", " "))
    score += 1.0 * len(mots_categorie & requete_racines)

    mots_reponse = _significatifs(fiche.get("reponse") or "")
    score += 0.4 * len(mots_reponse & requete_racines)

    try:
        score += 0.1 * float(fiche.get("priorite") or 5)
    except (TypeError, ValueError):
        score += 0.5
    return round(score, 3)


def chercher(db, texte: str, limite: int = 3) -> list:
    """Renvoie les fiches les plus pertinentes, ou ``[]`` si rien ne convient.

    Seuil haut (3,0), puis seuil bas (2,2) : on préfère le silence à une
    réponse à côté. C'est le principe P3 du cahier des charges.
    """
    requete_norm = normaliser(texte)
    if not requete_norm:
        return []
    requete_racines = _significatifs(texte)
    if not requete_racines:
        return []
    fiches = db.lignes("SELECT * FROM connaissances WHERE active = 1")
    notees = []
    for f in fiches:
        s = _score(f, requete_norm, requete_racines)
        if s > 0:
            f = dict(f)
            f["score"] = s
            notees.append(f)
    for seuil in (3.0, 2.2):
        retenues = [f for f in notees if f["score"] >= seuil]
        if retenues:
            retenues.sort(key=lambda f: (-f["score"], -int(f.get("priorite") or 0)))
            return retenues[:limite]
    return []


def fiche(db, identifiant):
    if isinstance(identifiant, int) or str(identifiant).isdigit():
        return db.ligne("SELECT * FROM connaissances WHERE id = ?", (int(identifiant),))
    return db.ligne("SELECT * FROM connaissances WHERE cle = ?", (str(identifiant),))


def fiches_a_completer(db) -> list:
    """Les fiches qui attendent la parole des frères."""
    return db.lignes(
        "SELECT * FROM connaissances WHERE active = 1 AND reponse LIKE ? "
        "ORDER BY categorie, cle", ("%" + MARQUEUR_A_COMPLETER + "%",))


def est_a_completer(reponse: str) -> bool:
    return MARQUEUR_A_COMPLETER in (reponse or "")


# ---------------------------------------------------------------------------
# Nettoyage avant envoi à un hôte
# ---------------------------------------------------------------------------
def nettoyer_reponse(texte: str) -> str:
    """Retire les mentions internes ``[[…]]`` et remet le texte en forme.

    Une consigne destinée aux frères ne doit jamais atteindre un hôte.
    """
    texte = texte or ""
    texte = re.sub(r"\[\[.*?\]\]", "", texte, flags=re.S)
    texte = re.sub(r"[ \t]+\n", "\n", texte)
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    return texte.strip()


def enregistrer(db, fiche_data: dict) -> int:
    """Crée ou met à jour une fiche ; renvoie son identifiant."""
    donnees = dict(fiche_data or {})
    identifiant = donnees.pop("id", None)
    cle = (donnees.get("cle") or "").strip()
    champs = (
        (donnees.get("categorie") or "divers").strip(),
        (donnees.get("question") or "").strip(),
        (donnees.get("mots_cles") or "").strip(),
        (donnees.get("reponse") or "").strip(),
        int(donnees.get("priorite") or 5),
        1 if str(donnees.get("active", 1)) not in ("0", "False", "false", "") else 0,
    )
    if identifiant:
        db.executer(
            "UPDATE connaissances SET categorie=?, question=?, mots_cles=?, reponse=?, "
            "priorite=?, active=?, maj_le=datetime('now','localtime') WHERE id=?",
            champs + (int(identifiant),))
        return int(identifiant)
    if not cle:
        cle = "fiche-" + re.sub(r"[^a-z0-9]+", "-", normaliser(donnees.get("question") or ""))[:40]
    existe = db.ligne("SELECT id FROM connaissances WHERE cle = ?", (cle,))
    if existe:
        # Une création avec une clé déjà prise met à jour la fiche existante :
        # mieux vaut corriger la parole de la maison que créer un doublon.
        db.executer(
            "UPDATE connaissances SET categorie=?, question=?, mots_cles=?, reponse=?, "
            "priorite=?, active=?, maj_le=datetime('now','localtime') WHERE id=?",
            champs + (int(existe["id"]),))
        return int(existe["id"])
    db.executer(
        "INSERT INTO connaissances (categorie, question, mots_cles, reponse, priorite, active, cle) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)", champs + (cle,))
    return int(db.valeur("SELECT id FROM connaissances WHERE cle = ?", (cle,), defaut=0) or 0)


def supprimer(db, identifiant) -> None:
    db.executer("DELETE FROM connaissances WHERE id = ?", (int(identifiant),))
