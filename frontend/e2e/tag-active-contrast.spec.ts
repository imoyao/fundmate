import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 激活标签必须**看得见**（2026-10-30 实机截图抓出的老 bug）。
 *
 * 缺陷形态：标签栏里当前页那个标签只剩一个 × 按钮，文字完全消失；换个页面，
 * 「空白」就跟着换到新的当前页。用户的原话是「标签块在、里面是空的」，
 * 以及「点击侧边栏的时候此处不是应该显示中文名吗」。
 *
 * 根因：`.scroll-item.is-active .tag-title` 用了 `--text-inverse`（#fff），
 * 而标签栏底色是白卡片（`--bg-card`）——**白字白底**。历史提交 `cbc043a6d`
 * 把标题从 `var(--el-color-primary)`（红字白底）改成 `--text-inverse`，
 * 却没给 `.scroll-item.is-active` 补背景色。
 *
 * 判据：激活标签文字与其实际背景的对比度 ≥ 4.5:1（WCAG AA 正文）。
 * 这条判据能同时挡住「白字白底」「浅灰字白底」两类回归，且不锁死具体色值。
 */

/** 取元素实际渲染背景：自身透明就向上找第一个不透明的祖先 */
const MEASURE = () => {
  const parse = (css: string) => {
    const m = css.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(",").map(s => parseFloat(s.trim()));
    return { r: parts[0], g: parts[1], b: parts[2], a: parts[3] ?? 1 };
  };
  const lum = (c: { r: number; g: number; b: number }) => {
    const f = (v: number) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };

  const item = document.querySelector(
    ".scroll-container .scroll-item.is-active"
  ) as HTMLElement | null;
  if (!item) return null;
  const title = item.querySelector(".tag-title") as HTMLElement | null;
  if (!title) return null;

  const fg = parse(getComputedStyle(title).color);
  if (!fg) return null;

  let node: HTMLElement | null = item;
  let bg = null as { r: number; g: number; b: number; a: number } | null;
  while (node) {
    const c = parse(getComputedStyle(node).backgroundColor);
    if (c && c.a > 0.9) {
      bg = c;
      break;
    }
    node = node.parentElement;
  }
  if (!bg) return null;

  const l1 = lum(fg);
  const l2 = lum(bg);
  const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);

  return {
    text: title.textContent?.trim(),
    fg: getComputedStyle(title).color,
    bg: getComputedStyle(node as HTMLElement).backgroundColor,
    ratio: Math.round(ratio * 100) / 100
  };
};

test("激活标签的文字清晰可读（对比度 ≥ 4.5:1）", async ({
  context,
  page,
  baseURL
}) => {
  await injectSupabaseSession(context, baseURL!);
  await page.goto("/#/welcome");
  await expect(
    page.locator(".scroll-container .scroll-item").first()
  ).toBeVisible({ timeout: 30_000 });

  // 多走几页，确保「当前页」换过（缺陷的表现就是空白跟着当前页跑）
  for (const p of ["/asset/position-analysis", "/asset/strategies"]) {
    await page.goto(`/#${p}`);
    await page.waitForTimeout(1200);

    const m = await page.evaluate(MEASURE);
    expect(m, `${p} 上没找到激活标签`).not.toBeNull();
    expect(m!.text, "激活标签必须有文字").toBeTruthy();
    expect(
      m!.ratio,
      `${p} 激活标签对比度不足：文字 ${m!.fg} / 背景 ${m!.bg}`
    ).toBeGreaterThanOrEqual(4.5);
  }
});
