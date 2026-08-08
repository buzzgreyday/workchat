# Database

Stop docker-compose to keep data and tables, the following will remove data and tables:
```bash
docker compose down -v
```

To build after development.
```bash
docker compose up --build
```

Use Alembic if docker container was taken down or schemas was changed:
```bash
docker compose exec backend alembic upgrade head
```
