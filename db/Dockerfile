# LandLens database image: PostGIS 17 + pgvector (spec 2.17).
# Pinned per DEC-003/OQ-33 (manifest resolves for amd64).
FROM postgis/postgis:17-3.6

# Add pgvector for the PostgreSQL 17 server.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-pgvector \
    && rm -rf /var/lib/apt/lists/*

# M0 extension bootstrap (DEC-004/OQ-32): run as the owner role at first init.
COPY initdb/00_extensions.sql /docker-entrypoint-initdb.d/00_extensions.sql

# Tuned settings for a 16 GB laptop (spec 2.17).
COPY postgresql.conf /etc/postgresql/postgresql.conf

CMD ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
