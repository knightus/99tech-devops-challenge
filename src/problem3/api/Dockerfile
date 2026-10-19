FROM node:20-alpine

ENV NODE_ENV=production
WORKDIR /app

# Install exactly what package-lock.json pins, so every build of the same
# commit ships the same dependency tree.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY src ./src

# Do not run the app as root inside the container.
USER node

CMD ["node", "src/index.js"]
