# CintaFactory

**CintaFactory** is a TODO Describe the product
---

## Quick Start (Docker)
For the full developer operations guide, use `README_dev.md`.

Start app stack:
```bash
docker compose -f docker-compose.dev.yml up -d --build
```

Apply migrations:
```bash
docker compose -f docker-compose.dev.yml exec -T web python manage.py migrate
```

Main app URL:
- `http://localhost:8101`

Start observability stack (Grafana/Prometheus/Loki/cAdvisor):
```bash
docker compose -f cintafactory/docker-compose.observability.dev.yml up -d
```

Observability URLs:
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`
- Loki: `http://localhost:3100/ready`
- cAdvisor: `http://localhost:8088`

## Technology Stack

| Component           | Technology           |
| ------------------- | -------------------- |
| **Framework**       | Django 5.2.5         |
| **Database**        | PostgreSQL |
| **Language**        | Python TODO VERSION       |

---

## Development Setup

### Clone the repository

```bash
git clone https://github.com/your-org/cintafactory.git
cd cintafactory
```

### Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Create and activate a virtual environment

```bash
uv venv .venv
source .venv/bin/activate
```

### Install dependencies

```bash
uv sync --frozen
```

Dependencies are managed via `pyproject.toml` and `uv.lock`.

If you add or update dependencies, run:

```bash
uv lock
```

### Apply migrations

```bash
python manage.py migrate
```

### Synchronise workflow definitions

```bash
python manage.py sync_workflows
```

The command reads the declarative configuration in `workflows/definitions.py`
and keeps the database (steps, permissions) in sync.

### Create a superuser

```bash
python manage.py createsuperuser
```

### Run the development server

```bash
python manage.py runserver
```

Now open:
-> [http://127.0.0.1:8050/admin/](http://127.0.0.1:8050/admin/) to access the Django admin interface.

### Optional: Embedded draw.io editor

If you deploy the bundled draw.io containers, configure the application with:

- `DRAWIO_BASE_URL`: address the Django backend should use to talk to the draw.io editor service on the Docker network (defaults to `http://drawio:8080`).
- `DRAWIO_PUBLIC_URL`: URL exposed to browsers that should be used inside the iframe (defaults to the same value as `DRAWIO_BASE_URL`; override it for public hosts, e.g. `https://drawio.example.com`).
- `DRAWIO_LIBS` (optional): built-in diagrams.net palettes to expose (defaults to `general`); use a comma-separated list such as `general,uml`.
- `DRAWIO_CLIBS` (optional): comma-separated list of HTTP(S) URLs that point to custom library XML files. Each entry is transformed into the `clibs` parameter so the iframe loads the libraries automatically. When unset, the application still loads any XML libraries found under `static/diagrams`.
- The `drawio-export` service (added to the Compose files) handles PNG generation locally; the application reaches it through the internal hostname `drawio-export:8000`.

To host custom libraries locally, serve the XML file from any container reachable by draw.io. A simple option is to drop the file under Django’s static directory (for example `cintafactory/static/drawio/mes-formes.xml`, mounted read-only in production) so it becomes available at `https://your-app/static/drawio/mes-formes.xml`. Then set `DRAWIO_CLIBS` to the internal URL exposed within your Docker network, e.g. `http://web:8000/static/drawio/mes-formes.xml`. The embedder automatically URL-encodes the parameter for draw.io.

The docker-compose stacks already pass reasonable defaults; adjust them to match your reverse-proxy/hostnames in production.

### DAT exports (PDF/JSON)

- Depuis la fiche DAT, lancez une nouvelle génération PDF en tâche de fond (action `dat:my_export_pdf_trigger`), téléchargez le dernier export stocké (`dat:my_export_pdf_download`) ou récupérez le JSON (`dat:my_export_json`). Un seul PDF est conservé par DAT pour éviter d'occuper trop d'espace disque et le bouton de génération reste indisponible tant que l'export en cours n'est pas terminé.
- Les deux formats s'appuient sur `cintafactory/dat/exporters.py`. Surclassez `DAT_EXPORT_MODEL_BUILDER` pour ajuster la structure retournée si besoin.
- Le gabarit PDF se trouve dans `cintafactory/dat/templates/dat/exports/dat_export_pdf.html` et s'appuie sur WeasyPrint (installez les bibliothèques système requises : Cairo, Pango…).

---

## CI/CD

The GitHub Actions workflow in `.github/workflows/deploy.yml` automates testing and deployments:

- Pushes to `dev`, `main`, or any `dev-*` branch always run the Django test suite.
- Successful pushes to `dev` and pull requests targeting `dev` deploy the shared test stack by executing `deploy/scripts/deploy.sh test` on the VPS.
- Successful pushes to `main` and pull requests from `dev` into `main` deploy the production/demo stack by executing `deploy/scripts/deploy.sh prod`.

Each environment uses distinct Docker Compose project names, host ports, and named volumes, allowing the two stacks to run on the same VPS simultaneously without resource conflicts.


### Required GitHub secrets

Add the following secrets to the repository (or organisation) so the workflow can reach the VPS:

| Secret | Description |
| ------ | ----------- |
| `VPS_IP` | SSH host name or IP address of the VPS. |
| `VPS_USER` | SSH user that can deploy and run Docker. |
| `VPS_SSH_KEY` | Private SSH key (PEM) for that user. |

Secrets stored in `deploy/env/*.env` remain on the VPS—they are excluded from the sync step during deployments.

---

## License

This project is licensed under the **AGPL-3.0 License**.
See the [LICENSE](./LICENSE) file for full details.

---

### Notes

* Default database: `PostgreSQL`
* Future features: SSO integration, role-based access control, external file storage....
