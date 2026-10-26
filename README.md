# Hôtellerie & Accueil — Monastère Bénédictin Sainte-Marie de Bouaké

Application complète d'accueil et de gestion de l'hôtellerie monastique :
un **agent d'accueil** qui reçoit les hôtes sur WhatsApp dans l'esprit de la
Règle de saint Benoît, et un **tableau de bord** où les pères et frères
responsables gardent la main sur le discernement.

> « Tous les hôtes qui se présentent seront reçus comme le Christ. »
> — Règle de saint Benoît, 53

---

## 1. Ce que fait l'application

| | |
|---|---|
| **L'agent d'accueil** | Répond aux hôtes 24 h/24, renseigne sur la maison (offices, accès, cadre de vie), recueille une demande de séjour avec douceur, et transmet une fiche de synthèse aux frères. |
| **Le tableau de bord** | Les frères consultent les demandes, discernent (accepter / refuser), attribuent une chambre, voient le calendrier d'occupation, répondent à l'hôte, et enrichissent la base de connaissances de l'agent. |
| **Le relais** | Chaque demande complète déclenche une fiche envoyée par courriel et sur WhatsApp aux frères hôteliers, en plus de son affichage dans le tableau de bord. |
| **Le webhook WhatsApp** | Prêt à être branché sur le numéro **07 97 00 80 52** (Meta Cloud API). |

### Ce que l'agent ne fait jamais — c'est le point le plus important

Il ne confirme **jamais** une réservation : le discernement final appartient
aux frères. Il n'invente **jamais** un prix, une disponibilité, un horaire, un
nom de frère ou une adresse. Ce qu'il ne sait pas, il le transmet.

---

## 2. Installation

### Prérequis

- Python **3.8 ou plus** (aucune bibliothèque à installer)
- Environ 5 Mo d'espace disque, et rien d'autre

L'application n'utilise que la **bibliothèque standard** : pas de `pip install`,
pas de dépendance à mettre à jour, pas de serveur de base de données à
administrer. Les données tiennent dans un seul fichier
(`data/hotellerie.db`) que l'on sauvegarde par simple copie.

### Démarrage en trois commandes

```bash
cd monastere-hotellerie

python3 run.py initialiser --demo     # crée la base, les chambres, les fiches
python3 run.py utilisateur --login hotelier --nom "Frère Hôtelier"
python3 run.py servir                 # http://localhost:8080
```

`--demo` ajoute six demandes fictives, pour que le tableau de bord parle tout
de suite. **À ne pas faire en production.**

### Première chose à faire après l'installation

1. **Renommer les chambres** dans « Occupation ». Neuf chambres génériques
   ont été créées (« Chambre 1 »… « Dortoir ») : la disponibilité calculée par
   l'agent dépend directement de leur nombre et de leur capacité.
2. **Compléter les fiches de connaissance** dans « Base de connaissances »
   (menu « À compléter »). Dix-sept fiches contiennent encore une mention
   `[[À COMPLÉTER …]]` : offrande conseillée, horaires du portail, capacité
   d'accueil des groupes, enfants et animaux, etc.
   **Tant qu'une fiche reste en blanc, l'agent ne répondra pas à côté : il dira
   honnêtement qu'il transmet la question aux frères.** C'est volontaire.

---

## 3. Ligne de commande

```bash
python3 run.py                        # installation si besoin, puis démarrage
python3 run.py servir --port 8080     # démarrer le serveur
python3 run.py initialiser [--demo]   # (ré)initialiser la base
python3 run.py utilisateur --login X  # créer ou modifier un compte
python3 run.py tester                 # dialoguer avec l'agent dans le terminal
python3 run.py importer [--ecraser]   # réimporter base_connaissances.json
python3 run.py sauvegarde [dossier]   # copier la base avec la date du jour
python3 run.py secret                 # générer un secret aléatoire
```

`python3 run.py tester` est le moyen le plus simple d'éprouver l'agent avant
de le brancher sur WhatsApp. Aucun message n'est envoyé pour de vrai.

### Vérifications automatiques

```bash
python3 tests.py
```

73 vérifications couvrent ce qui ne doit jamais se dérégler : la compréhension
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

### 4.2 Renseigner les paramètres

Ouvrir `Paramètres` dans le tableau de bord et remplir :

| Paramètre | Valeur |
|---|---|
| `wa_token` | le jeton d'accès permanent |
| `wa_phone_number_id` | l'identifiant du numéro |
| `wa_verify_token` | un mot de passe de votre choix (ex. `pax-bouake-2026`) |
| `wa_app_secret` | le secret de l'application (vérification de signature) |
| `hoteliers_whatsapp` | les numéros des frères, séparés par des virgules |

Les valeurs sont conservées dans la base, sauf si une variable
d'environnement du même nom existe (celle-ci garde la priorité). Un fichier
`.env` est également lu au démarrage — voir `.env.example`.

### 4.3 Déclarer le webhook

Dans la configuration WhatsApp de Meta :

- **URL de rappel** : `https://votre-serveur/webhook/whatsapp`
- **Jeton de vérification** : celui choisi ci-dessus
- **Champs abonnés** : cocher **messages**

L'URL doit être en **HTTPS** : Meta l'exige. Voir la section 6 pour les
options d'hébergement.

### 4.4 Vérifier

Depuis un téléphone, écrivez au numéro. Le message doit apparaître dans
« Échanges » puis dans « Demandes ». Consultez « Notifications » pour voir
l'accusé d'envoi ; en cas d'échec, le motif y est consigné.

**Tant que le jeton n'est pas configuré, rien n'est envoyé** : l'application
fonctionne normalement, les réponses sont simplement consignées dans la base
au lieu de partir. Cela permet de tester tout le reste hors ligne.

---

## 5. Le module de langage (facultatif)

Par défaut, l'agent n'utilise **aucune intelligence artificielle** : il puise
ses réponses dans la base de connaissances rédigée par les frères. C'est
gratuit, prévisible, et cela fonctionne même quand Internet est coupé — ce qui
compte à Bouaké.

Si vous le souhaitez, une clé d'API (OpenAI, Anthropic, ou tout service
compatible) ajoute une formulation plus souple. Dans `Paramètres` :

| Paramètre | Exemple |
|---|---|
| `ia_active` | `1` |
| `ia_fournisseur` | `openai` ou `anthropic` |
| `ia_modele` | `gpt-4o-mini` |
| `ia_cle_api` | la clé |

**Ce module n'a jamais le dernier mot.** La collecte des informations, la
vérification des disponibilités et l'enregistrement des demandes restent
déterministes : le modèle de langage ne fait que formuler. S'il est absent,
coupé, ou en erreur, l'agent retombe immédiatement sur ses propres réponses.
Un hôte ne reste jamais sans réponse à cause d'un service tiers.

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

Pour l'exposer en HTTPS, placer un reverse proxy (Caddy, le plus simple) :

```
hotellerie.monastere.ci {
    reverse_proxy 127.0.0.1:8080
}
```

Caddy obtient et renouvelle le certificat automatiquement.

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
python3 run.py sauvegarde /chemin/vers/les/sauvegardes
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
- Le webhook vérifie la signature `X-Hub-Signature-256` si `wa_app_secret`
  est renseigné.
- Les données des hôtes restent dans la base du monastère. Rien n'est envoyé
  à un tiers, **sauf** si le module de langage est activé : dans ce cas, le
  contenu des messages est transmis au fournisseur choisi pour produire la
  réponse. C'est le seul flux sortant, et il est désactivé par défaut.

---

## 9. Structure du projet

```
monastere-hotellerie/
├── run.py                    point d'entrée (ligne de commande)
├── base_connaissances.json   le « cerveau » de l'agent, éditable
├── README.md                 ce fichier
├── SPECIFICATION.md          cahier des charges complet
├── PROMPT_AGENT.md           la règle de vie de l'agent, à réutiliser ailleurs
├── .env.example              modèle de configuration
├── Dockerfile                déploiement en conteneur
├── deploiement/
│   └── hotellerie.service    unité systemd
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
| L'agent ne répond pas sur WhatsApp | `wa_token` ou `wa_phone_number_id` vide | « Paramètres », puis « Notifications » pour lire le motif d'échec |
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
