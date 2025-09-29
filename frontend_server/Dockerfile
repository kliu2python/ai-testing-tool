# syntax=docker/dockerfile:1
FROM node:20-alpine AS build

WORKDIR /app

COPY ./package*.json ./
RUN npm ci

COPY ./ ./
RUN npm run build

FROM nginx:1.27-alpine

RUN mkdir -p /etc/nginx/certs

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY tls.crt /etc/nginx/certs/tls.crt
COPY tls.key /etc/nginx/certs/tls.key
RUN chmod 600 /etc/nginx/certs/tls.key && \
    chmod 644 /etc/nginx/certs/tls.crt

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
