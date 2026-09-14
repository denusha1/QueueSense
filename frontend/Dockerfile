FROM node:22-alpine AS builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
COPY data/sample /app/data/sample
RUN npm run build
FROM node:22-alpine
WORKDIR /app/frontend
ENV NODE_ENV=production
COPY --from=builder /app /app
USER node
EXPOSE 3000
CMD ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
