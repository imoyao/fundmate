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
};

export const AGENT_CAPABILITIES: readonly AgentCapability[] = [
  {
    key: "assets",
    label: "资产总览",
    hint: "总资产、负债、净资产与账面盈亏",
    icon: Wallet,
    ask: "我的总资产和净资产现在是多少？"
  },
  {
    key: "performance",
    label: "收益表现",
    hint: "组合年化 XIRR、总投入与当前市值",
    icon: TrendCharts,
    ask: "我最近半年表现怎么样？"
  },
  {
    key: "position",
    label: "持仓盈亏",
    hint: "逐只标的的成本、市值、浮盈亏",
    icon: Coin,
    ask: "我的持仓现在值多少钱？"
  },
  {
    key: "benchmark",
    label: "跑赢大盘",
    hint: "对比沪深300 的超额与最大回撤",
    icon: Histogram,
    ask: "我今年跑赢沪深300了吗？"
  },
  {
    key: "attribution",
    label: "收益归因",
    hint: "区间收益拆到每只标的、每个账户",
    icon: PieChart,
    ask: "这半年我的收益主要是哪几只贡献的？"
  },
  {
    key: "behavior",
    label: "交易习惯",
    hint: "平均持有天数、买卖比、换手频率",
    icon: DataAnalysis,
    ask: "我平均一只基金拿多久？"
  },
  {
    key: "watchlist",
    label: "自选与净值",
    hint: "自选最新价、基金历史净值",
    icon: Star,
    ask: "我的自选今天表现怎么样？"
  },
  {
    key: "market",
    label: "市场温度",
    hint: "综合温度、分档结论与数据新鲜度",
    icon: Sunny,
    ask: "现在市场温度是多少？"
  },
  {
    key: "fund-profile",
    label: "基金档案",
    hint: "类型、规模、经理、费率与最新净值",
    icon: Document,
    ask: "110011 的规模多大、申购费率多少？"
  },
  {
    key: "fund-holdings",
    label: "持仓与风格",
    hint: "行业配置、前十大持仓、风格是否漂移",
    icon: Grid,
    ask: "110011 重仓什么行业？"
  }
];
