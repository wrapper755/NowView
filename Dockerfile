# NowView 앱 (Next.js)
#
# 멀티 스테이지 — 빌드 산출물만 런타임 이미지에 넣는다.
# `output: "standalone"`(next.config.ts) 덕분에 node_modules 전체를 복사하지 않는다.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# 락파일 기준으로 정확히 재현한다. 어긋나면 여기서 실패한다 — CI와 같은 몫이다.
RUN npm ci


FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# 데이터가 전부 Mock 코드라 빌드 시점에 환경 변수나 비밀값이 필요 없다.
# ENGINE_URL은 런타임에 읽으므로 여기서 굽지 않는다.
RUN npm run build


FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# root로 돌리지 않는다.
RUN addgroup -g 1001 -S nodejs && adduser -u 1001 -S nextjs -G nodejs

# standalone은 서버와 최소 node_modules를 담고 있다. static과 public은 별도로 넣어야 한다 —
# 빠뜨리면 페이지는 뜨는데 CSS·JS가 404가 난다.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

# standalone 산출물의 진입점이다 (`next start`가 아니다).
CMD ["node", "server.js"]
