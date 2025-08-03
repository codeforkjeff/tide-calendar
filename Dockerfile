
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /opt/tide-calendar

COPY pyproject.toml uv.lock .

RUN uv sync --locked

ENV PATH="/opt/tide-calendar/.venv/bin:$PATH"

COPY . .

EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app"]
