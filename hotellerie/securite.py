# -*- coding: utf-8 -*-
"""
Mots de passe, sessions, jetons CSRF et signatures Meta.

Aucune dépendance : tout repose sur ``hashlib``, ``hmac`` et ``secrets``.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets

ITERATIONS = 100_000
DUREE_SESSION_HEURES = 12
MAX_TENTATIVES = 6
FENETRE_TENTATIVES_MINUTES = 15


# ---------------------------------------------------------------------------
# Mots de passe
# ---------------------------------------------------------------------------
def hacher_mot_de_passe(mot_de_passe: str):
    """Renvoie ``(sel_hex, empreinte_hex)``. Sel aléatoire à chaque appel."""
    sel = secrets.token_bytes(16)
    empreinte = hashlib.pbkdf2_hmac("sha256", (mot_de_passe or "").encode("utf-8"),
                                    sel, ITERATIONS)
    return sel.hex(), empreinte.hex()


def verifier_mot_de_passe(mot_de_passe: str, sel_hex: str, empreinte_hex: str) -> bool:
    try:
        sel = bytes.fromhex(sel_hex or "")
        attendu = bytes.fromhex(empreinte_hex or "")
    except ValueError:
        return False
    if not sel or not attendu:
        return False
    calcule = hashlib.pbkdf2_hmac("sha256", (mot_de_passe or "").encode("utf-8"),
                                  sel, ITERATIONS)
    return hmac.compare_digest(calcule, attendu)


def creer_utilisateur(db, nom: str, login: str, mot_de_passe: str,
                      role: str = "hotelier", email: str = "") -> int:
    sel, empreinte = hacher_mot_de_passe(mot_de_passe)
    return db.executer(
        "INSERT INTO utilisateurs (login, nom, role, email, sel, empreinte) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ((login or "").strip().lower(), nom or login, role, email or "", sel, empreinte),
    )


# ---------------------------------------------------------------------------
# Tentatives de connexion
# ---------------------------------------------------------------------------
def _horodatage() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def tentatives_recentes(db, login: str, ip: str = "") -> int:
    depuis = (dt.datetime.now() - dt.timedelta(minutes=FENETRE_TENTATIVES_MINUTES))
    depuis_txt = depuis.strftime("%Y-%m-%d %H:%M:%S")
    return int(db.valeur(
        "SELECT COUNT(*) FROM tentatives WHERE succes = 0 AND horodatage >= ? "
        "AND (login = ? OR ip = ?)", (depuis_txt, (login or "").lower(), ip or ""),
        defaut=0) or 0)


def connexion_bloquee(db, login: str, ip: str = "") -> bool:
    return tentatives_recentes(db, login, ip) >= MAX_TENTATIVES


def enregistrer_tentative(db, login: str, ip: str, succes: bool) -> None:
    db.executer("INSERT INTO tentatives (login, ip, succes) VALUES (?, ?, ?)",
                ((login or "").lower(), ip or "", 1 if succes else 0))
    # Ménage : on ne garde pas indéfiniment l'historique des essais.
    db.executer("DELETE FROM tentatives WHERE horodatage < ?",
                ((dt.datetime.now() - dt.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),))


def authentifier(db, login: str, mot_de_passe: str, ip: str = ""):
    """Renvoie la fiche utilisateur si les identifiants sont bons, sinon None.

    Renvoie aussi ``None`` (sans le dire) lorsque le compte est bloqué :
    l'interface affiche le motif, le code ne distingue pas les cas.
    """
    login = (login or "").strip().lower()
    if connexion_bloquee(db, login, ip):
        return None
    u = db.ligne("SELECT * FROM utilisateurs WHERE login = ? AND actif = 1", (login,))
    if not u:
        enregistrer_tentative(db, login, ip, False)
        return None
    if not verifier_mot_de_passe(mot_de_passe, u["sel"], u["empreinte"]):
        enregistrer_tentative(db, login, ip, False)
        return None
    enregistrer_tentative(db, login, ip, True)
    db.executer("UPDATE utilisateurs SET derniere_connexion = ? WHERE id = ?",
                (_horodatage(), u["id"]))
    return u


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def creer_session(db, login: str, ip: str = "", agent: str = "",
                  heures: int = DUREE_SESSION_HEURES) -> str:
    jeton = secrets.token_urlsafe(40)
    expire = (dt.datetime.now() + dt.timedelta(hours=heures)).strftime("%Y-%m-%d %H:%M:%S")
    db.executer("INSERT INTO sessions (jeton, login, expire_le, ip, agent) VALUES (?, ?, ?, ?, ?)",
                (jeton, login, expire, ip[:120], agent[:200]))
    db.executer("DELETE FROM sessions WHERE expire_le < ?", (_horodatage(),))
    return jeton


def session_valide(db, jeton: str):
    if not jeton:
        return None
    s = db.ligne("SELECT * FROM sessions WHERE jeton = ?", (jeton,))
    if not s or s["expire_le"] < _horodatage():
        return None
    return db.ligne("SELECT * FROM utilisateurs WHERE login = ? AND actif = 1", (s["login"],))


def detruire_session(db, jeton: str) -> None:
    if jeton:
        db.executer("DELETE FROM sessions WHERE jeton = ?", (jeton,))


def jeton_csrf(jeton_session: str) -> str:
    """Jeton CSRF dérivé de la session : ni stockage, ni expiration séparée."""
    return hmac.new((jeton_session or "").encode("utf-8"), b"csrf-hotellerie",
                    hashlib.sha256).hexdigest()


def verifier_csrf(jeton_session: str, fourni: str) -> bool:
    if not jeton_session or not fourni:
        return False
    return hmac.compare_digest(jeton_csrf(jeton_session), fourni)


# ---------------------------------------------------------------------------
# Signature des webhooks Meta
# ---------------------------------------------------------------------------
def verifier_signature_meta(secret: str, corps: bytes, signature: str) -> bool:
    """Vérifie ``X-Hub-Signature-256: sha256=…``.

    Si aucun secret n'est configuré, la vérification est réputée satisfaite :
    c'est l'exploitant qui choisit ce niveau (voir « Paramètres »).
    """
    if not secret:
        return True
    if not signature:
        return False
    attendu = "sha256=" + hmac.new(secret.encode("utf-8"), corps or b"",
                                   hashlib.sha256).hexdigest()
    return hmac.compare_digest(attendu, signature.strip())
