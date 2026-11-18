// frontend/src/api/products.ts
// 产品域 API 公共入口（#2878）：本文件只做 barrel 转发，不含任何实现。
// 21 个端点按子域落在 ./products/*.ts；既有 `@/api/products` 调用点零改动。
// 新增端点请写进对应子域模块，勿把实现搬回来——
// scripts/guard_products_api.mjs 会拦住往 barrel 里堆代码的回潮。
export * from "./products/resolve";
export * from "./products/fund";
export * from "./products/fundRisk";
export * from "./products/indices";
export * from "./products/stock";
export * from "./products/manager";
export * from "./products/trend";
export * from "./products/advisor";
export * from "./products/pro";
