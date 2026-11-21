# LandLens API image (spec 2.1, 2.2).
# Base pinned per DEC-003/OQ-33 (manifest resolves for amd64).
FROM python:3.12.16-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for layer caching. psycopg[binary] ships wheels,
# so no libpq build toolchain is needed in M0.
COPY pyproject.toml ./
COPY landlens ./landlens
RUN pip install .

EXPOSE 8000

# Serve the FastAPI app under uvicorn with 2 workers.
CMD ["uvicorn", "landlens.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
