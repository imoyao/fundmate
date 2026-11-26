/**
 * 空态能力目录（唯一来源）。
 *
 * 设计约束：只列**后端工具已支撑**的能力（`services/ai_recognizer/tools.py` 的
 * TOOLS_METADATA + `tools_fund.py` 的 FUND_TOOLS_METADATA，共 14 个工具：10 个账户级
 * + 4 个基金级）。少一项用户点了会得到「做不到」，多一项就是承诺没兑现的空入口——
 * 新增条目必须先在工具注册表里有对应工具。
 *
 * 2026-11 改版：原先是「3 个快捷 chips + 3 个示例问句」同源两份写法，
 * 空态与输入区各渲染一遍同样那 3 件事（重复入口，观感像 demo）。
 * 改为一份目录、只在空态渲染一次；输入区不再放 chips。
 *
 * 2026-11 增补（#3111）：后端补了基金级工具后追加 2 项「单只基金」——粒度从账户递进
 * 到单只标的。示范问句一律用**数据查询**句式，避开「这只基金怎么样」这类会被
 * `intent_guard` B3 当建议拦掉的问法（那种问法点了必然被拒，等于空入口）。
 *
 * 2026-11-26 分层（用户反馈「10 个入口权重完全平等」）：
 * 10 项平铺、全部 2 列等宽，读起来是一张没有主次的菜单——用户既不知道该先点哪个，
 * 也看不出「单只基金」与「整个账户」是两个粒度。现在分三层：
 *   1. 主入口（{@link PRIMARY_CAPABILITY_KEY}）：整行大卡，权重最高；
 *   2. 常用 3 项（{@link DEFAULT_PINNED_KEYS}，用过之后按最近点击排序）：
 *      3 列一行，恰好一屏可见；
 *   3. 其余收进「更多能力」，按 {@link CAPABILITY_GROUP_LABELS} 分组展开——
 *      分组同时解决了粒度混排（单只基金不再与账户级并列）。
 * 折叠而非删除：能力清单本身是可发现性的一部分，藏起来不等于没有。
 */

import {
  Coin,
  DataAnalysis,
  Document,
  Grid,
  Histogram,
  PieChart,
  Star,
  Sunny,
  TrendCharts,
  Wallet
} from "@element-plus/icons-vue";
import type { Component } from "vue";

/** 能力粒度：账户/市场级 vs 单只基金级（「更多能力」展开后按它分组） */
export type AgentCapabilityGroup = "account" | "fund";

export const CAPABILITY_GROUP_LABELS: Record<AgentCapabilityGroup, string> = {
  account: "账户与市场",
  fund: "单只基金"
};

export type AgentCapability = {
  /** 稳定 key（模板 :key 用，兼作测试锚点） */
  key: string;
  /** 能力名（短标签） */
  label: string;
  /** 一句话说明能查到什么——只描述事实，不含预测 / 建议类承诺 */
  hint: string;
  icon: Component;
  /** 点击后真正发出的话（示范问句） */
  ask: string;
  /** 粒度分组：决定它落在「更多能力」的哪一节 */
  group: AgentCapabilityGroup;
};

/**
 * 主入口：整行大卡独占一行。
 *
 * 为什么是「资产总览」——它是唯一的**汇总口径**，其余 9 项都是它的下钻方向
 * （收益、持仓、归因、单只基金）。把它放首位等于先回答「我有多少钱」，
 * 再让用户顺着往下问，符合账本类产品的第一个问题。
 */
export const PRIMARY_CAPABILITY_KEY = "assets";

/** 没点过任何能力时，「常用」位默认放这 3 项（覆盖收益 / 持仓 / 市场三条主线） */
export const DEFAULT_PINNED_KEYS: readonly string[] = [
  "performance",
  "position",
  "market"
];

export const AGENT_CAPABILITIES: readonly AgentCapability[] = [
  {
    key: "assets",
    label: "资产总览",
    hint: "总资产、负债、净资产与账面盈亏",
    icon: Wallet,
    ask: "我的总资产和净资产现在是多少？",
    group: "account"
  },
  {
    key: "performance",
    label: "收益表现",
    hint: "组合年化 XIRR、总投入与当前市值",
    icon: TrendCharts,
    ask: "我最近半年表现怎么样？",
    group: "account"
  },
  {
    key: "position",
    label: "持仓盈亏",
    hint: "逐只标的的成本、市值、浮盈亏",
    icon: Coin,
    ask: "我的持仓现在值多少钱？",
    group: "account"
  },
  {
    key: "benchmark",
    label: "跑赢大盘",
    hint: "对比沪深300 的超额与最大回撤",
    icon: Histogram,
    ask: "我今年跑赢沪深300了吗？",
    group: "account"
  },
  {
    key: "attribution",
    label: "收益归因",
    hint: "区间收益拆到每只标的、每个账户",
    icon: PieChart,
    ask: "这半年我的收益主要是哪几只贡献的？",
    group: "account"
  },
  {
    key: "behavior",
    label: "交易习惯",
    hint: "平均持有天数、买卖比、换手频率",
    icon: DataAnalysis,
    ask: "我平均一只基金拿多久？",
    group: "account"
  },
  {
    key: "watchlist",
    label: "自选与净值",
    hint: "自选最新价、基金历史净值",
    icon: Star,
    ask: "我的自选今天表现怎么样？",
    group: "account"
  },
  {
    key: "market",
    label: "市场温度",
    hint: "综合温度、分档结论与数据新鲜度",
    icon: Sunny,
    ask: "现在市场温度是多少？",
    group: "account"
  },
  {
    key: "fund-profile",
    label: "基金档案",
    hint: "类型、规模、经理、费率与最新净值",
    icon: Document,
    ask: "110011 的规模多大、申购费率多少？",
    group: "fund"
  },
  {
    key: "fund-holdings",
    label: "持仓与风格",
    hint: "行业配置、前十大持仓、风格是否漂移",
    icon: Grid,
    ask: "110011 重仓什么行业？",
    group: "fund"
  }
];
