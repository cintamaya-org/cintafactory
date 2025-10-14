


# CintaFactory

**CintaFactory** is a TODO Describe the product
---

## Technology Stack

| Component           | Technology           |
| ------------------- | -------------------- |
| **Framework**       | Django 5.2.5         |
| **Database**        | SQLite (/PostgreSQL) |
| **Language**        | Python TODO VE       |

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


## TODO — CI/CD Setup

This section will describe how the project is built, tested, and deployed once the CI/CD pipeline is fully defined*.

**Planned content:**

* ✅ GitHub Actions / GitLab CI pipeline example
* ✅ Docker build and test workflow
* ✅ Auto‑deployment

*(To be completed once the CI/CD configuration is in place.)*

---

## License

This project is licensed under the **AGPL-3.0 License**.
See the [LICENSE](./LICENSE) file for full details.

---

### Notes

* Default database: `SQLite` for local development (TODO switch to PostgreSQL).
* Future features: SSO integration, role-based access control, external file storage....
