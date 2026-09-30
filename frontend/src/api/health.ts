// 系统健康检查（#1720）：展示后端 GET /api/health 返回的组件健康。
// 该接口免登录（监控/探活用），前端管理页据此向维护者呈现运维状态。
import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

export type ComponentStatus =
  | "ok"
  | "healthy"
  | "degraded"
  | "unhealthy"
  | "disabled"
  | string;

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
