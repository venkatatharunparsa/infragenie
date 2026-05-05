# ================================================================
# InfraGenie Backend — Dockerfile
# Multi-stage-aware single-stage build for local development.
# Installs Terraform, tfsec, Infracost, and Checkov alongside
# the Python application so every tool is available at runtime.
# ================================================================

FROM python:3.11-slim

# ── System metadata ────────────────────────────────────────────
LABEL maintainer="infragenie"
LABEL description="InfraGenie FastAPI backend with Terraform toolchain"

# ── Avoid interactive prompts during apt installs ──────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ── Versions (pin for reproducibility) ────────────────────────
ARG TERRAFORM_VERSION=1.8.1
ARG TFSEC_VERSION=1.28.6
ARG INFRACOST_VERSION=0.10.39

# ── System dependencies ────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        unzip \
        git \
        gnupg \
        ca-certificates \
        wget \
    && rm -rf /var/lib/apt/lists/*

# ── Terraform ─────────────────────────────────────────────────
RUN ARCH=$(dpkg --print-architecture) \
    && if [ "$ARCH" = "arm64" ]; then TF_ARCH="arm64"; else TF_ARCH="amd64"; fi \
    && TF_URL="https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${TF_ARCH}.zip" \
    && CHECKSUM_URL="https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_SHA256SUMS" \
    && curl -fsSL "$TF_URL" -o /tmp/terraform.zip \
    && curl -fsSL "$CHECKSUM_URL" -o /tmp/terraform_SHA256SUMS \
    && grep "linux_${TF_ARCH}.zip" /tmp/terraform_SHA256SUMS | sha256sum -c - \
    && unzip /tmp/terraform.zip -d /tmp/terraform_bin \
    && mv /tmp/terraform_bin/terraform /usr/local/bin/terraform \
    && chmod +x /usr/local/bin/terraform \
    && rm -rf /tmp/terraform.zip /tmp/terraform_SHA256SUMS /tmp/terraform_bin \
    && terraform version

# ── tfsec ─────────────────────────────────────────────────────
RUN ARCH=$(dpkg --print-architecture) \
    && if [ "$ARCH" = "arm64" ]; then TFSEC_ARCH="arm64"; else TFSEC_ARCH="amd64"; fi \
    && curl -fsSL "https://github.com/aquasecurity/tfsec/releases/download/v${TFSEC_VERSION}/tfsec-linux-${TFSEC_ARCH}" \
        -o /usr/local/bin/tfsec \
    && chmod +x /usr/local/bin/tfsec \
    && tfsec --version

# ── Infracost ─────────────────────────────────────────────────
RUN ARCH=$(dpkg --print-architecture) \
    && if [ "$ARCH" = "arm64" ]; then IC_ARCH="arm64"; else IC_ARCH="amd64"; fi \
    && curl -fsSL "https://github.com/infracost/infracost/releases/download/v${INFRACOST_VERSION}/infracost-linux-${IC_ARCH}.tar.gz" \
        -o /tmp/infracost.tar.gz \
    && tar -xzf /tmp/infracost.tar.gz -C /tmp \
    && mv /tmp/infracost-linux-${IC_ARCH} /usr/local/bin/infracost \
    && chmod +x /usr/local/bin/infracost \
    && rm /tmp/infracost.tar.gz \
    && infracost --version

# ── Python dependencies (including Checkov) ────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir checkov pytest pytest-asyncio

# Verify Checkov
RUN checkov --version

# ── Application source ─────────────────────────────────────────
COPY . .

# ── Runtime directories ────────────────────────────────────────
RUN mkdir -p /terraform_workspace /chroma_db /knowledge

# ── Port ──────────────────────────────────────────────────────
EXPOSE 8000

# ── Healthcheck ───────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Entrypoint ────────────────────────────────────────────────
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
