FROM python:3.12-slim

ARG REF=main

LABEL maintainer="iain.emsley@warwick.ac.uk"
LABEL org.opencontainers.image.source="https://github.com/iaine/app_histories"
LABEL org.opencontainers.image.description="CIM App Histories toolkit"

# Environment
ENV MPLBACKEND=Agg \
    PYTHONDONTWRITEBYTECODE=1

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git \
        libxml2-dev \
        libxslt1-dev; \
    pip install --no-cache-dir --upgrade pip; \
    pip install --no-cache-dir \
        "git+https://github.com/iaine/app_histories.git@${REF}"; \
    apt-get purge -y git; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*

# Basic build-time verification (equivalent to %test)
RUN cim-apps --version && \
    python -c "import cim_app_histories.ab.ab, cim_app_histories.localisation.localisation"

ENTRYPOINT ["cim-apps"]
CMD ["--help"]