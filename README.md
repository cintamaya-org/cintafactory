# CintaFactory

**CintaFactory** is a TODO Describe the product
---

## Technology Stack

| Component           | Technology           |
| ------------------- | -------------------- |
| **Framework**       | Django 5.2.5         |
| **Database**        | SQLite (/PostgreSQL) |
| **Language**        | Python TODO VE       |

---

## Development Setup

### Clone the repository

```bash
git clone https://github.com/your-org/cintafactory.git
cd cintafactory
```

### Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
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

If you deploy the bundled draw.io container, configure the application with:

- `DRAWIO_BASE_URL`: address the Django backend should use to talk to the draw.io service on the Docker network (defaults to `http://drawio:8080`).
- `DRAWIO_PUBLIC_URL`: URL exposed to browsers that should be used inside the iframe (defaults to the same value as `DRAWIO_BASE_URL`; override it for public hosts, e.g. `https://drawio.example.com`).
- `DRAWIO_LIBRARY_BASE_URL`: base URL from which draw.io should fetch custom libraries (set it when draw.io needs a different hostname to reach Django, e.g. `http://web:8000`; if omitted, the application falls back to the host handling the current HTTP request so the feature continues to work).

The docker-compose stacks already pass reasonable defaults; adjust them to match your reverse-proxy/hostnames in production.

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

* Default database: `SQLite` for local development (TODO switch to PostgreSQL).
* Future features: SSO integration, role-based access control, external file storage....
