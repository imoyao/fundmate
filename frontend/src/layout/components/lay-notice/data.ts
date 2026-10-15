// 消息盒（lay-notice）的展示模型与 Tab 定义。
//
// WHY：本文件原先是 pure-admin 脚手架的假数据（写死的「小铭 评论了你」「今天」等），
// 现已接到真实端点 `/api/notifications/`。之所以还保留一层 `ListItem` 展示模型、
// 而不是把 `NotificationItem` 直接透给列表项组件：时间格式化只需做一次、
// 且模板里不必再逐字段判空（后端 body / created_at 都可能为 null）。
import { formatDateTime } from "@/utils/date";
import type {
  NotificationCategory,
  NotificationItem,
  NotificationLevel
} from "@/api/notification";

/** 列表项右上角色标的类型（沿用 Element Plus `el-tag` 的 type 取值域） */
export type NoticeTagType =
  "primary" | "success" | "warning" | "info" | "danger";

/**
 * 消息列表项。
 *
 * 字段含义已随真实接口改造：`datetime` 由后端 `created_at` 格式化而来（不再是
 * 写死的「今天 / 昨天」字符串），`extra` / `status` 承载级别色标，新增 `isRead`
 * 供列表做未读圆点与「点击即已读」判定。原 `avatar` 字段删除——后端不提供头像，
 * 留着只会渲染出处处相同的占位图。
 */
export interface ListItem {
  /** 通知主键：列表的渲染 key，也是「标记已读」的入参 */
  id: number;
  title: string;
  description: string;
  /** 已格式化的时间文案（YYYY-MM-DD HH:mm） */
  datetime: string;
  /** 级别色标文案 */
  extra: string;
  /** 级别色标配色 */
  status: NoticeTagType;
  isRead: boolean;
}

/** 消息盒 Tab：一个 Tab 承接后端一种通知归类 */
export interface TabItem {
  key: string;
  name: string;
  category: NotificationCategory;
  emptyText: string;
}

/**
 * Tab 外壳沿用脚手架遗留的三个（通知 / 消息 / 订阅），与后端单流的三种 category
 * 一一对应：系统类就是「通知」，策略信号读起来是「消息」，自选标的的动态即「订阅」。
 * 这样既不必改调用方的观感，也不用为了让某个 Tab 有内容而编数据——某一类暂时没有
 * 就不显示，落到该 Tab 自己的空态文案。
 */
export const noticeTabs: TabItem[] = [
  {
    key: "1",
    name: "通知",
    category: "system",
    emptyText: "暂无系统通知"
  },
  {
    key: "2",
    name: "消息",
    category: "strategy",
    emptyText: "暂无策略消息"
  },
  {
    key: "3",
    name: "订阅",
    category: "watchlist",
    emptyText: "暂无自选动态"
  }
];

/** 级别色标：文案 + 配色 */
interface NoticeLevelMeta {
  extra: string;
  status: NoticeTagType;
}

/**
 * 用词中性（「重要 / 提醒 / 提示」）而非指令性的「立即处理」——前端不替后端加码，
 * 合规上也不允许把客观事实渲染成建议语气。
 */
const FALLBACK_META: NoticeLevelMeta = { extra: "提示", status: "info" };

const LEVEL_META: Partial<Record<NotificationLevel, NoticeLevelMeta>> = {
  P0: { extra: "重要", status: "danger" },
  P1: { extra: "提醒", status: "warning" },
  P2: FALLBACK_META
};

/** 后端单条通知 → 展示模型 */
export function toListItem(item: NotificationItem): ListItem {
  // 后端 level 是自由字符串列，出现预期外取值时退到最弱一档，不要让整个消息盒崩掉
  const meta = LEVEL_META[item.level] ?? FALLBACK_META;
  return {
    id: item.id,
    title: item.title,
    description: item.body ?? "",
    datetime: formatDateTime(item.created_at ?? ""),
    extra: meta.extra,
    status: meta.status,
    isRead: item.is_read
  };
}
