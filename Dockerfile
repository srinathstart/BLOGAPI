# A Dockerfile is a recipe: each line is a step Docker runs to build an "image"
# — a frozen, portable snapshot of our app + everything it needs to run. A host
# (Render/Railway/Fly) then runs that image as a "container". No venv, no "works
# on my machine": the image carries its own Python and libraries.

# ---- Base image ----
# Start FROM an official Python image instead of building Python ourselves.
# "3.13" matches the Python our venv uses; "-slim" is a stripped-down Debian
# (no compilers/docs) — a much smaller image, which means faster deploys.
FROM python:3.13-slim

# ---- Environment settings for Python inside the container ----
# PYTHONDONTWRITEBYTECODE=1 : don't litter the image with .pyc files (pointless
#   in a throwaway container).
# PYTHONUNBUFFERED=1 : send print()/log output straight to the terminal instead
#   of buffering it, so the host's log viewer shows our logs in real time.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ---- Where our code lives inside the image ----
# Every command after this runs from /code. We deliberately use /code (NOT /app)
# so it doesn't clash with our Python package, which is also called "app": the
# package will sit at /code/app, and "app.main:app" still imports cleanly.
WORKDIR /code

# ---- Install dependencies FIRST (before copying the code) ----
# Docker caches each step. By copying ONLY requirements.txt first and installing,
# this expensive step is re-run ONLY when requirements.txt changes — editing our
# own code won't trigger a full reinstall. That's the single biggest build-speed
# win, so it's worth the two-step copy.
COPY requirements.txt .

# --no-cache-dir : don't keep pip's download cache in the image (smaller image).
# --upgrade pip : start from a current pip so wheels install cleanly.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- Now copy the application code ----
# Copy the local ./app folder into /code/app. (The .dockerignore file decides
# what is EXCLUDED — venv, .env, tests, etc. — so secrets never enter the image.)
COPY ./app ./app

# ---- Run as a non-root user (security) ----
# By default a container runs as root; if the app were ever exploited, root
# inside the container is a bigger blast radius. Create an unprivileged user and
# switch to it. -m makes a home dir; then chown /code so the app can read it.
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /code
USER appuser

# ---- Document the port ----
# EXPOSE is documentation only (it doesn't actually open a port). It signals that
# the app listens on 8000 by default. Cloud hosts inject their own $PORT (see CMD).
EXPOSE 8000

# ---- The start command ----
# CMD is what runs when the container starts. "fastapi run" is the PRODUCTION
# counterpart to the "fastapi dev" we use locally: no auto-reload, tuned for
# serving. It wraps uvicorn (an ASGI server) under the hood.
#   --host 0.0.0.0 : listen on ALL interfaces, not just localhost — required so
#     traffic from OUTSIDE the container can reach the app.
#   --port ${PORT:-8000} : use the host-provided $PORT if set (Render/Railway/Fly
#     pick the port and pass it in via that env var), else fall back to 8000
#     for local runs. Shell form (with the bash -c) is what lets ${PORT} expand.
CMD ["sh", "-c", "fastapi run app/main.py --host 0.0.0.0 --port ${PORT:-8000}"]
