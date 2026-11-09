# Expo web build served by an unprivileged nginx. The same image also proxies /api/* to the
# backend Service, so the browser only ever talks to one origin.
FROM node:22-bookworm-slim AS build

WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Baked into the bundle. Same-origin by default; nginx forwards it to Service backend.
ARG EXPO_PUBLIC_API_URL=/api
ENV EXPO_PUBLIC_API_URL=$EXPO_PUBLIC_API_URL CI=1
RUN npx expo export --platform web --output-dir dist

FROM nginxinc/nginx-unprivileged:1.27-alpine

# The image's user is 101 (nginx). Listens on 8080. The entrypoint renders templates/*.template
# into /tmp/default.conf and nginx.conf includes /tmp/*.conf, so the only writable path at
# runtime is /tmp (an emptyDir in the pod; the root filesystem is read-only).
COPY nginx.conf /etc/nginx/nginx.conf
COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
# BACKEND_UPSTREAM: Service FQDN; nginx's resolver ignores /etc/resolv.conf search domains.
# NGINX_ENTRYPOINT_LOCAL_RESOLVERS: export the pod's nameserver as NGINX_LOCAL_RESOLVERS.
ENV BACKEND_UPSTREAM=backend.team-wearedevs.svc.cluster.local \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    NGINX_ENVSUBST_OUTPUT_DIR=/tmp \
    NGINX_ENVSUBST_FILTER='^(NGINX_LOCAL_RESOLVERS|BACKEND_UPSTREAM)$'

USER 101
EXPOSE 8080
