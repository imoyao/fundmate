/**
 * 系统状态页的口径（#980 批 B9 从 `views/status/index.vue` 抽出）。
 *
 * 页面只剩「什么时候取数」与外壳；「状态码怎么说成人话」「哪些算需要关注」
 * 「整体横幅该报什么」这三件事是纯映射，与 Vue 无关，故单独成文件以便单测。
 *
 * 之所以值得单独钉：`/api/health` 的 `status` 是**开放字符串联合**
 * （`ComponentStatus = "ok" | "healthy" | ... | string`），后端随时可能加新值。
 * 未知值若被当成「正常」，状态页就会在真出事时显示一片绿——这是本页最坏的失效方式。
 */
import type { ComponentStatus, HealthData } from "@/api/health";

/** 语义色调：点色 / 文字色 分别取令牌的不同档，这里只做归类 */
export type Tone = "ok" | "warn" | "error" | "muted";

/** 状态码 → 中文。未收录的新枚举**原样透出**，不猜成「正常」 */
export const STATUS_TEXT: Record<string, string> = {
  healthy: "正常",
  ok: "正常",
  degraded: "降级",
  unhealthy: "异常",
  disabled: "未启用"
};

export function statusText(status: ComponentStatus): string {
  return STATUS_TEXT[status] ?? status;
}

/**
 * 状态 → 语义色调。
 *
 * 注意兜底方向：**没见过的状态归到 error**（需关注），不是 ok。
 * 宁可让一次后端枚举新增显示成红色提醒，也不要让真实故障藏在「正常」里。
 */
export function statusTone(status: ComponentStatus): Tone {
  if (status === "healthy" || status === "ok") return "ok";
  if (status === "disabled") return "muted";
  if (status === "degraded") return "warn";
  return "error";
}

export interface ComponentRow {
  name: string;
  status: ComponentStatus;
  /** 常规要点（始终展示）：方言 / 最近成功运行 / 模型 */
  detail: string;
  /** 仅异常时展示的可读原因，正常时不占位（status page 的「无消息即正常」） */
  hint: string;
}

/** 健康数据 → 三行组件清单。无数据时给空数组（骨架屏阶段） */
export function buildComponentRows(health: HealthData | null): ComponentRow[] {
  const c = health?.components;
  if (!c) return [];
  const scheduler = c.scheduler;
  // 后端给的是 `2026-10-27T06:06:39.184874`，这里只取到分钟并换空格
  const lastRun = scheduler.last_success_run
    ? scheduler.last_success_run.slice(0, 16).replace("T", " ")
    : "";
  return [
    {
      name: "数据库",
      status: c.database.status,
      detail: (c.database.dialect ?? "").toUpperCase(),
      hint: c.database.status === "healthy" ? "" : (c.database.message ?? "")
    },
    {
      name: "数据调度",
      status: scheduler.status,
      detail: !scheduler.enabled
        ? "未开启自动更新"
        : lastRun
          ? `最近成功运行 ${lastRun}`
          : "尚无成功记录",
      hint:
        scheduler.status === "healthy" || scheduler.status === "disabled"
          ? ""
          : (scheduler.message ?? "")
    },
    {
      name: "AI 识别",
      status: c.llm.status,
      detail: c.llm.configured
        ? [c.llm.provider, c.llm.model].filter(Boolean).join(" · ")
        : "未配置",
      hint:
        c.llm.status === "healthy" || c.llm.status === "disabled"
          ? ""
          : (c.llm.message ?? "")
    }
  ];
}

export interface BannerModel {
  tone: Tone;
  icon: string;
  title: string;
  desc: string;
}

/**
 * 顶部整体横幅：一眼看出「有没有事」；异常时直接列出受影响的组件。
 *
 * 优先级：取数失败 > 无数据（返回 null，页面渲染骨架屏）> 按组件状态汇总。
 * 「取数失败」必须压过一切——后端连不上时拿不到任何组件状态，此时说「全部正常」
 * 是最严重的撒谎（#1793 / #1802 都栽在这上面）。
 */
export function buildBanner(input: {
  errorMessage: string;
  hasHealth: boolean;
  rows: ComponentRow[];
}): BannerModel | null {
  const { errorMessage, hasHealth, rows } = input;
  if (errorMessage) {
    return {
      tone: "error",
      icon: "ep:circle-close-filled",
      title: "暂时无法获取状态",
      desc: errorMessage
    };
  }
  if (!hasHealth) return null;
  const affected = rows.filter(r => {
    const tone = statusTone(r.status);
    return tone === "warn" || tone === "error";
  });
  if (affected.length === 0) {
    return {
      tone: "ok",
      icon: "ep:success-filled",
      title: "所有组件运行正常",
      desc: ""
    };
  }
  return {
    tone: "warn",
    icon: "ep:warning-filled",
    title: "部分组件需要关注",
    desc: affected.map(r => `${r.name}：${statusText(r.status)}`).join("；")
  };
}
