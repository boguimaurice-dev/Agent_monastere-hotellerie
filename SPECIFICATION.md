# Cahier des charges — Hôtellerie & Accueil
## Monastère Bénédictin Sainte-Marie de Bouaké

> **Document de référence.**
> Décrit ce qui a été construit, pourquoi, comment, et ce qui reste entre les
> mains de la communauté. À remettre à tout développeur, intégrateur ou outil
> de génération (Lovable, n8n…) qui reprendrait le projet.

**Version** 1.0 · **Date** 30 septembre 2026 · **Périmètre** Hôtellerie & Accueil (pôle 1 de 4)

---

## 1. Objet

Le monastère accueille des retraitants, des groupes et des personnes en
mission de travail. Les demandes arrivent par téléphone, par WhatsApp et par
courriel, à des heures où les frères sont à l'office, au travail ou au
silence. Des demandes se perdent ; des hôtes rappellent trois fois ; des
renseignements simples (horaires des offices, itinéraire depuis Abidjan)
mobilisent un frère alors qu'une réponse écrite suffirait.

L'objet du système est double :

1. **Ne laisser aucun hôte sans réponse** — un accueil écrit, chaleureux et
   fidèle à l'esprit bénédictin, disponible à toute heure.
2. **Ne retirer aux frères aucun discernement** — l'agent recueille, il ne
   décide pas. Chaque demande remonte sous forme de fiche lisible ; la
   décision d'accueillir reste à la communauté.

---

## 2. Principes de conception

Ces principes ont guidé chaque choix technique. Ils sont opposables : toute
évolution du système doit les respecter.

### 2.1 Principes pastoraux

| # | Principe | Traduction technique |
|---|---|---|
| P1 | **L'hôte est reçu comme le Christ** | Le premier message est une bénédiction, pas un menu. Aucune formule commerciale, aucun emoji superflu. |
| P2 | **Le discernement appartient aux frères** | L'agent ne confirme jamais une réservation. Statuts, validation et attribution sont des actes humains. |
| P3 | **Rien ne sera préféré à la vérité** | Interdiction absolue d'inventer un prix, un horaire, une disponibilité, un nom. L'ignorance est exprimée et transmise. |
| P4 | **L'attention est la première hospitalité** | On ne redemande jamais ce que l'hôte a déjà dit. On n'insiste pas plus de deux fois. |
| P5 | **La maison garde la main sur sa parole** | Ce que l'agent dit est rédigé par les frères, dans la base de connaissances, et modifiable à tout moment sans redéploiement. |

### 2.2 Vérification continue

Un jeu de **79 vérifications automatiques** (`python3 tests.py`) couvre ce qui
ne doit jamais se dérégler : la compréhension du français des hôtes (dates,
noms, nombres), la conduite du dialogue de bout en bout, les garde-fous (aucun
prix inventé, aucune consigne interne divulguée, urgence traitée, silence après
relais humain), le calcul des disponibilités, la sécurité et le webhook.

Elles s'exécutent sur une base temporaire, sans jamais toucher aux données
réelles. À relancer après toute modification de la base de connaissances ou du
moteur.

### 2.3 Principes techniques

| # | Principe | Conséquence |
|---|---|---|
| T1 | **Aucune dépendance externe** | Bibliothèque standard Python uniquement. Pas de `pip install`, pas de chaîne de mise à jour à maintenir. |
| T2 | **Dégradation gracieuse** | Sans clé d'API, sans WhatsApp, sans SMTP, sans réseau : l'application continue de fonctionner. Chaque service externe est un supplément, jamais un prérequis. |
| T3 | **Données locales et portables** | Un seul fichier SQLite. Sauvegarde = copie. Restauration = copie. |
| T4 | **Prévisibilité avant éloquence** | Le cœur (collecte, disponibilités, enregistrement) est déterministe. Le modèle de langage ne fait que formuler. |
| T5 | **Transparence** | Journal de toutes les actions, historique complet des échanges, journal des notifications avec motif d'échec. |

---

## 3. Périmètre

### 3.1 Dans le périmètre de la version 1

- Agent d'accueil conversationnel en français (WhatsApp, web, API)
- Base de connaissances monastique éditable par les frères
- Qualification et enregistrement des demandes de séjour
- Vérification des disponibilités sur la période demandée
- Relais automatique de la fiche de synthèse (courriel + WhatsApp + tableau de bord)
- Détection des urgences et relais immédiat vers un frère
- Tableau de bord : demandes, discernement, attribution des chambres, calendrier
  d'occupation, chambres et indisponibilités, notifications, journal
- Saisie manuelle d'une demande (téléphone, guichet, courriel)
- Export CSV des demandes
- Webhook WhatsApp Cloud API, prêt à brancher
- API JSON pour intégration au site web ou à un outil tiers

### 3.2 Hors périmètre de la version 1

- Paiement en ligne (l'offrande est libre et se règle sur place)
- Réservation en libre-service avec confirmation automatique (contraire à P2)
- Gestion des trois autres pôles (voir §12)
- Application mobile native
- Envoi de messages vocaux, images ou pièces jointes par l'agent

---

## 4. Acteurs

| Acteur | Rôle | Usage |
|---|---|---|
| **L'hôte** | Demande un renseignement ou un séjour | WhatsApp, site web, téléphone, courriel |
| **Le frère hôtelier** | Reçoit les fiches, discerne, attribue les chambres | Tableau de bord |
| **Le Père Prieur** | Supervision, arbitrage | Tableau de bord (lecture et décision) |
| **L'administrateur** | Comptes, paramètres, sauvegardes | Tableau de bord, ligne de commande |

Trois rôles sont prévus : `hotelier`, `prieur`, `admin`.

---

## 5. Fonctionnalités

### 5.1 Agent d'accueil

| Réf. | Fonction | Comportement |
|---|---|---|
| FA-1 | Salutation | « Pax. Bienvenue à l'hôtellerie du Monastère Sainte-Marie… » |
| FA-2 | Question pratique | Réponse issue de la base de connaissances, puis invitation à préparer une demande |
| FA-3 | Question hors base | Reconnaît son ignorance, transmet aux frères, donne le numéro de l'hôtellerie |
| FA-4 | Qualification du séjour | Identité, provenance, nature, dates, composition, besoins — une question à la fois |
| FA-5 | Compréhension du français courant | « du 12 au 15 octobre », « on sera quatre », « je viens d'Abidjan », « seul » |
| FA-6 | Récapitulatif | Présente la demande, demande confirmation, accepte les corrections |
| FA-7 | Transmission | Enregistre, notifie les frères, donne à l'hôte un délai honnête (24-48 h) et la référence du dossier |
| FA-8 | Urgence | Détection, orientation vers les secours et l'accueil, alerte immédiate des frères |
| FA-9 | Demande d'un frère | Relais humain, puis silence de l'agent |
| FA-10 | Non-insistance | Deux relances au maximum ; au-delà, transmission d'un dossier partiel |
| FA-11 | Annulation | Retrait de la demande, porte laissée ouverte |
| FA-12 | Demande inachevée | Création automatique d'un dossier dès le premier élément utile, visible par les frères |

### 5.2 Tableau de bord

| Réf. | Écran | Contenu |
|---|---|---|
| FB-1 | Tableau de bord | Statistiques du jour, alertes, demandes en attente, arrivées du jour, état du système |
| FB-2 | Demandes | Liste filtrable par statut et recherche libre |
| FB-3 | Fiche demande | Toutes les informations, disponibilité calculée, historique de l'échange, réponse à l'hôte, décision, attribution de chambre, notes internes, notifications |
| FB-4 | Occupation | Calendrier mensuel chambre × jour, arrivées/départs, chambres et indisponibilités |
| FB-5 | Base de connaissances | Liste, recherche, création, édition, import/export JSON, fiches à compléter |
| FB-6 | Simulateur | Essai de l'agent sans aucun envoi réel |
| FB-7 | Échanges | Toutes les conversations, données recueillies, reprise en main par un frère |
| FB-8 | Notifications | Journal des transmissions, avec motif d'échec |
| FB-9 | Journal | Traçabilité des actions |
| FB-10 | Paramètres | Agent, WhatsApp, courriel, module de langage, règles de la maison, sécurité |
| FB-11 | Saisie manuelle | Demande reçue par téléphone, courriel ou au portail |
| FB-12 | Export | CSV des demandes, JSON de la base de connaissances |

---

## 6. Scénarios validés

Ces échanges ont été réellement exécutés sur le système livré (mode
déterministe, sans module de langage).

### 6.1 Demande complète, informations données au fil de l'eau

```
HÔTE   Bonjour
AGENT  Pax. Bienvenue à l'hôtellerie du Monastère Sainte-Marie de Bouaké.
       Que la paix soit avec vous.
       Je suis le frère hôtelier numérique du monastère. Comment puis-je vous
       aider aujourd'hui ? Souhaitez-vous un renseignement, ou préparer une
       demande de séjour ?

HÔTE   Je voudrais venir en retraite
AGENT  Bien volontiers. Pour que je puisse préparer votre venue, puis-je vous
       demander votre nom et votre prénom ?

HÔTE   Jean Kouassi
AGENT  Enchanté, Jean. D'où nous écrivez-vous ? Cela nous aide à vous indiquer
       le meilleur trajet.

HÔTE   Abidjan
AGENT  C'est noté. Quelle période envisagez-vous ? Indiquez-moi la date
       d'arrivée et celle du départ, même approximativement.

HÔTE   du 12 au 15 octobre
AGENT  Du 12 octobre 2026 au 15 octobre 2026, c'est noté — 3 nuits.
       Combien de personnes serez-vous ?

HÔTE   seul
AGENT  Bien noté. Y a-t-il des besoins particuliers à prévoir — un régime
       alimentaire, une difficulté de déplacement, ou un souhait quant à la
       participation aux offices ? Un simple « rien de particulier » me
       convient très bien.

HÔTE   rien de particulier
AGENT  J'ai bien noté votre demande :
       • Hôte : Jean Kouassi
       • Provenance : Abidjan
       • Nature du séjour : Retraite spirituelle individuelle
       • Période : du 12 octobre 2026 au 15 octobre 2026 — 3 nuits
       • Composition : 1 personne
       • Besoins particuliers : aucun
       Est-ce bien cela ?

HÔTE   oui
AGENT  Votre demande a bien été recueillie avec soin. Je la transmets
       immédiatement aux pères et frères responsables de l'hôtellerie.
       Ils examineront les disponibilités dans le calme et vous répondront
       directement, en général dans les 24 à 48 heures, pour confirmer votre
       venue.
       Que Dieu vous garde.
       Votre demande porte la référence H-2026-0007.
```

### 6.2 Demande complète en un seul message

```
HÔTE   Bonjour, je suis Aya Koffi d'Abidjan, je voudrais venir avec mon groupe
       de 8 personnes du 3 au 7 novembre pour une session, deux sont
       végétariennes

AGENT  J'ai bien noté votre demande :
       • Hôte : Aya Koffi
       • Provenance : Abidjan
       • Nature du séjour : Groupe ou session
       • Période : du 3 novembre 2026 au 7 novembre 2026 — 4 nuits
       • Composition : 8 personnes
       • Besoins particuliers : végétarien
       Est-ce bien cela ?
```

Aucune information déjà donnée n'est redemandée : c'est la traduction
concrète du principe P4.

### 6.3 Question pratique

```
HÔTE   Quels sont les horaires des offices ?
AGENT  [réponse complète, semaine et dimanche, issue de la base]
       Souhaitez-vous que je prépare votre demande de séjour ?

HÔTE   Combien coûte une nuit ?
AGENT  L'hospitalité bénédictine est un don : vous n'êtes pas ici dans un
       hôtel. Une offrande libre est laissée à votre appréciation…
       Si le cœur vous en dit, je peux préparer votre venue tout de suite.
```

### 6.4 Question hors de la base — le cas le plus révélateur

```
HÔTE   Quelle est la capitale du Burkina Faso ?
AGENT  Je n'ai pas la réponse exacte à cette question dans ce que la maison
       m'a confié, et je ne veux rien vous dire d'inexact.
       Je transmets votre question aux frères : ils vous répondront
       directement. Vous pouvez aussi appeler l'hôtellerie au 07 97 00 80 52.
       Souhaitez-vous autre chose entre-temps ?
```

L'agent ne comble pas le silence par une invention. Il avoue, et il transmet.

---

## 7. Architecture

### 7.1 Vue d'ensemble

```
┌──────────────┐   WhatsApp Cloud API    ┌──────────────────────────┐
│  Hôte        │◄───────────────────────►│  /webhook/whatsapp       │
│  (téléphone) │        messages         │                          │
└──────────────┘                         │   ┌──────────────────┐   │
                                         │   │  Moteur (engine) │   │
┌──────────────┐   HTTPS                 │   │  • intentions    │   │
│  Site web    │────────────────────────►│   │  • collecte      │   │
│  n8n, autres │        /api/agent       │   │  • outils        │   │
└──────────────┘                         │   └────────┬─────────┘   │
                                         │            │             │
┌──────────────┐   HTTPS                 │   ┌────────▼─────────┐   │
│  Frères      │────────────────────────►│   │  Base SQLite     │   │
│  (navigateur)│     tableau de bord     │   │  Connaissances   │   │
└──────────────┘                         │   └────────┬─────────┘   │
                                         │            │             │
                                         │   ┌────────▼─────────┐   │
                                         │   │  Relais          │──► courriel
                                         │   │  (notify)        │──► WhatsApp frères
                                         │   └──────────────────┘   │
                                         └──────────────────────────┘
```

### 7.2 Séparation des responsabilités

| Couche | Rôle | Ne fait jamais |
|---|---|---|
| `comprehension.py` | Comprendre le français de l'hôte (dates, nombres, noms, besoins) | Décider de quoi que ce soit |
| `engine.py` | Conduire le dialogue, ordonner la collecte, appeler les outils | Inventer une donnée |
| `knowledge.py` | Retrouver la fiche pertinente | Rédiger à la place des frères |
| `metier.py` | Calculer les disponibilités, enregistrer les demandes | Supposer une capacité non déclarée |
| `notify.py` | Rédiger et transmettre la fiche aux frères | Répondre à l'hôte à la place des frères |
| `llm.py` | Formuler, si une clé est fournie | Piloter le dialogue |

Cette séparation est ce qui rend le module de langage optionnel : il n'est
qu'une couche de formulation posée sur un noyau déterministe.

### 7.3 Flux d'un message entrant

1. Réception (webhook WhatsApp, API, ou simulateur)
2. Journalisation du message entrant
3. Si un frère a pris la main → silence de l'agent
4. Détection d'urgence → alerte immédiate, puis relais humain
5. Demande expresse d'un frère → relais humain
6. Remerciement, annulation → réponses dédiées
7. Confirmation en cours (oui/non/correction) → enregistrement ou reprise
8. Question → recherche dans la base de connaissances, réponse, reprise
9. Sinon → collecte : extraction, enregistrement incrémental, question suivante
10. Journalisation de la réponse sortante (une seule fois)
11. Envoi sur le canal

### 7.4 Disponibilité : la règle de calcul

Une chambre est occupée sur une période `[arrivée, départ[` si une demande
ayant le statut **acceptée** ou **confirmée** (chambre attribuée), ou un
blocage déclaré (travaux, fermeture), chevauche cet intervalle.

Le jour de départ est libéré : un hôte qui part le 15 laisse la chambre
disponible dès le 15 au matin.

L'agent n'annonce jamais « il y a de la place » de lui-même : il transmet la
disponibilité **aux frères** dans la fiche de synthèse. La capacité affichée
dans le tableau de bord les aide à discerner.

---

## 8. Modèle de données

Neuf tables. Résumé :

| Table | Rôle | Champs notables |
|---|---|---|
| `chambres` | Le parc d'hébergement | nom, capacité, type, aile, accès PMR, active |
| `demandes` | Les demandes de séjour | référence, statut, identité, dates, composition, besoins, chambre |
| `conversations` | L'état du dialogue par fil | état, données recueillies (JSON), relais humain |
| `messages` | L'historique complet | direction, canal, corps, intention détectée |
| `blocages` | Indisponibilités déclarées | chambre, période, motif |
| `notifications` | Le journal des transmissions | canal, destinataire, statut, erreur |
| `envois` | La file d'attente WhatsApp | numéro, corps, statut, tentatives, erreur |
| `connaissances` | La base de connaissances | clé, catégorie, question, mots-clés, réponse, priorité |
| `utilisateurs`, `sessions`, `tentatives` | Comptes et sécurité | — |
| `parametres` | Configuration éditable | clé / valeur |
| `journal` | Traçabilité | acteur, action, objet, détails |

### Statuts d'une demande

| Statut | Signification | Compte dans l'occupation |
|---|---|---|
| `en_attente` | En attente de discernement | non |
| `acceptee` | Acceptée par les frères | **oui** |
| `confirmee` | Chambre attribuée | **oui** |
| `refusee` | Refusée | non |
| `annulee` | Annulée par l'hôte | non |
| `sejour_termine` | Séjour terminé | non |

### Natures de séjour

Retraite individuelle · Temps de repos · Couple · Groupe ou session ·
Mission de travail · Discernement vocationnel · Autre

---

## 9. La base de connaissances

C'est le véritable « cerveau » du système, et sa partie la plus précieuse :
elle contient la parole de la maison.

### 9.1 Contenu livré

36 fiches, réparties en 14 catégories, rédigées à partir des informations
publiques du site **benedictinsbouake.com** :

- **L'accueil** — présentation de l'hôtellerie, esprit bénédictin
- **Les offices** — horaires semaine et dimanche, participation
- **La vie de la communauté** — les frères, la journée, la lectio divina
- **Le séjour** — durée, chambres, repas, ce qu'il faut apporter
- **Les règles de la maison** — silence, clôture, tenue, tabac et alcool
- **L'offrande** — la participation financière
- **L'accès** — adresse, trajets depuis Abidjan et depuis Bouaké
- **Les contacts** — accueil, hôtellerie, boutique, urgences
- **La santé** — paludisme et précautions
- **Les groupes** — sessions et capacité
- **La vocation** — devenir moine, oblature
- **Le Studium** — formation philosophique et théologique
- **La boutique** — les produits du travail des mains
- **Divers** — données personnelles, climat, soutien, « Pax »

### 9.2 Le mécanisme « À compléter »

**17 fiches** contiennent une mention `[[À COMPLÉTER …]]`.

C'est un dispositif délibéré. Lorsqu'une information n'est pas publique —
l'offrande conseillée, l'heure de fermeture du portail, la capacité d'accueil
d'un groupe, l'âge minimum des enfants — le système refuse de la deviner. Il
enregistre le blanc, le signale aux frères dans le tableau de bord, et
l'agent, face à la question de l'hôte, répond qu'il transmet.

La mention n'est **jamais** montrée à l'hôte : elle est retirée avant l'envoi.
Le frère la voit, l'hôte ne la voit pas.

**Tant qu'une fiche reste à compléter, le système fonctionne : il est
simplement honnête à cet endroit-là.**

### 9.3 Recherche

La recherche est lexicale et pondérée, sans « embedding » ni appel réseau :

| Signal | Poids |
|---|---|
| Mot-clé déclaré, correspondance exacte | 3,0 |
| Mot présent dans la question de la fiche | 2,0 |
| Mot présent dans la catégorie | 1,0 |
| Mot présent dans le corps de la réponse | 0,4 |
| Expression entière retrouvée dans la question | 4,0 |
| Priorité éditoriale | 0,1 × priorité |

Seuil de pertinence : 2,2 en seconde passe, 3,0 en première.

Ce choix est volontaire : il est prévisible, gratuit, instantané, et il
fonctionne hors ligne. On sait toujours pourquoi une fiche a été choisie —
ce qui n'est pas le cas d'une recherche vectorielle.

### 9.4 Gouvernance

- Chaque fiche porte une **priorité** de 1 à 10 et peut être désactivée.
- Les frères créent et modifient les fiches sans toucher au code.
- Export et réimport JSON : la base de connaissances se sauvegarde et se
  transporte comme un simple fichier texte.
- Le fichier `base_connaissances.json` sert de socle ; la base de données est
  la source vivante.

---

## 10. La règle de vie de l'agent

Le comportement de l'agent est défini par un **prompt système** complet,
livré séparément dans **`PROMPT_AGENT.md`** afin de pouvoir être réutilisé
dans un autre outil (Lovable, n8n, un autre modèle).

Il fixe : l'identité (« frère hôtelier numérique »), la vocation, la manière
de parler (sobriété, brièveté, aucun emoji, vouvoiement), la liste de ce qui
est su, la liste — **la plus importante** — de ce qui n'est jamais fait, la
conduite de l'échange, et le rappel final.

> « Tu ne cherches pas à être impressionnant, ni à retenir la personne, ni à
> vendre quoi que ce soit. Tu cherches à ce que, lorsqu'elle referme la
> conversation, elle se dise : « Là-bas, on m'a écouté. » »

---

## 11. Intégrations

### 11.1 WhatsApp (Meta Cloud API)

| Sens | Mécanisme |
|---|---|
| Entrant | `POST /webhook/whatsapp` — vérification de signature `X-Hub-Signature-256` si `wa_app_secret` est renseigné |
| Sortant | `POST /{phone_number_id}/messages` — découpage automatique au-delà de 1 500 caractères, numérotation (1/2, 2/2) |
| Vérification | `GET /webhook/whatsapp?hub.mode=subscribe&hub.verify_token=…&hub.challenge=…` |
| Diagnostic | Écran « WhatsApp » : `GET /{phone_number_id}` chez Meta, erreurs traduites en français |
| File d'attente | Table `envois` : tout message est écrit avant l'envoi, rejouable sans perte |

Les messages non textuels (vocal, image) reçoivent une réponse polie invitant
à écrire, ou à appeler si c'est pressé. Les accusés de réception sont ignorés.

### 11.2 Courriel (SMTP)

Envoi de la fiche de synthèse au format texte et HTML, via `smtplib`.
Port 465 (SSL) ou 587 (STARTTLS). Gmail, OVH, Infomaniak ou le serveur du
diocèse conviennent.

### 11.3 API JSON

`POST /api/agent` avec `{"de": "+225…", "message": "…"}`, protégée par une
clé (`X-API-Key` ou `api_cle`). Permet de brancher le site web du monastère,
n8n, ou tout autre outil, sans dépendre de WhatsApp.

### 11.4 Ce qui se passe si rien n'est configuré

Rien n'est envoyé. Les fiches sont consignées dans la table `notifications`
avec le statut `ignore` et le motif. **Le système ne perd jamais une demande
à cause d'une configuration absente** — c'est le principe T2.

---

## 12. Sécurité et données personnelles

| Mesure | Détail |
|---|---|
| Mots de passe | PBKDF2-HMAC-SHA256, 100 000 itérations, sel aléatoire |
| Sessions | Jeton aléatoire de 40 octets, expiration (12 h), cookie `HttpOnly`, `SameSite=Lax`, `Secure` en HTTPS |
| CSRF | Jeton par session sur tous les formulaires ; rejet en 403 |
| Limitation | 6 tentatives de connexion, puis 15 minutes d'attente |
| Signature webhook | Vérification HMAC-SHA256 de chaque message entrant |
| En-têtes | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store` |
| Sortie HTML | Échappement systématique de toute donnée affichée |
| Requêtes | Paramètres liés en toute circonstance |

### Données des hôtes

Les informations recueillies (nom, provenance, téléphone, courriel, dates,
besoins alimentaires, accessibilité, intention) servent uniquement à
organiser le séjour. Elles sont conservées dans la base du monastère,
accessibles aux seuls comptes déclarés, jamais cédées.

Un hôte peut demander la consultation, la correction ou l'effacement de ses
données : la fiche de demande est supprimable depuis le tableau de bord.

**Un seul flux sortant existe** : si le module de langage est activé, le
contenu des messages est transmis au fournisseur d'API choisi pour produire la
réponse. Il est désactivé par défaut.

---

## 13. Exploitation

### Sauvegardes

Un fichier (`data/hotellerie.db`) + le dossier de l'application.
`python3 run.py sauvegarde` produit une copie datée. Une tâche planifiée
quotidienne, et **une copie conservée hors du monastère**, sont recommandées.

### Supervision

- `GET /sante` renvoie un JSON : état, heure, agent actif, WhatsApp configuré
- `data/logs/hotellerie.log` : toutes les requêtes et les erreurs
- « Notifications » : ce qui n'est pas parti, et pourquoi
- Écran « WhatsApp » : diagnostic du compte Meta et file d'attente (`envois`)
- « Journal » : qui a fait quoi

### Maintenance

Aucune mise à jour de dépendance : il n'y en a pas. La seule maintenance
courante est l'enrichissement de la base de connaissances, qui est un acte
pastoral, pas technique.

---

## 14. Plan de mise en œuvre

| Phase | Durée | Contenu | Responsable |
|---|---|---|---|
| **1. Installation** | 1 h | Serveur, initialisation, création des comptes | Administrateur |
| **2. Appropriation** | 2 h | Renommer les chambres, ajuster les capacités, parcourir les fiches | Frère hôtelier |
| **3. Complément** | 1 à 2 semaines | Remplir les 17 fiches « à compléter », au rythme de la maison | Communauté |
| **4. Essai** | 1 semaine | Simulateur, puis `run.py tester`, relecture par plusieurs frères | Frère hôtelier |
| **5. Branchement WhatsApp** | 2 h | Application Meta, jeton permanent, webhook HTTPS | Administrateur |
| **6. Mise en service** | 1 mois | Fonctionnement réel, ajustement des fiches selon les questions reçues | Communauté |
| **7. Bilan** | 1 h | Relire les échanges, corriger la base, décider de la suite | Père Prieur |

Le plus précieux se joue aux phases 3 et 6 : c'est là que la maison transmet
sa voix à l'agent, et que l'expérience réelle affine la base.

---

## 15. Feuille de route — les trois autres pôles

L'architecture a été conçue pour accueillir les autres services sans rien
réécrire : mêmes tables de base, même moteur, même tableau de bord, une base
de connaissances par pôle et un agent par métier.

### 15.1 Parc informatique et maintenance

| Table à ajouter | Contenu |
|---|---|
| `machines` | Registre : type, localisation, système, date d'achat, affectation |
| `interventions` | Pannes, diagnostics, pièces, résolutions, coût |
| `maintenances` | Entretiens préventifs planifiés et réalisés |

Agent associé : « frère sacristain du numérique ». Rôle : guider pas à pas
dans le diagnostic, consigner les pannes, rappeler les échéances d'entretien.

**Limite à garder en tête** : un agent ne répare pas un ordinateur, ne
rebranche pas un câble et ne configure pas un routeur physique. Il documente,
il guide, il alerte. La main reste humaine.

### 15.2 Stocks de provende et ferme

| Table à ajouter | Contenu |
|---|---|
| `articles` | Aliments, médicaments vétérinaires, emballages, produits de la boutique |
| `mouvements` | Entrées, sorties, inventaires, seuils d'alerte |
| `lots` | Bandes de pondeuses, suivi de production, mortalité, consommation |

Agent associé : « frère cellérier numérique ». Rôle : alerter avant la
rupture, consigner les mouvements, produire des situations mensuelles.

### 15.3 Centre de formation (Studium)

| Table à ajouter | Contenu |
|---|---|
| `etudiants` | Identité, communauté d'origine, parcours |
| `cours` | Modules, enseignants, calendrier |
| `inscriptions`, `notes` | Suivi académique, attestation, diplôme |

Agent associé : « frère économe des études ». Rôle : renseigner sur les
conditions d'admission, le calendrier, les frais ; transmettre les candidatures.

### 15.4 Le principe d'unification

Un socle commun (hôtes, utilisateurs, journal, notifications, paramètres) et
des pôles qui s'y greffent. Un seul tableau de bord, une seule sauvegarde, une
seule formation à faire. C'est la réponse à l'éparpillement des outils actuels.

---

## 16. Risques et limites

| Risque | Gravité | Traitement |
|---|---|---|
| L'agent répond à côté d'une fiche mal rédigée | Moyenne | Relecture par les frères, simulateur, historique complet |
| Dépendance à la connexion Internet (WhatsApp) | Moyenne | Fonctionnement complet hors ligne sauf envoi ; file d'attente en base |
| Une demande reste sans réponse si un frère oublie le tableau de bord | Moyenne | Alertes sur le tableau de bord, notification par courriel et WhatsApp, journal |
| Le numéro WhatsApp est déjà sur un téléphone | Faible | Migration Meta prévue, à planifier avec les frères |
| Un hôte attend une confirmation que l'agent ne donne pas | Faible | C'est le comportement voulu (P2) ; le message le dit clairement |
| Coût du module de langage, s'il est activé | Faible | Désactivé par défaut ; plafonnable ; l'agent fonctionne sans |

---

## 17. Ce que la communauté doit faire

Checklist de mise en service.

- [ ] Renommer les chambres et ajuster les capacités (Occupation)
- [ ] Renseigner les numéros et courriels des frères hôteliers (Paramètres)
- [ ] Compléter les 17 fiches « À compléter » (Base de connaissances)
- [ ] Relire les 36 fiches : est-ce bien la voix de la maison ?
- [ ] Configurer le SMTP, ou décider de s'en passer
- [ ] Essayer l'agent dans le simulateur, à plusieurs
- [ ] Créer l'application Meta et brancher le numéro 07 97 00 80 52
- [ ] Programmer une sauvegarde quotidienne, dont une copie hors du monastère
- [ ] Changer les mots de passe par défaut après la première connexion
- [ ] Décider, après un mois, de l'activation du module de langage

---

## 18. Annexes

### 18.1 Variables de configuration

Une variable d'environnement l'emporte toujours sur la base de données.

| Variable | Rôle |
|---|---|
| `HOTELLERIE_DATA_DIR` | Emplacement de la base et des journaux |
| `PORT` | Port d'écoute (défaut 8080) |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `IA_CLE_API` | Clé du module de langage |
| `HOTELLERIE_API_CLE` | Clé de l'API JSON |
| `wa_token`, `wa_phone_number_id`, `wa_verify_token`, `wa_app_secret` | WhatsApp |
| `smtp_*`, `hoteliers_emails`, `hoteliers_whatsapp` | Relais vers les frères |

Le fichier `.env` est lu au démarrage (voir `.env.example`).

### 18.2 Endpoints

| Méthode | Chemin | Accès |
|---|---|---|
| GET | `/tableau-de-bord` | authentifié |
| GET/POST | `/demandes`, `/demandes/<id>`, `/demandes/nouveau` | authentifié |
| POST | `/demandes/<id>/statut`, `/chambre`, `/notes`, `/repondre`, `/notifier` | authentifié + CSRF |
| GET | `/demandes/export.csv` | authentifié |
| GET | `/calendrier` | authentifié |
| POST | `/chambres`, `/blocages` | authentifié + CSRF |
| GET/POST | `/connaissances`, `/connaissances/<id>` | authentifié + CSRF |
| GET | `/connaissances/export.json` | authentifié |
| GET/POST | `/simulateur` | authentifié + CSRF |
| GET | `/conversations`, `/conversations/<id>` | authentifié |
| GET | `/notifications`, `/journal`, `/parametres` | authentifié |
| GET/POST | `/whatsapp` | authentifié (+ CSRF pour les actions) |
| POST | `/whatsapp/enregistrer`, `/verifier`, `/tester`, `/rejouer` | authentifié + CSRF |
| GET/POST | `/connexion` | public |
| GET | `/sante` | public |
| GET/POST | `/webhook/whatsapp` | public (signature) |
| POST | `/api/agent` | clé API |

### 18.3 Prérequis de l'hébergement

- Python ≥ 3.8
- 256 Mo de mémoire vive, 1 Go de disque
- Une adresse publique en HTTPS pour le webhook WhatsApp (Caddy recommandé)

---

*Ce document accompagne une application livrée, testée et fonctionnelle.
Il est destiné à être relu par la communauté, corrigé, et transmis à quiconque
reprendrait le projet.*
