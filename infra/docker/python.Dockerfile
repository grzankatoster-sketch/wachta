FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY src/python/pyproject.toml src/python/uv.lock ./
RUN uv sync --frozen --no-dev
COPY src/python/ .
ADD https://davidmegginson.github.io/ourairports-data/airports.csv data/airports.csv
# Trasy kabli i rurociagow sa DANYMI PROJEKTU, nie pobieranymi w locie: pochodza z OpenStreetMap
# przez Overpass, ktory przy ciezszych zapytaniach odpowiada 504, wiec pobieranie ich przy kazdej
# budowie obrazu bywaloby losowe. Bez tego pliku D6 startuje z wylaczonym detektorem - widac to
# w logu, ale wleczenie kotwicy po kablu po prostu nie jest liczone.
COPY data/infrastructure/ data/infrastructure/
CMD ["uv", "run", "--no-dev", "python", "-m", "wachta_detectors.run"]
