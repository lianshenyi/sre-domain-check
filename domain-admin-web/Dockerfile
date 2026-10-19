FROM node:18-alpine AS build

# 构建期 npm 源：默认官方源，国内构建传 --build-arg NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_REGISTRY=https://registry.npmjs.org

WORKDIR /app

COPY package*.json ./
RUN npm config set registry "${NPM_REGISTRY}" \
    && if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .
ARG VITE_APP_API=/api
ARG VITE_BASE_URL=/
RUN printf "NODE_ENV=production\nVITE_APP_API=%s\nVITE_BASE_URL=%s\n" "$VITE_APP_API" "$VITE_BASE_URL" > .env.production \
    && npm run build

FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
