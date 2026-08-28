# Frontend image: type-checked production build, served on port 3000 with
# /api proxied to the backend.
#
# `vite preview` serves the built bundle (not the dev server) and honours the
# `preview.proxy` block in vite.config.ts, so no extra web server or reverse
# proxy is needed for a single-user local tool.
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .

# Fails the build on a type error, so a broken frontend never ships.
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "3000"]
