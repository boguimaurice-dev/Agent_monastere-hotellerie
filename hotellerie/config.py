# -*- coding: utf-8 -*-
"""
Paramètres de l'application — Hôtellerie & Accueil,
Monastère Bénédictin Sainte-Marie de Bouaké.

Ordre de priorité, sans exception :

    variable d'environnement  >  table ``parametres``  >  valeur par défaut

C'est ce qui permet de garder les jetons hors de la base (donc hors des
sauvegardes) tout en laissant les frères régler le reste depuis le tableau
de bord, sans redéploiement.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Emplacements
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

_env_data = os.environ.get("HOTELLERIE_DATA_DIR", "").strip()
DATA_DIR = Path(_env_data) if _env_data else (BASE_DIR / "data")
DB_PATH = DATA_DIR / "hotellerie.db"
LOG_DIR = DATA_DIR / "logs"
SEED_PATH = BASE_DIR / "base_connaissances.json"
ENV_PATH = BASE_DIR / ".env"

VERSION = "1.0"
NOM_APP = "Hôtellerie & Accueil"
NOM_MAISON = "Monastère Bénédictin Sainte-Marie de Bouaké"
SITE_WEB = "https://benedictinsbouake.com"

# ---------------------------------------------------------------------------
# Coordonnées de la maison (source unique, utilisée par l'agent et les fiches)
# ---------------------------------------------------------------------------
TEL_ACCUEIL = "07 47 52 05 57"
TEL_HOTELLERIE = "07 97 00 80 52"
TEL_BOUTIQUE = "07 78 32 17 37"
EMAIL_MAISON = "info@benedictinsbouake.com"

# Jetons par défaut (modifiables dans « Paramètres » ou par .env)
VERIFY_TOKEN_DEFAUT = "monastere-bouake"

# ---------------------------------------------------------------------------
# Lecture du fichier .env (facultative, sans dépendance)
# ---------------------------------------------------------------------------
def _charger_env(chemin: Path = ENV_PATH) -> None:
    """Charge les lignes ``CLE=valeur`` du fichier .env dans l'environnement.

    Une variable déjà définie dans l'environnement n'est jamais écrasée :
    c'est le comportement attendu d'un fichier de confort, pas d'un fichier
    qui prendrait le dessus sur l'exploitant.
    """
    try:
        if not chemin.exists():
            return
        for brute in chemin.read_text(encoding="utf-8").splitlines():
            ligne = brute.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, valeur = ligne.split("=", 1)
            cle = cle.strip()
            valeur = valeur.strip().strip('"').strip("'")
            if cle and cle not in os.environ:
                os.environ[cle] = valeur
    except Exception:  # un .env illisible ne doit jamais empêcher le démarrage
        pass


_charger_env()


# ---------------------------------------------------------------------------
# Accès simple à l'environnement
# ---------------------------------------------------------------------------
def env(cle: str, defaut: str = "") -> str:
    valeur = os.environ.get(cle)
    return defaut if valeur is None else valeur.strip()


def drapeau(cle: str, defaut: bool = False) -> bool:
    valeur = os.environ.get(cle)
    if valeur is None or valeur.strip() == "":
        return defaut
    return valeur.strip().lower() in ("1", "true", "oui", "yes", "on")


def entier(cle: str, defaut: int) -> int:
    try:
        return int(os.environ.get(cle, ""))
    except (TypeError, ValueError):
        return defaut


def assurer_dossiers() -> Path:
    """Crée le dossier de données et celui des journaux si besoin."""
    try:
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return Path(DATA_DIR)


# ---------------------------------------------------------------------------
# Paramètres en base, avec priorité à l'environnement
# ---------------------------------------------------------------------------
def parametre(db, cle: str, defaut: str = "") -> str:
    valeur = os.environ.get(cle)
    if valeur is not None and valeur.strip() != "":
        return valeur.strip()
    try:
        v = db.valeur("SELECT valeur FROM parametres WHERE cle = ?", (cle,))
    except Exception:
        v = None
    if v is None or str(v).strip() == "":
        return defaut
    return str(v).strip()


def drapeau_parametre(db, cle: str, defaut: bool = False) -> bool:
    valeur = parametre(db, cle, "")
    if valeur == "":
        return defaut
    return valeur.lower() in ("1", "true", "oui", "yes", "on")


def entier_parametre(db, cle: str, defaut: int) -> int:
    try:
        return int(parametre(db, cle, str(defaut)))
    except (TypeError, ValueError):
        return defaut


def definir_parametre(db, cle: str, valeur) -> None:
    db.executer(
        "INSERT INTO parametres (cle, valeur, maj_le) VALUES (?, ?, datetime('now','localtime')) "
        "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur, maj_le = excluded.maj_le",
        (cle, "" if valeur is None else str(valeur)),
    )


def tout_parametres(db) -> dict:
    try:
        return {l["cle"]: l["valeur"] for l in db.lignes("SELECT cle, valeur FROM parametres")}
    except Exception:
        return {}
