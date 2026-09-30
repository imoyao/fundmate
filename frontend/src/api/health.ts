// 健康检查接口客户端（#1720）：展示后端 GET /api/health 返回的组件健康。
// 该接口免登录（监控/探活用），前端「系统状态」页（/system/status，#1795 命名收敛）据此呈现运维状态。
// 文件按**接口**命名（health），页面按**展示语义**命名（status）——两者刻意不同，勿强行统一。
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

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

export type HealthResult = ApiResponse<HealthData>;

export const getHealth = () => {
  return http.request<HealthResult>("get", "/api/health");
};
