# ─── Stage 1: Builder ────────────────────────────────────────────────────────
# python:3.12-slim ships only the interpreter and stdlib.
# "slim" is smaller than the full image but still glibc-based, which matters
# because asyncpg and pdfplumber both compile C extensions at install time.
# Alpine uses musl libc and breaks those extensions without extra patching.
FROM python:3.12-slim AS builder

# PYTHONDONTWRITEBYTECODE — skip .pyc files; containers are ephemeral so the
#   startup speedup .pyc files provide is irrelevant and the files waste space.
# PYTHONUNBUFFERED — send stdout/stderr straight to the terminal without
#   buffering; essential so log lines appear in docker logs in real time.
# PIP_NO_CACHE_DIR — pip's download cache has no value inside a build layer.
# PIP_DISABLE_PIP_VERSION_CHECK — suppresses the "new pip available" banner
#   that otherwise pollutes build output.
# HF_HOME — tells sentence-transformers (and any HuggingFace library) where
#   to store downloaded models. Using /app/models puts it in a predictable
#   location we can COPY into the runtime stage.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/models

WORKDIR /build

# gcc — required to compile asyncpg, which ships as a C extension.
# libpq-dev — PostgreSQL client headers required by asyncpg at compile time.
# --no-install-recommends — skip packages that apt suggests but we do not need.
# Clearing /var/lib/apt/lists in the same RUN layer prevents those lists from
# being committed to the image layer even though we delete them later.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only the dependency manifest first.
# Docker caches each RUN/COPY instruction as its own layer. If only app source
# changes (not pyproject.toml), every layer up to this point stays cached and
# the full pip install is skipped on the next build.
COPY pyproject.toml ./

# pip-tools reads pyproject.toml and produces a fully-pinned requirements.txt.
# Pinned deps mean the image is reproducible: two builds from the same commit
# produce the same bytes. Without pinning, a transitive dep update could
# silently change behavior between builds.
RUN pip install --no-cache-dir pip-tools \
    && pip-compile pyproject.toml --quiet --output-file /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt

# Copy source only after deps are installed. A code change now only invalidates
# this layer and the one below — not the expensive pip install.
COPY . .

# --no-deps installs just our package entry points and metadata without
# reinstalling anything that pip already placed in site-packages above.
RUN pip install --no-cache-dir --no-deps .

# Download the embedding model into the image.
# Baking it in means the container has zero runtime dependency on the
# Hugging Face CDN. A missing CDN endpoint or network policy cannot
# prevent the container from starting.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"


# ─── Stage 2: Runtime ────────────────────────────────────────────────────────
# Fresh base image. Nothing from the builder — gcc, libpq-dev, pip-tools,
# the pip cache, intermediate build artefacts — leaks into the final image.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/models

# libpq5 — the PostgreSQL client library that asyncpg links against at
#   runtime. The -dev headers from the builder are not needed here.
# curl — used by the HEALTHCHECK below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user. If the container is ever compromised, the attacker
# gets uid 1001, not root. This also prevents the app from accidentally
# writing to system paths inside the container.
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy the compiled Python packages from the builder stage.
# Only site-packages and bin entries travel; the build tools stay behind.
COPY --from=builder /usr/local/lib/python3.12/site-packages \
                    /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# boto3 added here (not in builder) so the large site-packages COPY above stays cached.
RUN pip install --no-cache-dir "boto3>=1.34"

# Copy the pre-downloaded embedding model. --chown sets ownership in a single
# layer instead of a separate RUN chown, which would double the layer size
# because Docker snapshots files before and after the chown.
COPY --from=builder --chown=appuser:appgroup /app/models /app/models

# Copy application source last. This layer is the most likely to change,
# so keeping it at the bottom maximises cache reuse for everything above.
COPY --chown=appuser:appgroup . .

# Drop privileges before any process runs.
USER appuser

# Document which port the process listens on. EXPOSE is metadata only —
# it does not publish the port. docker-compose handles the actual binding.
EXPOSE 8000

# Poll the health endpoint every 30 s.
# --start-period=40s gives the app time to load the embedding model and
# complete startup before the first check fires. Failures during the start
# period do not count against --retries.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Use exec form (JSON array) so uvicorn is PID 1 and receives SIGTERM
# directly from Docker. Shell form would make sh PID 1, and uvicorn would
# never receive the signal, causing a hard kill after the stop timeout.
# --no-access-log suppresses uvicorn's own request log lines; our middleware
# in main.py already logs every request as structured JSON.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--no-access-log"]
