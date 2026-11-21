# LandLens web image (spec 2.1, 2.17): Next.js production build, then `next start`.
# Base pinned per DEC-003/OQ-33 (node:22 per spec 2.17; manifest resolves for amd64).
FROM node:22.23.4-bookworm-slim

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

# Install dependencies first for layer caching. devDependencies (typescript,
# tailwindcss, @types/*) are needed to run `next build`, so include them even
# though NODE_ENV=production (approved deviation, T-M0-4). T-M0-4b: reproducible
# installs with npm ci from package-lock.json.
COPY package.json package-lock.json ./
RUN npm ci --include=dev

# Build the production bundle.
COPY . .
RUN npm run build

EXPOSE 3000

# Serve the production build (not the dev server).
CMD ["npm", "run", "start"]
