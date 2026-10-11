FROM node:24-bookworm-slim AS deps
WORKDIR /app
RUN npm install --global pnpm@11.25.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM deps AS build
ENV NEXT_TELEMETRY_DISABLED=1
COPY . .
RUN pnpm build

FROM node:24-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN groupadd --gid 10001 suni && useradd --uid 10001 --gid suni --create-home suni
COPY --from=build --chown=suni:suni /app/.next/standalone ./
COPY --from=build --chown=suni:suni /app/.next/static ./.next/static
COPY --from=build --chown=suni:suni /app/public ./public
USER 10001:10001
EXPOSE 3000
CMD ["node", "server.js"]
