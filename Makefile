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
