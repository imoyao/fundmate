import { expect, test, type Page } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * #980 拆分回归网：**外观设置面板拆成六个区块组件后，行为不变**。
 *
 * 拆分把 `layout/components/lay-setting/index.vue`（647 行）拆成
 * `sections/{Appearance,ThemeColor,NavMode,PageWidth,TabStyle,Display}Section.vue` +
 * `sections/settingModel.ts`（纯下标 / 色值计算）。等价性脚本证得了文案、
 * 类名、样式声明 0 缺失，但证不到下面三件只有真浏览器能证的事：
 *
 * 1. **导航模式的选中态**。原来有两套并存的机制——模板的 `:class` 绑定，和一段
 *    `watch($storage)` + `toggleClass` 的命令式 DOM 操作（作用于同一批 `li`、
 *    同一个类名、同一个条件）。拆到子组件后父层拿不到那些 `li` 的 ref，命令式
 *    那段必须删；本用例断言「点了混合菜单 → 只有它带 `is-select`」，守住删掉它之后
 *    选中态没丢。这是本次**唯一有意为之的实现改动**。
 * 2. **六个 `defineModel` 开关的回写顺序**。`DisplaySection` 是「props 进、emit 出」
 *    的展示件，`grey-change` 必须在开关值已回写父层之后才发，父层的 `greyChange()`
 *    才读得到新值。顺序反了不会报错，只会「点了没反应」——只能真点一次。
 * 3. **状态仍在父层**。`useDataThemeChange()` 每次调用都会新建 `dataTheme` /
 *    `overallStyle` 两个 ref（只有 `layoutTheme` / `layout` 是基于 `$storage`
 *    的共享 computed）。若某个子组件自己调一份，它拿到的就是互不同步的副本：
 *    本用例用「点主题色 → `<html data-theme>` 真的变了」和「点深色 → `<html>`
 *    加上 `dark` 类」两个跨层副作用钉住这条链路。
 *
 * 防假绿的三条刻意设计：
 * 1. **先坐实面板真的打开了**（`div.show .right-panel`）——面板内容常驻 DOM，
 *    关闭态只是 `transform: translate(100%)` 移出视口，Playwright 的 `toBeVisible`
 *    照样为真；少了这一条，后面所有断言都可能在「面板压根没开」的情况下通过；
 * 2. **每项都断言「副作用」而不是「元素还在」**——元素在只证明渲染没崩，
 *    `<html data-theme>` / `<body layout>` / `html-grey` 类才证明 emit 链真的通了；
 * 3. **页宽区要 1440 视口**——默认 1280 下 `getViewportWidth > 1280` 为假，
 *    整个区块不渲染；用默认视口断言「页宽区块存在」会直接假绿。
 *
 * 反向验证（写完必须做，否则不知道自己写的是不是恒真用例）：
 * 把 `NavModeSection` 里 `:class` 的 `props.layout === mode.layout` 改写成恒 `false`，
 * 用例一必须在「只有混合菜单带 is-select」那两行报红；把 `DisplaySection` 的
 * `@change="emit('grey-change')"` 删掉，用例一必须在 `html-grey` 那行报红。
 */

test.describe.configure({ timeout: 300_000 });

/** 页宽区需要 `getViewportWidth > 1280` 才渲染，默认 Desktop Chrome 是 1280（不渲染） */
test.use({ viewport: { width: 1440, height: 900 } });

/** `platform-config.json` 的默认布局 / 主题色，用来坐实「初始选中态」 */
const DEFAULT_LAYOUT = "vertical";
const DEFAULT_THEME = "showbuy";

/** 面板内容常驻 DOM，只有外层 `.show` 能区分开合 */
function panelOf(page: Page) {
  return page.locator("div.show .right-panel");
}

/** 读 `responsive-*` 命名空间里的存储块（`configure` / `layout`） */
function readStorage(page: Page, suffix: "configure" | "layout") {
  return page.evaluate(name => {
    for (const key of Object.keys(localStorage)) {
      if (key.endsWith(name)) {
        return JSON.parse(localStorage.getItem(key) ?? "null");
      }
    }
    return null;
  }, suffix);
}

async function openAppearancePanel(page: Page) {
  await page.getByRole("button", { name: "打开外观设置" }).first().click();
  const panel = panelOf(page);
  await expect(panel).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByRole("heading", { name: "外观" })).toBeVisible();
  return panel;
}

async function stubBackend(
  context: Parameters<typeof injectSupabaseSession>[0],
  page: Page,
  baseURL: string
) {
  await injectSupabaseSession(context, baseURL);
  await page.route(
    url => new URL(url).pathname.startsWith("/api/"),
    route => route.fulfill({ json: { data: [], total: 0, message: "" } })
  );
}

test.describe("外观设置面板（#980 拆分回归）", () => {
  test("六个区块齐全，主题色 / 导航模式 / 灰色模式的副作用都在", async ({
    context,
    page,
    baseURL
  }) => {
    await stubBackend(context, page, baseURL!);
    await page.goto("/#/welcome", { waitUntil: "commit" });
    await expect(page.locator(".sidebar-container")).toBeVisible({
      timeout: 150_000
    });

    const panel = await openAppearancePanel(page);

    // ── 前提一：六个区块的标题都在（少一个就是 v-if 接线错了）──
    for (const title of [
      "整体风格",
      "主题色",
      "导航模式",
      "页宽",
      "页签风格",
      "界面显示"
    ]) {
      await expect(panel.getByText(title, { exact: true })).toBeVisible();
    }

    // ── 前提二：初始态与 platform-config.json 一致 ──
    await expect
      .poll(() => page.evaluate(() => document.body.getAttribute("layout")))
      .toBe(DEFAULT_LAYOUT);
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.getAttribute("data-theme"))
      )
      .toBe(DEFAULT_THEME);

    // ── 主题色：点第二个色块（道奇蓝 / default）→ `<html data-theme>` 真的变 ──
    // 若子组件各自调 useDataThemeChange，这里的写存储仍会发生但父层状态不同步，
    // 所以下一段「导航模式选中态」一起看才构成完整证据。
    const colorBlocks = panel.locator(".theme-color li");
    await expect(colorBlocks).toHaveCount(9);
    await colorBlocks.nth(1).click();
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.getAttribute("data-theme"))
      )
      .toBe("default");

    // ── 导航模式：选中态只能由 `:class` 表达（命令式 toggleClass 已删）──
    const navItems = panel.locator(".pure-theme li");
    await expect(navItems).toHaveCount(3);
    await expect(navItems.nth(0)).toHaveClass(/is-select/);
    await panel.getByRole("button", { name: "混合菜单" }).click();
    await expect
      .poll(() => page.evaluate(() => document.body.getAttribute("layout")))
      .toBe("mix");
    await expect(navItems.nth(2)).toHaveClass(/is-select/);
    await expect(navItems.nth(0)).not.toHaveClass(/is-select/);

    // ── 界面显示：跨层 emit + defineModel 回写顺序 ──
    // `grey-change` 若早于 `update:grey` 发出，父层读到的还是旧值 → html 类不会加。
    // 注意：el-switch 的 `role="switch"` 落在**视觉隐藏**的 `<input>` 上
    // （Playwright 判 hidden 且点不动），可见可点的是 `.el-switch__core` 轨道。
    const greySwitch = panel
      .locator(".setting li")
      .filter({ hasText: "灰色模式" })
      .locator(".el-switch__core");
    await expect(greySwitch).toBeVisible();
    await greySwitch.click();
    await expect
      .poll(() =>
        page.evaluate(() =>
          document.documentElement.classList.contains("html-grey")
        )
      )
      .toBe(true);
    // 再点一次要能关掉（toggleClass 的 false 分支）
    await greySwitch.click();
    await expect
      .poll(() =>
        page.evaluate(() =>
          document.documentElement.classList.contains("html-grey")
        )
      )
      .toBe(false);
  });

  test("页宽区固定⇄自定义互斥，页签风格落存储", async ({
    context,
    page,
    baseURL
  }) => {
    await stubBackend(context, page, baseURL!);
    await page.goto("/#/welcome", { waitUntil: "commit" });
    await expect(page.locator(".sidebar-container")).toBeVisible({
      timeout: 150_000
    });

    const panel = await openAppearancePanel(page);

    // ── 页宽：默认 Stretch=false ⇒ 显示拉伸按钮、不显示数值输入 ──
    const widthButton = panel.getByRole("button", {
      name: "切换页宽（拉伸／非拉伸）"
    });
    const widthInput = panel.locator(".el-input-number");
    await expect(widthButton).toBeVisible();
    await expect(widthInput).toHaveCount(0);

    // 切到「自定义」：数值输入出现且落在 1440，拉伸按钮消失
    await panel
      .locator(".pure-segmented-item")
      .filter({ hasText: "自定义" })
      .click();
    await expect(widthInput).toBeVisible();
    await expect(widthInput.locator("input")).toHaveValue("1440");
    await expect(widthButton).toHaveCount(0);

    // 切回「固定」：拉伸按钮回来、数值输入消失
    await panel
      .locator(".pure-segmented-item")
      .filter({ hasText: "固定" })
      .click();
    await expect(widthButton).toBeVisible();
    await expect(widthInput).toHaveCount(0);

    // ── 页签风格：点「卡片」→ `configure.showModel` 真的写进存储 ──
    await panel
      .locator(".pure-segmented-item")
      .filter({ hasText: "卡片" })
      .click();
    await expect
      .poll(() => readStorage(page, "configure"))
      .toMatchObject({
        showModel: "card"
      });
  });
});
