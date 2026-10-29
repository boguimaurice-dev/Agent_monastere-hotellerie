# Feuille de route : exploitation et éventuelle évolution SaaS

## Ce qui existe aujourd’hui

Un prototype Python/SQLite pour **une seule maison**, avec agent déterministe,
tableau de bord, relais humain et intégration Meta/SMTP à configurer. Les
simulations ne créent pas de dossiers réels. Des tests locaux vérifient des
parcours HTTP et WhatsApp avec des services simulés ; ils ne valident ni les
faits fournis par la maison, ni un compte Meta/SMTP réel, ni la disponibilité
continue. La fonction expérimentale de reformulation IA n’est pas utilisée.

## Avant l’ouverture aux hôtes

1. Faire valider par la communauté toutes les fiches et coordonnées, les règles,
   les chambres, capacités et horaires ; compléter les informations manquantes.
2. Définir les responsables du relais et les délais réalistes, tester prise en
   charge, correction, annulation et reprise manuelle de la file ; surveiller
   quotidiennement les messages et les erreurs.
3. Configurer HTTPS, un nom de domaine, Meta (jeton, identifiant, jeton de
   vérification unique et secret de signature obligatoire), puis SMTP et les
   destinataires approuvés. Réaliser un essai entrant/sortant réel contrôlé,
   avec consentement ; ne pas utiliser de vraies données dans la démonstration.
4. Prévoir supervision, redémarrage, sauvegardes chiffrées hors site et essais
   réguliers de restauration. SQLite en WAL exige une sauvegarde cohérente via
   `python3 run.py sauvegarde`, pas une simple copie du fichier actif.
5. Effectuer une revue indépendante de sécurité et de confidentialité, définir
   accès, information des hôtes, durée de conservation, suppression et gestion
   des incidents. Les dossiers peuvent contenir des informations sensibles.
   La suppression d'une demande n'efface pas les conversations ou journaux :
   prévoir une procédure et des outils d'effacement complets.
6. Renforcer la fiabilité des webhooks et envois : traitement transactionnel
   des événements, reprise après crash, file persistante avec réessais contrôlés,
   contrôle des doublons, alertes, gestion des réponses et restrictions Meta.
   L'attribution de plusieurs chambres à un seul dossier de groupe reste à créer.
   La déduplication actuelle traite les doublons ordinaires mais ne garantit pas
   une livraison exactement une fois en cas de panne au mauvais moment.

## Avant un SaaS multi-établissements

- Concevoir un modèle explicite d’organisation, d’appartenance et de rôles ;
  imposer l’isolation des données côté serveur pour **chaque** lecture, écriture,
  fichier, file, webhook et journal. Les rôles actuels ne l’assurent pas.
- Gérer identité, invitations, contrôle d’accès fin, récupération de compte,
  authentification forte, secrets et audit ; ne pas partager une clé API entre
  clients. Prévoir rotation, révocation et limitation des appels.
- Associer de façon vérifiée chaque numéro/canal et chaque webhook à une seule
  organisation ; empêcher l’usurpation et tester les scénarios inter-clients.
- Introduire migrations versionnées, base adaptée à la charge, transactions,
  workers et files fiables ; tester concurrence, montée en charge, pannes,
  restauration et séparation des environnements.
- Prévoir conformité applicable, contrats, sous-traitants, consentement et
  minimisation, suppression/export par organisation, rétention et chiffrement.
- Ajouter observabilité sans données sensibles, métriques, alertes, objectifs
  de service, support, onboarding, facturation et gestion du cycle de vie.
- Faire des tests de sécurité indépendants et des tests automatiques d’isolation
  avant d’accueillir le premier autre établissement.

Aucune isolation multi-tenant, facturation ou garantie SaaS n’est implémentée à ce
stade. Ce document est une feuille de route, pas une certification.
