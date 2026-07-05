# Neubit FRS frontend — Next.js dev container (hot-reload).
FROM node:20-alpine

WORKDIR /app

# Install deps first for layer caching. --legacy-peer-deps: dashcode's peer set.
COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps

# Source is bind-mounted in compose for hot reload; copy for standalone builds too.
COPY . .

EXPOSE 3000

# Poll-based file watching so hot reload works reliably on Docker Desktop (macOS).
ENV WATCHPACK_POLLING=true

CMD ["npm", "run", "dev"]
