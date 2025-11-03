

#  CintaFactory — Developer Guide


---

##  Launch the Development Stack

Run the development containers using the dedicated `docker-compose.dev.yml` file.

```bash
docker compose -f docker-compose.dev.yml up
````

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


docker compose -f docker-compose.dev.yml exec web python manage.py migrate


| Collect static files (if needed)        | `docker compose -f docker-compose.dev.yml exec web python manage.py collectstatic --noinput` |
| --------------------------------------- | -------------------------------------------------------------------------------------------- |



---

## Logging & Observability

- Django routes every log through `cintafactory.logging_utils`, enriching records with request identifiers and user data when available. Prefer the helpers (`log_info`, `log_warning`, etc.) over raw `logging` calls to keep structured extras aligned.
- Console output stays human-readable; JSON lines land in `logs/application.jsonl` with rotation unless `RUNNING_IN_DOCKER=1` or `DJANGO_LOG_TO_STDOUT=1`, in which case only stdout/stderr are used so containers remain stateless.
- Attach a webhook with `LOG_CRITICAL_WEBHOOK=https://hooks/...` to receive critical alerts; if unset, the handler falls back to stderr so nothing is lost.
- Keep sensitive payloads out of log messages. The sanitiser masks common keys but cannot protect secrets accidentally written into the message text—log identifiers instead of raw data.
- Sampling reduces noisy subsystems (`django.db.backends` defaults to 10% of INFO-level events). Override with `LOG_SAMPLING_RATES=module.name:rate,module2:rate`.
- After deploys, run `python manage.py shell -c "from cintafactory.logging_utils import log_info; log_info('log-pipeline-check')"` to verify the pipeline end-to-end.

---
