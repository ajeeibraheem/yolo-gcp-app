FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm i
COPY . .
RUN npm run build
FROM node:20-alpine
ENV NODE_ENV=production
WORKDIR /app
COPY --from=build /app/.output ./.output
EXPOSE 3000
CMD ["node",".output/server/index.mjs"]
