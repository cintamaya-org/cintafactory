# 🚀 CICD Workflow
![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?logo=githubactions&logoColor=white) ![Security](https://img.shields.io/badge/security-Gitleaks%20%7C%20Grype%20%7C%20Syft-critical) ![Quality](https://img.shields.io/badge/quality-SonarQube-4E9BCD?logo=sonarqube&logoColor=white) ![Deploy](https://img.shields.io/badge/deploy-Docker%20Compose-2496ED?logo=docker&logoColor=white)

Documentation des pipelines mis en place pour le contrôle qualité, la sécurité et le déploiement automatisé du projet.

## 📋 Sommaire

- Check code — Vérifications sur PR
- Déploiement DEV

---

## 🔍 Check code — Vérifications sur Pull Request

> **Déclencheur :** Pull Request → `dev` ou `main`

Pipeline d'analyse exécutant plusieurs contrôles en parallèle avant fusion.

| Job               | Outil                | Rôle                                                                                         |
| ----------------- | -------------------- | -------------------------------------------------------------------------------------------- |
| 🔐 **Gitleaks**   | Gitleaks             | Détection de secrets exposés dans le code (clés, tokens, mots de passe)                      |
| 📦 **SbomScan**   | Syft + Grype + Grant | Inventaire des dépendances (SBOM), scan de vulnérabilités (CVE) et vérification des licences |
| 📊 **SonarQube**  | SonarQube Scan       | Analyse statique : bugs, code smells, vulnérabilités                                         |
| 🐳 **Hadolint**   | Hadolint             | Lint du `Dockerfile` (bonnes pratiques, non-bloquant)                                        |
| 📤 **RapportVps** | rsync/scp            | Centralisation et archivage des rapports sur VPS                                             |
|                   |                      |                                                                                              |

<details> <summary><b>Détails des jobs</b></summary>

**🔐 Gitleaks** Scan complet du dépôt, rapport JSON généré même en cas d'échec, publié en artifact.

**📦 SbomScan**

- `Syft` → génère un SBOM au format CycloneDX
- `Grype` → analyse le SBOM et détecte les CVE (sortie JSON + texte)
- `Grant` → contrôle la conformité des licences

**📊 SonarQube** Analyse remontée automatiquement sur le serveur SonarQube du projet (`Cintafactory-dev`).

**🐳 Hadolint** Vérifie le `Dockerfile` ; les erreurs sont signalées sans bloquer le pipeline (`no-fail: true`).

**📤 RapportVps** Déclenché après `Gitleaks` et `SbomScan` (`always()`) :

1. Téléchargement des artifacts
2. Réorganisation par outil : `syft/`, `grype/`, `grant/`, `gitleaks/` — fichiers horodatés
3. Envoi SCP vers `/home/debian/<repo>/`

</details>

---

## 🛠️ Déploiement DEV (`test_factory`)

> **Déclencheur :** Pull Request → `main` **Concurrency :** un seul déploiement actif à la fois — tout run en cours est annulé si un nouveau démarre

|Étape|Action|
|---|---|
|**1. Checkout**|Récupération du code source|
|**2. SSH Setup**|Génération de la clé privée temporaire + ajout du VPS aux `known_hosts`|
|**3. Sync**|`rsync -az --delete` vers `/opt/cintafactory/test` (exclut `.git`, `.github`)|
|**4. Déploiement**|Injection des secrets (base64) + `docker compose up -d --build` sur le VPS|
|**5. Cleanup**|Suppression de la clé SSH (`always()`, même en cas d'échec)|

**🔑 Variables injectées :** Django (`SECRET_KEY`, `ALLOWED_HOST`), LikeC4 (`METADATA_TOKEN`, `API_TOKEN`), PostgreSQL (`DB`, `USER`, `PASSWORD`).

> Transmises en base64 via SSH pour éviter les problèmes d'échappement shell, puis décodées côté serveur.