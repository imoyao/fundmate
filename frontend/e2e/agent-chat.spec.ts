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
    session_state: {
      goal: "分析账户收益",
      missing_params: ["fund_codes"],
      collected_params: {},
      history: []
    }
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
    session_state: {
      goal: "分析账户收益",
      missing_params: [],
      collected_params: {},
      history: []
    }
  },
  message: "ok"
};

/** 轮次闸实出信封（ErrorCode.AGENT_TURN_LIMIT_EXCEEDED = (4001, 429)） */
const turnLimitEnvelope = {
  data: null,
  message: "已超出分析轮次",
  error_code: 4001
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
});
