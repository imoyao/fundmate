import { expect, test } from "@playwright/test";
import { injectSupabaseSession } from "./support/session";

/**
 * 账本精灵对话页三态渲染（#1121 S1-B）。
 *
 * 为什么 mock 而不打真后端：本仓 E2E 的既有取舍是「不依赖后端」（见
 * playwright.config.ts 注释）——三态的**后端真实性**已由 2026-09-26 的本机
 * 真实走查钉过（curl 实抓，见 docs/working-notes/agent-dev-progress-2026-09-26.md
 * 步骤卡 #2）；这里验证的是**前端**对三态信封的渲染与回传链路，必须确定性。
 */

/** clarify 实出样本：后端 run_agent 的 type=clarify 形状（missing_params 随行） */
const clarifyTurn = {
  data: {
    type: "clarify",
    content:
      "请提供您要查询的招商中证白酒对应的6位基金代码，以便我为您查询其最新单位净值。",
    missing_params: ["fund_codes"],
    session_id: "sess-e2e-1"
  },
  message: "ok"
};

/** result 实出样本：自然语言总结 + 扁平标量 data（渲染成指标 chips） */
const resultTurn = {
  data: {
    type: "result",
    content:
      "当前组合价值约68.04万元，累计回报约44.99万元，年化实际收益率约54.6%。",
    data: {
      current_value: "680400.00",
      total_return: "449900.00",
      xirr: "54.63%"
    },
    session_id: "sess-e2e-1"
  },
  message: "ok"
};

/** 轮次闸实出信封（ErrorCode.AGENT_TURN_LIMIT_EXCEEDED = (4001, 429)） */
const turnLimitEnvelope = {
  data: null,
  message: "已超出分析轮次",
  error_code: 4001
};

/** 结构化块实出样本（#1712）：后端 parse_narrative_blocks 的块形状（含行级盈亏表） */
const structuredTurn = {
  data: {
    type: "result",
    content: "【结论】组合整体盈利。【明细】持仓盈亏如下。【风险提示】市场波动可能使收益回撤。",
    blocks: [
      { type: "summary", text: "组合整体盈利。" },
      { type: "text", text: "持仓盈亏如下。" },
      {
        type: "table",
        columns: [
          { key: "name", label: "名称", kind: "plain" },
          { key: "pnl", label: "盈亏", kind: "pnl" },
          { key: "pnl_rate", label: "盈亏率(%)", kind: "pnl" }
        ],
        rows: [
          { name: "赚的基金", pnl: 1000.5, pnl_rate: 10.25 },
          { name: "亏的股票", pnl: -200.25, pnl_rate: -5.5 },
          { name: "平的债券", pnl: 0, pnl_rate: 0 }
        ],
        truncated: false
      },
      { type: "risk", text: "市场波动可能使收益回撤。" }
    ],
    data: {},
    // S2：会话状态由服务端持有，响应只下发 session_id（与其他两个样本同形）
    session_id: "sess-e2e-1"
  },
  message: "ok"
};

test.describe("账本精灵对话页（#1121 S1-B）", () => {
  test("三态渲染：澄清追问 → 结果指标 chips → 错误提示；新对话可清空", async ({
    page,
    context,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);

    // 按调用序返回 clarify → result → 429 信封；正则精确匹配尾斜杠端点
    const turns: Array<unknown> = [clarifyTurn, resultTurn];
    let call = 0;
    await page.route(/\/api\/agent\/chat\/?$/, async route => {
      const index = call++;
      if (index < turns.length) {
        await route.fulfill({ json: turns[index] });
      } else {
        await route.fulfill({ status: 429, json: turnLimitEnvelope });
      }
    });

    await page.goto("/#/agent/chat");
    await expect(page).toHaveURL(/#\/agent\/chat/);

    // 静态路由注册生效：侧边栏菜单出现「账本精灵」（#1703 记录的注册方式）
    await expect(
      page.locator(".sidebar-container").getByText("账本精灵", { exact: true })
    ).toBeVisible();

    // 空态：示例问题（功能型空态）
    await expect(page.getByText("试着问一句")).toBeVisible();

    // 第一轮 → clarify：追问 fund_codes
    await page
      .getByPlaceholder(/Enter 发送/)
      .fill("帮我看看招商中证白酒这只基金现在多少钱一份");
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByText(/6位基金代码/)).toBeVisible();

    // 第二轮 → result：自然语言 + 指标 chips（key 与 value 都渲染）
    await page.getByPlaceholder(/Enter 发送/).fill("我现在持仓总市值是多少？");
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByText("current_value")).toBeVisible();
    await expect(page.getByText("680400.00")).toBeVisible();
    // chips 不染涨跌色（无 --color-rise/fall 类），且内容与 chips 同屏
    await expect(page.getByText(/年化实际收益率约54.6%/)).toBeVisible();

    // 第三轮 → 429 轮次闸：错误信封进聊天气泡（服务提示，而非白屏/静默）
    await page.getByPlaceholder(/Enter 发送/).fill("再来一轮");
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByText("已超出分析轮次")).toBeVisible();
    await expect(page.getByText("服务提示")).toBeVisible();

    // 截图留档（面试演示素材；test-results/ 已 gitignore）
    await page.screenshot({
      path: "test-results/agent-chat-s1b-three-states.png"
    });

    // 新对话清空回空态
    await page.getByRole("button", { name: "新对话" }).click();
    await expect(page.getByText("试着问一句")).toBeVisible();
    await expect(page.getByText("已超出分析轮次")).toHaveCount(0);
  });

  test("结构化块渲染（#1712）：结论加粗 / 行级盈亏涨红跌绿 / 风险提示弱化", async ({
    page,
    context,
    baseURL
  }) => {
    await injectSupabaseSession(context, baseURL!);
    await page.route(/\/api\/agent\/chat\/?$/, async route => {
      await route.fulfill({ json: structuredTurn });
    });

    await page.goto("/#/agent/chat");
    await page.getByPlaceholder(/Enter 发送/).fill("我的持仓盈亏怎么样？");
    await page.getByRole("button", { name: "发送" }).click();

    // 三类文本块按类渲染（结论 / 明细文本 / 风险提示）
    const summary = page.locator(".msg__block--summary");
    await expect(summary).toHaveText("组合整体盈利。");
    await expect(page.locator(".msg__block--text")).toHaveText("持仓盈亏如下。");
    const risk = page.locator(".msg__block--risk");
    await expect(risk).toHaveText("市场波动可能使收益回撤。");

    // 表格：列头 + 千分位数值
    const table = page.locator(".msg__table");
    await expect(table.locator("thead th")).toHaveText([
      "名称",
      "盈亏",
      "盈亏率(%)"
    ]);
    // 涨红跌绿：正数染 --color-rise-ink，负数染 --color-fall-ink，0 / 名称列不染
    const riseCell = table.locator("td.msg__cell--rise");
    await expect(riseCell).toHaveText(["1,000.50", "10.25"]);
    const fallCell = table.locator("td.msg__cell--fall");
    await expect(fallCell).toHaveText(["-200.25", "-5.50"]);
    // 名称列与 0 值单元格不染涨跌色（定位到第三行盈亏列，避免 0.00 命中两个同值单元格）
    await expect(
      table.locator("tbody tr").first().locator("td").first()
    ).not.toHaveClass(/msg__cell/);
    const zeroPnl = table.locator("tbody tr").nth(2).locator("td").nth(1);
    await expect(zeroPnl).toHaveText("0.00");
    await expect(zeroPnl).not.toHaveClass(/msg__cell/);

    // 原始 content 里的契约标记不外显（结构化态只渲染块，不再整段回显文本）
    await expect(page.getByText(/【结论】/)).toHaveCount(0);
  });
});
