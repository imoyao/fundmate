/**
 * 异常 / 后端错误信封的 unknown 安全取值（#2879）。
 *
 * catch 到的值是 unknown：直接点 `e.response.data.message`，在「不是 axios
 * 错误」时会二次抛 TypeError；错误处理路径里再抛错，用户看到的是另一个错。
 * 这里把「取后端中文消息 / HTTP 状态 / 业务 data」收成显式收窄函数。
 */

interface ErrorEnvelope {
  response?: {
    status?: number;
    data?: {
      message?: unknown;
      data?: unknown;
    };
  };
  message?: unknown;
  action?: unknown;
  status?: number;
}

/** 只有对象形态的异常才有信封字段；字符串 / null 一律当空信封。 */
export function asErrorEnvelope(e: unknown): ErrorEnvelope {
  return e && typeof e === "object" ? (e as ErrorEnvelope) : {};
}

/** 后端信封 message 优先，其次 Error.message / 字符串异常；取不到返回空串。 */
export function errorMessageOf(e: unknown): string {
  const env = asErrorEnvelope(e);
  const msg = env.response?.data?.message ?? env.message;
  if (typeof msg === "string" && msg) return msg;
  return typeof e === "string" ? e : "";
}

export function errorStatusOf(e: unknown): number | undefined {
  const env = asErrorEnvelope(e);
  return env.response?.status ?? env.status;
}

export function errorPayloadOf<T = unknown>(e: unknown): T | undefined {
  return asErrorEnvelope(e).response?.data?.data as T | undefined;
}
