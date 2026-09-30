// 健康检查接口客户端（#1720）：`GET /api/health` 的响应体。
//
// ⚠️ 本接口**不使用** `{data, message}` 信封（与 assets/positions 等业务接口不同）：
// 它是运维探活端点（探活工具普遍按 `/health` 调用、只认顶层 `status`），
// 与尾斜杠一样属 `conventions.md` 的明文例外（D28）。故这里直接以 `HealthData`
// 标注响应体——**写成 `ApiResponse<HealthData>` 会让人以为要读 `res.data`，
// 而实际 `res.data` 恒为 undefined，页面永远停在骨架屏（#1802 的根因）**。
import { http } from "@/utils/http";

export type ComponentStatus =
  "ok" | "healthy" | "degraded" | "unhealthy" | "disabled" | string;

export interface ComponentHealth {
  status: ComponentStatus;
  message?: string;
  [key: string]: unknown;
}

export interface DatabaseHealth extends ComponentHealth {
  dialect?: string;
}

export interface SchedulerHealth extends ComponentHealth {
  enabled: boolean;
  last_success_run: string | null;
}

export interface LlmHealth extends ComponentHealth {
  configured: boolean;
  provider?: string;
  model?: string;
  endpoint?: string;
}

export interface HealthData {
  status: "ok" | "degraded" | string;
  message: string;
  components: {
    database: DatabaseHealth;
    scheduler: SchedulerHealth;
    llm: LlmHealth;
  };
}

export const getHealth = () => {
  return http.request<HealthData>("get", "/api/health");
};
