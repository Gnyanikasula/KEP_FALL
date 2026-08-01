# KEP_FALL - Phase D runtime image.
# Prerequisite: the Chroma index must be built BEFORE `docker build`:
#     python -m kep_fall.phase_d_engine.vector_store

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

# Dependencies first - this layer survives code changes.
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Pre-warm the embedding model so the first query is not a cold start.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)"

# Application package, the pre-built Chroma index, and the runtime data the
# engine reads. .dockerignore excludes the build-only artefacts.
COPY --chown=user kep_fall/    ./kep_fall/
COPY --chown=user chroma_db/ ./chroma_db/

RUN mkdir -p data/cache

ENV PYTHONPATH=/home/user/app \
    HISTORY_DB_PATH=/home/user/app/data/cache/kep_fall_history.db \
    PORT=7860

EXPOSE 7860
CMD ["uvicorn", "kep_fall.phase_d_engine.api:app", "--host", "0.0.0.0", "--port", "7860"]