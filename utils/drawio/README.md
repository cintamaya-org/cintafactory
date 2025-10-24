# Editeur draw.io autonome

Ce dossier contient les outils utilitaires reliant l'application Django a une distribution hors-ligne de draw.io (diagrams.net). Les fichiers statiques exposes aux utilisateurs sont places sous `cintafactory/static/drawio/`.

## Installer les assets draw.io

1. Assurez-vous d'avoir Python 3.9+.
2. Depuis la racine du projet, lancez :

   ```bash
   python utils/drawio/download_drawio_release.py
   ```

   Par defaut, les fichiers sont deployes dans `cintafactory/static/drawio/vendor/drawio-editor`.

Options utiles :

- `--version latest` : telecharger la derniere release publique.
- `--version 24.7.12` : imposer une version specifique.
- `--force` : ecraser le repertoire cible si present.
- `--target <chemin>` : personnaliser l'emplacement d'installation.
- `--keep-archive` : conserver le fichier `.zip` telecharge.

Sans le script, telechargez l'archive correspondant a votre version depuis [jgraph/drawio/releases](https://github.com/jgraph/drawio/releases), puis copiez `src/main/webapp` dans `cintafactory/static/drawio/vendor/drawio-editor`.

## Intégration Django

- Le wrapper principal est `cintafactory/static/drawio/index.html`.
- Une vue Django peut simplement rendre un template qui embarque ce fichier dans une balise `iframe`, ou rediriger directement l'utilisateur vers `/static/drawio/index.html`.
- Lors de `collectstatic`, le repertoire `static/drawio` est embarque automatiquement (via WhiteNoise).

### Utilisation avec Docker

Ajoutez une etape d'image (ou de run) qui invoque :

```bash
python utils/drawio/download_drawio_release.py --force
python manage.py collectstatic --noinput
```

Cela garantit que les assets draw.io sont preinstalles avant que le conteneur ne serve l'application. A defaut, vous pouvez lancer le script lors du demarrage si le dossier `static/drawio/vendor/drawio-editor` est absent.

## Fonctionnement pour l'utilisateur

- **Chargement local** : le bouton *Charger dans l'editeur* ouvre un fichier `.drawio` ou `.xml` depuis le poste client.
- **Chargement distant** : fournissez une URL accessible (CORS requis) et choisissez la methode HTTP pour la sauvegarde (PUT/POST).
- **Sauvegarde** :
  - Un telechargement local se declenche par defaut a chaque enregistrement.
  - Si une URL distante est definie, une requete HTTP supplementaire pousse le fichier vers ce serveur.
  - Le bouton *Forcer la sauvegarde* demande immediatement a draw.io de retourner la version courante du diagramme.
- **Nouveau diagramme** : reinitialise l'editeur avec un `mxfile` minimal.

## Organisation

```
utils/drawio/
├── download_drawio_release.py   # Outil pour rapatrier draw.io
└── README.md                    # Ce document

cintafactory/static/drawio/
├── index.html                   # Wrapper autonome
└── vendor/                      # Assets draw.io installes via le script
    └── drawio-editor/           # Contenu officiel diagrams.net
```

Adaptez le wrapper selon vos besoins (authentification, theming, restrictions d'import). Les assets peuvent aussi etre exposes via un autre serveur statique (CDN, bucket S3, etc.) si vous synchronisez le repertoire `vendor/drawio-editor`.
