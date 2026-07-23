FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite bakes these into the static bundle at build time — there's no
# runtime env var equivalent for a static SPA, unlike the API.
ARG VITE_ENTRA_TENANT_ID
ARG VITE_ENTRA_SPA_CLIENT_ID
ARG VITE_API_CLIENT_ID
ARG VITE_API_BASE_URL
ENV VITE_ENTRA_TENANT_ID=$VITE_ENTRA_TENANT_ID
ENV VITE_ENTRA_SPA_CLIENT_ID=$VITE_ENTRA_SPA_CLIENT_ID
ENV VITE_API_CLIENT_ID=$VITE_API_CLIENT_ID
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
