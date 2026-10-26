# -*- coding: utf-8 -*-
"""
Module de langage — facultatif, et toujours facultatif.

Sans clé d'API, l'agent répond depuis la base de connaissances : gratuit,
prévisible, instantané, et fonctionnel hors ligne. La clé n'ajoute qu'une
formulation plus souple. Si l'appel échoue, on retombe silencieusement sur la
réponse déterministe : le service ne dépend jamais d'un tiers.

Aucune bibliothèque : ``urllib`` suffit.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from .. import config

log = logging.getLogger(__name__)

API_OPENAI = "https://api.openai.com/v1/chat/completions"
API_ANTHROPIC = "https://api.anthropic.com/v1/messages"

CONSIGNE = (
    "Tu reformules une réponse déjà rédigée par la maison. Tu ne dois ajouter "
    "AUCUN fait : ni prix, ni horaire, ni disponibilité, ni nom, ni adresse, ni "
    "date. Tu gardes le vouvoiement, la sobriété, et tu ne dépasses pas 700 "
    "caractères. Si la réponse fournie contient une information, tu la conserves "
    "exactement. Tu ne confirmes jamais une réservation. Tu réponds uniquement "
    "par le texte final, sans commentaire."
)


class Moteur:
    """Enveloppe minimale autour d'une API de langage, avec repli systématique."""

    def __init__(self, db):
        self.db = db

    # -- configuration -----------------------------------------------------
    def cle(self) -> str:
        for variable in ("IA_CLE_API", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            valeur = config.env(variable)
            if valeur:
                return valeur
        return config.parametre(self.db, "ia_cle_api", "")

    def fournisseur(self) -> str:
        return config.parametre(self.db, "ia_fournisseur", "openai").lower()

    def modele(self) -> str:
        defaut = "claude-3-5-haiku-latest" if self.fournisseur() == "anthropic" else "gpt-4o-mini"
        return config.parametre(self.db, "ia_modele", defaut)

    def disponible(self) -> bool:
        return config.drapeau_parametre(self.db, "ia_active", False) and bool(self.cle())

    # -- appel -------------------------------------------------------------
    def formuler(self, message: str, reponse_defaut: str, contexte: str = "") -> str:
        """Renvoie une reformulation, ou la réponse d'origine en cas de doute."""
        if not self.disponible() or not reponse_defaut:
            return reponse_defaut
        try:
            delai = config.entier_parametre(self.db, "ia_delai", 20)
            temperature = float(config.parametre(self.db, "ia_temperature", "0.4") or 0.4)
            contenu = (
                f"Question de l'hôte : {message}\n\n"
                f"Réponse de la maison :\n{reponse_defaut}\n\n"
                f"Contexte du dialogue : {contexte or 'aucun'}"
            )
            if self.fournisseur() == "anthropic":
                texte = self._anthropic(contenu, temperature, delai)
            else:
                texte = self._openai(contenu, temperature, delai)
            texte = (texte or "").strip()
            if not texte or len(texte) < 10:
                return reponse_defaut
            # Garde-fou : jamais de consigne interne dans une réponse d'hôte.
            if "[[" in texte or "À COMPLÉTER" in texte:
                return reponse_defaut
            return texte
        except Exception as exc:  # réseau, quota, format : on n'insiste pas
            log.warning("Module de langage indisponible : %s", exc)
            return reponse_defaut

    def _openai(self, contenu: str, temperature: float, delai: int) -> str:
        corps = {
            "model": self.modele(),
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": CONSIGNE},
                {"role": "user", "content": contenu},
            ],
        }
        requete = urllib.request.Request(
            API_OPENAI, data=json.dumps(corps).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.cle()}",
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(requete, timeout=delai) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8"))
        return donnees["choices"][0]["message"]["content"]

    def _anthropic(self, contenu: str, temperature: float, delai: int) -> str:
        corps = {
            "model": self.modele(),
            "max_tokens": 700,
            "temperature": temperature,
            "system": CONSIGNE,
            "messages": [{"role": "user", "content": contenu}],
        }
        requete = urllib.request.Request(
            API_ANTHROPIC, data=json.dumps(corps).encode("utf-8"),
            headers={"x-api-key": self.cle(), "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(requete, timeout=delai) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8"))
        return "".join(bloc.get("text", "") for bloc in donnees.get("content", []))
