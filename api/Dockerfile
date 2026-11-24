# LandLens API image (spec 2.1, 2.2).
# Base pinned per DEC-003/OQ-33 (manifest resolves for amd64).
FROM python:3.12.16-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for layer caching. psycopg[binary] ships wheels,
# so no libpq build toolchain is needed in M0.
COPY pyproject.toml ./
# Dependencies in their own layer (an empty package stands in for the code), so a code change does not
# re-download numpy, shapely, pymupdf, ... on every build.
RUN mkdir landlens && touch landlens/__init__.py && pip install . && pip uninstall -y landlens-api && rm -rf landlens
COPY landlens ./landlens
RUN pip install --no-deps .

EXPOSE 8000

# Serve the FastAPI app under uvicorn with 2 workers. Access logs come from the app's timing middleware.
CMD ["uvicorn", "landlens.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-access-log"]

# Test image (`make test`, `make concurrency`): the runtime plus pytest and httpx.
FROM runtime AS test
RUN pip install ".[test]"

# Default target: the runtime image (api, migrate, bench).
FROM runtime
