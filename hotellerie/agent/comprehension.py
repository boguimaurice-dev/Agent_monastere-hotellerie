# -*- coding: utf-8 -*-
"""
Comprendre le français des hôtes, sans modèle de langage.

Ce module ne décide de rien : il extrait. Dates (« du 12 au 15 octobre »),
identité, provenance, nombre de personnes, besoins. Tout est déterministe et
vérifiable à la main — c'est ce qui permet à l'agent de fonctionner hors ligne,
chez un hôte qui écrit parfois très vite, parfois avec des fautes.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

MOIS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12,
}
MOIS_RE = "|".join(MOIS)

NOMBRES = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
    "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
}

# Mots qui ne peuvent jamais être un nom de personne, une ville ou un besoin.
MOTS_VIDES = {
    "oui", "non", "peut", "etre", "sais", "sait", "ne", "pas", "rien", "aucun",
    "aucune", "bonjour", "bonsoir", "salut", "merci", "pax", "daccord",
    "accord", "volontiers", "d", "l", "j", "m", "t", "s", "n", "c", "qu",
    "le", "la", "les", "un", "une", "des", "de", "du", "au", "aux", "a",
    "et", "ou", "en", "dans", "sur", "pour", "par", "avec", "sans", "je",
    "tu", "il", "elle", "on", "nous", "vous", "ils", "elles", "mon", "ma",
    "mes", "ce", "cet", "cette", "ces", "qui", "que", "quoi", "est", "sont",
    "voudrais", "veux", "vouloir", "souhaite", "aimerais", "viens", "venir",
    "arrive", "rester", "sejourner", "reserver", "retraite", "repos", "couple",
    "groupe", "seul", "seule", "travail", "mission", "discernement", "vocation",
    "malade", "urgent", "urgence", "pere", "frere", "soeur", "monastere",
    "hotellerie", "chambre", "demande", "sejour", "information", "renseignement",
    "question", "reponse", "aujourdhui", "demain", "semaine", "mois", "jour",
    "nuit", "nuits", "personne", "personnes", "gens", "monde", "peu", "tres",
    "bien", "tout", "tous", "toute", "toutes", "plus", "moins", "aussi",
    "janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
    "septembre", "octobre", "novembre", "decembre", "annee", "an", "pourquoi",
    "comment", "combien", "quand", "quel", "quelle", "quels", "quelles",
    "desole", "desolee", "content", "contente", "interesse", "interessee",
}

# Verbes et tournures qui montrent une phrase, jamais un nom de personne :
# « Nous venons de Korhogo » ne doit pas donner l'hôte « Venons ».
VERBES_REFUS = {
    "venons", "viens", "venait", "sommes", "arrivons", "habitons", "residons",
    "voudrions", "voudrais", "voulons", "souhaitons", "cherchons", "cherche",
    "preparer", "preparons", "organiser", "participer", "annuler", "annulons",
    "pouvons", "peux", "pouvons", "aimerions", "desirons", "esperons",
}


# ---------------------------------------------------------------------------
# Outils de texte
# ---------------------------------------------------------------------------
def _preparer(texte: str) -> str:
    """Minuscules, sans accents, apostrophes d'élision en espaces.

    Les apostrophes internes sont retirées : « N'Guessan » → « nguessan » —
    on ne coupe pas un nom en deux.
    """
    t = (texte or "").lower()
    t = re.sub(r"\bqu['’]", "qu ", t)
    t = re.sub(r"\b([dljmtsc])['’]", r"\1 ", t)
    # « n'est », « n'a » : élision. Mais « N'Guessan », « N'Dri » : un nom.
    t = re.sub(r"\bn['’](?=(?:est|a|en|y|ont|avait|aurait|etait|aura|aie)\b)", "n ", t)
    t = t.replace("'", "").replace("’", "")
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9/:.,;!?\s-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _mots(texte: str) -> list:
    return [m for m in re.split(r"[^a-z0-9]+", _preparer(texte)) if m]


def _restaurer_expression(retenus, texte_original: str) -> str:
    """Restitue une expression telle qu'elle a été écrite : « San-Pédro »."""
    mots = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’\-]*", texte_original or "")
    cible = " ".join(retenus)
    # De un à n mots : « San-Pédro » est un seul mot, « San Pedro » en est deux.
    for taille in range(1, len(retenus) + 1):
        for i in range(0, max(0, len(mots) - taille + 1)):
            fenetre = mots[i:i + taille]
            essai = " ".join(_preparer(m).replace("-", " ") for m in fenetre)
            if essai == cible:
                return " ".join(fenetre)
    return " ".join(_restaurer(j, texte_original) for j in retenus)


def _jolie(mot: str) -> str:
    return mot[:1].upper() + mot[1:] if mot else ""


def _restaurer(valeur: str, texte_original: str) -> str:
    """Rend aux mots leurs accents d'origine : « Bouake » → « Bouaké ».

    La compréhension travaille sans accents (c'est plus robuste), mais ce que
    lit un frère doit être écrit correctement : c'est le nom d'une ville, pas
    une approximation.
    """
    if not valeur or not texte_original:
        return _jolie(valeur) if valeur and valeur.islower() else valeur
    cible = _preparer(valeur)
    for mot in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’\-]*", texte_original):
        if _preparer(mot) == cible:
            return mot[:1].upper() + mot[1:]
    return _jolie(valeur) if valeur.islower() else valeur


# ===========================================================================
# DATES
# ===========================================================================
def _ajouter(entrees, debut, fin, jour, mois, annee) -> None:
    for e in entrees:
        if not (fin <= e["debut"] or debut >= e["fin"]):
            return
    entrees.append({"debut": debut, "fin": fin, "jour": jour, "mois": mois,
                    "annee": annee})


def _dater(entree, reference: dt.date, apres=None):
    if not entree.get("mois"):
        return None
    annee = entree.get("annee") or reference.year
    for essai in range(0, 3):
        try:
            d = dt.date(annee + essai, entree["mois"], entree["jour"])
        except ValueError:
            continue
        if entree.get("annee"):
            return d
        if d < reference:
            continue
        if apres and d <= apres:
            continue
        return d
    return None


def _duree(texte: str):
    """Durée exprimée en nuits, si l'hôte la donne en mots."""
    t = _preparer(texte)
    for motif, jours in (
        (r"\btrois\s+semaines\b", 21),
        (r"\bdeux\s+semaines\b", 14),
        (r"\bune?\s+semaine\b", 7),
        (r"\b(?:la|cette)\s+semaine\s+(?:du|de)\b", 7),
        (r"\bquinze\s+jours\b", 15),
        (r"\bun\s+week\s*end\b", 2),
        (r"\bune?\s+nuit\b", 1),
        (r"\bune?\s+journee\b", 1),
    ):
        if re.search(motif, t):
            return jours
    m = re.search(r"\b(\d{1,2})\s*(nuits?|jours?)\b", t)
    if m:
        return int(m.group(1))
    return None


def extraire_dates(texte: str, aujourdhui=None):
    """Renvoie ``(arrivée ISO | None, départ ISO | None, infos)``.

    Aucune date n'est inventée : si l'hôte écrit « une semaine » sans dire
    quand, on renvoie ``(None, None)`` et l'agent redemandera la période.
    """
    reference = aujourdhui or dt.date.today()
    if isinstance(reference, str):
        try:
            reference = dt.date.fromisoformat(reference[:10])
        except ValueError:
            reference = dt.date.today()
    t = _preparer(texte)
    entrees = []

    # 1. Dates ISO : 2026-12-01
    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t):
        _ajouter(entrees, m.start(), m.end(), int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # 2. Dates numériques : 12/10 ou 12/10/2026
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t):
        annee = None
        if m.group(3):
            annee = int(m.group(3))
            if annee < 100:
                annee += 2000
        _ajouter(entrees, m.start(), m.end(), int(m.group(1)), int(m.group(2)), annee)

    # 3. Jour + mois en toutes lettres : 12 octobre, 3 mars
    for m in re.finditer(r"\b(\d{1,2})(?:er|eme)?\s+(" + MOIS_RE + r")\b", t):
        _ajouter(entrees, m.start(), m.end(), int(m.group(1)), MOIS[m.group(2)], None)

    # 4. Jour seul introduit par « du », « le », « au » : du 12 au 15 octobre
    for m in re.finditer(r"\b(?:du|le|des|vers le|a partir du|a compter du)\s+(\d{1,2})\b", t):
        _ajouter(entrees, m.start(), m.end(), int(m.group(1)), None, None)

    # 5. Premier jour d'un intervalle : « 12 au 15 octobre »
    for m in re.finditer(r"\b(\d{1,2})\s+au\b", t):
        _ajouter(entrees, m.start(), m.end(), int(m.group(1)), None, None)

    entrees.sort(key=lambda e: e["debut"])
    if not entrees:
        return None, None, {"nuits": 0, "duree_jours": None}

    # Le mois manquant se prend sur la mention la plus proche.
    avec_mois = [e for e in entrees if e["mois"]]
    if not avec_mois:
        return None, None, {"nuits": 0, "duree_jours": None}
    for e in entrees:
        if not e["mois"]:
            proche = min(avec_mois, key=lambda x: abs(x["debut"] - e["debut"]))
            e["mois"] = proche["mois"]

    arrivee = _dater(entrees[0], reference)
    depart = None
    if len(entrees) > 1:
        depart = _dater(entrees[1], reference, apres=arrivee)
    if arrivee and depart is None:
        duree = _duree(texte)
        if duree:
            depart = arrivee + dt.timedelta(days=duree)
    if arrivee and depart and depart <= arrivee:
        depart = None

    infos = {
        "nuits": (depart - arrivee).days if (arrivee and depart) else 0,
        "duree_jours": _duree(texte),
        "arrivee": arrivee.isoformat() if arrivee else None,
        "depart": depart.isoformat() if depart else None,
    }
    return infos["arrivee"], infos["depart"], infos


# ===========================================================================
# IDENTITÉ, PROVENANCE, COMPOSITION, BESOINS
# ===========================================================================
def extraire_identite(texte: str, attendu: bool = False):
    """Renvoie ``(nom, prénom)``, dans cet ordre — comme l'état civil."""
    t = _preparer(texte)
    if not t:
        return "", ""
    candidat = ""
    m = re.search(r"(?:je m appelle|je me nomme|mon nom est|moi c est|c est|je suis)\s+(.+)$", t)
    if m:
        candidat = m.group(1)
    elif attendu:
        candidat = t
    if not candidat:
        return "", ""

    candidat = candidat.strip(" .,;!?")
    # On ne prend pas la suite d'une phrase : « Aya Koffi d'Abidjan » → « Aya Koffi »
    morceaux = re.split(r"\b(?:d|de|du|des|a|au|aux|en|depuis|pour|avec|et|qui|que)\b", candidat)
    morceaux = [x.strip() for x in morceaux if x.strip()]
    candidat = morceaux[0] if morceaux else ""

    jetons = [j for j in re.split(r"[^a-z]+", candidat) if j]
    if any(j in VERBES_REFUS for j in jetons):
        return "", ""
    retenus = []
    for j in jetons:
        if len(j) < 2 or j in MOTS_VIDES or j.isdigit():
            continue
        retenus.append(j)
    if not retenus or len(retenus) > 3:
        return "", ""
    if len(retenus) == 1:
        return _restaurer(retenus[0], texte), ""
    return _restaurer(retenus[-1], texte), _restaurer(retenus[0], texte)


def extraire_provenance(texte: str, attendu: bool = False) -> str:
    """« Je viens d'Abidjan », « j'habite à Bouaké », ou simplement « Abidjan »."""
    brut = texte or ""
    t = _preparer(brut)
    if not t:
        return ""
    # Le pays est un cas à part : « Côte d'Ivoire » ne doit pas finir en « Ivoire ».
    if re.search(r"\bivoire\b", t):
        return "Côte d'Ivoire"
    candidat = ""
    m = re.search(r"(?:je viens|nous venons|j arrive|nous arrivons|je suis|nous sommes"
                  r"|j habite|nous habitons|je reside|nous residons|originaire)\s+(.+)$", t)
    if m:
        candidat = m.group(1)
    else:
        # Une ville écrite avec une majuscule après « de », « d' », « depuis ».
        m2 = re.search(r"\b(?:d'|de |du |des |depuis )([A-Z\u00c0-\u017f][\w\u00c0-\u017f'\-]+"
                       r"(?:\s+[A-Z\u00c0-\u017f][\w\u00c0-\u017f'\-]+)?)", brut)
        if m2:
            return _restaurer(_preparer(m2.group(1)).strip(), m2.group(1))
        if attendu:
            candidat = t
    if not candidat:
        return ""

    candidat = candidat.strip(" .,;!?")
    # On reste dans la première proposition : « je suis Aya Koffi d'Abidjan,
    # je voudrais venir… » ne doit pas transformer la suite en ville.
    candidat = candidat.split(",")[0].strip()
    morceaux = re.split(r"\b(?:d|de|du|des|depuis|a|au|aux|en|pour|avec|et|qui|que)\b", candidat)
    morceaux = [x.strip() for x in morceaux if x.strip()]
    candidat = morceaux[-1] if morceaux else ""
    jetons = [j for j in re.split(r"[^a-z]+", candidat) if j]
    retenus = []
    for j in jetons:
        if len(j) < 2 or j in MOTS_VIDES or j.isdigit():
            break
        retenus.append(j)
    if not retenus or len(retenus) > 4:
        return ""
    return _restaurer_expression(retenus, brut)


def extraire_nombre_personnes(texte: str):
    """Renvoie un entier, ou ``None`` si l'hôte ne l'a pas dit."""
    t = _preparer(texte)
    if not t:
        return None
    if re.search(r"\b(seul|seule|tout seul|toute seule|moi seul|moi seule)\b", t):
        return 1
    if re.search(r"\bun couple\b|\bnous sommes deux\b|\bnous deux\b|\bmon epouse\b"
                 r"|\bmon mari\b|\bma femme\b|\bma femme et moi\b", t):
        return 2
    m = re.search(r"\b(\d{1,3}|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix"
                  r"|onze|douze|treize|quatorze|quinze|seize|vingt)\s*"
                  r"(?:personnes?|pax|hotes?|adultes?|participants?|membres?"
                  r"|eleves?|etudiants?|retraitants?|places?)\b", t)
    if m:
        valeur = m.group(1)
        return int(valeur) if valeur.isdigit() else NOMBRES.get(valeur)
    # « pour deux », « nous serons trois » : le nombre sans le mot « personne ».
    m = re.search(r"\b(?:pour|nous serons|on sera|serons)\s+"
                  r"(\d{1,3}|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix"
                  r"|onze|douze|quinze|vingt)\b(?!\s*(?:nuits?|jours?|semaines?|mois))", t)
    if m:
        valeur = m.group(1)
        return int(valeur) if valeur.isdigit() else NOMBRES.get(valeur)
    m = re.search(r"\b(?:groupe|equipe|paroisse|delegation|nous sommes|on sera|nous serons"
                  r"|on est|nous etions|serons)\s+(?:de\s+|a\s+)?([a-z]+|\d{1,3})\b", t)
    if m:
        valeur = m.group(1)
        if valeur.isdigit():
            return int(valeur)
        if valeur in NOMBRES:
            return NOMBRES[valeur]
    return None


def extraire_repartition(texte: str):
    """Renvoie ``(hommes, femmes)``; ``(0, 0)`` si l'hôte ne l'a pas dit."""
    t = _preparer(texte)
    h = re.search(r"(\d{1,3}|[a-z]+)\s*hommes?\b", t)
    f = re.search(r"(\d{1,3}|[a-z]+)\s*femmes?\b", t)

    def valeur(m):
        if not m:
            return 0
        x = m.group(1)
        return int(x) if x.isdigit() else NOMBRES.get(x, 0)
    return valeur(h), valeur(f)


def extraire_besoins(texte: str) -> dict:
    """Régime, accessibilité, offices, première visite.

    ``vide`` vaut True quand l'hôte a explicitement répondu qu il n'avait
    aucun besoin : c'est une information, pas une absence de réponse.
    """
    t = _preparer(texte)
    besoins = {"regime": "", "accessibilite": "", "participation_offices": "",
               "premiere_visite": None, "vide": False, "note": ""}
    if not t:
        return besoins

    regimes = []
    if re.search(r"vegetarien|vegetarienne|veggie|sans viande|pas de viande", t):
        regimes.append("végétarien")
    if re.search(r"sans porc|pas de porc", t):
        regimes.append("sans porc")
    if re.search(r"halal", t):
        regimes.append("halal")
    if re.search(r"sans gluten", t):
        regimes.append("sans gluten")
    if re.search(r"allergi", t):
        regimes.append("allergie (à préciser)")
    if re.search(r"diabet", t):
        regimes.append("diabète")
    besoins["regime"] = ", ".join(regimes)

    acces = []
    if re.search(r"fauteuil roulant|mobilite reduite|handicap|pmr|difficulte a marcher"
                 r"|escalier|ascenseur|rez de chaussee", t):
        acces.append("mobilité réduite")
    if re.search(r"malvoyant|aveugle|malentendant|sourd", t):
        acces.append("handicap sensoriel")
    besoins["accessibilite"] = ", ".join(acces)

    if re.search(r"participer aux offices|aux offices|suivre les offices|prier avec", t):
        besoins["participation_offices"] = "souhaite participer"
    if re.search(r"premiere fois|jamais venu|premier sejour", t):
        besoins["premiere_visite"] = True
    if re.search(r"rien de particulier|aucun besoin|pas de besoin|aucune demande"
                 r"|rien a signaler|rien de special|non rien|aucun|^non$|^rien$", t):
        besoins["vide"] = True
    return besoins


# ===========================================================================
# INTENTIONS
# ===========================================================================
def est_demande_sejour(texte: str) -> bool:
    t = _preparer(texte)
    if not t:
        return False
    if re.search(r"\b(savoir|renseignement|renseignements|information|informations|connaitre)\b", t) \
            and not re.search(r"\b(venir|sejourner|reserver|dormir|preparer|organiser)\b", t):
        return False
    if re.search(r"\b(preparer|organiser)\s+(?:une\s+|un\s+|mon\s+|notre\s+)?"
                 r"(retraite|sejour|venue|session|temps)\b", t):
        return True
    if re.search(r"\b(venir en retraite|faire une retraite|venir pour une retraite|retraite spirituelle)\b", t):
        return True
    if re.search(r"\b(reserver|reservation|demande de sejour|disponibilite|une chambre libre"
                 r"|cherche une chambre|cherchons une chambre)\b", t):
        return True
    return bool(re.search(
        r"\b(je voudrais|je veux|nous voudrions|nous voulons|je souhaite|nous souhaitons"
        r"|j aimerais|nous aimerions|je desire|nous desirons|on voudrait)\b"
        r".{0,60}\b(venir|sejourner|rester|dormir|passer|etre accueilli|loger)\b", t))


def est_une_question(texte: str) -> bool:
    t = _preparer(texte)
    if not t:
        return False
    if "?" in (texte or ""):
        return True
    if re.match(r"^(quel|quelle|quels|quelles|comment|combien|ou|quand|pourquoi|qui|que|quoi"
                r"|est ce|y a t il|avez vous|peut on|puis je|savez vous|pouvez vous|est il|est elle)\b", t):
        return True
    return bool(re.search(r"(je voudrais savoir|je voudrais des renseignements|j aimerais savoir"
                          r"|pouvez vous me dire|je me demande|dites moi)\b", t))


def extraire_type_sejour(texte: str) -> str:
    t = _preparer(texte)
    if re.search(r"\b(retraite|retraitant|spirituel|recollection|silence)\b", t):
        return "retraite"
    if re.search(r"\bdiscernement|vocation\b", t):
        return "discernement"
    if re.search(r"\b(groupe|session|paroisse|mouvement|association|delegation|equipe|seminaire)\b", t):
        return "groupe"
    if re.search(r"\b(couple|epouse|epoux|mari|femme|fianc)", t):
        return "couple"
    if re.search(r"\b(travail|mission|chantier|stage|professionnel|affaires)\b", t):
        return "travail"
    if re.search(r"\b(repos|reposer|vacances|detente|souffler|ressourcement)\b", t):
        return "repos"
    return ""


def est_urgence(texte: str) -> bool:
    t = _preparer(texte)
    return bool(re.search(
        r"\b(urgent|urgence|malade|maladie|accident|hopital|hospitalise|secours|samu"
        r"|pompiers|blesse|blessee|saigne|inconscient|mourir|mourant|deces|decde"
        r"|tres mal|grave|danger)\b", t))


def demande_humain(texte: str) -> bool:
    t = _preparer(texte)
    return bool(re.search(
        r"(parler a un (pere|frere|moine)|parler avec un (pere|frere|moine)"
        r"|parler aux (peres|freres|moines)|parler avec les (peres|freres)"
        r"|joindre un (pere|frere|moine)|joindre les (peres|freres)"
        r"|un (pere|frere) peut|etre rappele|qu on me rappelle"
        r"|rappeler|appeler les freres|contacter les freres|un humain|une personne reelle"
        r"|le pere prieur|le pere abbe|voir un pretre|voir un frere|parler a quelqu un)", t))


def est_confirmation(texte: str) -> bool:
    t = _preparer(texte).strip(" .!?")
    return bool(re.match(
        r"^(oui|ouais|exact|exactement|c est exact|c est bien cela|c est cela|tout a fait"
        r"|parfait|d accord|je confirme|confirme|oui merci|oui c est bien|oui c est exact"
        r"|c est juste|correct|valider|valide|ok|okay)\b", t))


def est_negation(texte: str) -> bool:
    t = _preparer(texte).strip(" .!?")
    if re.match(r"^(non|pas|plutot non)\b", t):
        return True
    return bool(re.search(r"(pas exactement|pas tout a fait|il y a une erreur|ce n est pas"
                          r"|corriger|correction|une erreur|pas ca|pas cela)", t))


def est_salutation(texte: str) -> bool:
    t = _preparer(texte).strip(" .!?")
    return bool(re.match(r"^(bonjour|bonsoir|salut|coucou|hello|pax|akwaba|shalom|bonne journee"
                         r"|bonne soiree)\b", t))


def extraire_annulation(texte: str) -> bool:
    t = _preparer(texte)
    return bool(re.search(r"\b(annuler|annulation|je ne peux plus venir|je ne viendrai pas"
                          r"|finalement pas|renoncer|desister)\b", t))


def extraire_telephone(texte: str) -> str:
    m = re.search(r"(?:\+?225[\s.-]?)?(\d[\d\s.-]{7,14}\d)", texte or "")
    if not m:
        return ""
    chiffres = re.sub(r"\D", "", m.group(0))
    if len(chiffres) < 8:
        return ""
    return chiffres


def extraire_email(texte: str) -> str:
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", texte or "")
    return m.group(0) if m else ""
