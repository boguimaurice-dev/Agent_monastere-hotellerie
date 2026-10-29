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
  --parchment:#f5f7f4; --paper:#fff; --ink:#21332d; --muted:#6b7d75;
  --line:#e4ebe6; --brown:#256b55; --brown-dark:#153d32; --green:#2b8061;
  --red:#a44b42; --gold:#bb9561; --shadow:0 12px 35px rgba(35,70,53,.055);
  --sans:Inter,"Segoe UI",system-ui,-apple-system,BlinkMacSystemFont,sans-serif;
}
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; background:var(--parchment); color:var(--ink); font:14px/1.6 var(--sans); }
a { color:var(--brown); text-decoration:none; }
a:hover { text-decoration:underline; }
button, input, select, textarea { font:inherit; }
button, a, input, select, textarea { -webkit-tap-highlight-color:transparent; }
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, summary:focus-visible { outline:3px solid #8ecab0; outline-offset:3px; }
.app-shell { min-height:100vh; display:flex; }
.sidebar { position:sticky; top:0; flex:0 0 238px; width:238px; height:100vh; display:flex; flex-direction:column; background:#fff; border-right:1px solid var(--line); padding:27px 15px 18px; overflow-y:auto; }
.brand { display:flex; align-items:center; gap:11px; padding:0 9px 27px; color:#173b2f; text-decoration:none; }
.brand:hover { text-decoration:none; }
.brand-icon { width:39px; height:39px; display:grid; place-items:center; border-radius:13px; background:#e6f3e9; color:#286c50; flex:none; }
.brand-icon svg { width:23px; height:23px; }
.brand-name { font-size:15px; font-weight:750; line-height:1.25; letter-spacing:-.025em; }
.brand-name small { display:block; color:#8a9a91; font-size:10px; font-weight:650; letter-spacing:.1em; text-transform:uppercase; margin-top:4px; }
.nav-caption { color:#a1ada5; font-size:10px; font-weight:750; letter-spacing:.13em; text-transform:uppercase; padding:10px 12px 7px; }
nav.barre { display:flex; flex-direction:column; gap:3px; }
nav.barre a, .nav-mobile-links a { display:flex; align-items:center; gap:11px; min-height:42px; padding:9px 12px; border-radius:9px; color:#6a7b72; font-weight:550; font-size:13px; transition:background .18s,color .18s,transform .18s; }
nav.barre a svg, .nav-mobile-links a svg { width:17px; height:17px; flex:none; color:#91a59a; }
nav.barre a:hover, .nav-mobile-links a:hover { background:#f4f8f5; color:#246248; text-decoration:none; }
nav.barre a.actif, .nav-mobile-links a.actif { background:#e9f5ed; color:#246c4e; font-weight:700; }
nav.barre a.actif svg, .nav-mobile-links a.actif svg { color:#348866; }
.sidebar-foot { margin-top:auto; padding:22px 9px 0; }
.sidebar-note { padding:15px 13px; border:1px solid #e6eee8; border-radius:13px; background:linear-gradient(145deg,#f7faf6,#f0f6ef); }
.sidebar-note strong { display:block; font-family:Georgia,serif; font-size:15px; font-weight:400; color:#35654d; }
.sidebar-note span { display:block; color:#829189; font-size:11px; margin-top:3px; line-height:1.45; }
.workspace { min-width:0; flex:1; }
.topbar { height:72px; background:rgba(255,255,255,.88); backdrop-filter:blur(14px); border-bottom:1px solid var(--line); display:flex; align-items:center; justify-content:space-between; gap:16px; padding:0 34px; }
.topbar-left { display:flex; align-items:center; gap:10px; color:#85958c; font-size:12px; }
.topbar-left strong { color:#42574c; font-weight:650; }
.topbar-right { display:flex; align-items:center; gap:13px; }
.topbar-status { display:flex; align-items:center; gap:7px; color:#678076; font-size:11px; font-weight:600; }
.dot { width:7px; height:7px; border-radius:50%; background:#56aa7d; box-shadow:0 0 0 4px #e5f5e9; flex:none; }
.account { display:flex; align-items:center; gap:10px; border-left:1px solid var(--line); padding-left:17px; }
.avatar { width:34px; height:34px; border-radius:11px; display:grid; place-items:center; background:#eaf2e9; color:#3b7658; font-size:12px; font-weight:750; }
.account-text { color:#53665b; font-size:12px; line-height:1.3; }
.account-text small { display:block; color:#9aaba0; font-size:10px; }
.account a { font-size:11px; color:#7e9086; }
.nav-mobile { display:none; position:relative; }
.nav-mobile summary { list-style:none; cursor:pointer; width:38px; height:38px; display:grid; place-items:center; border:1px solid var(--line); border-radius:10px; background:#fff; color:#345b49; }
.nav-mobile summary::-webkit-details-marker { display:none; }
.nav-mobile summary svg { width:19px; height:19px; }
.nav-mobile[open] summary { background:#eaf5ed; }
.nav-mobile-links { position:absolute; top:48px; left:0; z-index:50; width:min(300px,calc(100vw - 30px)); background:#fff; border:1px solid var(--line); border-radius:14px; padding:9px; box-shadow:0 20px 55px rgba(20,55,37,.16); max-height:calc(100vh - 85px); overflow:auto; }
.conteneur { max-width:1500px; margin:0 auto; padding:32px 34px 55px; }
h1 { font-family:Georgia,"Times New Roman",serif; font-size:32px; line-height:1.17; letter-spacing:-.025em; margin:4px 0 8px; font-weight:400; color:#1f3b2d; }
h2 { font-size:16px; line-height:1.3; margin:0 0 15px; font-weight:700; letter-spacing:-.015em; color:#2b4034; }
h3 { font-size:14px; margin:16px 0 8px; }
.sous-titre { color:var(--muted); margin:0 0 22px; }
.carte { min-width:0; overflow-x:auto; background:var(--paper); border:1px solid var(--line); border-radius:16px; padding:22px; margin-bottom:17px; box-shadow:var(--shadow); }
.carte h2 { margin:0 0 15px; }
.grille { display:grid; gap:15px; }
.grille-4 { grid-template-columns:repeat(4,minmax(0,1fr)); }
.grille-2 { grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr)); }
.chiffre { font-size:30px; line-height:1.1; font-weight:700; color:#244c38; letter-spacing:-.04em; }
.chiffre small { display:block; font-size:11px; font-weight:600; color:var(--muted); letter-spacing:0; margin-top:9px; }
table { width:100%; border-collapse:collapse; font-size:12px; }
th, td { text-align:left; padding:13px 11px; border-bottom:1px solid #edf2ee; vertical-align:top; }
th { font-size:10px; text-transform:uppercase; letter-spacing:.075em; color:#8a9b91; font-weight:700; white-space:nowrap; }
tbody tr:last-child td { border-bottom:0; }
tbody tr:hover { background:#f9fbf9; }
.tableau-scroll { max-width:100%; overflow-x:auto; }
.tableau-large table { min-width:600px; }
.tableau-indication { display:none; }
.badge { display:inline-flex; align-items:center; gap:5px; padding:4px 9px; border-radius:7px; font-size:10px; font-weight:700; border:1px solid transparent; white-space:nowrap; }
.b-en_attente { background:#fff6e8; border-color:#f8e9cc; color:#a16c20; }
.b-acceptee,.b-confirmee,.b-envoye { background:#eaf7ed; border-color:#d7eddd; color:#347653; }
.b-refusee,.b-echoue { background:#fcefeb; border-color:#f5ddd8; color:#ad5b4c; }
.b-annulee,.b-sejour_termine,.b-ignore,.b-out { background:#f2f5f2; border-color:#e7ede8; color:#718178; }
.alerte { padding:13px 16px; border-radius:11px; margin-bottom:14px; border:1px solid; font-size:12px; }
.alerte a { font-weight:700; }
.alerte-ok { background:#eff8f0; border-color:#d5ead9; color:#356a49; }
.alerte-ko { background:#fff3ef; border-color:#f2d8d0; color:#9a5045; }
.alerte-info { background:#f9f8ef; border-color:#ece9d5; color:#776b3e; }
label { display:block; font-size:11px; font-weight:700; color:#72847a; margin:12px 0 5px; }
input[type=text], input[type=password], input[type=email], input[type=number], input[type=date], select, textarea { width:100%; padding:10px 12px; border:1px solid #dce7df; background:#fbfdfb; color:var(--ink); font-size:13px; border-radius:9px; transition:border-color .15s,box-shadow .15s; }
input:focus, select:focus, textarea:focus { outline:none; border-color:#75b394; box-shadow:0 0 0 3px rgba(89,160,116,.13); }
textarea { min-height:110px; resize:vertical; }
.btn { display:inline-flex; align-items:center; justify-content:center; gap:7px; background:#267552; color:#fff; border:1px solid #267552; padding:10px 15px; border-radius:9px; cursor:pointer; font-size:12px; font-weight:700; transition:background .18s,transform .18s,box-shadow .18s; }
.btn:hover { background:#1c6244; color:#fff; text-decoration:none; transform:translateY(-1px); box-shadow:0 6px 14px rgba(32,105,69,.15); }
.btn-secondaire { background:#fff; color:#416b52; border-color:#dce9de; }
.btn-secondaire:hover { background:#f4f9f4; color:#275e3e; box-shadow:none; }
.btn-danger { background:#ad5a4b; border-color:#ad5a4b; }
.btn-mini { padding:6px 10px; font-size:11px; }
.barre-actions { display:flex; flex-wrap:wrap; gap:9px; align-items:end; margin-top:14px; }
.ligne { display:flex; gap:14px; flex-wrap:wrap; }
.ligne > * { flex:1; min-width:170px; }
.fiche, .fiche dl { display:grid; grid-template-columns:150px 1fr; gap:8px 12px; margin:0; }
.fiche dt { color:var(--muted); font-size:12px; }
.fiche dd { margin:0; }
.muted { color:var(--muted); }
.petit { font-size:11px; }
.mono { font-family:"SFMono-Regular",Consolas,monospace; font-size:12px; white-space:pre-wrap; overflow-wrap:anywhere; }
.calendrier { border-collapse:collapse; font-size:11px; }
.calendrier th,.calendrier td { border:1px solid var(--line); padding:3px; text-align:center; min-width:30px; }
.calendrier th.nom { text-align:left; min-width:110px; }
.case-sejour { background:#dceee2; } .case-attente { background:#fff3d7; } .case-blocage { background:#f4e5db; }
.case-arrivee { outline:2px solid var(--green); outline-offset:-2px; } .case-depart { outline:2px solid var(--gold); outline-offset:-2px; }
.case-lien { display:block; padding:4px 2px; color:var(--ink); } .case-lien:hover { text-decoration:none; background:#eff7f0; }
.transcription { max-height:520px; overflow-y:auto; padding-right:6px; }
.bulle { margin:10px 0; padding:12px 15px; border-radius:13px; max-width:78%; white-space:pre-wrap; overflow-wrap:anywhere; }
.bulle-hote { background:#f2f5f1; border:1px solid #e4ebe4; } .bulle-agent { background:#edf8ef; border:1px solid #d8eddd; margin-left:auto; }
.bulle-meta { font-size:10px; font-weight:700; color:var(--muted); margin-bottom:4px; }
.pagination { display:flex; gap:10px; align-items:center; margin-top:10px; }
footer.pied { text-align:center; color:#97a69c; font-size:11px; padding:4px 22px 28px; }
/* Accueil */
.kicker { color:#5e9a74; text-transform:uppercase; font-size:10px; font-weight:750; letter-spacing:.14em; }
.accueil-heading { display:flex; justify-content:space-between; align-items:flex-end; gap:20px; margin-bottom:22px; }
.accueil-heading .sous-titre { margin:0; }
.date-pill { border:1px solid #e0e9e1; border-radius:9px; background:#fff; color:#788b7e; padding:8px 12px; font-size:11px; font-weight:600; white-space:nowrap; }
.hero { position:relative; overflow:hidden; display:flex; align-items:center; justify-content:space-between; gap:28px; min-height:208px; background:radial-gradient(circle at 83% 30%,rgba(149,202,162,.32),transparent 32%),linear-gradient(115deg,#eaf4e7,#f4f7eb 58%,#e8f4e9); border:1px solid #deecdd; border-radius:18px; padding:29px 32px; margin-bottom:19px; }
.hero-content { position:relative; z-index:1; max-width:620px; }
.hero-kicker { display:inline-flex; align-items:center; gap:7px; color:#508567; font-size:10px; letter-spacing:.12em; font-weight:750; text-transform:uppercase; }
.hero h2 { font:400 29px/1.15 Georgia,serif; letter-spacing:-.035em; color:#214d35; margin:11px 0 10px; }
.hero p { margin:0; color:#678273; font-size:13px; max-width:500px; }
.hero .barre-actions { margin-top:18px; }
.hero-illustration { align-self:stretch; display:flex; align-items:center; justify-content:center; min-width:210px; padding-right:20px; color:#81b993; }
.hero-illustration svg { width:190px; height:150px; opacity:.8; }
.stat-card { position:relative; overflow:hidden; margin-bottom:17px; min-height:134px; }
.stat-top { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:19px; }
.stat-label { font-size:11px; font-weight:700; color:#84968a; }
.stat-icon { width:34px; height:34px; border-radius:10px; display:grid; place-items:center; background:#eef8f0; color:#5d9b73; }
.stat-icon svg { width:16px; height:16px; }
.stat-foot { color:#98aa9f; font-size:10px; margin-top:6px; }
.dashboard-grid { display:grid; grid-template-columns:minmax(0,1.7fr) minmax(280px,1fr); gap:16px; align-items:start; }
.dashboard-grid > * { min-width:0; }
.section-head { display:flex; align-items:center; justify-content:space-between; gap:14px; margin-bottom:6px; }
.section-head h2 { margin:0; }
.section-meta { color:#97a69d; font-size:11px; margin:2px 0 10px; }
.section-link { color:#4d8d65; font-size:11px; font-weight:700; white-space:nowrap; }
.agent-card { background:linear-gradient(155deg,#f4f9f0,#fff 63%); border-color:#dfecdf; }
.agent-mark { width:43px; height:43px; border-radius:13px; display:grid; place-items:center; background:#e6f3e6; color:#4b9265; margin-bottom:15px; }
.agent-mark svg { width:21px; height:21px; }
.agent-card h2 { margin-bottom:7px; }
.agent-card p { color:#819489; font-size:12px; margin:0 0 16px; }
.agent-status { display:flex; align-items:center; gap:9px; border-top:1px solid #e5eee5; border-bottom:1px solid #e5eee5; padding:12px 0; font-size:11px; color:#657a6d; margin-bottom:15px; }
.dashboard-two { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.empty-state { padding:12px 0 4px; color:#9aaba0; font-size:12px; }
.dashboard-system { display:flex; flex-direction:column; gap:9px; }
.system-line { display:flex; align-items:flex-start; gap:9px; color:#71877a; font-size:11px; }
.system-dot { width:7px; height:7px; border-radius:50%; background:#8ebd96; margin-top:6px; flex:none; }
.system-dot.warn { background:#dcb27a; }
.login-shell .workspace { min-height:100vh; }
.login-shell .topbar { justify-content:center; }
.login-shell .topbar .brand { padding:0; }
@media (max-width:1100px) { .sidebar { flex-basis:216px; width:216px; } .conteneur { padding:27px 25px 48px; } .topbar { padding:0 25px; } .dashboard-grid { grid-template-columns:minmax(0,1fr); } }
@media (max-width:800px) { .sidebar { display:none; } .nav-mobile { display:block; } .topbar { height:64px; padding:0 18px; } .topbar-left { gap:10px; } .topbar-left .crumb-home { display:none; } .conteneur { padding:24px 18px 45px; } .grille-4 { grid-template-columns:repeat(2,minmax(0,1fr)); } .account-text, .topbar-status { display:none; } .topbar-left { min-width:0; } .account { padding-left:10px; } .hero-illustration { min-width:135px; padding-right:0; } .hero-illustration svg { width:130px; } }
@media (max-width:520px) { h1 { font-size:27px; } .conteneur { padding:20px 14px 38px; } .accueil-heading { align-items:flex-start; flex-direction:column; gap:11px; } .date-pill { padding:6px 9px; } .hero { min-height:0; padding:24px 20px; } .hero h2 { font-size:25px; } .hero-illustration { display:none; } .carte { padding:18px; border-radius:14px; } .stat-card { min-height:122px; } .stat-top { margin-bottom:15px; } .dashboard-two { grid-template-columns:minmax(0,1fr); gap:0; } .tableau-large + .tableau-indication { display:block; color:var(--muted); font-size:11px; margin:8px 0; } .fiche, .fiche dl { grid-template-columns:1fr; gap:3px; } .fiche dd { margin-bottom:8px; } .bulle { max-width:95%; } .topbar-right { gap:5px; } .topbar-left strong { font-size:12px; } }
@media (prefers-reduced-motion:reduce) { *, *::before, *::after { scroll-behavior:auto !important; transition:none !important; animation:none !important; } }
@media print { .sidebar,.topbar,.btn,footer.pied { display:none; } body { background:#fff; } .conteneur { padding:0; } }
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


ICONS = {
    "bord": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "demandes": '<path d="M6 3h9l3 3v15H6z"/><path d="M15 3v4h4M9 11h6M9 15h6"/>',
    "calendrier": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18M7 14h2m3 0h2m3 0h1M7 17h2m3 0h2"/>',
    "connaissances": '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21z"/><path d="M4 18.5A2.5 2.5 0 0 1 6.5 16H20M9 7h7M9 10h6"/>',
    "conversations": '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5 8.6 8.6 0 0 1-4-.9L3 21l1.9-5.5A8.5 8.5 0 1 1 21 11.5z"/><path d="M8 11h8M8 14h5"/>',
    "simulateur": '<path d="M12 3v3m-1.5-1.5h3M5 13H3m18 0h-2"/><rect x="5" y="7" width="14" height="12" rx="4"/><path d="M9 12h.01M15 12h.01M9 16c2 1.3 4 1.3 6 0M8 21h8"/>',
    "notifications": '<path d="M18 8a6 6 0 0 0-12 0c0 7-2 7-2 9h16c0-2-2-2-2-9M10 20h4"/>',
    "journal": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2M3 4v4h4"/>',
    "parametres": '<circle cx="12" cy="12" r="3"/><path d="m19 13 2-1-2-1-.7-2.2 1-2.1-2.2-1-1.8 1-2.3-.7L12 3l-1 2.1-2.2.7-2-1-1 2.2 1 1.8L6 11l-2 1 2 1 .8 2.2-1 2 2 1 2-1 2.2.8 1 2 1-2 2.2-.8 2 1 1-2-1-2z"/>',
    "whatsapp": '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5 8.6 8.6 0 0 1-4-.9L3 21l1.9-5.5A8.5 8.5 0 1 1 21 11.5z"/><path d="M9 8c0 3 3 6 6 6l1-1.5-2-1-1 1a7 7 0 0 1-2-2l1-1-1-2z"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "maison": '<path d="M4 21V10a8 8 0 0 1 16 0v11M8 21v-8a4 4 0 0 1 8 0v8M2 21h20M12 2v5M10 4h4"/>',
    "arrivee": '<path d="M3 12h12m-4-4 4 4-4 4M14 4h5a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-5"/>',
    "depart": '<path d="M21 12H9m4-4-4 4 4 4M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5"/>',
}


def icone(nom: str) -> str:
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            + ICONS.get(nom, ICONS["bord"]) + '</svg>')


def page(titre: str, contenu: str, utilisateur=None, actif: str = "",
         message: str = "", erreur: str = "") -> str:
    liens = "".join(
        f'<a href="{lien}" class="{"actif" if cle == actif else ""}"'
        f'{" aria-current=page" if cle == actif else ""}>{icone(cle)}<span>{esc(libelle)}</span></a>'
        for lien, libelle, cle in LIENS)
    brand = ('<a class="brand" href="/tableau-de-bord">'
             f'<span class="brand-icon">{icone("maison")}</span>'
             '<span class="brand-name">Sainte-Marie<small>Hôtellerie &amp; accueil</small></span></a>')
    sidebar = (f'<aside class="sidebar">{brand}<div class="nav-caption">Espace de travail</div>'
               f'<nav class="barre" aria-label="Navigation principale">{liens}</nav>'
               '<div class="sidebar-foot"><div class="sidebar-note"><strong>Une maison ouverte</strong>'
               '<span>Accueillir chacun avec simplicité et bienveillance.</span></div></div></aside>') if utilisateur else ""
    if utilisateur:
        nom = utilisateur.get("nom") or utilisateur.get("login") or "Accueil"
        initials = "".join(part[0] for part in str(nom).split()[:2]).upper()
        topbar = (f'<div class="topbar-left"><details class="nav-mobile"><summary aria-label="Ouvrir le menu">{icone("menu")}</summary>'
                  f'<nav class="nav-mobile-links" aria-label="Navigation mobile">{liens}</nav></details>'
                  f'<span class="crumb-home">Hôtellerie <span aria-hidden="true">/</span></span> <strong>{esc(titre)}</strong></div>'
                  f'<div class="topbar-right"><span class="topbar-status"><span class="dot"></span>Espace d’accueil</span>'
                  f'<div class="account"><span class="avatar" aria-hidden="true">{esc(initials)}</span>'
                  f'<span class="account-text">{esc(nom)}<small>{esc(utilisateur.get("role") or "Équipe d’accueil")}</small></span>'
                  '<a href="/deconnexion">quitter</a></div></div>')
    else:
        topbar = brand
    flash = ""
    if message:
        flash += f'<div class="alerte alerte-ok" role="status">{esc(message)}</div>'
    if erreur:
        flash += f'<div class="alerte alerte-ko" role="alert">{esc(erreur)}</div>'
    shell_class = "app-shell" if utilisateur else "app-shell login-shell"
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f5f7f4">
<title>{esc(titre)} — Hôtellerie du monastère</title>
<style>{CSS}</style>
</head>
<body>
<div class="{shell_class}">
{sidebar}
<div class="workspace">
<header class="topbar">{topbar}</header>
<main class="conteneur">
{flash}
{contenu}
</main>
<footer class="pied">« Tous les hôtes qui se présentent seront reçus comme le Christ. » — Règle de saint Benoît, 53</footer>
</div>
</div>
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
