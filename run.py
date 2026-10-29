#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Point d'entrée de l'application Hôtellerie & Accueil
Monastère Bénédictin Sainte-Marie de Bouaké.

Utilisation
-----------
    python run.py                         première installation, puis démarrage
    python run.py servir                  démarrer le serveur
    python run.py initialiser --demo      (ré)initialiser, avec données de démonstration
    python run.py utilisateur --login frerejean
    python run.py tester                  dialoguer avec l'agent dans le terminal
    python run.py importer                réimporter base_connaissances.json
    python run.py sauvegarde              copier la base dans un fichier daté
    python run.py whatsapp                état du branchement WhatsApp
    python run.py whatsapp --verifier     interroger Meta sur le compte
    python run.py whatsapp --envoyer TEXTE --numero NUMERO_AUTORISE
    python run.py secret                  générer un secret aléatoire

Aucune dépendance à installer : bibliothèque standard Python 3.8+ uniquement.
"""
from __future__ import annotations

import argparse
import getpass
import logging
import secrets
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hotellerie import config, seed  # noqa: E402
from hotellerie.db import Base  # noqa: E402
from hotellerie.securite import creer_utilisateur  # noqa: E402


def configurer_journal(verbeux: bool = False) -> None:
    config.assurer_dossiers()
    niveau = logging.DEBUG if verbeux else logging.INFO
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(config.LOG_DIR / "hotellerie.log",
                                            encoding="utf-8"))
    except Exception:
        pass
    logging.basicConfig(
        level=niveau,
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def _lire_secret(invite: str) -> str:
    """getpass échoue sans terminal (script, Docker) : on retombe sur input()."""
    try:
        return getpass.getpass(invite)
    except (EOFError, OSError):
        try:
            return input(invite)
        except EOFError:
            return ""


def base() -> Base:
    return Base(config.DB_PATH)


def base_initialisee() -> Base:
    nouvelle = not config.DB_PATH.exists()
    db = base()
    if nouvelle:
        seed.initialiser(db, silencieux=True)
    return db


def cmd_initialiser(args) -> int:
    db = base()
    print("Initialisation de l'hôtellerie…")
    r = seed.initialiser(db, demo=args.demo)
    print("\nC'est prêt.")
    if r["chambres"]:
        print("→ Pensez à renommer les chambres dans « Occupation » :")
        print("  elles ont été créées de façon générique.")
    if not db.valeur("SELECT COUNT(*) FROM utilisateurs", defaut=0):
        print("\nAucun compte n'existe encore. Créez le premier :")
        print('  python run.py utilisateur --login hotelier --nom "Frère hôtelier"')
    return 0


def cmd_servir(args) -> int:
    if not config.DB_PATH.exists():
        cmd_initialiser(argparse.Namespace(demo=False))
    from hotellerie.web.server import demarrer
    demarrer(base(), hote=args.hote, port=args.port, ouvrir=args.ouvrir)
    return 0


def cmd_utilisateur(args) -> int:
    db = base_initialisee()
    login = (args.login or input("Identifiant : ")).strip().lower()
    if not login:
        print("Identifiant requis.", file=sys.stderr)
        return 1
    nom = args.nom or login

    existe = db.ligne("SELECT * FROM utilisateurs WHERE login = ?", (login,))
    if existe:
        rep = input(f"Le compte « {login} » existe. Changer son mot de passe ? [o/N] ")
        if rep.strip().lower() not in ("o", "oui", "y", "yes"):
            return 0

    if args.motdepasse:
        mdp = args.motdepasse
        if len(mdp) < 8:
            print("Trop court. Huit caractères au moins.", file=sys.stderr)
            return 1
    else:
        while True:
            mdp = _lire_secret("Mot de passe (8 caractères minimum) : ")
            if len(mdp) < 8:
                print("Trop court. Huit caractères au moins.")
                continue
            confirme = _lire_secret("Confirmez : ")
            if mdp != confirme:
                print("Les deux saisies diffèrent. Recommencez.")
                continue
            break

    if existe:
        from hotellerie.securite import hacher_mot_de_passe
        sel, emp = hacher_mot_de_passe(mdp)
        db.executer("UPDATE utilisateurs SET sel=?, empreinte=?, nom=?, role=?, email=?, actif=1 "
                    "WHERE login=?", (sel, emp, nom, args.role, args.email or "", login))
        db.journal("cli", "mot_de_passe_change", login)
        print(f"Mot de passe de « {login} » mis à jour.")
    else:
        creer_utilisateur(db, nom, login, mdp, role=args.role, email=args.email or "")
        db.journal("cli", "utilisateur_cree", login)
        print(f"Compte « {login} » créé ({args.role}).")
    return 0


def cmd_tester(args) -> int:
    """Dialogue avec l'agent depuis le terminal, sans aucun envoi réel."""
    db = base_initialisee()
    from hotellerie.agent.engine import Agent

    agent = Agent(db)
    cid = "terminal-" + secrets.token_hex(3)

    print("\n" + "─" * 68)
    print("  ESSAI DE L'AGENT D'ACCUEIL — aucune réponse n'est envoyée pour de vrai")
    print("  Écrivez comme un hôte. « quitter » pour sortir, « nouvel » pour réinitialiser.")
    print("─" * 68 + "\n")

    print("AGENT  " + agent.repondre(cid, "Bonjour", canal="terminal").replace("\n", "\n       "))
    while True:
        try:
            texte = input("\nHÔTE  ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break
        if not texte:
            continue
        if texte.lower() in ("quitter", "exit", "q"):
            print("Au revoir.")
            break
        if texte.lower() in ("nouvel", "reset"):
            cid = "terminal-" + secrets.token_hex(3)
            print("(nouvel échange)")
            continue
        rep = agent.repondre(cid, texte, canal="terminal")
        print("AGENT  " + (rep or "(silence : un frère a pris la main)").replace("\n", "\n       "))
    return 0


def cmd_importer(args) -> int:
    db = base_initialisee()
    from hotellerie.knowledge import charger_graine, SEED_PATH
    n = charger_graine(db, ecraser=args.ecraser)
    print(f"{n} fiche(s) importée(s) depuis {SEED_PATH.name}"
          f"{' (écrasement)' if args.ecraser else ''}.")
    return 0


def cmd_sauvegarde(args) -> int:
    dest = Path(args.destination) if args.destination else \
        config.DATA_DIR / f"hotellerie-{__import__('datetime').date.today()}.db"
    if dest.is_dir():
        dest = dest / f"hotellerie-{__import__('datetime').date.today()}.db"
    if not config.DB_PATH.exists():
        print("Aucune base à sauvegarder.", file=sys.stderr)
        return 1
    if dest.resolve() == config.DB_PATH.resolve():
        print("La destination doit être différente de la base active.", file=sys.stderr)
        return 1
    db = base()
    try:
        db.sauvegarder(dest)
    finally:
        db.fermer()
    print(f"Sauvegarde : {dest}")
    return 0



def cmd_whatsapp(args) -> int:
    """Brancher, vérifier et éprouver WhatsApp depuis le terminal."""
    from hotellerie.channels import whatsapp

    db = base_initialisee()

    if args.rejouer:
        resultat = whatsapp.rejouer(db)
        print(f"{resultat.get('envoyes', 0)} message(s) envoyé(s), "
              f"{resultat.get('restants', 0)} encore en attente.")
        if resultat.get("erreur"):
            print(resultat["erreur"], file=sys.stderr)
            return 1
        return 0

    if args.verifier:
        releve = whatsapp.diagnostic(db, args.numero or "")
        print("")
        print("Diagnostic WhatsApp")
        for etape in releve["etapes"]:
            print(("  ✓ " if etape["ok"] else "  ✗ ") + etape["etape"] + " — " + etape["detail"])
        compte = releve.get("compte") or {}
        if compte:
            print(f"  Compte : {compte.get('verified_name') or '—'} · "
                  f"{compte.get('display_phone_number') or '—'} · "
                  f"qualité {compte.get('quality_rating') or '—'}")
        if releve["pret"]:
            print("  → Contrôles préalables satisfaits ; l'accès au webhook reste à vérifier.")
            print("    Faites un échange complet depuis un téléphone réel avant l'ouverture.")
        else:
            print("  → Il reste des points à régler : voyez les ✗ ci-dessus.")
        return 0 if releve["pret"] else 1

    if args.envoyer:
        numero = args.numero or config.parametre(db, "wa_numero_test", "")
        resultat = whatsapp.envoyer(db, numero, args.envoyer)
        if resultat.get("ok"):
            print(f"Message envoyé à {whatsapp.afficher_numero(numero)}.")
            return 0
        print("Message non envoyé : " + (resultat.get("erreur") or "motif inconnu"),
              file=sys.stderr)
        if resultat.get("envoi_id"):
            print("Le message reste dans la file ; vérifiez-le avant « run.py whatsapp --rejouer ».")
        else:
            print("Le message n'a pas été ajouté à la file.")
        return 1

    conf = whatsapp.configuration(db)
    file_attente = whatsapp.file_attente(db, 200)
    print("")
    print("WhatsApp — état du branchement")
    print("  Jeton d'accès          : " + ("présent" if conf["token"] else "absent"))
    print("  phone_number_id        : " + (conf["phone_number_id"] or "absent"))
    print("  Jeton du webhook       : " + ("présent" if conf["verify_token"] else "absent"))
    print("  Secret d'application   : " + ("présent" if conf["app_secret"] else "absent"))
    print("  Version de l'API       : " + (conf["version"] or "v21.0"))
    print("  Numéro d'essai         : " + (whatsapp.afficher_numero(conf["numero_test"]) or "non renseigné"))
    print("  URL publique           : " + (conf["site_url"] or "non renseignée"))
    print(f"  File d'attente         : {len(file_attente)} message(s)")
    print("  Diagnostic             : python3 run.py whatsapp --verifier")
    return 0


def cmd_secret(args) -> int:
    print(secrets.token_urlsafe(32))
    return 0


def cmd_prompt(args) -> int:
    """
    Régénère PROMPT_AGENT.md à partir du code, pour que le document et
    l'application ne puissent pas diverger.
    """
    from hotellerie.agent.prompts import SYSTEME
    dest = Path(__file__).resolve().parent / "PROMPT_AGENT.md"
    entete = (
        "# Le prompt de l'agent d'accueil\n"
        "## Monastère Bénédictin Sainte-Marie de Bouaké\n\n"
        "> Ce fichier est **généré** depuis `hotellerie/agent/prompts.py`\n"
        "> (commande `python run.py prompt`). Ne le modifiez pas à la main :\n"
        "> modifiez le fichier source, puis régénérez.\n\n"
        "Il contient l'instruction système — la « règle de vie » — qui donne à\n"
        "l'agent sa posture, son ton et ses limites. Elle sert de référence\n"
        "pour les réponses déterministes. Le module de langage expérimental\n"
        "n'est pas branché aux réponses de l'agent.\n\n"
        "Vous pouvez la reprendre intégralement dans un autre outil\n"
        "(Lovable, n8n, un autre modèle de langage) : elle est autonome.\n\n"
        "---\n\n"
    )
    dest.write_text(entete + SYSTEME.strip() + "\n", encoding="utf-8")
    print(f"Écrit : {dest}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="run.py",
        description="Hôtellerie & Accueil — Monastère Sainte-Marie de Bouaké",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    p.add_argument("-v", "--verbeux", action="store_true")
    sub = p.add_subparsers(dest="commande")

    s = sub.add_parser("initialiser", help="créer le schéma et importer la base de connaissances")
    s.add_argument("--demo", action="store_true", help="ajouter des demandes de démonstration")
    s.set_defaults(func=cmd_initialiser)

    s = sub.add_parser("servir", help="démarrer le serveur et le tableau de bord")
    s.add_argument("--hote", default="0.0.0.0")
    s.add_argument("--port", type=int, default=int(__import__("os").environ.get("PORT", 8080)))
    s.add_argument("--ouvrir", action="store_true", help="ouvrir le navigateur")
    s.set_defaults(func=cmd_servir)

    s = sub.add_parser("utilisateur", help="créer ou modifier un compte")
    s.add_argument("--login")
    s.add_argument("--nom")
    s.add_argument("--role", default="hotelier", choices=["hotelier", "prieur", "admin"])
    s.add_argument("--email", default="")
    s.add_argument("--motdepasse", default="",
                   help="évite la saisie interactive (scripts, conteneurs)")
    s.set_defaults(func=cmd_utilisateur)

    s = sub.add_parser("tester", help="dialoguer avec l'agent dans le terminal")
    s.set_defaults(func=cmd_tester)

    s = sub.add_parser("importer", help="réimporter base_connaissances.json")
    s.add_argument("--ecraser", action="store_true")
    s.set_defaults(func=cmd_importer)

    s = sub.add_parser("sauvegarde", help="copier la base de données")
    s.add_argument("destination", nargs="?")
    s.set_defaults(func=cmd_sauvegarde)

    s = sub.add_parser("whatsapp", help="brancher et éprouver WhatsApp (Meta Cloud API)")
    s.add_argument("--verifier", action="store_true", help="interroger Meta sur le compte")
    s.add_argument("--envoyer", metavar="TEXTE", help="envoyer un message d'essai")
    s.add_argument("--numero", help="destinataire de l'essai")
    s.add_argument("--rejouer", action="store_true", help="rejouer la file d'attente")
    s.set_defaults(func=cmd_whatsapp)

    s = sub.add_parser("secret", help="générer un secret aléatoire")
    s.set_defaults(func=cmd_secret)

    s = sub.add_parser("prompt", help="régénérer PROMPT_AGENT.md depuis le code")
    s.set_defaults(func=cmd_prompt)

    args = p.parse_args()
    configurer_journal(args.verbeux)

    if not args.commande:
        # Première exécution : on installe puis on démarre.
        if not config.DB_PATH.exists():
            cmd_initialiser(argparse.Namespace(demo=False))
            print()
        args = argparse.Namespace(hote="0.0.0.0",
                                  port=int(__import__("os").environ.get("PORT", 8080)),
                                  ouvrir=False)
        return cmd_servir(args)

    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nArrêt.")
        sys.exit(0)
