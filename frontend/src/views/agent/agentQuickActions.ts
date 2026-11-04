/**
 * 能力快捷 chips 与空态示例的单一来源。
 *
 * 两者同源（示例 = 快捷动作的 ask 文本）：只列后端工具**已支撑**的能力，
 * 少一项用户点了会得到「做不到」，多一项就是承诺没兑现的空入口。
 * 放在独立模块是因为它同时被空态 hero 与输入区 chips 消费——留在 index.vue
 * 会让「页面外壳」重新背上业务常量。
 */

import { Sunny, TrendCharts, Wallet } from "@element-plus/icons-vue";
import type { Component } from "vue";

export type AgentQuickAction = {
  /** chips 上的短标签 */
  label: string;
  icon: Component;
  /** 点击后真正发出的话（也是空态示例文案） */
  ask: string;
};

export const QUICK_ACTIONS: readonly AgentQuickAction[] = [
  { label: "投资表现", icon: TrendCharts, ask: "我最近半年表现怎么样？" },
  { label: "持仓价值", icon: Wallet, ask: "我的持仓现在值多少钱？" },
  { label: "市场温度", icon: Sunny, ask: "现在市场温度是多少？" }
];

/** 空态示例问题：与 chips 同源，改一处不会让两处文案漂移 */
export const EXAMPLES: readonly string[] = QUICK_ACTIONS.map(a => a.ask);
