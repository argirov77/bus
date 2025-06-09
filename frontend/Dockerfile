# --- STAGE 1: сборка React-приложения ---
FROM node:18-alpine AS node_builder

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend ./
RUN npm run build

# --- STAGE 2: отдача статических файлов через nginx ---
FROM nginx:stable-alpine

COPY --from=node_builder /app/build /usr/share/nginx/html
# (опционально) свой конфиг nginx
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
