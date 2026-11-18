import type { FundProfileResult } from "@/api/products/fund";

/**
 * 详情页端点打桩工厂（#2958）。
 *
 * ## 为什么要有这个文件
 *
 * 此前 5 个详情页 spec 各自手写 `/api/products/fund-profile/` 的响应，其中 4 份
 * 只写了 **8 个字段**，而 `FundProfileResult` 有 **21 个**。契约（`api/products/fund.ts`
 * 顶部注释）明写「字段缺失一律为 null，前端据此降级为「—」」——于是那 4 个 spec 的
 * **22 个用例全程跑在降级态**：基金经理、费率、晨星评级、规模、成立日、业绩基准
 * 全是占位符。测试是绿的，但它们看到的页面和用户看到的不是同一个。
 *
 * 更贵的是「不可分辨」：#2191 专项用例测「缺 managers ⇒ 降级为 —」，而其余用例的
 * 基线本来就缺 managers，两者 DOM 形态一模一样。模板一旦回退成 `profile.managers.length`，
 * 只有钉了胶囊静态清单的那条会红，其余静默变空。
 *
 * ## 用法
 *
 * - 常规用例：`fundProfileFixture()`，默认给齐 21 个字段且都有值；
 * - 换某个字段：`fundProfileFixture({ scale: 0.42 })`；
 * - 测「后端没给这个字段」：`withoutFields(fundProfileFixture(), ["managers"])`
 *   ——**e2e 里只有 #2191 那条允许这么写**，其余用例缺字段就等于退回本卡之前的状态。
 *
 * ## 类型即守卫
 *
 * 返回类型标成 `FundProfileResult`（不是 `any`、不另写 interface），所以契约加必填
 * 字段时本文件不改就**类型检查报错**——桩不会再一次悄悄落后于契约。
 */

/** 与各详情页 spec 的 `SYMBOL` / `NAME` 同值（`023887` / 永赢北证50成份指数发起C） */
const FUND_CODE = "023887";
const FUND_NAME = "永赢北证50成份指数发起C";

export function fundProfileFixture(
  overrides: Partial<FundProfileResult> = {}
): FundProfileResult {
  return {
    fund_code: FUND_CODE,
    name: FUND_NAME,
    full_name: "永赢北证50成份指数发起式证券投资基金",
    fund_type: "指数型-股票",
    fund_variety: "股票型",
    company: "永赢基金管理有限公司",
    unit_nav: 0.8234,
    nav_date: "2026-10-09",
    prev_unit_nav: 0.8201,
    prev_nav_date: "2026-10-08",
    change_pct: 0.402,
    scale: 12.34,
    create_time: "2022-03-15",
    risk_level: 3,
    benchmark: "中证北证50成份指数收益率*95%+银行活期存款利率*5%",
    morningstar_rating: 4,
    morningstar_rating_delta: 1,
    morningstar_rating_asof: "2026-09-30",
    // 两只经理：一只是代表作（渲染「代表作」徽标）、一只不是——#2958 之前
    // e2e 里没有任何用例见过「经理列表非空」的形态。
    managers: [
      {
        mgr_code: "MGR0001",
        name: "测试经理",
        company: "永赢基金管理有限公司",
        appointment_date: "2022-03-15",
        is_classic: true
      },
      {
        mgr_code: "MGR0002",
        name: "协同经理",
        company: "永赢基金管理有限公司",
        appointment_date: "2023-05-08",
        is_classic: false
      }
    ],
    // 申购两档（比例档 + 千万级低档）、赎回两档（7 天内惩罚档 + 之后免赎回费）
    // ——费率格只显示「最低一档 + 适用条件」，阶梯明细在折叠区，故档位要够全。
    fee_rates: {
      fund_code: FUND_CODE,
      currency: "CNY",
      purchase: [
        {
          start_quota: 0,
          end_quota: 1_000_000,
          rate: 0.012,
          fee_amount: null
        },
        {
          start_quota: 1_000_000,
          end_quota: null,
          rate: 0.0008,
          fee_amount: null
        }
      ],
      redeem: [
        { start_day: 0, end_day: 7, rate: 0.015 },
        { start_day: 7, end_day: null, rate: 0 }
      ]
    },
    source: "天天基金",
    ...overrides
  };
}

/**
 * 从完整桩里摘掉若干字段，模拟「后端没返回这个键」。
 *
 * 用 `delete` 而不是赋 `undefined`：`route.fulfill({ json })` 会把对象
 * `JSON.stringify`，两者产出的报文相同（键都消失），但 `delete` 在注释与断言
 * 里读起来就是「这个键不存在」，不必先想一遍序列化规则。
 */
export function withoutFields<T extends object>(
  source: T,
  keys: (keyof T)[]
): Partial<T> {
  const copy = { ...source };
  for (const key of keys) delete copy[key];
  return copy;
}
