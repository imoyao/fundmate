// frontend/build/supabase-env-guard.ts
//
// 目的（#1028）：把「开发与生产必须指向**不同的** Supabase 项目」从文档约定变成机器判据。
//
// 为什么需要它：
//   `frontend/.env.development` 是**不入库**的本地文件，CI 看不到它 → 任何「仓库内静态检查」
//   都无法证明 dev 与 prod 已隔离。真正出过事的形态是：dev 文件里的 VITE_SUPABASE_URL 与
//   `.env.production` 指向同一个项目 ⇒ 开发期注册的测试账号直接写进**生产** Auth 用户表，
//   且没有任何报错。本守卫接在 **dev server 启动**这个真实入口上，命中即拒绝启动。
//
// 本文件只管**本地态**（CI 看不到的那些文件）；仓库内入库文件的规则归
// `scripts/guard_supabase_env_separation.py`（CI 拦合并）。两条规则不重叠、各有唯一实现。
//
// 判据边界（重要，不要越界）：
//   - 比对对象 = **Vite 解析后的 dev 值** vs **入库的 .env.production 的值**。
//     用解析后的值（而非裸读文件）是必须的：e2e 通过 process.env 注入假 Supabase
//     （frontend/playwright.config.ts），此时 dev 值是 e2etest 项目，不该被当成「指向生产」。
//   - `.env.development` 不存在 ⇒ **不判**（CI / 全新 worktree），不制造假红。
//   - dev 值缺失或形态非法 ⇒ **只提示不阻断**（允许「本地不接 Supabase」的离线开发）。
//   - 基础 `frontend/.env`（本地文件，所有 mode 都会加载）**不得**带 Supabase 凭证：
//     否则开发凭证会被打进生产产物（#1028 立项时的原始故障形态）。
//   - `.env.staging` 目前与生产同项目（没有独立 staging 项目），因此不要求它与生产不同。
//
// 关闭开关（仅本地排查用，勿提交）：
//   DISABLE_SUPABASE_ENV_GUARD=1 pnpm dev

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { Plugin } from "vite";

/** 解析后的 env 键值对 */
export type EnvMap = Record<string, string>;

/** 一次隔离检查的输入（全部可注入 ⇒ 便于单测直接覆盖每条分支） */
export interface IsolationInput {
  /** dev 模式**实际生效**的 Supabase URL（Vite 已合并 process.env 优先级） */
  resolvedDevUrl: string | null;
  /** 入库的 `.env.production` 里的 URL（「生产项目」的权威口径） */
  prodFileUrl: string | null;
  /** 本地基础文件 `frontend/.env` 的内容（用于查「凭证混进基础文件」） */
  baseEnvContent: string | null;
}

/** 一次隔离检查的结论 */
export interface IsolationResult {
  /** 硬问题：非空 ⇒ dev server 拒绝启动 */
  error: string | null;
  /** 软提示：只提示、不阻断 */
  warnings: string[];
}

const SUPABASE_URL_KEY = "VITE_SUPABASE_URL";
const SUPABASE_ANON_KEY = "VITE_SUPABASE_ANON_KEY";

/**
 * 解析 dotenv 文本：`KEY=VALUE`，忽略空行与 `#` 开头的注释，
 * 去掉 key/value 两侧空白与成对引号；行尾注释（未加引号时）一并去掉。
 */
export function parseEnvFile(content: string): EnvMap {
  const out: EnvMap = {};
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (!key) continue;
    if (
      (value.startsWith('"') && value.endsWith('"') && value.length >= 2) ||
      (value.startsWith("'") && value.endsWith("'") && value.length >= 2)
    ) {
      value = value.slice(1, -1);
    } else {
      const hash = value.indexOf(" #");
      if (hash >= 0) value = value.slice(0, hash).trim();
    }
    out[key] = value;
  }
  return out;
}

/** 从 `https://<ref>.supabase.co` 抽出 ref；形态不合法返回 null（不猜、不截断） */
export function extractSupabaseRef(
  url: string | null | undefined
): string | null {
  if (!url) return null;
  const m = /^https:\/\/([a-z0-9-]+)\.supabase\.co\/?$/i.exec(url.trim());
  return m ? m[1].toLowerCase() : null;
}

/** 读一个 env 文件（不存在返回 null） */
export function readEnvFile(root: string, envFile: string): string | null {
  const abs = path.resolve(root, envFile);
  if (!existsSync(abs)) return null;
  return readFileSync(abs, "utf-8");
}

/**
 * 核心判据（纯函数）。
 *
 * 判定「dev 与 prod 是否指向同一个 Supabase 项目」。
 */
export function checkDevProdIsolation(input: IsolationInput): IsolationResult {
  const warnings: string[] = [];
  let error: string | null = null;

  // ① 基础 .env 不得带 Supabase 凭证（会随所有 mode 打进产物）
  if (input.baseEnvContent !== null) {
    const base = parseEnvFile(input.baseEnvContent);
    for (const key of [SUPABASE_URL_KEY, SUPABASE_ANON_KEY]) {
      if (base[key] !== undefined && base[key] !== "") {
        error =
          `frontend/.env 含有 ${key}：基础文件会被所有 mode 加载，` +
          `开发凭证会被打进生产产物。请把它移到 .env.development / .env.production。`;
      }
    }
  }

  // ② dev 与 prod 是否同项目
  const devRef = extractSupabaseRef(input.resolvedDevUrl);
  const prodRef = extractSupabaseRef(input.prodFileUrl);
  if (!input.resolvedDevUrl) {
    warnings.push(
      `当前 dev 模式没有解析到 ${SUPABASE_URL_KEY}：本地开发将无法登录（属主动选择，不阻断）。`
    );
  } else if (!devRef) {
    warnings.push(
      `当前 dev 模式的 ${SUPABASE_URL_KEY} 形态非法（期望 https://<ref>.supabase.co）。`
    );
  } else if (prodRef && devRef === prodRef) {
    error =
      `开发与生产指向同一个 Supabase 项目（ref=${devRef}）：` +
      `开发期注册的测试账号会写进生产 Auth 用户表。` +
      `请新建独立 dev 项目（issue #1028）并替换 .env.development 的 ` +
      `${SUPABASE_URL_KEY} / ${SUPABASE_ANON_KEY}。`;
  } else if (!prodRef) {
    warnings.push(
      `读不到 .env.production 里的 ${SUPABASE_URL_KEY}：无法校验 dev/prod 是否同项目。`
    );
  }

  return { error, warnings };
}

/** 报错文案统一出口，避免各处拼错 */
export function formatIsolationResult(result: IsolationResult): string {
  const lines: string[] = [];
  if (result.error) {
    lines.push("以下问题会导致 dev server 拒绝启动：");
    lines.push(`  - ${result.error}`);
  }
  if (result.warnings.length) {
    lines.push("以下问题只提示、不阻断：");
    for (const w of result.warnings) lines.push(`  - ${w}`);
  }
  return lines.join("\n");
}

/**
 * Vite 插件：只在 **dev server** 上生效（生产构建读的是入库的 .env.production，
 * 与本地 .env.development 无关；入库文件的规则由 scripts/guard_supabase_env_separation.py 负责）。
 */
export function supabaseEnvGuard(): Plugin {
  const disabled = process.env.DISABLE_SUPABASE_ENV_GUARD === "1";

  return {
    name: "fundmate:supabase-env-guard",
    configureServer(server) {
      if (disabled) {
        server.config.logger.info(
          "[supabase-env-guard] 已通过环境变量关闭（DISABLE_SUPABASE_ENV_GUARD=1）"
        );
        return;
      }
      const root = server.config.envDir;
      const prodEnvContent = readEnvFile(root, ".env.production");
      const prodFileUrl = prodEnvContent
        ? (parseEnvFile(prodEnvContent)[SUPABASE_URL_KEY] ?? null)
        : null;
      const result = checkDevProdIsolation({
        // server.config.env 是 Vite 按 mode=development 解析后的结果（process.env 优先级最高）
        resolvedDevUrl: server.config.env?.[SUPABASE_URL_KEY] ?? null,
        prodFileUrl,
        baseEnvContent: readEnvFile(root, ".env")
      });

      if (result.error || result.warnings.length) {
        server.config.logger.warn(formatIsolationResult(result));
      }
      if (result.error) {
        // 硬失败：dev server 继续跑下去，就等于继续往生产 Auth 里写测试账号
        throw new Error(
          `[supabase-env-guard] 开发环境变量校验未通过，dev server 拒绝启动。\n` +
            formatIsolationResult(result)
        );
      }
    }
  };
}
