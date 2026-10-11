import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { injectSupabaseSession } from "./support/session";

/**
 * #1789 回归网：导入向导草稿的 30s 自动保存 / 7 天过期 / 离开三选提示。
 *
 * 覆盖验收：
 * 1. 草稿超过 7 天不再提示恢复——把 savedAt 改成 8 天前而 expires 保持未来，
 *    证明拦截来自 savedAt 第二道防线（而非存储层 TTL 顺带生效）；
 * 2. 30s 自动保存捕获最新勾选——取消全选后等自动保存落盘，刷新恢复出 0 勾选；
 *    修复前盘上仍是解析时的全选快照 → 恢复为 2 → 用例红；
 * 3. 离开提示只在有未保存修改时出现——干净刷新不弹 beforeunload；脏状态刷新弹；
 *    站内路由离开（点侧边栏 router-link 触发 onBeforeRouteLeave）弹三选对话框，
 *    取消留在本页、保存后离开放行、丢弃后回站无恢复 Banner。
 *
 * 打桩（docs/dev/frontend-e2e.md §7）：GET /api/ledgers/（含 sales-institutions 子路径）、
 * POST /api/importers/parse/。草稿读写直接操作 localforage 底层 IndexedDB
 * （DB=pure-admin / store=keyvaluepairs / key=recon-draft，包装形如 {data, expires}）。
 */

const IMPORT_HASH = "#/inventory/investment/import";
/**
 * 整页加载导入页用的 URL：query 放在 `#` 之前。
 * 同源下 hash-only 的跳转是同文档导航（不重载），而 vue-router 只听 popstate、
 * 不听 hashchange——页面会停在原路由。`#` 前带 query 则是不同的文档 URL，必整页加载；
 * 且 query 位于 hash 之外，hash 模式 router 只解析 hash，完全无感。
 */
const IMPORT_URL = `/?e2e=1${IMPORT_HASH}`;
const BANNER = ".draft-banner";
const SELECTED_STRONG = ".summary-primary strong";
const HEADER_CHECKBOX = ".table-wrapper thead .el-checkbox";
const LEAVE_DIALOG = ".el-dialog";
const IMPORT_HEADER = ".import-header";

const LEDGER = {
  id: 7,
  name: "测试证券账户",
  ledger_type: "stock",
  created_at: "2026-09-01T00:00:00Z",
  last_used_at: null
};

/** 完整 ImportPreviewRow：qty/price 均有效，保证 isRowBlocked=false、可被全选 */
function makeRow(
  symbol: string,
  name: string,
  opType: "buy" | "sell",
  opTypeLabel: string,
  price: number
) {
  const quantity = 100;
  return {
    symbol,
    name,
    type: "stock",
    display_type: "股票",
    op_type: opType,
    op_type_label: opTypeLabel,
    quantity,
    price,
    amount: quantity * price,
    fee: 5,
    trade_date: "2026-09-28",
    account_name: "",
    ledger_id: 7,
    contract_id: "",
    is_cash_transfer: false,
    error: null,
    import_hash: `e2e-${symbol}-${opType}`,
    is_duplicate: false,
    allocation: null,
    link_group_id: null,
    trade_amount: quantity * price,
    net_amount: quantity * price,
    notes: "",
    source: "e2e",
    is_calculated: false
  };
}

const PARSE_BODY = {
  data: [
    makeRow("600519", "贵州茅台", "buy", "买入", 1650),
    makeRow("000858", "五粮液", "sell", "卖出", 128.5)
  ],
  total: 2,
  error_count: 0,
  duplicate_count: 0,
  cash_transfer_count: 0,
  message: ""
};

async function stubApis(page: Page) {
  // /api/ledgers/ 与 /api/ledgers/sales-institutions/ 同前缀：按 URL 分流
  await page.route(/\/api\/ledgers\//, route => {
    const isSales = route.request().url().includes("sales-institutions");
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        isSales
          ? { data: [], message: "", error_code: 0 }
          : { data: [LEDGER], message: "", error_code: 0 }
      )
    });
  });
  await page.route(/\/api\/importers\/parse\//, route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PARSE_BODY)
    })
  );
}

/** 进入导入页 → 选账户 → 上传解析 → 落在预览步骤（解析完成时已由 #1239 路径落一次草稿，此后脏标为假） */
async function preparePreview(page: Page) {
  await page.goto(IMPORT_URL);
  await page.locator(".account-select").click();
  await page.getByRole("option", { name: "测试证券账户" }).click();
  await page.locator(".upload-step input[type='file']").setInputFiles({
    name: "e2e-transactions.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "date,symbol,op,qty,price\n2026-09-28,600519,buy,100,1650\n"
    )
  });
  await expect(page.locator(SELECTED_STRONG)).toHaveText("2");
  // 等解析落盘完成再返回：stats 在 flush 时即可见，而 persist 清脏标要等 IDB 首写提交
  //（实测窗口约 0.4~1s）——立刻刷新会撞进「已渲染未落盘」的脏窗口误触 beforeunload。
  // 草稿可读 ⇒ 写事务已提交 ⇒ 清标的微任务先于本次读取执行，故此轮询即落盘完成信号。
  await expect
    .poll(() => page.evaluate(readDraftWrap).then(Boolean), {
      timeout: 15_000
    })
    .toBe(true);
}

/** 读取 localforage 底层草稿包装 {data, expires}（key 不存在返回 undefined）。直接传给 page.evaluate */
function readDraftWrap(): Promise<
  | { data?: { savedAt?: string; selectedKeys?: string[] }; expires?: number }
  | undefined
> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open("pure-admin");
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const db = open.result;
      const req = db
        .transaction("keyvaluepairs", "readonly")
        .objectStore("keyvaluepairs")
        .get("recon-draft");
      req.onerror = () => {
        db.close();
        reject(req.error);
      };
      req.onsuccess = () => {
        db.close();
        resolve(req.result);
      };
    };
  });
}

/** 把草稿 savedAt 改写为指定时间（expires 不动：过期判定必须由 savedAt 防线独立拦下） */
function expireDraft(savedAtIso: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open("pure-admin");
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const db = open.result;
      const read = db
        .transaction("keyvaluepairs")
        .objectStore("keyvaluepairs")
        .get("recon-draft");
      read.onerror = () => {
        db.close();
        reject(read.error);
      };
      read.onsuccess = () => {
        const wrap = read.result as { data?: { savedAt?: string } } | undefined;
        if (!wrap?.data) {
          db.close();
          reject(new Error("recon-draft 未落盘"));
          return;
        }
        wrap.data.savedAt = savedAtIso;
        const write = db
          .transaction("keyvaluepairs", "readwrite")
          .objectStore("keyvaluepairs")
          .put(wrap, "recon-draft");
        write.onerror = () => {
          db.close();
          reject(write.error);
        };
        write.onsuccess = () => {
          db.close();
          resolve();
        };
      };
    };
  });
}

test.describe("导入草稿自动保存 / 过期 / 离开提示（#1789）", () => {
  test("超过 7 天的草稿不再提示恢复", async ({ context, page, baseURL }) => {
    // 文件级首跑可能撞上 vite 冷启动（依赖现编译），预算放宽
    test.setTimeout(120_000);
    await injectSupabaseSession(context, baseURL!);
    await stubApis(page);
    await preparePreview(page);

    // 对照组：新鲜草稿刷新后 Banner 可见——证明「草稿存在 + 提示链路通」，
    // 否则后面的「不见」可能只是链路本身坏了（假绿）
    await page.reload();
    await expect(page.locator(BANNER)).toBeVisible();

    // savedAt 改成 8 天前、expires 保持未来：只有 savedAt 第二道防线能拦下恢复提示
    await page.evaluate(
      expireDraft,
      new Date(Date.now() - 8 * 24 * 3600 * 1000).toISOString()
    );

    await page.reload();
    // 过期即懒清理（getDraft 里 removeItem）：key 消失 = 挂载期 checkDraft 已判定过期
    await expect
      .poll(() => page.evaluate(readDraftWrap), { timeout: 10_000 })
      .toBeUndefined();
    await expect(page.locator(BANNER)).toHaveCount(0);
  });

  test("30 秒自动保存捕获最新勾选状态", async ({ context, page, baseURL }) => {
    test.setTimeout(120_000);
    await injectSupabaseSession(context, baseURL!);
    // 刷新若落在脏窗口边缘，beforeunload 原生框会被自动接受让导航继续；
    // 真正的回归断言在恢复后的勾选数上
    page.on("dialog", dialog => dialog.accept());
    await stubApis(page);
    await preparePreview(page);
    await expect(page.locator(SELECTED_STRONG)).toHaveText("2");

    // 取消全选 = 未保存修改（此刻盘上草稿仍是解析时的全选快照）
    await page.locator(HEADER_CHECKBOX).click();
    await expect(page.locator(SELECTED_STRONG)).toHaveText("0");

    // 轮询底层存储：30s 自动保存把最新勾选写进草稿（比固定 sleep 稳，写入内容可直接证伪）
    await expect
      .poll(
        () =>
          page
            .evaluate(readDraftWrap)
            .then(wrap => wrap?.data?.selectedKeys?.length),
        { timeout: 45_000, intervals: [1_000] }
      )
      .toBe(0);

    await page.reload();
    await expect(page.locator(BANNER)).toBeVisible();
    await page
      .locator(BANNER)
      .getByRole("button", { name: "恢复草稿" })
      .click();
    // 修复前：盘上还是全选快照 → 恢复为 2 → 本断言红
    await expect(page.locator(SELECTED_STRONG)).toHaveText("0");
  });

  test("离开提示：干净不弹、脏弹三选（取消/保存后离开/丢弃）", async ({
    context,
    page,
    baseURL
  }) => {
    test.setTimeout(120_000);
    await injectSupabaseSession(context, baseURL!);
    const nativeDialogs: string[] = [];
    page.on("dialog", dialog => {
      nativeDialogs.push(dialog.type());
      dialog.accept().catch(() => {});
    });
    await stubApis(page);

    await preparePreview(page);

    // 1) 干净状态刷新：不弹 beforeunload
    await page.reload();
    expect(nativeDialogs).toHaveLength(0);
    await page
      .locator(BANNER)
      .getByRole("button", { name: "恢复草稿" })
      .click();
    await expect(page.locator(SELECTED_STRONG)).toHaveText("2");

    // 2) 脏状态刷新：弹 beforeunload（type=beforeunload），接受后继续
    await page.locator(HEADER_CHECKBOX).click();
    await expect(page.locator(SELECTED_STRONG)).toHaveText("0");
    await page.reload();
    expect(nativeDialogs).toContain("beforeunload");
    await page
      .locator(BANNER)
      .getByRole("button", { name: "恢复草稿" })
      .click();
    // beforeunload 的尽力落盘可能成功也可能没赶上，恢复值不作假设；
    // 点表头必然翻转勾选态（0↔2），无论翻到哪边都构成未保存修改
    const strong = page.locator(SELECTED_STRONG);
    const before = await strong.textContent();
    await page.locator(HEADER_CHECKBOX).click();
    await expect(strong).not.toHaveText(before ?? "");

    // 站内路由离开必须在**同一文档内**用 router.push 触发：history.back() 若跨历史条目
    // 属于跨文档遍历 = 整页重载，SPA 守卫根本不跑；而 hash 直改 vue-router 只听 popstate
    // 也不受理。侧边栏叶子链接是 router-link，守卫通过后 vue-router 才提交 URL。
    const dialog = page.locator(LEAVE_DIALOG, { hasText: "离开导入页面" });
    async function sidebarNavigate(): Promise<void> {
      const link = page
        .locator('.sidebar-container .el-menu a[href^="#/"]:visible')
        .first();
      await link.click();
    }

    // 3) 取消 → 留在导入页，URL 不变
    await sidebarNavigate();
    await expect(dialog).toBeVisible();
    await expect(page.locator(IMPORT_HEADER)).toBeVisible();
    await dialog.getByRole("button", { name: "取消" }).click();
    await expect(dialog).toBeHidden();
    await expect(page).toHaveURL(/#\/inventory\/investment\/import/);
    await expect(page.locator(IMPORT_HEADER)).toBeVisible();

    // 4) 再次离开 → 保存后离开：放行（目标页可能带 redirect，断言「已离开导入页」而非精确 URL）
    await sidebarNavigate();
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "保存后离开" }).click();
    await expect(dialog).toBeHidden();
    await expect(page).not.toHaveURL(/#\/inventory\/investment\/import/);
    await expect(page.locator(IMPORT_HEADER)).toHaveCount(0);

    // 5) 丢弃分支：回导入页恢复 → 制造脏 → 丢弃 → 草稿整份删除，回站无 Banner
    await page.goto(IMPORT_URL);
    await page
      .locator(BANNER)
      .getByRole("button", { name: "恢复草稿" })
      .click();
    const strong2 = page.locator(SELECTED_STRONG);
    const before2 = await strong2.textContent();
    await page.locator(HEADER_CHECKBOX).click();
    await expect(strong2).not.toHaveText(before2 ?? "");
    await sidebarNavigate();
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "丢弃" }).click();
    await expect(dialog).toBeHidden();
    await expect(page).not.toHaveURL(/#\/inventory\/investment\/import/);
    await expect(page.locator(IMPORT_HEADER)).toHaveCount(0);
    await expect
      .poll(() => page.evaluate(readDraftWrap), { timeout: 10_000 })
      .toBeUndefined();

    // 6) 回导入页：草稿已丢弃，不出现恢复 Banner
    await page.goto(IMPORT_URL);
    await expect(page.locator(BANNER)).toHaveCount(0);
  });
});
