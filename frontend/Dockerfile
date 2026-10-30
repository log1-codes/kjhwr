# frontend/Dockerfile

# Stage 1: Build production React + Vite bundle
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Production Nginx web server
FROM nginx:alpine

# Copy compiled static assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy Nginx template (supports dynamic BACKEND_URL via envsubst)
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Ensure only BACKEND_URL is replaced by envsubst, preserving Nginx variables ($host, $uri, etc.)
ENV NGINX_ENVSUBST_FILTER=BACKEND_URL
ENV BACKEND_URL=http://backend:8000

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
