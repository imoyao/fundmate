import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * MCP 连接管理 API 的契约防回潮（源码字符串断言，不依赖桩）。
 *
 * 两类真实踩过的坑：
 * 1. 端点漏 `/api` 前缀 → vite 只代理 `/api`，未知路径走 SPA 回退返回
 *    index.html（HTTP 200），前端把 HTML 当数据 → 空态且不抛错（#2866）；
 * 2. `http.request(method, url, param)` 的第三参数是 **AxiosRequestConfig**，
 *    POST body 必须放 `data` 字段。直接写 `{ provider, api_key }` 会被
 *    当成 config 的未知属性 → tsc TS2353，且运行时代理层拿不到 body。
 *
 * 桩能骗过渲染断言，骗不过源码本身；这两条都是"测试全绿但线上空态"的形状。
 */
const source = readFileSync(new URL("../mcp.ts", import.meta.url), "utf8");

const apiPaths = Array.from(
  source.matchAll(/"(\/api\/[a-z0-9/_.-]*)"/g),
  m => m[1]
);

describe("MCP 接口路径前缀", () => {
  it("覆盖 4 个字面量端点 + verify 模板路径（callback 由后端 302，前端不调用）", () => {
    expect(apiPaths).toEqual(
      expect.arrayContaining([
        "/api/mcp/connections/",
        "/api/mcp/connections/static/",
        "/api/mcp/oauth/begin/"
      ])
    );
    // verify 的 provider 走 encodeURIComponent 模板串，正则抓不到引号字面量，单独断言
    expect(source).toContain(
      "`/api/mcp/connections/${encodeURIComponent(provider)}/verify/`"
    );
  });

  it("所有路径都以 /api/ 开头", () => {
    expect(apiPaths.length).toBeGreaterThan(0);
    for (const p of apiPaths) {
      expect(p.startsWith("/api/")).toBe(true);
    }
  });

  it("不调用 OAuth 回调端点（那是浏览器独立请求、免登录）", () => {
    expect(source).not.toMatch(
      /http\.request<[^>]*>\(\s*"get",\s*"\/api\/mcp\/oauth\/callback/
    );
  });
});

describe("POST body 用 data 包裹", () => {
  // 只看 http.request 调用的参数行（去掉注释与类型声明），否则注释里的 `data:` 会喂假绿
  const requestCalls = source
    .split("\n")
    .filter(line => !line.trimStart().startsWith("//"))
    .filter(line => line.includes("data"))
    .join("\n");

  it("static 与 oauth/begin 两个写端点的 body 都写在 data key 下", () => {
    // static 用 `{ data }` 简写（形参名即 data），oauth/begin 用 `{ data: { provider } }`
    expect(requestCalls).toMatch(/\{\s*data\s*\}/);
    expect(requestCalls).toContain("{ data: { provider } }");
  });

  it("不把 provider/api_key 直接作为 config 顶层属性", () => {
    expect(requestCalls).not.toMatch(/^\s*\{\s*provider\s*[,}]/m);
    expect(requestCalls).not.toMatch(/^\s*\{\s*api_key/m);
  });
});
