/**
 * 接口错误 → 用户可读文案（#2879）。
 *
 * ## 为什么需要显式收窄
 *
 * 本仓后端所有接口统一返回信封 `{ data, message, error_code }`：axios 抛出的
 * `error.message` 是英文的 `Request failed with status code 400`，真正给人看的
 * 中文在 `error.response.data.message`。而 `catch` 的入参是 **`unknown`** ——
 * 直接点 `e.response.data.message` 时，一旦抛出物不是 axios 错误（字符串、`null`、
 * 业务层自己 `throw new Error`），就会在**错误处理路径里**再抛一次 TypeError，
 * 用户看到的是完全不相干的错。
 *
 * ## 判据顺序
 *
 * 1. 抛出物本身是字符串（`throw "…"`）→ 直接用；
 * 2. 后端信封 `response.data.message`；
 * 3. `Error.message`（网络层、前端自抛）；
 * 4. 调用方兜底文案。
 *
 * 边界：只负责「文案」，不判断是否该重试、是否该跳转；认证类错误码映射见
 * `utils/authError.ts`（那层的判据是 GoTrue 的 `code`，与接口信封不同源）。
 */
export function apiErrorMessage(e: unknown, fallback: string): string {
  if (typeof e === "string" && e.trim()) return e;
  if (!e || typeof e !== "object") return fallback;

  const err = e as {
    message?: unknown;
    response?: { data?: { message?: unknown } };
  };
  const backend = err.response?.data?.message;
  if (typeof backend === "string" && backend.trim()) return backend;
  if (typeof err.message === "string" && err.message.trim()) return err.message;

  return fallback;
}
