#!/usr/bin/env node
/**
 * 多多贝反馈中心 · 三平台复用部署脚本
 *
 * 复用文档站（docs）的 VitePress 构建产物，按 EdgeOne(主) → Cloudflare(备) → Vercel(兜底)
 * 优先级部署反馈站（feedback.duoduobei.com）。
 *
 * 用法：
 *   node feedback/deploy.mjs eo        # 部署到 EdgeOne Pages（主）
 *   node feedback/deploy.mjs cf        # 部署到 Cloudflare Pages（备）
 *   node feedback/deploy.mjs vercel    # 部署到 Vercel（兜底）
 *   node feedback/deploy.mjs all       # 依次部署三平台
 *
 * 前置：
 *   - pnpm install 已完成（vitepress 在根 devDependencies）
 *   - EdgeOne CLI / wrangler / vercel CLI 已登录对应账号
 *   - 环境变量 EO_PROJECT_ID / CLOUDFLARE_API_TOKEN 等按需注入
 */
import { execSync } from 'node:child_process'
import { resolve } from 'node:path'

const ROOT = resolve(process.cwd())
const OUT = resolve(ROOT, 'feedback/.vitepress/dist')

function run(cmd, opts = {}) {
  console.log(`\n▶ ${cmd}`)
  execSync(cmd, { stdio: 'inherit', cwd: ROOT, ...opts })
}

function build() {
  console.log('🔨 构建反馈站（VitePress）...')
  run('pnpm run feedback:build')
}

const targets = {
  eo: () => {
    // EdgeOne Pages：优先用 edgeone 官方 CLI；回退到 eo deploy
    try {
      run(`npx edgeone pages deploy ${OUT} --name duoduobei-feedback`)
    } catch {
      run(`eo deploy ${OUT} --project duoduobei-feedback`)
    }
  },
  cf: () => {
    run(`npx wrangler pages deploy ${OUT} --project-name=duoduobei-feedback`)
  },
  vercel: () => {
    run(`npx vercel deploy ${OUT} --prod --name duoduobei-feedback`)
  },
}

const arg = process.argv[2] || 'all'
build()

if (arg === 'all') {
  for (const k of ['eo', 'cf', 'vercel']) targets[k]()
} else if (targets[arg]) {
  targets[arg]()
} else {
  console.error(`未知目标: ${arg}（可选: eo | cf | vercel | all）`)
  process.exit(1)
}

console.log('\n✅ 反馈站部署完成')
