# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

# Multi-stage build using openenv-base
# This Dockerfile is flexible and works for both:
# - In-repo environments (with local OpenEnv sources)
# - Standalone environments (with openenv from PyPI/Git)
# The build script (openenv build) handles context detection and sets appropriate build args.

ARG BASE_IMAGE=ghcr.io/meta-pytorch/openenv-base:latest
FROM ${BASE_IMAGE} AS builder

WORKDIR /app

# OSS CAD Suite release to install into the image.
ARG OSS_CAD_SUITE_VERSION=20260407
ARG TARGETARCH

# Ensure git and perl are available (required for installing dependencies from VCS and running Verilator)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git perl perl-modules-5.40 && \
    rm -rf /var/lib/apt/lists/*

# Install OSS CAD Suite so tools like yosys are available in the container.
RUN set -eux; \
    case "${TARGETARCH}" in \
        arm64) asset_arch=arm64 ;; \
        amd64) asset_arch=x64 ;; \
        *) echo "Unsupported target architecture: ${TARGETARCH}" && exit 1 ;; \
    esac; \
    archive="/tmp/oss-cad-suite.tgz"; \
    curl -fsSL -o "${archive}" \
      "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-04-07/oss-cad-suite-linux-${asset_arch}-${OSS_CAD_SUITE_VERSION}.tgz"; \
    top_level_dir="$(tar -tzf "${archive}" | head -n 1 | cut -d/ -f1)"; \
    tar -xzf "${archive}" -C /opt; \
    if [ "${top_level_dir}" != "oss-cad-suite" ]; then \
        mv "/opt/${top_level_dir}" /opt/oss-cad-suite; \
    fi; \
    rm -f "${archive}"

# Build argument to control whether we're building standalone or in-repo
ARG BUILD_MODE=in-repo
ARG ENV_NAME=chipforge

# Copy environment code (always at root of build context)
COPY . /app/env

# For in-repo builds, openenv is already vendored in the build context
# For standalone builds, openenv will be installed via pyproject.toml
WORKDIR /app/env

# Ensure uv is available (for local builds where base image lacks it)
RUN if ! command -v uv >/dev/null 2>&1; then \
        curl -LsSf https://astral.sh/uv/install.sh | sh && \
        mv /root/.local/bin/uv /usr/local/bin/uv && \
        mv /root/.local/bin/uvx /usr/local/bin/uvx; \
    fi
    
# Install dependencies using uv sync
# If uv.lock exists, use it; otherwise resolve on the fly
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-install-project --no-editable; \
    else \
        uv sync --no-install-project --no-editable; \
    fi

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-editable; \
    else \
        uv sync --no-editable; \
    fi

# Final runtime stage
FROM ${BASE_IMAGE}

WORKDIR /app

# Install runtime Perl support for Verilator's wrapper script.
RUN apt-get update && \
    apt-get install -y --no-install-recommends g++ make perl perl-modules-5.40 && \
    rm -rf /var/lib/apt/lists/*

# Copy OSS CAD Suite into the runtime image.
COPY --from=builder /opt/oss-cad-suite /opt/oss-cad-suite

# Copy the virtual environment from builder
COPY --from=builder /app/env/.venv /app/.venv

# Copy the environment code
COPY --from=builder /app/env /app/env

# Set PATH to use the virtual environment
ENV PATH="/opt/oss-cad-suite/bin:/app/.venv/bin:$PATH"

# Set PYTHONPATH so imports work correctly
ENV PYTHONPATH="/app/env:$PYTHONPATH"

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

EXPOSE 7860
# Run the FastAPI server
# Use the package-qualified module path so relative imports resolve correctly.
CMD ["sh", "-c", "cd /app/env && uvicorn server.app:app --host 0.0.0.0 --port 7860"]
