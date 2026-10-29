# -*- coding: utf-8 -*-
"""
Habillage du tableau de bord.

Aucune ressource externe : ni police, ni script, ni feuille de style distante.
Le monastère doit pouvoir ouvrir son tableau de bord sur une connexion
intermittente, dans dix ans, avec le même navigateur.
"""
from __future__ import annotations

import html

CSS = """
:root {
  --parchment: #f6f2e8;
  --paper: #fffdf7;
  --ink: #2b2823;
  --muted: #6f6a60;
  --line: #ded6c6;
  --brown: #6b4f2a;
  --brown-dark: #4d381d;
  --green: #4d5f49;
  --red: #8c3b2e;
  --gold: #a8894f;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--parchment); color: var(--ink);
  font-family: Georgia, "Times New Roman", serif; line-height: 1.55; font-size: 15px;
}
a { color: var(--brown); text-decoration: none; }
a:hover { text-decoration: underline; }
.entete {
  background: var(--brown-dark); color: #f7f2e6; padding: 14px 22px;
  display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
}
.entete .marque { font-size: 17px; letter-spacing: .02em; }
.entete .marque small { display: block; font-size: 12px; color: #d9c9ab; letter-spacing: .06em; text-transform: uppercase; }
.entete .espace { flex: 1; }
.entete .compte { font-size: 13px; color: #ece2ce; }
.entete .compte a { color: #f0d9a8; }
nav.barre { background: var(--brown); padding: 0 14px; display: flex; flex-wrap: wrap; }
nav.barre a {
  color: #f4ead6; padding: 10px 13px; font-size: 14px; display: block;
  border-bottom: 3px solid transparent;
}
nav.barre a:hover { background: rgba(255,255,255,.07); text-decoration: none; }
nav.barre a.actif { border-bottom-color: var(--gold); background: rgba(255,255,255,.10); }
.conteneur { max-width: 1180px; margin: 0 auto; padding: 22px 18px 60px; }
h1 { font-size: 25px; margin: 6px 0 4px; font-weight: normal; }
h2 { font-size: 19px; margin: 26px 0 10px; font-weight: normal; color: var(--brown-dark); }
h3 { font-size: 16px; margin: 18px 0 8px; }
.sous-titre { color: var(--muted); margin-top: 0; }
.carte {
  min-width: 0; overflow-x: auto;
  background: var(--paper); border: 1px solid var(--line); border-radius: 3px;
  padding: 18px 20px; margin-bottom: 18px; box-shadow: 0 1px 0 rgba(0,0,0,.03);
}
.grille { display: grid; gap: 14px; }
.grille-4 { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
.grille-2 { grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); }
.chiffre { font-size: 32px; line-height: 1.1; color: var(--brown); }
.chiffre small { display: block; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-top: 4px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 8px 9px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: normal; }
tbody tr:hover { background: #faf6ec; }
.tableau-scroll { max-width: 100%; overflow-x: auto; }
.tableau-large table { min-width: 600px; }
.tableau-indication { display: none; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; border: 1px solid transparent; white-space: nowrap; }
.b-en_attente { background: #fbf1d6; border-color: #e6d29a; color: #6b5411; }
.b-acceptee { background: #e4eee1; border-color: #b6cbb0; color: #33502e; }
.b-confirmee { background: #dce9dc; border-color: #a9c4a7; color: #27452a; }
.b-refusee { background: #f3ded9; border-color: #d9b3a9; color: #6f2b20; }
.b-annulee { background: #ece8e1; border-color: #d3cabb; color: #5d5547; }
.b-sejour_termine { background: #e8e6e1; border-color: #cfc9bd; color: #55503f; }
.b-envoye { background: #e4eee1; border-color: #b6cbb0; color: #33502e; }
.b-echoue { background: #f3ded9; border-color: #d9b3a9; color: #6f2b20; }
.b-ignore { background: #ece8e1; border-color: #d3cabb; color: #5d5547; }
.b-out { background: #ece8e1; border-color: #d3cabb; color: #5d5547; }
.alerte { padding: 11px 14px; border-radius: 3px; margin-bottom: 14px; border: 1px solid; font-size: 14px; }
.alerte-ok { background: #eaf2e6; border-color: #b9cdb2; color: #33502e; }
.alerte-ko { background: #f7e4df; border-color: #dcb3a8; color: #7a2c20; }
.alerte-info { background: #f6efdd; border-color: #ddcc9f; color: #6b5411; }
label { display: block; font-size: 13px; color: var(--muted); margin: 10px 0 4px; text-transform: uppercase; letter-spacing: .04em; }
input[type=text], input[type=password], input[type=email], input[type=number], input[type=date], select, textarea {
  width: 100%; padding: 8px 10px; border: 1px solid var(--line); background: #fff; color: var(--ink);
  font-family: inherit; font-size: 14px; border-radius: 2px;
}
textarea { min-height: 110px; resize: vertical; }
input:focus, select:focus, textarea:focus { outline: 2px solid #cbb98d; outline-offset: 0; }
.btn {
  display: inline-block; background: var(--brown); color: #fff8ea; border: 1px solid var(--brown-dark);
  padding: 8px 15px; border-radius: 2px; cursor: pointer; font-family: inherit; font-size: 14px;
}
.btn:hover { background: var(--brown-dark); text-decoration: none; }
.btn-secondaire { background: transparent; color: var(--brown); border-color: var(--brown); }
.btn-danger { background: var(--red); border-color: #6f2b20; }
.btn-mini { padding: 4px 9px; font-size: 12px; }
.barre-actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin-top: 12px; }
.ligne { display: flex; gap: 14px; flex-wrap: wrap; }
.ligne > * { flex: 1; min-width: 170px; }
.fiche dl { display: grid; grid-template-columns: 190px 1fr; gap: 6px 14px; margin: 0; }
.fiche dt { color: var(--muted); font-size: 14px; }
.fiche dd { margin: 0; }
.muted { color: var(--muted); }
.petit { font-size: 12px; }
.mono { font-family: "Courier New", monospace; font-size: 13px; white-space: pre-wrap; }
.calendrier { border-collapse: collapse; font-size: 12px; }
.calendrier th, .calendrier td { border: 1px solid var(--line); padding: 3px; text-align: center; min-width: 30px; }
.calendrier th.nom { text-align: left; min-width: 110px; }
.case-sejour { background: #dfe8d9; }
.case-attente { background: #fbf1d6; }
.case-blocage { background: #efe0d3; }
.case-arrivee { outline: 2px solid var(--green); outline-offset: -2px; }
.case-depart { outline: 2px solid var(--gold); outline-offset: -2px; }
.case-lien { display: block; padding: 4px 2px; color: var(--ink); }
.case-lien:hover { text-decoration: none; background: #f2ecdd; }
.transcription { max-height: 520px; overflow-y: auto; padding-right: 6px; }
.bulle { margin: 10px 0; padding: 9px 13px; border-radius: 8px; max-width: 78%; white-space: pre-wrap; }
.bulle-hote { background: #eee7d8; border: 1px solid #ddd1ba; }
.bulle-agent { background: #e8efe4; border: 1px solid #c3d3bb; margin-left: auto; }
.bulle-meta { font-size: 11px; color: var(--muted); margin-bottom: 3px; }
.pagination { display: flex; gap: 10px; align-items: center; margin-top: 10px; }
footer.pied { text-align: center; color: var(--muted); font-size: 12px; padding: 20px 0 30px; }
@media (max-width: 600px) {
  .conteneur { padding: 16px 12px 40px; }
  .grille-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grille-4 .carte { padding: 14px; }
  .grille-4 .chiffre { font-size: 28px; }
  .tableau-large + .tableau-indication { display: block; color: var(--muted); font-size: 12px; margin: 8px 0; }
  .entete { padding: 12px; }
  nav.barre { padding: 0 4px; }
  nav.barre a { padding: 9px 8px; }
  .fiche dl { grid-template-columns: 1fr; gap: 3px; }
  .fiche dd { margin-bottom: 8px; }
  .bulle { max-width: 95%; overflow-wrap: anywhere; }
}
@media print { .entete, nav.barre, .btn, footer.pied { display: none; } body { background: #fff; } }
"""

LIENS = [
    ("/tableau-de-bord", "Tableau de bord", "bord"),
    ("/demandes", "Demandes", "demandes"),
    ("/calendrier", "Occupation", "calendrier"),
    ("/connaissances", "Base de connaissances", "connaissances"),
    ("/conversations", "Échanges", "conversations"),
    ("/simulateur", "Essayer l’agent", "simulateur"),
    ("/notifications", "Notifications", "notifications"),
    ("/journal", "Journal", "journal"),
    ("/parametres", "Paramètres", "parametres"),
    ("/whatsapp", "WhatsApp", "whatsapp"),
]


def esc(valeur) -> str:
    return html.escape("" if valeur is None else str(valeur), quote=True)


def badge(statut: str, libelle: str = "") -> str:
    statut = (statut or "").strip() or "inconnu"
    return f'<span class="badge b-{esc(statut)}">{esc(libelle or statut.replace("_", " "))}</span>'


def page(titre: str, contenu: str, utilisateur=None, actif: str = "",
         message: str = "", erreur: str = "") -> str:
    liens = "".join(
        f'<a href="{lien}" class="{"actif" if cle == actif else ""}">{esc(libelle)}</a>'
        for lien, libelle, cle in LIENS)
    compte = ""
    if utilisateur:
        compte = (f'<span class="compte">{esc(utilisateur.get("nom") or utilisateur.get("login"))}'
                  f' · {esc(utilisateur.get("role"))} · <a href="/deconnexion">quitter</a></span>')
    flash = ""
    if message:
        flash += f'<div class="alerte alerte-ok">{esc(message)}</div>'
    if erreur:
        flash += f'<div class="alerte alerte-ko">{esc(erreur)}</div>'
    barre = f'<nav class="barre">{liens}</nav>' if utilisateur else ""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(titre)} — Hôtellerie du monastère</title>
<style>{CSS}</style>
</head>
<body>
<header class="entete">
  <div class="marque">Hôtellerie &amp; Accueil<small>Monastère Sainte-Marie de Bouaké</small></div>
  <div class="espace"></div>
  {compte}
</header>
{barre}
<main class="conteneur">
{flash}
{contenu}
</main>
<footer class="pied">« Tous les hôtes qui se présentent seront reçus comme le Christ. » — Règle de saint Benoît, 53</footer>
</body>
</html>"""


def carte(titre: str, contenu: str, actions: str = "") -> str:
    entete = f'<h2>{esc(titre)}</h2>' if titre else ""
    return f'<section class="carte">{entete}{contenu}{actions}</section>'


def tableau(entetes, lignes, vide: str = "Aucun élément.") -> str:
    if not lignes:
        return f'<p class="muted">{esc(vide)}</p>'
    thead = "".join(f'<th scope="col">{esc(e)}</th>' for e in entetes)
    corps = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in ligne) + "</tr>" for ligne in lignes)
    large = len(entetes) >= 5
    classe = "tableau-scroll tableau-large" if large else "tableau-scroll"
    indication = ('<p class="tableau-indication">Faites défiler le tableau horizontalement pour tout voir →</p>'
                  if large else "")
    return (f'<div class="{classe}" tabindex="0" role="region" aria-label="Tableau défilable">'
            f"<table><thead><tr>{thead}</tr></thead><tbody>{corps}</tbody></table></div>{indication}")
