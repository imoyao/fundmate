// frontend/src/__tests__/supabaseEnvGuard.spec.ts
//
// #1028：把「dev 与 prod 必须指向不同 Supabase 项目」钉成可回归的单测。
//
// 这组用例只测**纯函数** `checkDevProdIsolation`：它吃三份输入，
// 吐出 error / warnings。插件（vite 接线层）另有接线探针验证。

import { describe, expect, it } from "vitest";
import {
  checkDevProdIsolation,
  extractSupabaseRef,
  parseEnvFile
} from "../../build/supabase-env-guard";

const PROD_REF = "abcdefghijklmnopqrst";
const DEV_REF = "zyxwvutsrqponmlkjihg";
const PROD_URL = `https://${PROD_REF}.supabase.co`;
const DEV_URL = `https://${DEV_REF}.supabase.co`;

describe("parseEnvFile", () => {
  it("忽略注释与空行，去掉引号与行尾注释", () => {
    const env = parseEnvFile(
      [
        "# 一行注释",
        "",
        "VITE_APP_ENV=development",
        'VITE_PUBLIC_PATH = "/"',
        'VITE_ROUTER_HISTORY="hash"',
        "VITE_CDN=false # 行尾注释",
        "VITE_EMPTY="
      ].join("\n")
    );
    expect(env.VITE_APP_ENV).toBe("development");
    expect(env.VITE_PUBLIC_PATH).toBe("/");
    expect(env.VITE_ROUTER_HISTORY).toBe("hash");
    expect(env.VITE_CDN).toBe("false");
    expect(env.VITE_EMPTY).toBe("");
  });
});

describe("extractSupabaseRef", () => {
  it("从合法 URL 抽出 ref", () => {
    expect(extractSupabaseRef(PROD_URL)).toBe(PROD_REF);
    expect(extractSupabaseRef(`${PROD_URL}/`)).toBe(PROD_REF);
  });

  it("形态非法时返回 null（不猜、不截断）", () => {
    expect(
      extractSupabaseRef("http://abcdefghijklmnopqrst.supabase.co")
    ).toBeNull();
    expect(extractSupabaseRef("https://example.com")).toBeNull();
    expect(extractSupabaseRef("not-a-url")).toBeNull();
    expect(extractSupabaseRef(null)).toBeNull();
    expect(extractSupabaseRef("")).toBeNull();
  });
});

describe("checkDevProdIsolation", () => {
  it("dev 与 prod 指向不同项目 ⇒ 无错误", () => {
    const result = checkDevProdIsolation({
      resolvedDevUrl: DEV_URL,
      prodFileUrl: PROD_URL,
      baseEnvContent: "VITE_PORT=8848\n"
    });
    expect(result.error).toBeNull();
    expect(result.warnings).toEqual([]);
  });

  it("dev 与 prod 指向同一项目 ⇒ 必须报错（#1028 的原始故障形态）", () => {
    const result = checkDevProdIsolation({
      resolvedDevUrl: PROD_URL,
      prodFileUrl: PROD_URL,
      baseEnvContent: "VITE_PORT=8848\n"
    });
    expect(result.error).toContain("同一个 Supabase 项目");
    expect(result.error).toContain(PROD_REF);
  });

  it("e2e 的假项目（process.env 注入）不算「指向生产」", () => {
    // frontend/playwright.config.ts 注入 VITE_SUPABASE_URL=https://e2etest.supabase.co
    const result = checkDevProdIsolation({
      resolvedDevUrl: "https://e2etest.supabase.co",
      prodFileUrl: PROD_URL,
      baseEnvContent: null
    });
    expect(result.error).toBeNull();
  });

  it("基础 .env 带 Supabase 凭证 ⇒ 报错（会被打进所有 mode 的产物）", () => {
    const result = checkDevProdIsolation({
      resolvedDevUrl: DEV_URL,
      prodFileUrl: PROD_URL,
      baseEnvContent: `VITE_SUPABASE_URL=${DEV_URL}\n`
    });
    expect(result.error).toContain("frontend/.env 含有");
  });

  it("dev 没解析到凭证 ⇒ 只告警不阻断（允许离线开发）", () => {
    const result = checkDevProdIsolation({
      resolvedDevUrl: null,
      prodFileUrl: PROD_URL,
      baseEnvContent: null
    });
    expect(result.error).toBeNull();
    expect(result.warnings.length).toBeGreaterThan(0);
  });

  it("dev URL 形态非法 ⇒ 只告警不阻断", () => {
    const result = checkDevProdIsolation({
      resolvedDevUrl: "https://example.com",
      prodFileUrl: PROD_URL,
      baseEnvContent: null
    });
    expect(result.error).toBeNull();
    expect(result.warnings.some(w => w.includes("形态非法"))).toBe(true);
  });

  it("读不到 .env.production ⇒ 无法比对，只告警", () => {
    const result = checkDevProdIsolation({
      resolvedDevUrl: PROD_URL,
      prodFileUrl: null,
      baseEnvContent: null
    });
    expect(result.error).toBeNull();
    expect(result.warnings.some(w => w.includes("无法校验"))).toBe(true);
  });
});
