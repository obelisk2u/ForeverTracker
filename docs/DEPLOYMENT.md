# Deployment

## Recommended initial hosting

One Linux VM with Docker Compose runs everything (`docker-compose.prod.yml`): PostgreSQL, a migration job, the API,
the Next.js site and Caddy (automatic HTTPS). A machine with 2 vCPU, 4 GB RAM and 40 GB SSD is a reasonable start for
launch traffic; size it after observing real load. No cloud-specific services are required. **Nothing has been
provisioned**: choosing and paying for a host is a decision for the project owner.

Before going public, also decide on: off-host backup storage, an uptime monitor, and DNS for the domain.

## Environments

| Environment | How | Data |
|---|---|---|
| Development | `docker compose up` (`docker-compose.yml`) | Local Postgres; synthetic data via `python -m app.cli seed` |
| Test | `pytest` against the `forevertracker_test` database | Truncated per test |
| Staging | `docker compose -p forevertracker-staging -f docker-compose.prod.yml --env-file .env.staging up -d` with `ENVIRONMENT=staging` and its own domain | Separate volume; synthetic data allowed |
| Production | `docker compose -f docker-compose.prod.yml --env-file .env up -d` with `ENVIRONMENT=production` | Separate volume; synthetic data refused at ingestion and filtered from responses |

Production refuses to start with development secrets (`ADMIN_TOKEN` shorter than 32 characters or the default,
default `CONTRIBUTOR_ID_SALT`, or synthetic data allowed).

## First deployment

```sh
git clone <repo> /srv/forevertracker && cd /srv/forevertracker
cp deploy/env.example .env && chmod 600 .env   # fill in DOMAIN, ACME_EMAIL and three generated secrets
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
docker compose -f docker-compose.prod.yml logs -f migrate backend
curl https://$DOMAIN/health/ready
```

Point DNS at the host first, so Caddy can obtain the certificate. Secrets live only in `.env` on the host (mode 600,
never committed). To use a secrets manager instead, inject the same variables into the environment.

## Updates

```sh
git pull
docker compose -f docker-compose.prod.yml --env-file .env up -d --build   # migrate runs before backend starts
```

Migrations run in the `migrate` service, and the backend starts only after it succeeds. Take a backup before
deploying a migration.

## Backups and restore

`deploy/backup.sh` writes a compressed `pg_dump` (custom format), verifies it with `pg_restore --list` and keeps 14
days. Schedule it from cron and **copy the files off the host**.

Restore:

```sh
docker compose -f docker-compose.prod.yml stop backend frontend
docker compose -f docker-compose.prod.yml exec -T db dropdb -U forevertracker forevertracker
docker compose -f docker-compose.prod.yml exec -T db createdb -U forevertracker forevertracker
docker compose -f docker-compose.prod.yml exec -T db pg_restore -U forevertracker -d forevertracker --no-owner < backup.dump
docker compose -f docker-compose.prod.yml up -d
```

Test a restore into staging regularly. A backup that has never been restored is unproven.

Raw observations are the system of record. If derived tables are ever suspect, `python -m app.cli rebuild`
recomputes runs and statistics from them.

## Scaling

In the order you are likely to need them:

1. **Cache public pages** with a CDN in front of Caddy (API responses already send `Cache-Control`).
2. **More API replicas** (`WEB_CONCURRENCY`, or more containers). Move the in-process rate limiter to Redis first.
3. **Managed PostgreSQL** with automated backups and a read replica for public reads.
4. **Ingestion worker**: accept uploads into `upload_batches` and process them asynchronously; partition the
   ingestion advisory lock by namespace and dungeon.
5. **Partition** `raw_observations` and `metric_observations` by month.

## Performance notes (measured, development machine)

* Through Docker Desktop's port forwarding on Windows, some mid-size PostgreSQL messages took about 50 ms
  (Nagle/delayed-ACK behaviour of the port proxy). From a container on the compose network the same operations took
  0.12–0.84 ms. Run seeds and benchmarks inside compose: `docker compose exec backend python -m app.cli seed`.
* Seeding the default synthetic dataset (2,754 batches, 5,589 observations, 1,200 runs) inside compose took 228 s
  (about 12 batches/s) on the development machine. Production hardware has not been measured.
