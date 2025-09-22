# syntax=docker/dockerfile:1
FROM node:20-alpine AS build

WORKDIR /app

COPY frontend_server/package*.json ./
RUN npm ci

COPY frontend_server/ ./
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
