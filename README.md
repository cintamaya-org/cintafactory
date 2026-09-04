# Cintafactory

Cintafactory est une plateforme opensource conçue pour structurer, gouverner et industrialiser la production et la validation des dossiers d’architecture technique dans les systèmes d’information complexes.

Elle répond à un problème récurrent dans les grandes organisations : la valeur de l’architecture se perd dans des processus lourds, des validations manuelles, une traçabilité faible et une capitalisation insuffisante.

## Pourquoi Archifactory ?

Dans la plupart des organisations, la production des dossiers d’architecture est freinée par :

- des allers-retours multiples et peu tracés entre intervenants
- une documentation éclatée (Word, Visio, Excel, SharePoint, etc.)
- un manque de visibilité sur l’état d’avancement et les responsabilités
- une faible réutilisation des architectures passées

## Archifactory est né d’un constat simple 

Les architectes doivent se concentrer sur les choix et décisions d’architecture, pas sur la mécanique documentaire.


## Qu’est-ce qu’Archifactory ?

Archifactory est une application web de gouvernance de l’architecture qui combine :

* un moteur de workflow de validation
* un référentiel centralisé de dossiers d’architecture (DAT)
* une production guidée des artefacts d’architecture
* une traçabilité complète des décisions, revues et validations

Archifactory ne remplace pas les outils de modélisation existants : il les orchestre, les structure et leur donne un cadre de gouvernance.

## Concepts clés

Archifactory repose sur quelques principes simples et robustes :

1. Dossier d’architecture

Un conteneur structuré regroupant l’ensemble des éléments nécessaires à la description et à la validation d’une architecture.

2. Rôles et gouvernance

Une séparation claire des responsabilités :

* porteur de la demande
* architecte référent
* contributeurs
* validateurs

3. Cycle de vie piloté par workflow

Chaque dossier suit des états explicites :

brouillon → revue → validation → publication 

4. Capitalisation dans le temps

Les dossiers d’architecture deviennent des actifs du SI, réutilisables et exploitables.

### Fonctionnalités principales

* Création guidée des dossiers d’architecture
* Workflows de validation configurables
* Référentiel d’architecture centralisé (versionné, historisé)
* Gestion des rôles et des habilitations
* Traçabilité des actions et décisions
* Capitalisation et réutilisation des architectures
 (Les fonctionnalités concrètes dépendent de l’implémentation choisie.)

* Vue d’architecture (conceptuelle)

Archifactory est conçu comme une plateforme modulaire et extensible :
* un cœur métier centré sur le dossier d’architecture
* un moteur de workflow (machine à états)
* un modèle de données orienté architecture
* des intégrations possibles avec des outils de modélisation (draw.io, LikeC4, etc.)
* des échanges basés sur des formats ouverts (JSON)

Cette approche permet une forte adaptabilité sans remettre en cause le socle.

### Cas d’usage typiques

* Gouvernance de l’architecture d’entreprise
* Comités de validation d’architectures techniques
* Programmes de transformation à grande échelle
* Environnements réglementés nécessitant traçabilité et auditabilité
* Capitalisation et transmission de la connaissance SI

## Démarrer avec Archifactory

Archifactory n’est pas un produit “clé en main”.

Ce dépôt fournit :
* un socle fonctionnel et conceptuel
* un modèle de données de référence
* des exemples de workflows
* une architecture cible extensible

Chaque organisation est invitée à adapter Archifactory à :
* son modèle de gouvernance
* ses pratiques d’architecture
* son écosystème d’outillage

Pour cela, grâce à ses activités de Conseil, Cintamaya peut vous aider dans l'adaptation de votre organisation à cet outil.

* Feuille de route (indicative)
* Stabilisation du moteur de workflow
* Modèle de données de référence (DAT / ADR)
* APIs d’import / export
* Intégration d’outils de modélisation

## Documentation détaillée et exemples

### Contribuer

Les contributions sont bienvenues, notamment sur :
* modèles d’architecture
* workflows de validation
* modèles de données
* code
* documentation et retours d’expérience

Voir CONTRIBUTING.md pour les modalités. 

## Licence

Ce produit est publié sous licence AGPLv3 pour le code et CC-BY-ND pour les docs.

### À propos

Archifactory est issu de retours d’expérience concrets dans de grandes organisations, confrontées à des SI complexes et à des enjeux forts de gouvernance de l’architecture.

Le projet est porté par des praticiens, pour des praticiens.