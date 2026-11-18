import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * 域 E「确认无需记账」的两条静默失败点（#541，2026-11-08 补）。
 *
 * 这里刻意用源码断言而不是渲染断言，因为两处失效都**不报错**：
 *
 * 1. `account_name` 是确认记录的身份之一（后端按 symbol + 账户 + 分红日定位）。
 *    少了它，后端查不到那笔分红，接口照样 200，用户点完「确认」下次刷新照旧被催——
 *    但页面不白屏、控制台不报错，桩化渲染断言一路全绿。
 * 2. 撤销走 `POST /ack/revoke/` 而不是 `DELETE /ack/`：`PureHttp` 只暴露 get/post，
 *    写 `http.delete` 会在运行期抛「不是函数」，只有 `vue-tsc` 拦得住；
 *    换个人图省事再加回 delete，这条把理由钉住。
 */
const read = (rel: string): string =>
  readFileSync(new URL(rel, import.meta.url), "utf8");

const apiSource = read("../../../../../../api/reconciliation.ts");
const tableSource = read("../DomainEDividendTaxTable.vue");
const actionSource = read("../ReconItemAction.vue");

describe("红利税确认：身份字段与端点形态（#541）", () => {
  it("api 层用 POST 打 /ack/revoke/，不依赖 http.delete", () => {
    expect(apiSource).toContain(
      '"/api/reconciliation/dividend-tax/ack/revoke/"'
    );
    expect(apiSource).not.toContain("http.delete");
  });

  it("确认与撤销都声明了 account_name（身份的一部分，缺了静默匹配不到）", () => {
    expect(apiSource).toContain("account_name");
    // 两个入口都要从待办项上取回账户名，而不是只传 symbol + 日期
    expect(tableSource).toContain("account_name: item.account_name");
    expect(actionSource).toContain("account_name: row.account_name");
  });

  it("确认不写 0 元扣税流水：调用的是 ack 而不是 record", () => {
    expect(tableSource).toContain("ackDividendTax(");
    expect(tableSource).not.toContain("recordDividendTax(");
    expect(actionSource).toContain("ackDividendTax(");
  });
});
