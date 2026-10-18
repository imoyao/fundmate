// src/api/strategyEngine.ts
/**
 * 策略引擎（#2224 / #2225 / #2237）接口封装。
 *
 * WHY 单独成文件
 *     `@/api/strategy` 里的「策略」是**投资风格标签**（用户自己给持仓打的标签，
 *     如「核心仓」「卫星仓」），与这里的「策略引擎」完全是两件事。塞进同一个文件
 *     会让后来者以为两者同源，进而写出错误的调用。故本文件独立命名 `strategyEngine`。
 *
 * 类型放在本文件内（项目规则：本文件专属类型不放 `api/types.d.ts`）。
 *
 * 合规
 *     后端只产出**客观事实**（「趋势成立」「偏离 6.2 个百分点」），不含投资建议。
 *     前端只陈列，不得把 `reason` 加工成建议语气。
 */
import { http } from "@/utils/http";

/** 策略引擎端点前缀（与 allocation 共用 `/api/strategy/` 前缀，故 BASE_URL 不带 engine） */
const BASE_URL = "/api/strategy/";

/** 信号动作：规则被触发的**客观状态**，不是投资建议 */
export type SignalAction = "buy" | "hold" | "reduce" | "sell" | "watch";

/** 目标配比 —— 单个标的（对齐 `services/strategy_engine/allocation.compute_deviation` 的 items[]） */
export interface AllocationItem {
  symbol: string;
  /** 展示名；后端按 symbol 聚合持仓时取到的名称 */
  name: string;
  /** 市值（分，已折 CNY） */
  market_value_cents: number;
  /** 当前占比（百分点） */
  weight_pct: number;
  /** 目标占比（百分点）；**null = 该标的未设目标** */
  target_pct: number | null;
  /** 偏离（百分点，正 = 高于目标）；未设目标时为 null */
  deviation_pct: number | null;
  /** 偏离绝对值是否达到阈值。**未设目标恒为 false**——「没定规矩」不算「违反规矩」 */
  breached: boolean;
}

/** 目标配比响应体（GET / PUT 共用；PUT 多一个 saved_count） */
export interface AllocationData {
  /** 持仓总市值（分） */
  total_value_cents: number;
  /** 本次使用的偏离阈值（百分点） */
  threshold_pct: number;
  /** 已设目标的标的数 */
  configured_count: number;
  /** 目标占比之和（百分点，只作提示，不强制 100） */
  target_sum_pct: number;
  items: AllocationItem[];
  /** 越线标的数 */
  breached_count: number;
  /** 仅 PUT 返回：本次落库条数 */
  saved_count?: number;
}

/** PUT 的单条入参（对齐后端 AllocationItemIn） */
export interface AllocationTargetInput {
  symbol: string;
  /** 目标占比（百分点，0~100） */
  target_weight: number;
  notes?: string;
}

/** 策略元信息（对齐 `strategy_engine/diagnosis.list_strategies`） */
export interface EngineStrategyMeta {
  code: string;
  name: string;
  /** 策略族：timing / valuation / allocation / behavior */
  family: string;
  summary: string;
  /** 心法 / 纪律一句话 */
  discipline: string;
  params: Record<string, unknown>;
  required_data: string[];
}

/** 单条信号（对齐 `contracts.Signal.to_dict`） */
export interface EngineSignal {
  strategy_code: string;
  symbol: string;
  action: SignalAction;
  /** 状态机状态；P0 阶段不落库，仅作语义标记 */
  state: string;
  /** 后端保证是**客观陈述**，前端原样展示 */
  reason: string;
  metrics: Record<string, unknown>;
  /** 数据日期 YYYY-MM-DD；无数据时为 null */
  as_of: string | null;
}

/** 单个标的的诊断结果 */
export interface DiagnosisItem {
  symbol: string;
  name: string;
  asset_type: string;
  /** 取到的行情点数；0 表示完全没有序列 */
  sample_size: number;
  as_of: string | null;
  /** false = 样本不足，此时 signals 里的结论不可信，须明示而非显示 0 */
  data_sufficient: boolean;
  signals: EngineSignal[];
}

/** 持仓诊断响应体 */
export interface DiagnosisData {
  family_id: number;
  holding_count: number;
  items: DiagnosisItem[];
}

/** 单个标的的行为画像（对齐 `behavior_profile.BehaviorProfile.to_dict` + 后端补 name） */
export interface BehaviorProfile {
  symbol: string;
  name: string;
  trade_count: number;
  /** 平均持有天数；数据不足为 null */
  avg_hold_days: number | null;
  /** 追涨买入占比（%）；数据不足为 null */
  chase_buy_ratio: number | null;
  /** 盈利卖出占比（%）；数据不足为 null */
  profitable_sell_ratio: number | null;
  /** 提前卖出的机会成本（元）。**可能为负**：负数表示提前卖出反而躲过了下跌，须如实显示 */
  early_exit_cost: number | null;
  classified_as: string;
  /** 分类中文标签，如「趋势交易」「长期持有」；样本不足时后端给「样本不足，暂不判定」 */
  classified_label: string;
  evidence: Record<string, unknown>;
}

/** 行为反推响应体 */
export interface BehaviorData {
  family_id: number;
  profiles: BehaviorProfile[];
  summary: {
    symbol_count: number;
    total_early_exit_cost: number;
    avg_hold_days: number | null;
    avg_chase_buy_ratio: number | null;
    dominant_style: string;
    dominant_label: string;
  };
}

/**
 * 目标配比：当前占比 vs 目标占比（对齐 `GET /api/strategy/allocation/`）。
 *
 * @param threshold 偏离阈值（百分点，0~100）；不传用后端默认 5
 */
export function getAllocation(threshold?: number) {
  return http.request<{ data: AllocationData; message: string }>(
    "get",
    `${BASE_URL}allocation/`,
    { params: { threshold } }
  );
}

/**
 * 整体覆盖式保存目标配比（对齐 `PUT /api/strategy/allocation/`）。
 *
 * 提交列表即最终状态：未出现在列表里的旧目标会被后端移除，`items: []` 等价清空。
 */
export function saveAllocation(items: AllocationTargetInput[]) {
  return http.request<{ data: AllocationData; message: string }>(
    "put",
    `${BASE_URL}allocation/`,
    { data: { items } }
  );
}

/** 清空目标配比（对齐 `DELETE /api/strategy/allocation/`），幂等 */
export function clearAllocation() {
  return http.request<{ data: { cleared_count: number }; message: string }>(
    "delete",
    `${BASE_URL}allocation/`
  );
}

/**
 * 当前数据条件下可运行的策略及其元信息（对齐 `GET /api/strategy/engine/strategies/`）。
 * 供前端把 `strategy_code` 翻译成人话的策略名。
 */
export function getEngineStrategies() {
  return http.request<{ data: EngineStrategyMeta[]; message: string }>(
    "get",
    `${BASE_URL}engine/strategies/`
  );
}

/** 持仓诊断（对齐 `GET /api/strategy/engine/diagnosis/`），只读、实时计算 */
export function getEngineDiagnosis() {
  return http.request<{ data: DiagnosisData; message: string }>(
    "get",
    `${BASE_URL}engine/diagnosis/`
  );
}

/** 行为反推画像（对齐 `GET /api/strategy/engine/behavior/`），只陈述用户自己的历史事实 */
export function getEngineBehavior() {
  return http.request<{ data: BehaviorData; message: string }>(
    "get",
    `${BASE_URL}engine/behavior/`
  );
}

/**
 * 跑一次偏离扫描并写入站内通知（对齐 `POST /api/strategy/engine/reminders/refresh/`）。
 *
 * 幂等：后端按 `dedup_key`（含日期）去重，同一天重复调用不会刷屏。
 *
 * @param threshold 偏离阈值（百分点，0~100）；不传用后端默认 5
 */
export function refreshStrategyReminders(threshold?: number) {
  return http.request<{ data: { created: number }; message: string }>(
    "post",
    `${BASE_URL}engine/reminders/refresh/`,
    { params: { threshold } }
  );
}
