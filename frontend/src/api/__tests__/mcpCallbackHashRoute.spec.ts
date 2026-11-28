import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * OAuth 回调默认回跳必须适配 hash 路由模式（#3280 实测事故）。
 *
 * 本项目 `VITE_ROUTER_HISTORY=hash`：URL 形如 `/#/settings/mcp-connections?x=1`。
 * 若后端默认回跳写成普通路径 `/settings/mcp-connections?x=1`，SPA 加载后
 * hash 为空 → 路由守卫判定无匹配 → 重定向登录页，用户授权成功却看不到结果。
 * query 也必须放在 hash 段之后，`useRoute().query` 才读得到。
 *
 * e2e 能验当前行为，源码断言防止后来者把默认值改回去。
 */
const views = readFileSync(
  new URL("../../../../backend/app/domains/mcp/views.py", import.meta.url),
  "utf8"
);

const remaining = readFileSync(
  new URL("../../router/modules/remaining.ts", import.meta.url),
  "utf8"
);

describe("OAuth 回调回跳与 hash 路由一致", () => {
  it("后端默认回跳带 /#/ 前缀", () => {
    expect(views).toMatch(
      /default\s*=\s*['"]\/#\/settings\/mcp-connections['"]/
    );
  });

  it("后端注释写明 hash 模式原因（防止后人当冗余删掉）", () => {
    expect(views).toMatch(/hash\s*模式|VITE_ROUTER_HISTORY/);
  });

  it("前端注册了 /settings/mcp-connections 路由接住回跳", () => {
    expect(remaining).toMatch(/path:\s*["']\/settings\/mcp-connections["']/);
  });
});
