

#  CintaFactory — Developer Guide


---

##  Launch the Development Stack

Run the development containers using the dedicated `docker-compose.dev.yml` file.

```bash
docker compose -f docker-compose.dev.yml up
````

➡️ This will:

* Start the **PostgreSQL** database.
* Start the **Django development server** with `python manage.py runserver 0.0.0.0:8000`.
* Automatically **reload** the app when you change any `.py`, `.html`, or `.css` file.

You can access the app locally at:

 [http://localhost:8101](http://localhost:8101)

---

##  Rebuild When Dependencies Change (rare)

If you modify `requirements.txt` or the `Dockerfile`, rebuild your image once:

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

>  You **don’t** need to rebuild for normal code changes — only when installing or removing Python packages.

---

##  Create a Superuser (Admin Account)

If this is your first run and you need an admin account for Django:

```bash
docker compose -f docker-compose.dev.yml exec web python manage.py createsuperuser
```

Then follow the prompts:

```
Username: admin
Email address: admin@example.com
Password:
Password (again):
```

Once created, you can log in to the Django admin panel:

👉 [http://localhost:8101/admin/](http://localhost:8101/admin/)

---

## 🧹 Useful Commands

| Action                                  | Command                                                                                      |
| --------------------------------------- | -------------------------------------------------------------------------------------------- |
| Stop the stack                          | `docker compose -f docker-compose.dev.yml down`                                              |
| View logs                               | `docker compose -f docker-compose.dev.yml logs -f`                                           |
| Access a shell inside the web container | `docker compose -f docker-compose.dev.yml exec web bash`                                     |
| Apply migrations manually               | `docker compose -f docker-compose.dev.yml exec web python manage.py migrate`                 |
| Collect static files (if needed)        | `docker compose -f docker-compose.dev.yml exec web python manage.py collectstatic --noinput` |

---
