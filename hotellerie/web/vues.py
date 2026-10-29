# -*- coding: utf-8 -*-
"""
Les écrans du tableau de bord.

Chaque fonction renvoie du HTML complet. Toute donnée affichée est échappée :
un nom d'hôte vient d'un inconnu, il ne doit jamais pouvoir devenir du code.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.parse

from .. import config, knowledge, metier
from .templates import badge, carte, esc, icone, page, tableau


def _csrf(jeton: str) -> str:
    return f'<input type="hidden" name="csrf" value="{esc(jeton)}">'


def _hote(dem) -> str:
    return f"{dem.get('prenom', '')} {dem.get('nom', '')}".strip() or "—"


def _lien_demande(dem) -> str:
    return f'<a href="/demandes/{dem["id"]}">{esc(dem.get("reference") or dem["id"])}</a>'


def _libelle_message(db, message):
    if message["direction"] == "entrant":
        return "Hôte"
    try:
        meta = json.loads(message.get("meta") or "{}")
        if not isinstance(meta, dict):
            meta = {}
    except (TypeError, ValueError):
        meta = {}
    if not meta.get("auteur"):
        return "Agent"
    libelle = "Frère / équipe"
    statut = meta.get("statut", "")
    if meta.get("envoi_id"):
        statut = db.valeur("SELECT statut FROM envois WHERE id = ?", (meta["envoi_id"],), defaut="")
    return libelle + ({"envoye": " · accepté par WhatsApp" if meta.get("envoi_id") else " · envoyé",
                       "en_attente": " · en attente d'envoi", "echoue": " · envoi échoué"}.get(statut, ""))


def _periode(dem) -> str:
    if not dem.get("date_arrivee"):
        return "—"
    if not dem.get("date_depart"):
        return f"dès le {metier.format_date(dem['date_arrivee'])}"
    return (f"{metier.format_date(dem['date_arrivee'])} → "
            f"{metier.format_date(dem['date_depart'])}")


# ===========================================================================
# Connexion
# ===========================================================================
def connexion(message: str = "", erreur: str = "") -> str:
    contenu = f"""
<div style="max-width: 420px; margin: 40px auto;">
  <h1>Entrer dans la maison</h1>
  <p class="sous-titre">Tableau de bord de l'hôtellerie</p>
  <form method="post" action="/connexion" class="carte">
    <label for="login">Identifiant</label>
    <input type="text" id="login" name="login" autocomplete="username" required autofocus>
    <label for="motdepasse">Mot de passe</label>
    <input type="password" id="motdepasse" name="motdepasse" autocomplete="current-password" required>
    <div class="barre-actions"><button class="btn" type="submit">Entrer</button></div>
  </form>
  <p class="petit muted">Six tentatives au maximum, puis quinze minutes d'attente.
  Les mots de passe ne sont jamais conservés en clair.</p>
</div>"""
    return page("Connexion", contenu, message=message, erreur=erreur)


# ===========================================================================
# Tableau de bord
# ===========================================================================
def tableau_de_bord(db, user, message: str = "", erreur: str = "") -> str:
    s = metier.stats(db)
    manquantes = len(knowledge.fiches_a_completer(db))
    en_attente = db.lignes(
        "SELECT * FROM demandes WHERE statut = 'en_attente' ORDER BY date_arrivee LIMIT 8")
    auj = metier.aujourdhui().isoformat()
    arrivees = db.lignes(
        "SELECT * FROM demandes WHERE date_arrivee = ? AND statut IN ('acceptee','confirmee')", (auj,))
    departs = db.lignes(
        "SELECT * FROM demandes WHERE date_depart = ? AND statut IN ('acceptee','confirmee')", (auj,))

    def statistique(libelle, valeur, precision, pictogramme):
        return (f'<div class="carte stat-card"><div class="stat-top"><span class="stat-label">{esc(libelle)}</span>'
                f'<span class="stat-icon">{icone(pictogramme)}</span></div>'
                f'<div class="chiffre">{esc(valeur)}</div><div class="stat-foot">{esc(precision)}</div></div>')

    cartes = '<div class="grille grille-4">' + ''.join([
        statistique("Demandes en attente", s['en_attente'], "À examiner par l’équipe", "demandes"),
        statistique("Arrivées du jour", s['arrivees_jour'], "Séjours acceptés ou confirmés", "arrivee"),
        statistique("Départs du jour", s['departs_jour'], "Séjours acceptés ou confirmés", "depart"),
        statistique("Chambres actives", s['chambres_actives'], f"{s['capacite_totale']} places au total", "maison"),
    ]) + '</div>'

    alertes = []
    if manquantes:
        alertes.append(f'<div class="alerte alerte-info">{manquantes} fiche(s) de connaissance '
                       f'attendent la parole des frères. <a href="/connaissances?manquantes=1">Les voir</a></div>')
    if s["notifications_echouees"]:
        alertes.append(f'<div class="alerte alerte-info">{s["notifications_echouees"]} transmission(s) '
                       f'non partie(s). <a href="/notifications">Voir le motif</a></div>')
    if s["humain_requis"]:
        alertes.append(f'<div class="alerte alerte-ko">{s["humain_requis"]} échange(s) attendent un frère. '
                       f'<a href="/conversations">Prendre le relais</a></div>')
    en_attente_wa = int(db.valeur("SELECT COUNT(*) FROM envois WHERE statut IN ('en_attente', 'echoue')", defaut=0) or 0)
    if en_attente_wa:
        alertes.append(f'<div class="alerte alerte-info">{en_attente_wa} message(s) '
                       f'WhatsApp attendent leur départ ou ont échoué. <a href="/whatsapp">Voir la file</a></div>')

    lignes = [[_lien_demande(d), esc(_hote(d)), esc(_periode(d)),
               esc(d.get("nb_personnes") or 1),
               badge(d.get("statut"), metier.libelle_statut(d.get("statut")))]
              for d in en_attente]
    lignes_arrivees = [[esc(_hote(d)), esc((metier.chambre(db, d.get('chambre_id')) or {}).get('nom') or 'à attribuer'),
                        esc(_periode(d))] for d in arrivees]
    lignes_departs = [[esc(_hote(d)), esc((metier.chambre(db, d.get('chambre_id')) or {}).get('nom') or '—'),
                       esc(_periode(d))] for d in departs]

    agent_actif = config.drapeau_parametre(db, "agent_actif", True)
    wa = bool(config.parametre(db, "wa_token", "") and config.parametre(db, "wa_phone_number_id", ""))
    smtp = bool(config.parametre(db, "smtp_hote", ""))
    etats = [
        ("Agent : " + ("actif" if agent_actif else "en relais humain"), not agent_actif),
        ("WhatsApp : " + ("jeton et identifiant présents ; webhook et échange réel à vérifier" if wa
                         else "non configuré (les messages ne partent pas)"), not wa),
        ("Courriel : " + ("configuré" if smtp else "non configuré"), not smtp),
        ("Réponses : base de connaissances, sans génération IA", False),
    ]
    etat_html = '<div class="dashboard-system">' + ''.join(
        f'<div class="system-line"><span class="system-dot{" warn" if attention else ""}"></span>{esc(texte)}</div>'
        for texte, attention in etats) + '</div>'
    etat_html += (f'<p class="petit muted">Version {esc(config.VERSION)} · '
                  '<a href="/sante">santé technique (JSON)</a></p>')
    illustration = '''<svg viewBox="0 0 200 160" fill="none" aria-hidden="true">
      <circle cx="100" cy="80" r="70" fill="#d8ebd4"/><circle cx="100" cy="80" r="57" stroke="#b2d5b7"/>
      <path d="M61 133V80a39 39 0 0 1 78 0v53M73 133V81a27 27 0 0 1 54 0v52M91 133v-28a9 9 0 0 1 18 0v28M49 133h102M100 30v20M94 36h12" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
      <path d="M30 118c11 0 19 5 25 14M170 118c-11 0-19 5-25 14M28 102c9 2 16 8 20 16M172 102c-9 2-16 8-20 16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    </svg>'''
    contenu = f"""
<div class="accueil-heading">
  <div><div class="kicker">Hôtellerie · Monastère Sainte-Marie</div>
    <h1>Bonjour, {esc(user.get('nom') or user.get('login'))}.</h1>
    <p class="sous-titre">Bienvenue dans votre espace d’accueil. Voici la vie de la maison aujourd’hui.</p></div>
  <div class="date-pill">{esc(metier.format_date_longue(auj))}</div>
</div>
{''.join(alertes)}
<section class="hero" aria-labelledby="hero-title">
  <div class="hero-content"><span class="hero-kicker"><span class="dot"></span> Un accueil à visage humain</span>
    <h2 id="hero-title">Chaque hôte est une rencontre.</h2>
    <p>Un espace pour suivre les demandes, accompagner les échanges et préparer les séjours en toute sérénité.</p>
    <div class="barre-actions"><a class="btn" href="/demandes/nouveau">+ &nbsp; Nouvelle demande</a>
    <a class="btn btn-secondaire" href="/simulateur">Découvrir l’agent &nbsp; →</a></div></div>
  <div class="hero-illustration">{illustration}</div>
</section>
{cartes}
<div class="dashboard-grid">
  <div>
    <section class="carte"><div class="section-head"><h2>Demandes en attente</h2><a class="section-link" href="/demandes?statut=en_attente">Tout voir →</a></div>
      <p class="section-meta">Les dernières demandes à examiner · 8 maximum</p>
      {tableau(["Référence", "Hôte", "Période", "Pers.", "Statut"], lignes, "Aucune demande en attente. La maison est en paix.")}
      <div class="barre-actions"><a class="btn btn-secondaire btn-mini" href="/demandes/nouveau">+ Saisir une demande</a></div></section>
    <div class="dashboard-two">
      {carte("Arrivées du jour", tableau(["Hôte", "Chambre", "Période"], lignes_arrivees, "Aucune arrivée aujourd’hui."))}
      {carte("Départs du jour", tableau(["Hôte", "Chambre", "Période"], lignes_departs, "Aucun départ aujourd’hui."))}
    </div>
  </div>
  <div>
    <section class="carte agent-card"><div class="agent-mark">{icone('simulateur')}</div>
      <h2>Votre agent d’accueil</h2><p>Une aide pour renseigner les visiteurs et transmettre les situations qui demandent une présence humaine.</p>
      <div class="agent-status"><span class="system-dot{' warn' if not agent_actif else ''}"></span>{'Agent actif' if agent_actif else 'Relais humain activé'}</div>
      <a class="btn btn-secondaire" href="/simulateur">Essayer l’agent &nbsp; →</a>
    </section>
    <section class="carte"><div class="section-head"><h2>État du système</h2><a class="section-link" href="/parametres">Paramètres →</a></div>
      <p class="section-meta">Configuration et points de vigilance</p>{etat_html}</section>
  </div>
</div>
"""
    return page("Tableau de bord", contenu, user, "bord", message, erreur)


# ===========================================================================
# Demandes
# ===========================================================================
def demandes_liste(db, user, statut: str = "", recherche: str = "",
                   message: str = "", erreur: str = "") -> str:
    liste = metier.demandes(db, statut=statut, recherche=recherche)
    lignes = [[_lien_demande(d), esc(_hote(d)), esc(d.get("provenance") or "—"),
               esc(_periode(d)), esc(d.get("nb_personnes") or 1),
               esc(metier.nature(d.get("type_sejour"))),
               badge(d.get("statut"), metier.libelle_statut(d.get("statut"))),
               esc((d.get("cree_le") or "")[:10])] for d in liste]
    options = '<option value="">Tous les statuts</option>' + "".join(
        f'<option value="{esc(c)}" {"selected" if c == statut else ""}>{esc(l)}</option>'
        for c, l in metier.STATUTS.items())
    contenu = f"""
<h1>Demandes</h1>
<p class="sous-titre">{len(liste)} demande(s) affichée(s).</p>
{carte("", f'''<form method="get" action="/demandes" class="ligne">
  <div><label for="q">Recherche</label><input type="text" id="q" name="q" value="{esc(recherche)}" placeholder="nom, référence, provenance…"></div>
  <div><label for="statut">Statut</label><select id="statut" name="statut">{options}</select></div>
  <div style="align-self:end"><button class="btn" type="submit">Filtrer</button></div>
</form>''')}
{carte("", tableau(["Référence", "Hôte", "Provenance", "Période", "Pers.", "Nature", "Statut", "Reçue"],
      lignes, "Aucune demande ne correspond."),
      '<div class="barre-actions"><a class="btn" href="/demandes/nouveau">Saisir une demande</a>'
      '<a class="btn btn-secondaire" href="/demandes/export.csv">Export CSV</a></div>')}
"""
    return page("Demandes", contenu, user, "demandes", message, erreur)


def demande_nouvelle(db, user, csrf: str, valeurs=None, message: str = "",
                     erreur: str = "") -> str:
    v = valeurs or {}
    champs_nature = "".join(
        f'<option value="{esc(c)}" {"selected" if c == v.get("type_sejour") else ""}>{esc(l)}</option>'
        for c, l in metier.NATURES.items())
    contenu = f"""
<h1>Saisir une demande</h1>
<p class="sous-titre">Demande reçue par téléphone, au portail ou par courriel.</p>
{carte("", f'''<form method="post" action="/demandes/nouveau">
  {_csrf(csrf)}
  <div class="ligne">
    <div><label>Prénom</label><input type="text" name="prenom" value="{esc(v.get('prenom'))}"></div>
    <div><label>Nom</label><input type="text" name="nom" value="{esc(v.get('nom'))}" required></div>
  </div>
  <div class="ligne">
    <div><label>Provenance</label><input type="text" name="provenance" value="{esc(v.get('provenance'))}"></div>
    <div><label>Téléphone</label><input type="text" name="telephone" value="{esc(v.get('telephone'))}"></div>
    <div><label>Courriel</label><input type="email" name="email" value="{esc(v.get('email'))}"></div>
  </div>
  <div class="ligne">
    <div><label>Nature du séjour</label><select name="type_sejour">{champs_nature}</select></div>
    <div><label>Arrivée</label><input type="date" name="date_arrivee" value="{esc(v.get('date_arrivee'))}"></div>
    <div><label>Départ</label><input type="date" name="date_depart" value="{esc(v.get('date_depart'))}"></div>
  </div>
  <div class="ligne">
    <div><label>Nombre de personnes</label><input type="number" min="1" name="nb_personnes" value="{esc(v.get('nb_personnes') or 1)}"></div>
    <div><label>Hommes</label><input type="number" min="0" name="nb_hommes" value="{esc(v.get('nb_hommes'))}"></div>
    <div><label>Femmes</label><input type="number" min="0" name="nb_femmes" value="{esc(v.get('nb_femmes'))}"></div>
  </div>
  <div class="ligne">
    <div><label>Régime alimentaire</label><input type="text" name="regime_alimentaire" value="{esc(v.get('regime_alimentaire'))}"></div>
    <div><label>Accessibilité</label><input type="text" name="accessibilite" value="{esc(v.get('accessibilite'))}"></div>
  </div>
  <label>Besoins ou remarques</label><textarea name="besoin_note">{esc(v.get('besoin_note'))}</textarea>
  <label>Message de l'hôte</label><textarea name="message">{esc(v.get('message'))}</textarea>
  <div class="barre-actions">
    <button class="btn" type="submit">Enregistrer et transmettre</button>
    <a class="btn btn-secondaire" href="/demandes">Annuler</a>
  </div>
</form>''')}
"""
    return page("Saisir une demande", contenu, user, "demandes", message, erreur)


# ===========================================================================
# Fiche d'une demande
# ===========================================================================
def demande_detail(db, user, dem, csrf: str, message: str = "", erreur: str = "") -> str:
    identifiant = dem["id"]
    dispo = metier.verifier_disponibilite(db, dem.get("date_arrivee"), dem.get("date_depart"),
                                           dem.get("nb_personnes") or 1,
                                           exclure_demande_id=dem.get("id"))
    chambre = metier.chambre(db, dem.get("chambre_id"))
    messages = []
    if dem.get("conversation_id"):
        messages = db.lignes("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id",
                             (dem["conversation_id"],))
    notifications = db.lignes(
        "SELECT * FROM notifications WHERE demande_id = ? ORDER BY id DESC", (identifiant,))

    def ligne(label, valeur):
        return f"<dt>{esc(label)}</dt><dd>{valeur}</dd>"

    composition = f"{esc(dem.get('nb_personnes') or 1)} personne(s)"
    if dem.get("nb_hommes") or dem.get("nb_femmes"):
        composition += f" — {esc(dem.get('nb_hommes') or 0)} hommes, {esc(dem.get('nb_femmes') or 0)} femmes"

    besoins = []
    for cle, libelle in (("regime_alimentaire", "Régime"), ("accessibilite", "Accessibilité"),
                         ("participation_offices", "Offices"), ("besoin_note", "Remarque")):
        if dem.get(cle):
            besoins.append(f"{libelle} : {esc(dem[cle])}")
    if dem.get("premiere_visite"):
        besoins.append("Première visite")

    options_statut = "".join(
        f'<option value="{esc(c)}" {"selected" if c == dem.get("statut") else ""}>{esc(l)}</option>'
        for c, l in metier.STATUTS.items())
    libres = {c["id"] for c in dispo["chambres_libres"]}
    options_chambre = '<option value="0">— aucune —</option>' + "".join(
        f'<option value="{c["id"]}" {"selected" if c["id"] == dem.get("chambre_id") else ""}>'
        f'{esc(c["nom"])} ({c["capacite"]} pl.) '
        f'{"attribuée à cette demande" if c["id"] == dem.get("chambre_id") else ("libre" if c["id"] in libres else "occupée")}</option>'
        for c in metier.chambres(db))

    dispo_html = (
        f"<strong>{'Disponible' if dispo['disponible'] else 'À vérifier'}</strong> — "
        f"{dispo['nb_chambres_libres']} chambre(s) libre(s) sur {dispo['nb_chambres_totales']}, "
        f"{dispo['capacite_libre']} place(s) pour {esc(dem.get('nb_personnes') or 1)} personne(s)"
        + (f" <span class=\"muted\">({esc(dispo['motif'])})</span>" if dispo.get("motif") else ""))

    fil = ""
    if messages:
        bulles = []
        for m in messages:
            classe = "bulle-hote" if m["direction"] == "entrant" else "bulle-agent"
            nom = _libelle_message(db, m)
            bulles.append(f'<div class="bulle {classe}"><div class="bulle-meta">{esc(nom)} · '
                          f'{esc(m["horodatage"])} · {esc(m["canal"])}</div>{esc(m["corps"])}</div>')
        fil = f'<div class="transcription">{"".join(bulles)}</div>'
    else:
        fil = '<p class="muted">Aucun échange enregistré.</p>'

    notif_html = tableau(
        ["Date", "Canal", "Destinataire", "Statut", "Motif"],
        [[esc((n["horodatage"] or "")[:16]), esc(n["canal"]), esc(n["destinataire"]),
          badge(n["statut"]), esc(n["erreur"] or "—")] for n in notifications],
        "Aucune transmission consignée.")

    lien_conv = (f'<a href="/conversations/{esc(dem.get("conversation_id"))}">Voir l\'échange complet</a>'
                 if dem.get("conversation_id") else "—")

    contenu = f"""
<h1>Demande {esc(dem.get('reference'))}</h1>
<p class="sous-titre">{esc(_hote(dem))} · {badge(dem.get('statut'), metier.libelle_statut(dem.get('statut')))}</p>
<div class="grille grille-2">
  {carte("Ce que l'hôte a confié", f'''<dl class="fiche">
    {ligne("Hôte", esc(_hote(dem)))}
    {ligne("Provenance", esc(dem.get('provenance') or 'à préciser'))}
    {ligne("Téléphone", esc(dem.get('telephone') or '—'))}
    {ligne("Courriel", esc(dem.get('email') or '—'))}
    {ligne("Nature", esc(metier.nature(dem.get('type_sejour'))))}
    {ligne("Période", esc(_periode(dem)))}
    {ligne("Composition", composition)}
    {ligne("Besoins", '<br>'.join(besoins) if besoins else 'aucun')}
    {ligne("Reçue le", esc(dem.get('cree_le') or '—'))}
    {ligne("Source", esc(dem.get('source') or 'agent'))}
    {ligne("Échange", lien_conv)}
  </dl>''')}
  {carte("Discernement", f'''<p>{dispo_html}</p>
    <form method="post" action="/demandes/{identifiant}/statut" class="barre-actions">
      {_csrf(csrf)}
      <div><label>Décision</label><select name="statut">{options_statut}</select></div>
      <div><button class="btn" type="submit">Enregistrer</button></div>
    </form>
    <form method="post" action="/demandes/{identifiant}/chambre" class="barre-actions">
      {_csrf(csrf)}
      <div><label>Chambre attribuée</label><select name="chambre_id">{options_chambre}</select></div>
      <div><button class="btn" type="submit">Attribuer</button></div>
    </form>
    <p class="petit muted">Chambre actuelle : {esc((chambre or {}).get('nom') or 'non attribuée')}.
    Attribuer une chambre confirme la demande. Une seule chambre peut être attribuée par dossier ; les groupes nécessitant plusieurs chambres doivent être traités séparément.</p>''')}
</div>
{carte("Répondre à l'hôte", f'''<form method="post" action="/demandes/{identifiant}/repondre">
  {_csrf(csrf)}
  <label>Message envoyé à l'hôte</label>
  <textarea name="message" required placeholder="Bien volontiers, nous vous accueillons du …"></textarea>
  <div class="barre-actions">
    <button class="btn" type="submit">Envoyer</button>
    <button class="btn btn-secondaire" type="submit" formaction="/demandes/{identifiant}/notifier">Retransmettre la fiche aux frères</button>
  </div>
  <p class="petit muted">Le message part par WhatsApp si un jeton est configuré, sinon par courriel.</p>
</form>''')}
{carte("Notes internes", f'''<form method="post" action="/demandes/{identifiant}/notes">
  {_csrf(csrf)}
  <textarea name="notes_internes">{esc(dem.get('notes_internes') or '')}</textarea>
  <div class="barre-actions"><button class="btn" type="submit">Enregistrer les notes</button></div>
</form>''')}
{carte("Historique de l'échange", fil)}
{carte("Transmissions", notif_html)}
{carte("", f'''<form method="post" action="/demandes/{identifiant}/supprimer" onsubmit="return confirm('Supprimer cette fiche ? Les échanges et journaux associés restent conservés.');">
  {_csrf(csrf)}
  <button class="btn btn-danger btn-mini" type="submit">Supprimer la demande</button>
  <span class="petit muted">Supprime cette fiche uniquement : les échanges, notifications et journaux peuvent rester conservés.</span>
</form>''')}
"""
    return page(f"Demande {dem.get('reference')}", contenu, user, "demandes", message, erreur)


# ===========================================================================
# Calendrier
# ===========================================================================
def calendrier(db, user, annee: int, mois: int, csrf: str, message: str = "",
               erreur: str = "") -> str:
    occ = metier.occupation_mois(db, annee, mois)
    mois_noms = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                 "août", "septembre", "octobre", "novembre", "décembre"]
    precedent = (dt.date(annee, mois, 1) - dt.timedelta(days=1))
    suivant = (dt.date(annee, mois, 28) + dt.timedelta(days=7)).replace(day=1)

    entete = "<tr><th class=\"nom\">Chambre</th>" + "".join(
        f"<th>{j.day}</th>" for j in occ["jours"]) + "</tr>"
    lignes = []
    for c in occ["chambres"]:
        cellules = []
        for j in occ["jours"]:
            case = occ["cases"].get((j.isoformat(), c["id"]))
            if not case:
                cellules.append("<td></td>")
                continue
            if case["type"] == "sejour":
                classe = ("case-attente" if case.get("statut") == "en_attente" else "case-sejour")
                if case.get("arrivee") == j.isoformat():
                    classe += " case-arrivee"
                if case.get("depart") == j.isoformat():
                    classe += " case-depart"
                contenu_case = (f'<a class="case-lien" href="/demandes/{case["demande_id"]}" '
                                f'title="{esc(case.get("nom"))} — {esc(case.get("reference"))}">'
                                f'{"↦" if case.get("arrivee") == j.isoformat() else ("⇥" if case.get("depart") == j.isoformat() else "•")}</a>')
            else:
                classe = "case-blocage"
                contenu_case = f'<span class="case-lien" title="{esc(case.get("motif") or "indisponible")}">✕</span>'
            cellules.append(f'<td class="{classe}">{contenu_case}</td>')
        lignes.append(f'<tr><th class="nom">{esc(c["nom"])}</th>' + "".join(cellules) + "</tr>")

    blocages = metier.blocages(db)
    options = "".join(f'<option value="{c["id"]}">{esc(c["nom"])}</option>'
                      for c in metier.chambres(db))
    liste_blocages = tableau(
        ["Chambre", "Du", "Au", "Motif", ""],
        [[esc(b.get("chambre_nom") or "—"), esc(metier.format_date(b["date_debut"])),
          esc(metier.format_date(b["date_fin"])), esc(b.get("motif") or "—"),
          f'<form method="post" action="/blocages/{b["id"]}/supprimer">{_csrf(csrf)}'
          f'<button class="btn btn-mini btn-secondaire" type="submit">Retirer</button></form>']
         for b in blocages], "Aucune indisponibilité déclarée.")

    contenu = f"""
<h1>Occupation — {esc(mois_noms[mois])} {annee}</h1>
<p class="sous-titre">↦ arrivée · ⇥ départ · • nuit · ✕ chambre indisponible</p>
<div class="pagination">
  <a href="/calendrier?annee={precedent.year}&mois={precedent.month}">← {esc(mois_noms[precedent.month])}</a>
  <strong>{esc(mois_noms[mois])} {annee}</strong>
  <a href="/calendrier?annee={suivant.year}&mois={suivant.month}">{esc(mois_noms[suivant.month])} →</a>
</div>
{carte("", f'<div style="overflow-x:auto"><table class="calendrier">{entete}{"".join(lignes)}</table></div>')}
<div class="grille grille-2">
  {carte("Déclarer une indisponibilité", f'''<form method="post" action="/blocages">
    {_csrf(csrf)}
    <div class="ligne">
      <div><label>Chambre</label><select name="chambre_id">{options}</select></div>
      <div><label>Du</label><input type="date" name="date_debut" required></div>
      <div><label>Au</label><input type="date" name="date_fin" required></div>
    </div>
    <label>Motif</label><input type="text" name="motif" placeholder="travaux, retraite de la communauté…">
    <div class="barre-actions"><button class="btn" type="submit">Bloquer</button></div>
  </form>''')}
  {carte("Chambres", f'''<form method="post" action="/chambres">
    {_csrf(csrf)}
    <div class="ligne">
      <div><label>Nom</label><input type="text" name="nom" required></div>
      <div><label>Capacité</label><input type="number" min="1" name="capacite" value="1"></div>
      <div><label>Aile</label><input type="text" name="aile"></div>
    </div>
    <div class="ligne">
      <div><label>Accès PMR</label><select name="pmr"><option value="0">non</option><option value="1">oui</option></select></div>
      <div style="align-self:end"><button class="btn" type="submit">Ajouter la chambre</button></div>
    </div>
  </form>''')}
</div>
{carte("Indisponibilités déclarées", liste_blocages)}
"""
    return page("Occupation", contenu, user, "calendrier", message, erreur)


# ===========================================================================
# Base de connaissances
# ===========================================================================
def connaissances_liste(db, user, q: str = "", manquantes: bool = False,
                        message: str = "", erreur: str = "") -> str:
    if manquantes:
        fiches = knowledge.fiches_a_completer(db)
    elif q:
        motif = f"%{q}%"
        fiches = db.lignes(
            "SELECT * FROM connaissances WHERE question LIKE ? OR mots_cles LIKE ? "
            "OR reponse LIKE ? OR cle LIKE ? OR categorie LIKE ? "
            "ORDER BY categorie, priorite DESC", (motif,) * 5)
    else:
        fiches = db.lignes("SELECT * FROM connaissances ORDER BY categorie, priorite DESC, cle")
    lignes = []
    for f in fiches:
        etat = ("<span class=\"badge b-echoue\">à compléter</span>"
                if knowledge.est_a_completer(f["reponse"]) else
                ("<span class=\"badge b-envoye\">active</span>" if f["active"]
                 else "<span class=\"badge b-ignore\">désactivée</span>"))
        lignes.append([
            f'<a href="/connaissances/{f["id"]}">{esc(f["cle"])}</a>',
            esc(f["categorie"]), esc(f["question"]), esc(f["priorite"]), etat])
    n_manquantes = len(knowledge.fiches_a_completer(db))
    contenu = f"""
<h1>Base de connaissances</h1>
<p class="sous-titre">La parole de la maison, que l'agent ne fait que transmettre.</p>
{carte("", f'''<form method="get" action="/connaissances" class="ligne">
  <div><label for="q">Recherche</label><input type="text" id="q" name="q" value="{esc(q)}" placeholder="offices, offrande, trajet…"></div>
  <div style="align-self:end"><label style="display:flex;gap:8px;align-items:center;text-transform:none">
    <input type="checkbox" name="manquantes" value="1" {"checked" if manquantes else ""} style="width:auto">
    Seulement les fiches à compléter ({n_manquantes})</label></div>
  <div style="align-self:end"><button class="btn" type="submit">Chercher</button></div>
</form>''')}
{carte("", tableau(["Clé", "Catégorie", "Question", "Prio.", "État"], lignes,
      "Aucune fiche ne correspond."),
      '<div class="barre-actions"><a class="btn" href="/connaissances/nouvelle">Nouvelle fiche</a>'
      '<a class="btn btn-secondaire" href="/connaissances/export.json">Export JSON</a></div>')}
<p class="petit muted">Une mention <span class="mono">[[À COMPLÉTER …]]</span> n'est jamais
montrée à un hôte : l'agent répond alors qu'il transmet la question aux frères.</p>
"""
    return page("Base de connaissances", contenu, user, "connaissances", message, erreur)


def connaissance_fiche(db, user, fiche, csrf: str, message: str = "",
                       erreur: str = "") -> str:
    f = fiche or {"cle": "", "categorie": "divers", "question": "", "mots_cles": "",
                  "reponse": "", "priorite": 5, "active": 1, "id": ""}
    categories = sorted({x["categorie"] for x in db.lignes("SELECT DISTINCT categorie FROM connaissances")}
                        | {"accueil", "offices", "sejour", "regles_maison", "tarif", "acces",
                           "contacts", "sante", "groupes", "vocation", "formation", "boutique",
                           "vie_monastique", "divers"})
    options = "".join(f'<option value="{esc(c)}" {"selected" if c == f["categorie"] else ""}>{esc(c)}</option>'
                      for c in categories)
    supprimer = ""
    if f.get("id"):
        supprimer = f'''<form method="post" action="/connaissances/{f["id"]}/supprimer"
          onsubmit="return confirm('Supprimer cette fiche ?');" style="display:inline">
          {_csrf(csrf)}<button class="btn btn-danger btn-mini" type="submit">Supprimer</button></form>'''
    contenu = f"""
<h1>{'Modifier une fiche' if f.get('id') else 'Nouvelle fiche'}</h1>
<p class="sous-titre">Écrire ici, c'est écrire ce que l'agent dira. Relisez à voix haute.</p>
{carte("", f'''<form method="post" action="/connaissances/{f.get('id') or 'nouvelle'}">
  {_csrf(csrf)}
  <div class="ligne">
    <div><label>Clé (identifiant stable)</label><input type="text" name="cle" value="{esc(f.get('cle'))}" required></div>
    <div><label>Catégorie</label><select name="categorie">{options}</select></div>
    <div><label>Priorité (1–10)</label><input type="number" min="1" max="10" name="priorite" value="{esc(f.get('priorite') or 5)}"></div>
  </div>
  <label>Question type</label>
  <input type="text" name="question" value="{esc(f.get('question'))}" required>
  <label>Mots-clés (séparés par des virgules)</label>
  <input type="text" name="mots_cles" value="{esc(f.get('mots_cles'))}">
  <label>Réponse de la maison</label>
  <textarea name="reponse" style="min-height:260px">{esc(f.get('reponse'))}</textarea>
  <div class="ligne" style="margin-top:10px">
    <div><label style="display:flex;gap:8px;align-items:center;text-transform:none">
      <input type="checkbox" name="active" value="1" {"checked" if f.get('active', 1) else ""} style="width:auto">
      Fiche active</label></div>
  </div>
  <div class="barre-actions">
    <button class="btn" type="submit">Enregistrer</button>
    <a class="btn btn-secondaire" href="/connaissances">Retour</a>
    {supprimer}
  </div>
  <p class="petit muted">Pour signaler une information manquante, laissez une mention
  <span class="mono">[[À COMPLÉTER : …]]</span> : elle sera visible des frères seulement.</p>
</form>''')}
"""
    return page("Fiche de connaissance", contenu, user, "connaissances", message, erreur)


# ===========================================================================
# Simulateur
# ===========================================================================
def simulateur(db, user, cid: str, csrf: str, message: str = "", erreur: str = "") -> str:
    messages = db.lignes("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (cid,))
    conversation = db.ligne("SELECT * FROM conversations WHERE id = ?", (cid,))
    donnees = {}
    if conversation:
        try:
            donnees = json.loads(conversation.get("donnees") or "{}")
        except ValueError:
            donnees = {}
    bulles = []
    for m in messages:
        classe = "bulle-hote" if m["direction"] == "entrant" else "bulle-agent"
        bulles.append(f'<div class="bulle {classe}"><div class="bulle-meta">'
                      f'{"Hôte" if m["direction"] == "entrant" else "Agent"} · {esc(m["horodatage"])}</div>'
                      f'{esc(m["corps"]) or "(silence)"}</div>')
    if not bulles:
        bulles.append('<div class="bulle bulle-agent"><div class="bulle-meta">Agent</div>'
                      'Écrivez « Bonjour » pour commencer l\'essai.</div>')
    resume = {k: v for k, v in donnees.items()
              if k in ("etape", "nom", "prenom", "provenance", "type_sejour",
                       "date_arrivee", "date_depart", "nb_personnes", "regime",
                       "accessibilite", "besoins_connus", "relances", "humain_requis")}
    contenu = f"""
<h1>Simulateur</h1>
<p class="sous-titre">Essai isolé : aucune demande réelle ni notification n'est créée. Les échanges de test restent visibles dans le journal des conversations.</p>
<div class="grille grille-2">
  {carte("Échange", f'''<div class="transcription">{"".join(bulles)}</div>
    <form method="post" action="/simulateur">
      {_csrf(csrf)}
      <input type="hidden" name="cid" value="{esc(cid)}">
      <label>Message de l'hôte</label>
      <textarea name="message" required style="min-height:70px" autofocus></textarea>
      <div class="barre-actions">
        <button class="btn" type="submit">Envoyer</button>
        <a class="btn btn-secondaire" href="/simulateur?nouveau=1">Nouvel essai</a>
      </div>
    </form>''')}
  {carte("Ce que l'agent a compris", f'''<pre class="mono">{esc(json.dumps(resume, ensure_ascii=False, indent=2))}</pre>
    <p class="petit muted">En situation réelle, les frères décident après réception de la demande.</p>''')}
</div>
"""
    return page("Simulateur", contenu, user, "simulateur", message, erreur)


# ===========================================================================
# Échanges
# ===========================================================================
def conversations_liste(db, user, message: str = "", erreur: str = "") -> str:
    liste = db.lignes("SELECT * FROM conversations ORDER BY maj DESC LIMIT 200")
    lignes = []
    for c in liste:
        relais = ("<span class=\"badge b-echoue\">à reprendre</span>" if c["humain_requis"]
                  else "<span class=\"badge b-envoye\">agent</span>")
        demande = (f'<a href="/demandes/{c["demande_id"]}">dossier</a>' if c.get("demande_id") else "—")
        lignes.append([f'<a href="/conversations/{esc(c["id"])}">{esc(c["id"])[:26]}</a>',
                       esc(c.get("nom_affiche") or "—"), esc(c.get("canal") or "—"),
                       esc(c.get("etat") or "—"), relais, demande, esc((c.get("maj") or "")[:16])])
    contenu = f"""
<h1>Échanges</h1>
<p class="sous-titre">Toutes les conversations, et celles où un frère doit prendre le relais.</p>
{carte("", tableau(["Conversation", "Hôte", "Canal", "État", "Qui répond", "Dossier", "Dernier message"],
      lignes, "Aucun échange pour le moment."))}
"""
    return page("Échanges", contenu, user, "conversations", message, erreur)


def conversation_detail(db, user, conv, csrf: str, message: str = "",
                        erreur: str = "") -> str:
    messages = db.lignes("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id",
                         (conv["id"],))
    bulles = []
    for m in messages:
        classe = "bulle-hote" if m["direction"] == "entrant" else "bulle-agent"
        bulles.append(f'<div class="bulle {classe}"><div class="bulle-meta">'
                      f'{esc(_libelle_message(db, m))} · '
                      f'{esc(m["horodatage"])} · {esc(m["canal"])}</div>'
                      f'{esc(m["corps"]) or "(silence)"}</div>')
    donnees = {}
    try:
        donnees = json.loads(conv.get("donnees") or "{}")
    except ValueError:
        pass
    action = ("rendre" if conv.get("humain_requis") else "prendre")
    libelle = ("Rendre la parole à l'agent" if conv.get("humain_requis")
               else "Prendre le relais (l'agent se taira)")
    demande = (f'<a href="/demandes/{conv["demande_id"]}">Voir le dossier</a>'
               if conv.get("demande_id") else "Aucun dossier constitué")
    adresse = urllib.parse.quote(str(conv['id']), safe="")
    if conv.get("canal") == "whatsapp" and conv.get("telephone"):
        if conv.get("humain_requis"):
            reponse_humaine = carte("Répondre à l'hôte", f'''<form method="post" action="/conversations/{esc(adresse)}/repondre">
      {_csrf(csrf)}
      <label for="message-relais">Votre message WhatsApp</label>
      <textarea id="message-relais" name="message" maxlength="4000" required></textarea>
      <div class="barre-actions"><button class="btn" type="submit">Envoyer à l'hôte</button></div>
      <p class="petit muted">Si l'envoi échoue, le message reste dans la file WhatsApp. La réception effective dépend de Meta et de la fenêtre de 24 heures.</p>
    </form>''')
        else:
            reponse_humaine = carte("Répondre à l'hôte", '<p>Pour éviter une réponse simultanée de l’agent, prenez d’abord le relais.</p>')
    else:
        reponse_humaine = ''
    contenu = f"""
<h1>Échange {esc(conv['id'])}</h1>
<p class="sous-titre">{esc(conv.get('nom_affiche') or 'hôte non identifié')} ·
{esc(conv.get('canal') or '')} · {esc(conv.get('telephone') or '')} · {demande}</p>
{carte("Transcription", f'<div class="transcription">{"".join(bulles) or "<p class=muted>Aucun message.</p>"}</div>')}
{carte("Ce que l'agent a recueilli", f'<pre class="mono">{esc(json.dumps(donnees, ensure_ascii=False, indent=2))}</pre>')}
{carte("Relais", f'''<form method="post" action="/conversations/{esc(conv['id'])}/relais">
  {_csrf(csrf)}<input type="hidden" name="action" value="{action}">
  <button class="btn" type="submit">{esc(libelle)}</button>
</form>''')}
{reponse_humaine}
"""
    return page("Échange", contenu, user, "conversations", message, erreur)


# ===========================================================================
# Notifications et journal
# ===========================================================================
def notifications_liste(db, user, message: str = "", erreur: str = "") -> str:
    liste = db.lignes(
        "SELECT n.*, d.reference FROM notifications n LEFT JOIN demandes d "
        "ON d.id = n.demande_id ORDER BY n.id DESC LIMIT 300")
    lignes = []
    for n in liste:
        ref = (f'<a href="/demandes/{n["demande_id"]}">{esc(n["reference"])}</a>'
               if n.get("reference") else "—")
        conversation = (f'<a href="/conversations/{esc(urllib.parse.quote(n["conversation_id"], safe=""))}">Voir l’échange</a>'
                        if n.get("conversation_id") else "—")
        lignes.append([esc((n["horodatage"] or "")[:16]), esc(n.get("sujet") or "—"),
                       ref, conversation, esc(n["canal"]), esc(n["destinataire"] or "—"),
                       badge(n["statut"]), esc(n["erreur"] or "—")])
    contenu = f"""
<h1>Notifications</h1>
<p class="sous-titre">Ce qui est parti, ce qui n'est pas parti, et pourquoi.</p>
{carte("", tableau(["Date", "Sujet", "Dossier", "Échange", "Canal", "Destinataire", "Statut", "Motif"],
      lignes, "Aucune transmission."))}
"""
    return page("Notifications", contenu, user, "notifications", message, erreur)


def journal_liste(db, user) -> str:
    liste = db.lignes("SELECT * FROM journal ORDER BY id DESC LIMIT 400")
    lignes = [[esc((j["horodatage"] or "")[:19]), esc(j["acteur"]), esc(j["action"]),
               esc(j["objet"]), esc(j["details"])] for j in liste]
    contenu = f"""
<h1>Journal</h1>
<p class="sous-titre">Qui a fait quoi. Rien n'est effaçable depuis l'interface.</p>
{carte("", tableau(["Date", "Acteur", "Action", "Objet", "Détails"], lignes, "Journal vide."))}
"""
    return page("Journal", contenu, user, "journal")


# ===========================================================================
# Paramètres
# ===========================================================================
MASQUE = "••••••••"

GROUPES_PARAMETRES = [
    ("L'agent d'accueil", [
        ("agent_actif", "Agent actif (1 = répond, 0 = relais humain seul)", "drapeau"),
        ("agent_heures_debut", "Heure de début affichée", "texte"),
        ("agent_heures_fin", "Heure de fin affichée", "texte"),
        ("agent_delai_reponse", "Délai honnête annoncé aux hôtes", "texte"),
    ]),
    ("WhatsApp (Meta Cloud API)", [
        ("wa_token", "Jeton permanent", "secret"),
        ("wa_phone_number_id", "Identifiant du numéro (phone_number_id)", "texte"),
        ("wa_verify_token", "Jeton de vérification du webhook", "secret"),
        ("wa_app_secret", "Secret de l'application (signature)", "secret"),
    ]),
    ("Relais vers les frères", [
        ("hoteliers_emails", "Adresses de courriel (séparées par des virgules)", "texte"),
        ("hoteliers_whatsapp", "Numéros WhatsApp (séparés par des virgules)", "texte"),
        ("notifier_par_email", "Notifier par courriel", "drapeau"),
        ("notifier_par_whatsapp", "Notifier par WhatsApp", "drapeau"),
    ]),
    ("Courriel (SMTP)", [
        ("smtp_hote", "Serveur SMTP", "texte"),
        ("smtp_port", "Port (465 = SSL, 587 = STARTTLS)", "texte"),
        ("smtp_utilisateur", "Compte", "texte"),
        ("smtp_mot_de_passe", "Mot de passe d'application", "secret"),
        ("smtp_expediteur", "Adresse d'expédition", "texte"),
        ("smtp_tls", "Utiliser TLS", "drapeau"),
    ]),
    ("API JSON (/api/agent)", [
        ("api_cle", "Clé d'API (laisser vide ferme l'API)", "secret"),
        ("api_ouverte", "Ouvrir l'API sans clé (déconseillé)", "drapeau"),
    ]),
]

PARAMETRES_SECRETS = {cle for _, champs in GROUPES_PARAMETRES for cle, _, type_ in champs
                      if type_ == "secret"}
PARAMETRES_CLEFS = [cle for _, champs in GROUPES_PARAMETRES for cle, _, _ in champs]


def parametres(db, user, csrf: str, message: str = "", erreur: str = "") -> str:
    import os
    blocs = []
    for titre, champs in GROUPES_PARAMETRES:
        lignes = []
        for cle, libelle, type_ in champs:
            valeur = config.parametre(db, cle, "")
            force = bool(os.environ.get(cle))
            note = (' <span class="petit muted">(défini par l\'environnement, prioritaire)</span>'
                    if force else "")
            if type_ == "drapeau":
                actif = valeur.lower() in ("1", "true", "oui", "on")
                html_champ = (f'<select name="{cle}">'
                              f'<option value="1" {"selected" if actif else ""}>oui</option>'
                              f'<option value="0" {"" if actif else "selected"}>non</option></select>')
            elif type_ == "secret":
                affiche = MASQUE if valeur else ""
                html_champ = (f'<input type="password" name="{cle}" value="{esc(affiche)}" '
                              f'autocomplete="off" placeholder="(vide)">')
            else:
                html_champ = f'<input type="text" name="{cle}" value="{esc(valeur)}">'
            lignes.append(f'<label for="{cle}">{esc(libelle)}{note}</label>{html_champ}')
        blocs.append(carte(titre, "".join(lignes)))
    contenu = f"""
<h1>Paramètres</h1>
<p class="sous-titre">Une variable d'environnement l'emporte toujours sur la valeur saisie ici.</p>
<form method="post" action="/parametres">
  {_csrf(csrf)}
  <div class="grille grille-2">{"".join(blocs)}</div>
  <div class="barre-actions"><button class="btn" type="submit">Enregistrer les paramètres</button></div>
  <p class="petit muted">Un secret déjà enregistré s'affiche masqué : le laisser tel quel ne le change pas.</p>
</form>
"""
    return page("Paramètres", contenu, user, "parametres", message, erreur)


# ===========================================================================
# WhatsApp
# ===========================================================================
WHATSAPP_CLEFS = ["wa_token", "wa_phone_number_id", "wa_verify_token", "wa_app_secret",
                  "wa_api_version", "wa_numero_test", "site_url"]
WHATSAPP_SECRETS = {"wa_token", "wa_verify_token", "wa_app_secret"}


def whatsapp_page(db, user, csrf: str, message: str = "", erreur: str = "") -> str:
    from ..channels import whatsapp

    conf = whatsapp.configuration(db)
    pret = bool(conf["token"] and conf["phone_number_id"])
    numero_essai = conf["numero_test"] or ""
    url_webhook = ((conf["site_url"] + "/webhook/whatsapp") if conf["site_url"]
                   else "— (renseignez l'adresse publique ci-dessous)")

    dernier = None
    brut = config.parametre(db, "wa_dernier_diagnostic", "")
    if brut:
        try:
            dernier = json.loads(brut)
        except ValueError:
            dernier = None

    diagnostic_fait = bool(dernier and dernier.get("etapes"))
    est_diagnostic = bool(dernier and dernier.get("type") == "configuration")
    essentiels = (dernier or {}).get("etapes", []) or []
    manquants = [e for e in essentiels if not e.get("ok")]
    # Un test d'envoi seul, ou un ancien diagnostic, ne prouve jamais que
    # le webhook est opérationnel.
    tout_vert = est_diagnostic and bool(dernier.get("pret")) and not manquants

    etapes_html = ""
    if diagnostic_fait:
        elements = []
        for e in dernier["etapes"]:
            marque = "✓" if e.get("ok") else "✗"
            couleur = "color:#33502e" if e.get("ok") else "color:#7a2c20"
            elements.append(f'<li><strong style="{couleur}">{marque} {esc(e.get("etape"))}</strong>'
                            f' — {esc(e.get("detail"))}</li>')
        if tout_vert:
            verdict = ('<p><span class="badge b-envoye">Contrôles préalables satisfaits</span> '
                       'La réception et la réponse réelles restent à tester.</p>')
        elif est_diagnostic:
            verdict = (f'<p><span class="badge b-en_attente">Configuration incomplète — '
                       f'{len(manquants)} point(s) à régler</span></p>')
        else:
            verdict = '<p>Résultat d’essai uniquement ; lancez le diagnostic complet.</p>'
        etapes_html = (f'<p class="petit muted">Relevé du {esc(dernier.get("horodatage", ""))}</p>'
                       + verdict + f'<ul>{"".join(elements)}</ul>')
        if dernier.get("compte"):
            compte = dernier["compte"]
            etapes_html += ("<p>Compte joint : <strong>" + esc(compte.get("verified_name") or "—")
                            + "</strong> · numéro " + esc(compte.get("display_phone_number") or "—")
                            + " · qualité " + esc(compte.get("quality_rating") or "—") + "</p>")
    else:
        etapes_html = '<p class="muted">Aucun relevé pour le moment. Cliquez sur « Vérifier le compte ».</p>'

    file_attente = whatsapp.file_attente(db, 100)
    derniers = whatsapp.derniers_envois(db, 12)
    lignes = []
    for e in derniers:
        extrait = (e["corps"] or "").replace("\n", " ")
        extrait = extrait[:90] + ("…" if len(extrait) > 90 else "")
        lignes.append([esc((e["cree_le"] or "")[:16]),
                       esc(whatsapp.afficher_numero(e["numero"]) or "—"),
                       esc(extrait), badge(e["statut"]), esc(e["erreur"] or "—")])

    def champ(cle, libelle, type_="text", valeur=None, placeholder=""):
        v = config.parametre(db, cle, "") if valeur is None else valeur
        if cle in WHATSAPP_SECRETS:
            v = MASQUE if v else ""
            html = (f'<input type="password" name="{cle}" value="{esc(v)}" autocomplete="off" '
                    f'placeholder="(vide)">')
        else:
            html = (f'<input type="text" name="{cle}" value="{esc(v)}" '
                    f'placeholder="{esc(placeholder)}">')
        return f'<label for="{cle}">{esc(libelle)}</label>{html}'

    guide = """<ol>
  <li>Sur <strong>developers.facebook.com</strong>, créez une application de type
      <em>Business</em>, puis ajoutez le produit <strong>WhatsApp</strong>.</li>
  <li>Dans <strong>WhatsApp → API Setup</strong>, relevez le <em>Phone number ID</em>
      et générez un <strong>jeton permanent</strong> (utilisateur système).</li>
  <li>Ajoutez votre numéro d'essai dans <strong>« Destinataires de test »</strong>
      (ou passez le numéro Business en production).</li>
  <li>Dans <strong>Configuration → Webhook</strong>, collez l'adresse ci-dessous et le
      jeton de vérification, puis abonnez-vous au champ <strong>messages</strong>.
      L'adresse doit être en <strong>HTTPS public</strong> (Caddy devant le serveur).</li>
  <li>Depuis votre téléphone, écrivez « Bonjour » au numéro WhatsApp Business :
      l'agent répondra. C'est le test le plus fidèle, car Meta n'autorise un message
      libre que dans les 24 h qui suivent un message de l'hôte.</li>
</ol>"""

    if tout_vert:
        classe_bandeau = "alerte-ok"
        bandeau = ("Les contrôles préalables sont satisfaits. Il reste à vérifier le webhook "
                   "et un échange complet avec un téléphone réel.")
    elif est_diagnostic:
        noms = ", ".join(e.get("etape") or "?" for e in manquants) or "—"
        classe_bandeau = "alerte-info"
        bandeau = f"Il reste {len(manquants)} point(s) à régler : {noms}."
    elif diagnostic_fait:
        classe_bandeau = "alerte-info"
        bandeau = "Un essai seul ne vérifie pas le webhook. Lancez le diagnostic complet et un échange réel."
    elif pret:
        classe_bandeau = "alerte-ok"
        bandeau = ("Réglages présents. Lancez « Vérifier le compte » pour confirmer "
                   "que tout est vert.")
    else:
        classe_bandeau = "alerte-info"
        bandeau = ("WhatsApp n’est pas encore configuré. Les envois en échec doivent "
                   "être surveillés dans la file et repris manuellement.")
    if file_attente:
        bandeau += f" — {len(file_attente)} message(s) en attente."

    contenu = f"""
<h1>Brancher WhatsApp</h1>
<p class="sous-titre">Meta Cloud API — vérifiez la configuration et testez le canal avant de recevoir des hôtes.</p>
<div class="alerte {classe_bandeau}">
  {esc(bandeau)}
</div>
<div class="grille grille-2">
  {carte("Réglages Meta", f'''<form method="post" action="/whatsapp/enregistrer">
    {_csrf(csrf)}
    {champ("wa_token", "Jeton d'accès permanent")}
    {champ("wa_phone_number_id", "Phone number ID")}
    {champ("wa_verify_token", "Jeton de vérification du webhook")}
    {champ("wa_app_secret", "Secret de l'application (signature)")}
    {champ("wa_api_version", "Version de l'API", placeholder="v21.0")}
    {champ("site_url", "Adresse publique du tableau de bord", placeholder="https://hotellerie.exemple.org")}
    {champ("wa_numero_test", "Numéro d'essai", valeur=numero_essai)}
    <div class="barre-actions">
      <button class="btn" type="submit">Enregistrer</button>
    </div>
    <p class="petit muted">Les secrets s'affichent masqués : les laisser tels quels ne les change pas.</p>
  </form>''')}
  {carte("Adresse à déclarer dans Meta", f'''<dl class="fiche">
    <dt>URL du webhook</dt><dd class="mono">{esc(url_webhook)}</dd>
    <dt>Jeton de vérification</dt><dd>{"configuré (masqué)" if conf.get("verify_token") else "non configuré"}</dd>
    <dt>Champ à s'abonner</dt><dd class="mono">messages</dd>
  </dl>
  <form method="post" action="/whatsapp/verifier" class="barre-actions">
    {_csrf(csrf)}
    <button class="btn" type="submit">Vérifier le compte chez Meta</button>
  </form>
  <p class="petit muted">Vérifie le jeton et le numéro en interrogeant graph.facebook.com.</p>''')}
</div>
{carte("Relevé du diagnostic", etapes_html)}
<div class="grille grille-2">
  {carte("Envoyer un message d'essai", f'''<form method="post" action="/whatsapp/tester">
    {_csrf(csrf)}
    <label for="numero">Destinataire</label>
    <input type="text" id="numero" name="numero" value="{esc(numero_essai)}">
    <p class="petit muted">Indiquez un numéro d'essai autorisé par Meta, au format international.</p>
    <label for="message_essai">Message</label>
    <textarea id="message_essai" name="message" style="min-height:90px">Pax. Ceci est un message d'essai de l'hôtellerie du Monastère Sainte-Marie de Bouaké. Que Dieu vous garde.</textarea>
    <div class="barre-actions"><button class="btn" type="submit">Envoyer l'essai</button></div>
    <p class="petit muted">Si Meta refuse avec le code 131047, écrivez d'abord
    « Bonjour » au numéro Business depuis votre téléphone : la fenêtre de 24 h s'ouvrira.</p>
  </form>''')}
  {carte("File d'attente", f'''<p>{len(file_attente)} message(s) en attente de départ.</p>
  <form method="post" action="/whatsapp/rejouer">
    {_csrf(csrf)}
    <button class="btn" type="submit">Rejouer la file</button>
  </form>
  <p class="petit muted">Chaque message est écrit en base avant l'envoi : une coupure
  de réseau ou un jeton absent ne fait perdre aucune parole.</p>''')}
</div>
{carte("Derniers messages WhatsApp", tableau(
    ["Date", "Destinataire", "Message", "Statut", "Motif"], lignes,
    "Aucun message pour le moment."))}
{carte("Ce qu'il faut faire dans Meta", guide)}
"""
    return page("WhatsApp", contenu, user, "whatsapp", message, erreur)
