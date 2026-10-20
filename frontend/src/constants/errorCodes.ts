// src/constants/errorCodes.ts
/**
 * 后端业务错误码（与 `backend/app/core/exceptions.py::ErrorCode` 对齐）。
 *
 * 只登记**前端需要按码分支**的少数几个；不复制整张表——表一长就没人核对，
 * 反而会与后端漂移。新增前先问：前端真的要靠它分支吗？
 */

/**
 * `PRO_NOT_ENTITLED`（#2324）：家庭未开通该 Pro 功能（HTTP 403）。
 *
 * 为什么必须与通用 403 分开：403 在本仓还承载「viewer 只读」等语义，
 * 前端只凭状态码会把「该开通 Pro」误判成「没有权限做这件事」，
 * 或者反过来把权限问题说成故障。
 */
export const PRO_NOT_ENTITLED_CODE = 1007;
