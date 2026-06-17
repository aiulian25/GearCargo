# GearCargo - Development & Security Tasks

IMAGE_TAG ?= gearcargo:latest

# ============================================================
# Security Scanning
# ============================================================

.PHONY: scan lint scan-trivy scan-grype scan-all

## Run all security scans
scan-all: lint scan-trivy scan-grype

## Lint the Dockerfile with hadolint
lint:
	@echo "==> Linting Dockerfile..."
	hadolint Dockerfile --ignore DL3008

## Scan image for vulnerabilities with Trivy
scan-trivy:
	@echo "==> Trivy scan on $(IMAGE_TAG)..."
	trivy image --exit-code 1 --severity HIGH,CRITICAL $(IMAGE_TAG)

## Scan image for vulnerabilities with Grype
scan-grype:
	@echo "==> Grype scan on $(IMAGE_TAG)..."
	grype $(IMAGE_TAG) --fail-on high

## Quick scan (Trivy only, no fail)
scan:
	@echo "==> Quick Trivy scan on $(IMAGE_TAG)..."
	trivy image --severity HIGH,CRITICAL $(IMAGE_TAG)

## Generate SBOM with Syft
sbom:
	@echo "==> Generating SBOM for $(IMAGE_TAG)..."
	syft $(IMAGE_TAG) -o spdx-json > sbom.json
	@echo "SBOM written to sbom.json"

# ============================================================
# Source Dependency Scanning (S13 — mirrors the CI "Dependency Audit" workflow)
# Scans the SOURCE manifests (requirements.txt / package-lock.json),
# complementing the image-level scans above (Trivy/Grype/Syft).
# ============================================================

.PHONY: audit audit-py audit-js

## Audit Python dependencies for known CVEs (needs: pip install pip-audit)
audit-py:
	@echo "==> pip-audit on backend/requirements.txt..."
	pip-audit -r backend/requirements.txt --desc

## Audit frontend dependencies for known CVEs (npm audit, fails on high+)
audit-js:
	@echo "==> npm audit (high+) on frontend..."
	cd frontend && npm audit --audit-level=high

## Audit ALL source dependencies (Python + npm)
audit: audit-py audit-js
