# Hôtellerie & Accueil — Monastère Bénédictin Sainte-Marie de Bouaké

Application d'accueil et de gestion de l'hôtellerie monastique :
un **agent d'accueil** qui reçoit les hôtes sur WhatsApp dans l'esprit de la
Règle de saint Benoît, et un **tableau de bord** où les pères et frères
responsables gardent la main sur le discernement.

> **État actuel :** prototype mono-établissement, pas encore validé pour la
> production ni pour un SaaS. Les coordonnées, horaires, règles, fiches et
> chambres doivent être confirmés par la communauté. Les tests locaux ne
> prouvent pas le fonctionnement des comptes Meta ou SMTP réels. Voir
> [ROADMAP_SAAS.md](ROADMAP_SAAS.md) avant toute mise en service.

> « Tous les hôtes qui se présentent seront reçus comme le Christ. »
> — Règle de saint Benoît, 53

---

## 1. Ce que fait l'application

| | |
|---|---|
| **L'agent d'accueil** | Peut répondre automatiquement lorsque le serveur et le canal fonctionnent, renseigne sur la maison (offices, accès, cadre de vie), recueille une demande de séjour avec douceur, et transmet une fiche de synthèse aux frères. |
| **Le tableau de bord** | Les frères consultent les demandes, discernent (accepter / refuser), attribuent une chambre, voient le calendrier d'occupation, répondent à l'hôte, et enrichissent la base de connaissances de l'agent. |
| **Le relais** | Chaque demande complète est inscrite dans le tableau de bord ; les notifications externes dépendent de leur configuration et de leur disponibilité. |
| **Le webhook WhatsApp** | Prêt à être branché sur le numéro **07 97 00 80 52** (Meta Cloud API). |

### Ce que l'agent ne fait jamais — c'est le point le plus important

Il ne confirme **jamais** une réservation : le discernement final appartient
aux frères. Il ne doit pas inventer de faits : ses réponses proviennent des fiches, qui
doivent être vérifiées par les frères. La recherche lexicale peut se tromper ;
lorsqu'un sujet n'est pas documenté, elle invite à contacter la maison.

---

## 2. Installation

### Prérequis

- Python **3.8 ou plus** (aucune bibliothèque à installer)
- Environ 5 Mo d'espace disque, et rien d'autre

L'application n'utilise que la **bibliothèque standard** : pas de `pip install`,
pas de dépendance à mettre à jour, pas de serveur de base de données à
administrer. Les données tiennent dans un seul fichier
(`data/hotellerie.db`) à sauvegarder avec `python3 run.py sauvegarde` (copie SQLite cohérente, même en mode WAL).

### Démarrage en trois commandes

```bash
cd monastere-hotellerie

python3 run.py initialiser --demo     # crée la base, les chambres, les fiches
python3 run.py utilisateur --login hotelier --nom "Frère Hôtelier"
python3 run.py servir                 # http://localhost:8080
```

`--demo` ajoute six demandes fictives, pour que le tableau de bord parle tout
de suite. **À ne pas faire en production.**

Pour visualiser l’interface sans installer de compte ni toucher aux données
réelles, lancez `python3 deploiement/apercu_demo.py`, puis ouvrez le port 8080.
Cet aperçu est public et sans authentification : sa base temporaire contient
des données fictives et est détruite à l’arrêt ; les envois externes sont
désactivés. N’y saisissez aucune donnée personnelle et ne l’utilisez jamais
comme serveur de production.

### Première chose à faire après l'installation

1. **Renommer les chambres** dans « Occupation ». Neuf chambres génériques
   ont été créées (« Chambre 1 »… « Dortoir ») : la disponibilité calculée par
   l'agent dépend directement de leur nombre et de leur capacité.
2. **Compléter les fiches de connaissance** dans « Base de connaissances »
   (menu « À compléter »). Dix-sept fiches contiennent encore une mention
   `[[À COMPLÉTER …]]` : offrande conseillée, horaires du portail, capacité
   d'accueil des groupes, enfants et animaux, etc.
   Lorsqu’une fiche est incomplète, l’agent indique que certains détails restent
   à confirmer. Vérifiez aussi les autres fiches : leur contenu n’est pas
   automatiquement validé et une recherche lexicale peut choisir la mauvaise fiche.

---

## 3. Ligne de commande

```bash
python3 run.py                        # installation si besoin, puis démarrage
python3 run.py servir --port 8080     # démarrer le serveur
python3 run.py initialiser [--demo]   # (ré)initialiser la base
python3 run.py utilisateur --login X  # créer ou modifier un compte
python3 run.py tester                 # dialoguer avec l'agent dans le terminal
python3 run.py whatsapp               # état du branchement WhatsApp
python3 run.py whatsapp --verifier    # interroger Meta sur le compte
python3 run.py whatsapp --envoyer "Pax. Essai" --numero 0151740187
python3 run.py whatsapp --rejouer     # rejouer la file d'attente
python3 run.py importer [--ecraser]   # réimporter base_connaissances.json
python3 run.py sauvegarde [dossier]   # copier la base avec la date du jour
python3 run.py secret                 # générer un secret aléatoire
```

`python3 run.py tester` est le moyen le plus simple d'éprouver l'agent avant
de le brancher sur WhatsApp. Aucun message n'est envoyé pour de vrai.

### Vérifications automatiques

```bash
python3 tests.py
python3 -m unittest discover -s tests -v
```

79 vérifications couvrent ce qui ne doit jamais se dérégler : la compréhension
des dates et des noms en français courant, la conduite du dialogue, les
garde-fous (aucun prix inventé, aucune consigne interne divulguée, urgence
traitée), le calcul des disponibilités, la sécurité et le webhook.
Elles s'exécutent sur une base temporaire : **vos données ne sont jamais
touchées**. À relancer après chaque modification de la base de connaissances.

---

## 4. Brancher WhatsApp (numéro 07 97 00 80 52)

### 4.1 Créer l'application Meta

1. Aller sur <https://developers.facebook.com> et créer une application de
   type **Entreprise**.
2. Ajouter le produit **WhatsApp**, puis « Commencer » avec un numéro de test
   (ou le numéro réel de l'hôtellerie).
3. Noter le **Phone number ID** et générer un **jeton d'accès permanent**
   (un jeton temporaire de 24 h ne convient pas : il faudrait le renouveler
   chaque jour).

> **Point d'attention sur le numéro.** Si 07 97 00 80 52 est aujourd'hui
> utilisé dans l'application WhatsApp Business sur un téléphone, Meta
> demandera de le migrer vers l'API Cloud. Les messages déjà présents sur le
> téléphone ne sont pas transférés. Prévoyez cette bascule avec les frères.

### 4.2 Renseigner les paramètres — l'écran « WhatsApp »

Le tableau de bord a un écran dédié, **WhatsApp**, dans le menu. Il sert à
enregistrer les réglages, à **vérifier le compte chez Meta** et à **envoyer un
message d'essai**. C'est là que tout se joue, sans ligne de commande.

| Paramètre | Valeur |
|---|---|
| `wa_token` | le jeton d'accès permanent |
| `wa_phone_number_id` | l'identifiant du numéro |
| `wa_verify_token` | un jeton secret choisi par vous pour le webhook (aucun jeton par défaut) |
| `wa_app_secret` | le secret de l'application (vérification de signature) |
| `wa_api_version` | version de l'API (défaut `v21.0`) |
| `wa_numero_test` | le numéro qui reçoit les essais (défaut `2250151740187`) |
| `site_url` | l'adresse publique HTTPS du tableau de bord |

Les valeurs sont conservées dans la base, sauf si une variable
d'environnement du même nom existe (celle-ci garde la priorité). Un fichier
`.env` est également lu au démarrage — voir `.env.example`.

Le bouton **Vérifier le compte** interroge `graph.facebook.com` et affiche, en
français, ce qui manque : jeton expiré (190), numéro non autorisé en mode test
(131030), fenêtre de 24 h fermée (131047)… Le bouton **Envoyer l'essai** écrit
au numéro d'essai.

### 4.3 Déclarer le webhook

Dans la configuration WhatsApp de Meta :

- **URL de rappel** : `https://votre-serveur/webhook/whatsapp`
- **Jeton de vérification** : celui choisi ci-dessus (`monastere-bouake` par défaut)
- **Champs abonnés** : cocher **messages**

L'adresse exacte est affichée dans l'écran « WhatsApp » dès que `site_url` est
renseignée. Meta exige **HTTPS** : voir la section 6 pour l'hébergement.

**Pour essayer tout de suite, sans nom de domaine**, un tunnel suffit :

```bash
./deploiement/tunnel.sh        # affiche une adresse https://….trycloudflare.com
```

Déclarer `<adresse-affichée>/webhook/whatsapp` dans Meta. Le tunnel ne dure
que le temps du terminal : c'est fait pour l'essai, pas pour la production.

### 4.4 Vérifier — le parcours d'essai (numéro 0151740187)

1. Dans l'application Meta, ajouter **0151740187** aux « Destinataires de test ».
2. Depuis ce téléphone, écrire « Bonjour » au numéro WhatsApp Business.
3. L'agent répond dans la conversation ; l'échange apparaît dans « Échanges ».
4. En cas d'échec, le motif est lisible dans « WhatsApp » (derniers messages) et
   dans « Notifications ».

Meta n'autorise un message libre que dans les **24 heures** qui suivent un
message de l'hôte. D'où l'étape 2 : le code d'erreur 131047 signifie exactement
« la fenêtre est fermée ». Pour écrire le premier, il faudrait un modèle
(template) validé par Meta.

### 4.5 La file d'attente

Chaque message WhatsApp est **écrit en base avant l'envoi** (table `envois`).
Sans jeton, sans réseau, ou après un refus de Meta, il reste `en_attente` et
repart avec le bouton « Rejouer la file » ou :

```bash
python3 run.py whatsapp --rejouer
```

La reprise est manuelle ; surveillez la file et les erreurs. En cas de coupure
au milieu d’un appel réseau, la livraison effective peut être incertaine :
contrôlez les doublons et la réponse de Meta avant de rejouer. Une coupure
pendant le traitement d’un webhook peut également nécessiter une intervention.

---

## 5. Réponses de l’agent et API

L’agent est **déterministe**, sans modèle de langage. Le code expérimental du
module de langage est conservé mais n’est pas branché aux réponses : une simple
consigne ne suffit pas à garantir qu’une IA n’ajoute pas de faits. Avant toute
réactivation, il faut une validation adaptée, des tests et une politique de
confidentialité. Les échanges du simulateur sont conservés localement, mais
ne créent ni demande réelle ni notification externe.

L’API `/api/agent` est fermée par défaut. Pour un usage contrôlé, configurez
`api_cle`, puis envoyez des requêtes JSON avec l’en-tête `X-API-Key`. Passez
la valeur `conversation` renvoyée par l’API dans les requêtes suivantes pour
conserver le dialogue. Ne mettez pas la clé dans une URL. L’option d’ouverture
sans clé n’est pas adaptée à une exposition publique.

---

## 6. Hébergement

### 6.1 Sur un petit ordinateur au monastère (recommandé pour commencer)

Une machine sous Linux, même ancienne, suffit. Copier le dossier, puis :

```bash
python3 run.py servir --port 8080
```

Pour que le service démarre tout seul et redémarre après une coupure
d'électricité, installer l'unité systemd fournie :

```bash
sudo cp deploiement/hotellerie.service /etc/systemd/system/
sudo systemctl enable --now hotellerie
```

Pour l'exposer en HTTPS, placer un reverse proxy (Caddy, le plus simple).
Un `Caddyfile` prêt à copier est fourni :

```bash
sudo cp deploiement/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Il suffit d'y remplacer `hotellerie.exemple.org` par le nom de domaine réel.
Caddy obtient et renouvelle le certificat automatiquement. Sans cette adresse
HTTPS, Meta refusera le webhook : c'est la seule pièce que la maison doit
fournir (un nom de domaine, ou un VPS avec Caddy).

### 6.2 Chez un hébergeur (VPS)

Un VPS à quelques euros par mois (OVH, Hetzner, Scaleway) convient. Le
`Dockerfile` fourni permet un déploiement en une commande :

```bash
docker build -t hotellerie .
docker run -d -p 8080:8080 -v hotellerie-data:/app/data hotellerie
```

### 6.3 Ce qu'il faut éviter

Les plateformes « serverless » (Cloudflare Workers, Vercel, Lambda) : elles ne
garantissent pas un disque persistant, et c'est précisément ce dont une base
de données a besoin.

---

## 7. Sauvegardes

La base entière tient dans un fichier. Une sauvegarde quotidienne suffit :

```bash
python3 run.py sauvegarde /chemin/vers/une-sauvegarde.db
```

Ajouter cette ligne dans `crontab` pour l'automatiser chaque nuit à 2 h :

```
0 2 * * * cd /opt/monastere-hotellerie && python3 run.py sauvegarde /var/sauvegardes
```

Conservez au moins une copie **hors du monastère** (clé USB confiée à un
voisin, ou envoi chiffré). Une inondation, un vol ou un orage emportent le
serveur et sa sauvegarde s'ils sont dans la même pièce.

---

## 8. Sécurité

- Les mots de passe sont hachés (PBKDF2-HMAC-SHA256, 100 000 itérations) ;
  ils ne sont jamais stockés en clair.
- Les sessions expirent (12 h par défaut) ; le cookie est `HttpOnly`.
- Tous les formulaires sont protégés contre la contrefaçon (jeton CSRF).
- Les tentatives de connexion sont limitées (6 essais, puis 15 min d'attente).
- Les jetons et secrets sont masqués dans l'interface ; une variable
  d'environnement peut les remplacer pour ne jamais les écrire dans la base.
- Le webhook refuse les messages entrants si `wa_app_secret` n’est pas
  renseigné ou si la signature `X-Hub-Signature-256` est invalide.
- Les notifications configurées peuvent transmettre des données d’hôtes à
  Meta et au fournisseur SMTP. Protégez l’accès, minimisez les données et
  définissez leur durée de conservation avant d’accueillir de vrais hôtes.
- Les rôles affichés ne constituent pas encore une séparation d’autorisations
  complète. N’ouvrez pas l’application à plusieurs organisations.
- Le serveur intégré et SQLite ciblent un seul établissement ; audits de
  sécurité, contrôle des accès, sauvegardes restaurables et supervision sont
  nécessaires avant l’ouverture sur Internet.

---

## 9. Structure du projet

```
monastere-hotellerie/
├── run.py                    point d'entrée (ligne de commande)
├── tests.py                  79 vérifications automatiques
├── base_connaissances.json   le « cerveau » de l'agent, éditable
├── README.md                 ce fichier
├── SPECIFICATION.md          cahier des charges complet
├── PROMPT_AGENT.md           la règle de vie de l'agent, à réutiliser ailleurs
├── .env.example              modèle de configuration
├── Dockerfile                déploiement en conteneur
├── deploiement/
│   ├── hotellerie.service    unité systemd
│   ├── Caddyfile             HTTPS automatique (webhook Meta)
│   └── tunnel.sh             tunnel HTTPS d'essai (cloudflared)
├── data/                     la base SQLite et les journaux (à sauvegarder)
└── hotellerie/
    ├── config.py             paramètres (env > base > défaut)
    ├── db.py                 schéma et accès aux données
    ├── metier.py             disponibilités, demandes, occupation
    ├── knowledge.py          recherche dans la base de connaissances
    ├── notify.py             le relais vers les frères
    ├── securite.py           mots de passe, sessions, CSRF, signatures
    ├── seed.py               amorçage
    ├── agent/
    │   ├── prompts.py        la voix de la maison
    │   ├── engine.py         le moteur de dialogue
    │   ├── comprehension.py  dates, nombres, noms, besoins en français
    │   └── llm.py            module de langage optionnel
    ├── channels/
    │   ├── whatsapp.py       réception et envoi
    │   └── emailer.py        courriel (SMTP)
    └── web/
        ├── server.py         routes, webhook, API
        ├── vues.py           écrans du tableau de bord
        └── templates.py      habillage (CSS inline, aucune ressource externe)
```

---

## 10. Dépannage

| Symptôme | Cause probable | Remède |
|---|---|---|
| L'agent ne répond pas sur WhatsApp | `wa_token` ou `wa_phone_number_id` vide | Écran « WhatsApp » : « Vérifier le compte », puis « Rejouer la file » |
| Le webhook renvoie 403 | Jeton de vérification différent | Le même mot de passe des deux côtés |
| Page blanche après une action | Session expirée | Se reconnecter |
| « La base est occupée » | Deux instances lancées | Arrêter le doublon |
| L'agent répond à côté | Une fiche de connaissance imprécise | La corriger dans « Base de connaissances » |

Les journaux sont dans `data/logs/hotellerie.log`.

---

## 11. Aller plus loin

Le cahier des charges (`SPECIFICATION.md`) décrit l'extension prévue aux
autres services du monastère : parc informatique et maintenance, stocks de
provende, et centre de formation du Studium. L'architecture a été conçue pour
que ces pôles viennent s'y ajouter sans rien réécrire.
