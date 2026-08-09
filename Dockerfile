# Pinned to the interpreter both verified room builds ran on. A floating tag
# would let a base-image bump land between a rehearsal and the real demo.
FROM python:3.12.12-slim

# Cloud Run sends SIGTERM and gives 10s before SIGKILL. Running uvicorn as PID 1
# without an init means it, not the shell, receives that signal.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependency layer first: pyproject alone changes far less often than source,
# so a code edit does not reinstall google-adk.
# research_dept/ is listed in pyproject.toml's explicit [tool.setuptools]
# packages, so setuptools requires the directory to exist even though
# nothing in star/ imports it at runtime (it's the `adk web` dev entry point).
COPY pyproject.toml README.md ./
COPY star/ ./star/
COPY research_dept/ ./research_dept/
RUN pip install --no-cache-dir .

COPY web/ ./web/

# Cloud Run supplies PORT and it is not always 8080. Honour it.
ENV PORT=8080
CMD exec uvicorn star.server:app --host 0.0.0.0 --port ${PORT}
