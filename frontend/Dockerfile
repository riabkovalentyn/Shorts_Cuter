# Frontend Dockerfile
FROM node:20-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM deps AS build
WORKDIR /app
COPY tsconfig.json vite.config.ts tailwind.config.js postcss.config.js index.html ./
COPY src ./src
RUN npm run build

FROM nginx:1.27-bookworm AS runner
WORKDIR /usr/share/nginx/html
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
