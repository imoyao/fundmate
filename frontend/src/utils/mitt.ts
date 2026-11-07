import type { Emitter } from "mitt";
import type { RouteConfigs } from "@/layout/types";
import mitt from "mitt";

/**
 * 全局公共事件需要在此处添加类型。
 *
 * #2879：`tagOnClick` / `tagViewsChange` 原先都声明成 `string`，与**实际发出的值**
 * 不符——这是「类型说谎」而不是「类型宽松」：
 * - `tagOnClick` 发的是被点击的那条标签对象（`lay-tag/index.vue` 的 `tagOnClick`），
 *   声明成 `string` 只会逼调用方写 `as unknown as string` 这类断言；
 * - `tagViewsChange` 发的是「是否隐藏标签栏」的布尔值
 *   （`lay-setting/index.vue` 的 `tagsChange`），原先靠 `as unknown as string` 硬转，
 *   接收端再 `as any` 转回来——一来一回等于没有类型。
 */
type Events = {
  openPanel: string;
  tagOnClick: RouteConfigs;
  logoChange: boolean;
  tagViewsChange: boolean;
  changLayoutRoute: string;
  tagViewsShowModel: string;
  "refresh-ledger-data": undefined;
};

export const emitter: Emitter<Events> = mitt<Events>();
