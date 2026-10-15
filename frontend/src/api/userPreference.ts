import { http } from "@/utils/http";
import type { ApiResponse } from "@/api/types";

/**
 * 用户私有偏好键值（#1337 方案 B 跨设备同步，后端 user_preferences 表）。
 * 按 `g.current_user` 私有；GET 无值返回 data=null（非 404）。
 */
export interface UserPreferenceData<T = unknown> {
  key: string;
  value: T;
  /** 服务端最后写入时间（ISO 字符串），供前端「最近修改时间取胜」合并比较 */
  updated_at?: string | null;
}

/** 读取当前用户某偏好键（无值 → data=null） */
export function getUserPreference<T = unknown>(key: string) {
  return http.request<ApiResponse<UserPreferenceData<T> | null>>(
    "get",
    `/api/users/preferences/${key}/`
  );
}

/** upsert 写入当前用户某偏好键（同 key 覆盖，服务端刷新 updated_at） */
export function putUserPreference<T = unknown>(key: string, value: T) {
  return http.request<ApiResponse<UserPreferenceData<T>>>(
    "put",
    `/api/users/preferences/${key}/`,
    { data: { value } }
  );
}
