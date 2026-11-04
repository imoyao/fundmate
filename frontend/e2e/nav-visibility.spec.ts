import { expect, test } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * 导航区文字可见性总巡检（2026-10-31 补）。
 *
 * ## 为什么要有这个文件
 *
 * 「激活标签白字白底」这个缺陷存在了很久，之前的测试全是**结构断言**：
 * 面包屑文字对不对、标签有没有生成、层级是否对齐——DOM 里文字确实在，
 * `innerText` 也读得到，所以一路绿灯，用户在界面上却只看到一个 × 按钮。
 *
 * 教训：**DOM 里有文字 ≠ 屏幕上看得到**。凡是「给人看的文字」，至少要钉三条：
 *
 * 1. **有宽度**：`getBoundingClientRect().width > 0`（被 flex 压扁 / 溢出裁剪会是 0）；
 * 2. **不被裁到视口外**：元素中心点落在视口内（标签栏横向滚动时会移出去）；
 * 3. **对比度达标**：文字色与其**实际渲染背景**（自身透明就向上找第一个不透明祖先）
 *    的对比度 ≥ 4.5:1（WCAG AA 正文）。
 *
 * 这三条对颜色/排版类回归都有效，且不锁死具体色值——换成任何配色都能验。
 * 覆盖侧边栏、面包屑、标签栏三处（用户日常看的最多的导航区）。
 */

const PAGES = [
  "/welcome",
  "/asset/position-analysis",
  "/analysis",
  "/asset/strategies",
  "/asset/precious",
  "/asset/realestate",
  "/asset/fund-ranking",
  "/asset/portfolios",
  "/inventory",
  "/transactions"
];

/** 在页面里跑的巡检：返回不达标的元素清单 */
const AUDIT = () => {
  const parse = (css: string) => {
    const m = css.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(",").map(s => parseFloat(s.trim()));
    return { r: p[0], g: p[1], b: p[2], a: p[3] ?? 1 };
  };
  const lum = (c: { r: number; g: number; b: number }) => {
    const f = (v: number) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const contrast = (a: any, b: any) => {
    const l1 = lum(a);
    const l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };
  const effectiveBg = (el: HTMLElement) => {
    let node: HTMLElement | null = el;
    while (node) {
      const c = parse(getComputedStyle(node).backgroundColor);
      if (c && c.a > 0.9) return { c, node };
      node = node.parentElement;
    }
    return null;
  };

  const targets: Array<{ area: string; sel: string }> = [
    { area: "侧边栏", sel: ".sidebar-container .el-menu-item" },
    { area: "面包屑", sel: ".el-breadcrumb__item" },
    { area: "标签栏", sel: ".scroll-container .scroll-item" }
  ];

  const bad: string[] = [];

  for (const t of targets) {
    for (const el of Array.from(
      document.querySelectorAll<HTMLElement>(t.sel)
    )) {
      // 只检查自身带文字的元素（父级容器会把子项文字合并进来）
      const hasOwnText = Array.from(el.childNodes).some(
        n => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim()
      );
      const textEl =
        (el.querySelector(".tag-title") as HTMLElement) ??
        (hasOwnText ? el : null);
      const label = (el.textContent ?? "").replace(/\s+/g, " ").trim();
      if (!textEl || !label) continue;

      const rect = textEl.getBoundingClientRect();
      const cs = getComputedStyle(textEl);

      if (rect.width < 2 || rect.height < 2) {
        bad.push(`[${t.area}] 「${label}」宽度/高度为 0（被压扁或未渲染）`);
        continue;
      }

      const inViewport =
        rect.top < window.innerHeight &&
        rect.bottom > 0 &&
        rect.left < window.innerWidth &&
        rect.right > 0;
      if (!inViewport) {
        bad.push(`[${t.area}] 「${label}」被裁到视口外`);
        continue;
      }

      if (cs.visibility === "hidden" || cs.opacity === "0") {
        bad.push(`[${t.area}] 「${label}」visibility/opacity 不可见`);
        continue;
      }

      const fg = parse(cs.color);
      const bg = effectiveBg(textEl);
      if (!fg || !bg) continue;

      const ratio = Math.round(contrast(fg, bg.c) * 100) / 100;
      if (ratio < 4.5) {
        bad.push(
          `[${t.area}] 「${label}」对比度 ${ratio}:1（文字 ${cs.color} / 背景 ${getComputedStyle(bg.node).backgroundColor}）`
        );
      }
    }
  }

  return bad;
};

test("导航区文字可见性（宽度 / 视口 / 对比度 ≥ 4.5:1）", async ({
  context,
  page,
  baseURL
}) => {
  await injectSupabaseSession(context, baseURL!);
  await page.goto("/#/welcome");
  await expect(page.locator(".sidebar-container")).toBeVisible({
    timeout: 30_000
  });
  await page.waitForTimeout(1500);

  const problems: string[] = [];

  for (const p of PAGES) {
    await page.goto(`/#${p}`);
    await page.waitForTimeout(1200); // 等路由与标签栏更新
    const bad = await page.evaluate(AUDIT);
    for (const b of bad) problems.push(`${p} ${b}`);
  }

  expect(problems, "导航区有不可见/不可读的文字").toEqual([]);
});
