# Repo-Root-Dockerfile für Railway - siehe docs/superpowers/plans/2026-08-16-production-hosting.md.
#
# Ersetzt den ursprünglich geplanten Nixpacks-Build: drei aufeinander-
# folgende Versuche, die für pillow-heif/mediapipe/opencv nötige
# libstdc++.so.6 über Nixpacks' nixPkgs/aptPkgs-Mechanismen bereitzustellen,
# sind gescheitert (Nix-gebautes Python sucht nicht in Standard-System-
# Pfaden, ein manuelles LD_LIBRARY_PATH hat stattdessen das System-libc
# vor das inkompatible Nix-libc geschoben und Python selbst zum Absturz
# gebracht). Ein normales Debian-basiertes Python-Image (python:3.12-slim)
# hat dieses Problem nicht: apt-get installierte Bibliotheken landen in
# den ldconfig-Standardpfaden, die ein normal gebautes Python ohnehin
# durchsucht - keine Nix-Eigenheiten, kein manuelles Pfad-Gefrickel nötig.

# --- Stage 1: Frontend bauen ---
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build && npx tsc --noEmit

# --- Stage 2: Backend + fertiges Image ---
FROM python:3.12-slim

# Laufzeit-Bibliotheken für pillow-heif (HEIC) und mediapipe/opencv
# (Posen-Normalisierung) - siehe Kommentar oben zur Historie.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libstdc++6 libgl1 libegl1 libgles2 libglib2.0-0 libsm6 libxext6 \
    libxrender1 libgomp1 libx11-6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=frontend-build /app/frontend/dist frontend/dist

WORKDIR /app/backend

# Tests als Deploy-Gate: schlägt dieser Schritt fehl, bricht der
# Docker-Build ab und es wird nichts Kaputtes deployed (siehe Design-Spec
# Abschnitt "Testing als Deploy-Gate").
RUN python -m pytest -q

ENV PORT=8000
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
