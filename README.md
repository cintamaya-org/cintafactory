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

### Create a superuser

```bash
python manage.py createsuperuser
```

### Run the development server

```bash
python manage.py runserver
```

Now open:
-> [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) to access the Django admin interface.

---

## CI/CD

The GitHub Actions workflow in `.github/workflows/deploy.yml` automates testing and deployments:

- Pushes to `dev`, `main`, or any `dev-*` branch always run the Django test suite.
- After a successful push to `dev`, the workflow deploys the code to the shared test stack by executing `deploy/scripts/deploy.sh test` on the VPS.
- After a successful push to `main`, the workflow deploys the code to the production/demo stack by executing `deploy/scripts/deploy.sh prod`.

Each environment uses distinct Docker Compose project names, host ports, and named volumes, allowing the two stacks to run on the same VPS simultaneously without resource conflicts.

### VPS preparation

1. Install Docker Engine (24+) and the Docker Compose plugin on the VPS, and ensure the deploy user can run Docker commands.
2. Create two working directories, for example `/opt/cintafactory/test` and `/opt/cintafactory/prod`.
3. Copy this repository into each directory once, then create:
   - `deploy/env/test.env` (start from `deploy/env/test.env.example`).
   - `deploy/env/prod.env` (start from `deploy/env/prod.env.example`) and set a strong `PROD_DJANGO_SECRET_KEY`. Adjust the ports if required.
4. Confirm that the chosen HTTP ports are free (defaults: `8100` for test, `8000` for production) or override `*_HTTP_PORT` in the environment files.

You can trigger the same deployment steps manually on the VPS via `bash deploy/scripts/deploy.sh test` or `bash deploy/scripts/deploy.sh prod`.

### Required GitHub secrets

Add the following secrets to the repository (or organisation) so the workflow can reach the VPS:

| Secret | Description |
| ------ | ----------- |
| `VPS_HOST` | SSH host name or IP of the VPS. |
| `VPS_USER` | SSH user that can deploy and run Docker. |
| `VPS_SSH_KEY` | Private SSH key (PEM) for that user. |
| `TEST_DEPLOY_PATH` | Absolute path to the test deployment directory (e.g. `/opt/cintafactory/test`). |
| `PROD_DEPLOY_PATH` | Absolute path to the production deployment directory (e.g. `/opt/cintafactory/prod`). |

Secrets stored in `deploy/env/*.env` remain on the VPS—they are excluded from the sync step during deployments.

---

## License

This project is licensed under the **AGPL-3.0 License**.
See the [LICENSE](./LICENSE) file for full details.

---

### Notes

* Default database: `SQLite` for local development (TODO switch to PostgreSQL).
* Future features: SSO integration, role-based access control, external file storage....
