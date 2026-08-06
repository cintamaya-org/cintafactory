### 1. Workflow `Check code` — Vérifications sur Pull Request

**Déclenchement :** à chaque Pull Request vers `dev` ou `main`.

Ce workflow exécute plusieurs analyses de sécurité et de qualité en parallèle, puis centralise les rapports.

#### Jobs

**Gitleaks : Détection de secrets**  
Scanne le code source à la recherche de secrets exposés (clés API, tokens, mots de passe, etc.) via l'outil Gitleaks. Un rapport JSON est généré et conservé en artifact, même en cas d'échec du scan.

**SbomScan : Analyse des dépendances**

- **Syft** génère un SBOM (Software Bill of Materials) au format CycloneDX, listant l'ensemble des composants et dépendances du projet.
- **Grype** analyse ce SBOM pour détecter les vulnérabilités connues (CVE), avec un rapport au format JSON et texte.
- **Grant** vérifie la conformité des licences des dépendances utilisées.

Tous les rapports (SBOM, SCA, licences) sont regroupés et publiés en artifact.

**SonarQube : Qualité du code**  
Analyse statique du code (bugs, vulnérabilités, code smells, couverture) via SonarQube Scan Action, remontée sur le serveur SonarQube du projet.

**Hadolint : Lint du Dockerfile**  
Vérifie les bonnes pratiques d'écriture du `Dockerfile` (mode non bloquant : les erreurs sont signalées sans faire échouer le pipeline).

**RapportVps : Centralisation des rapports**  
Une fois les jobs Gitleaks et SbomScan terminés (`always()`), les rapports générés sont :

1. Téléchargés depuis les artifacts GitHub Actions
2. Réorganisés par outil (`syft/`, `grype/`, `grant/`, `gitleaks/`) et horodatés
3. Envoyés par SCP vers un VPS dédié à l'archivage, sous `/home/debian/<nom-du-repo>/`

---

### 2. Workflow `Déploiement DEV (test_factory)`

**Déclenchement :** à chaque Pull Request vers `main`.  
**Concurrency :** un seul déploiement à la fois pour cet environnement (`deploy-dev-test_factory`) ; tout déploiement en cours est annulé si un nouveau démarre.

#### Étapes

1. **Récupération du code** : checkout du dépôt.
2. **Configuration SSH** : génération d'une clé privée temporaire et ajout du VPS aux hôtes connus.
3. **Synchronisation vers le VPS** : envoi du contenu du dépôt via `rsync` (mode miroir : suppression des fichiers absents du dépôt), en excluant `.git` et `.github`. Destination : `/opt/cintafactory/test`.
4. **Déploiement** : connexion SSH au VPS pour :
    - Créer le réseau Docker `swag-network` si absent
    - Injecter les variables d'environnement (secrets Django, LikeC4, PostgreSQL, hôtes autorisés) transmises en base64 pour éviter les problèmes d'échappement shell, puis décodées côté serveur
    - Lancer `docker compose up -d --build` pour reconstruire et démarrer les conteneurs
5. **Nettoyage** : suppression systématique (`always()`) de la clé SSH privée du runner, même en cas d'échec.