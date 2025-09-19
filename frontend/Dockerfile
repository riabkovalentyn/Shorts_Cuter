# Frontend Dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM deps AS build
WORKDIR /app
COPY tsconfig.json vite.config.ts tailwind.config.js postcss.config.js index.html ./
COPY src ./src
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /usr/share/nginx/html
# Use nginx to serve static files
RUN apk add --no-cache nginx && rm -rf /var/cache/apk/*
COPY --from=build /app/dist ./
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
