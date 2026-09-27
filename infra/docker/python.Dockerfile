FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY src/python/pyproject.toml src/python/uv.lock ./
RUN uv sync --frozen --no-dev
COPY src/python/ .
ADD https://davidmegginson.github.io/ourairports-data/airports.csv data/airports.csv
CMD ["uv", "run", "--no-dev", "python", "-m", "wachta_detectors.run"]
