# ---------------------------------------------------------
# Stage 1: Build the React (Vite) app
# ---------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

# Install deps first (better layer caching)
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the source and build
COPY . .
RUN npm run build

# ---------------------------------------------------------
# Stage 2: Serve the built app with nginx
# ---------------------------------------------------------
FROM nginx:alpine

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy build output from stage 1
COPY --from=build /app/dist /usr/share/nginx/html

# NOTE: this repo's real nginx.conf lives at the REPO ROOT, not in frontend/.
# If you build this Dockerfile standalone, you must first copy it in, e.g.:
#   cp ../nginx.conf ./nginx.conf   (run from frontend/ before "docker build")
# Prefer building the ROOT Dockerfile via docker-compose instead - it already
# copies the correct nginx.conf and also runs the FastAPI backend, so /api and
# /docs actually work. This standalone frontend image serves static files ONLY.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Must match the "listen" port inside nginx.conf (5378)
EXPOSE 5378

CMD ["nginx", "-g", "daemon off;"]
