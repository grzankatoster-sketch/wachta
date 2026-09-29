FROM node:22-alpine AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
# Kable i rurociagi. Vite kopiuje ten plik do dist/dane/ (patrz web/vite.config.ts) - musi wiec byc
# w kontekscie budowania, i musi byc TYM SAMYM plikiem, ktory czytaja detektory: mapa i alarm D6
# mowia o tych samych liniach albo o niczym. Sciezka odpowiada ../data/ wzgledem /web.
COPY data/infrastructure/baltic_cables.geojson /data/infrastructure/baltic_cables.geojson
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
