# -*- coding: utf-8 -*-
"""
Accès à la base SQLite de l'hôtellerie.

Un seul fichier tient toute l'application : sauvegarde = copie, restauration =
copie. Aucune dépendance externe, aucun serveur à administrer.

La connexion est ouverte une fois et partagée entre les requêtes du serveur
(``ThreadingHTTPServer``) : elle est donc protégée par un verrou, et ouverte
avec ``check_same_thread=False``. SQLite en mode WAL supporte sans peine la
charge d'un monastère.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS chambres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL UNIQUE,
        capacite INTEGER NOT NULL DEFAULT 1,
        type TEXT NOT NULL DEFAULT 'individuelle',
        aile TEXT NOT NULL DEFAULT '',
        pmr INTEGER NOT NULL DEFAULT 0,
        note TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS demandes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference TEXT,
        cree_le TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        maj_le TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        statut TEXT NOT NULL DEFAULT 'en_attente',
        nom TEXT NOT NULL DEFAULT '',
        prenom TEXT NOT NULL DEFAULT '',
        provenance TEXT NOT NULL DEFAULT '',
        telephone TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        type_sejour TEXT NOT NULL DEFAULT 'autre',
        date_arrivee TEXT,
        date_depart TEXT,
        nb_personnes INTEGER NOT NULL DEFAULT 1,
        nb_hommes INTEGER,
        nb_femmes INTEGER,
        regime_alimentaire TEXT NOT NULL DEFAULT '',
        accessibilite TEXT NOT NULL DEFAULT '',
        participation_offices TEXT NOT NULL DEFAULT '',
        premiere_visite INTEGER,
        besoin_note TEXT NOT NULL DEFAULT '',
        message TEXT NOT NULL DEFAULT '',
        chambre_id INTEGER REFERENCES chambres(id) ON DELETE SET NULL,
        notes_internes TEXT NOT NULL DEFAULT '',
        conversation_id TEXT,
        source TEXT NOT NULL DEFAULT 'agent',
        decision_le TEXT,
        decide_par TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        canal TEXT NOT NULL DEFAULT 'whatsapp',
        telephone TEXT NOT NULL DEFAULT '',
        nom_affiche TEXT NOT NULL DEFAULT '',
        debut TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        maj TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        etat TEXT NOT NULL DEFAULT 'accueil',
        donnees TEXT NOT NULL DEFAULT '{}',
        relances INTEGER NOT NULL DEFAULT 0,
        humain_requis INTEGER NOT NULL DEFAULT 0,
        demande_id INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        horodatage TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        direction TEXT NOT NULL,
        canal TEXT NOT NULL DEFAULT '',
        corps TEXT NOT NULL DEFAULT '',
        intention TEXT NOT NULL DEFAULT '',
        meta TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS blocages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chambre_id INTEGER REFERENCES chambres(id) ON DELETE CASCADE,
        date_debut TEXT NOT NULL,
        date_fin TEXT NOT NULL,
        motif TEXT NOT NULL DEFAULT '',
        cree_le TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""",
    """CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        demande_id INTEGER,
        canal TEXT NOT NULL,
        destinataire TEXT NOT NULL DEFAULT '',
        sujet TEXT NOT NULL DEFAULT '',
        statut TEXT NOT NULL DEFAULT 'envoye',
        erreur TEXT NOT NULL DEFAULT '',
        horodatage TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""",
    """CREATE TABLE IF NOT EXISTS connaissances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cle TEXT NOT NULL UNIQUE,
        categorie TEXT NOT NULL DEFAULT 'divers',
        question TEXT NOT NULL DEFAULT '',
        mots_cles TEXT NOT NULL DEFAULT '',
        reponse TEXT NOT NULL DEFAULT '',
        priorite INTEGER NOT NULL DEFAULT 5,
        active INTEGER NOT NULL DEFAULT 1,
        maj_le TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""",
    """CREATE TABLE IF NOT EXISTS utilisateurs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT NOT NULL UNIQUE,
        nom TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT 'hotelier',
        email TEXT NOT NULL DEFAULT '',
        sel TEXT NOT NULL,
        empreinte TEXT NOT NULL,
        actif INTEGER NOT NULL DEFAULT 1,
        cree_le TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        derniere_connexion TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        jeton TEXT PRIMARY KEY,
        login TEXT NOT NULL,
        cree_le TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        expire_le TEXT NOT NULL,
        ip TEXT NOT NULL DEFAULT '',
        agent TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS tentatives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT NOT NULL DEFAULT '',
        ip TEXT NOT NULL DEFAULT '',
        horodatage TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        succes INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS parametres (
        cle TEXT PRIMARY KEY,
        valeur TEXT NOT NULL DEFAULT '',
        maj_le TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )""",
    """CREATE TABLE IF NOT EXISTS journal (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        horodatage TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        acteur TEXT NOT NULL DEFAULT '',
        action TEXT NOT NULL DEFAULT '',
        objet TEXT NOT NULL DEFAULT '',
        details TEXT NOT NULL DEFAULT ''
    )""",
    "CREATE INDEX IF NOT EXISTS idx_demandes_statut ON demandes (statut)",
    "CREATE INDEX IF NOT EXISTS idx_demandes_dates ON demandes (date_arrivee, date_depart)",
    "CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages (conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_demande ON notifications (demande_id)",
    """CREATE TABLE IF NOT EXISTS envois (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        demande_id INTEGER,
        conversation_id TEXT NOT NULL DEFAULT '',
        numero TEXT NOT NULL,
        corps TEXT NOT NULL,
        statut TEXT NOT NULL DEFAULT 'en_attente',
        erreur TEXT NOT NULL DEFAULT '',
        tentatives INTEGER NOT NULL DEFAULT 0,
        cree_le TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        envoye_le TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_journal_date ON journal (horodatage)",
    "CREATE INDEX IF NOT EXISTS idx_envois_statut ON envois (statut, id)",
]


class Base:
    """Connexion SQLite partagée, avec verrou d'écriture."""

    def __init__(self, chemin):
        self.chemin = Path(chemin)
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._verrou = threading.RLock()
        self.conn = sqlite3.connect(str(self.chemin), timeout=30.0,
                                   check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._verrou.acquire()
        try:
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("PRAGMA busy_timeout = 30000")
            self.conn.execute("PRAGMA synchronous = NORMAL")
            for instruction in SCHEMA:
                self.conn.execute(instruction)
            self.conn.commit()
        finally:
            self._verrou.release()

    # -- écriture -----------------------------------------------------------
    def executer(self, sql: str, params=()):
        """Exécute une instruction d'écriture et renvoie le dernier identifiant."""
        with self._verrou:
            cur = self.conn.execute(sql, tuple(params))
            self.conn.commit()
            return cur.lastrowid

    def executer_plusieurs(self, sql: str, series) -> None:
        with self._verrou:
            self.conn.executemany(sql, series)
            self.conn.commit()

    # -- lecture -----------------------------------------------------------
    def lignes(self, sql: str, params=()) -> list:
        with self._verrou:
            cur = self.conn.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def ligne(self, sql: str, params=()):
        with self._verrou:
            cur = self.conn.execute(sql, tuple(params))
            r = cur.fetchone()
            return dict(r) if r is not None else None

    def valeur(self, sql: str, params=(), defaut=None):
        with self._verrou:
            cur = self.conn.execute(sql, tuple(params))
            r = cur.fetchone()
            return r[0] if r is not None else defaut

    # -- services ----------------------------------------------------------
    def journal(self, acteur: str, action: str, objet: str = "", details: str = "") -> None:
        """Trace une action. Ne lève jamais : la traçabilité ne doit pas casser le service."""
        try:
            self.executer(
                "INSERT INTO journal (acteur, action, objet, details) VALUES (?, ?, ?, ?)",
                (acteur or "", action or "", objet or "", details or ""),
            )
        except Exception:
            pass

    def sauvegarder(self, destination) -> Path:
        """Copie cohérente de la base (même si le serveur tourne)."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._verrou:
            cible = sqlite3.connect(str(destination))
            try:
                self.conn.backup(cible)
            finally:
                cible.close()
        return destination

    def fermer(self) -> None:
        with self._verrou:
            try:
                self.conn.close()
            except Exception:
                pass
