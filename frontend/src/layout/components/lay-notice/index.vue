<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  getNotifications,
  getUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationItem
} from "@/api/notification";
import { noticeTabs, toListItem, type ListItem } from "./data";
import NoticeList from "./components/NoticeList.vue";
import BellIcon from "~icons/ep/bell";

defineOptions({ name: "LayNotice" });

// 下拉浮层不套 CardBlock / SectionHeader：那两个是页面区块容器（自带 padding、
// radius-lg 与 shadow-raised），塞进 popper 等于在浮层里再画一张卡。浮层的描边与
// 阴影由 el-dropdown-menu 自带，这里只做内容排布。

// 单次最多要 50 条：铃铛是个下拉，超过这个量也不会有人翻，再多只是拖慢首开。
const LIST_LIMIT = 50;

const loading = ref(false);
const error = ref(false);
const items = ref<NotificationItem[]>([]);
const activeKey = ref(noticeTabs[0]?.key);

/**
 * 红点计数取自后端 `unread_count`（此前是静态数组长度，等于假数据的条目数）。
 * 初值 0 表示「还不知道」，拉取失败时保留上一次的值——把「取不到」显示成
 * 「0 条未读」会让用户以为消息都被处理掉了。
 */
const unreadCount = ref(0);

/** 三个 Tab 的列表由同一份数据按后端 category 分流（映射理由见 data.ts） */
const notices = computed(() =>
  noticeTabs.map(tab => ({
    ...tab,
    list: items.value
      .filter(item => item.category === tab.category)
      .map(toListItem)
  }))
);

const getLabel = computed(
  () => item =>
    item.name + (item.list.length > 0 ? `(${item.list.length})` : "")
);

const fetchList = async () => {
  loading.value = true;
  error.value = false;
  try {
    const res = await getNotifications({ limit: LIST_LIMIT });
    items.value = res.data?.items ?? [];
    unreadCount.value = res.data?.unread_count ?? 0;
  } catch (e) {
    // 失败态不落到「0 条」：整块换成错误提示（模板里的 role="alert" 分支），
    // 与首页「资产加载失败不显示 ¥0」同一原则。
    items.value = [];
    error.value = true;
    console.debug("[lay-notice] 通知列表加载失败", e);
  } finally {
    loading.value = false;
  }
};

/** 未读数用独立轻量端点，不开铃铛也要把红点点上 */
const fetchUnreadCount = async () => {
  try {
    const res = await getUnreadCount();
    unreadCount.value = res.data?.unread_count ?? 0;
  } catch (e) {
    console.debug("[lay-notice] 未读数拉取失败，沿用上次值", e);
  }
};

const onVisibleChange = (visible: boolean) => {
  // 每次展开都重拉：本地没有任何失效通知机制，缓存住就会让「这次会话途中新增的消息」
  // 在铃铛里始终不出现，而红点（走另一个端点）已经涨了。
  if (visible) void fetchList();
};

/** 点击单条 → 乐观置为已读，失败回滚并提示 */
const onRead = async (item: ListItem) => {
  const target = items.value.find(row => row.id === item.id);
  if (!target || target.is_read) return;
  target.is_read = true;
  unreadCount.value = Math.max(0, unreadCount.value - 1);
  try {
    await markNotificationRead(item.id);
  } catch (e) {
    target.is_read = false;
    unreadCount.value += 1;
    console.debug("[lay-notice] 标记已读失败，已回滚", e);
    ElMessage.warning("标记已读失败，请稍后重试");
  }
};

/** 全部已读 → 同样先本地生效，失败整批还原 */
const onReadAll = async () => {
  const before = unreadCount.value;
  const snapshot = items.value.map(row => row.is_read);
  items.value.forEach(row => {
    row.is_read = true;
  });
  unreadCount.value = 0;
  try {
    await markAllNotificationsRead();
  } catch (e) {
    items.value.forEach((row, index) => {
      row.is_read = snapshot[index];
    });
    unreadCount.value = before;
    console.debug("[lay-notice] 全部标记已读失败，已回滚", e);
    ElMessage.warning("全部标记已读失败，请稍后重试");
  }
};

onMounted(() => {
  void fetchUnreadCount();
});
</script>

<template>
  <el-dropdown
    trigger="click"
    placement="bottom-end"
    @visible-change="onVisibleChange"
  >
    <span
      :class="[
        'dropdown-badge',
        'navbar-bg-hover',
        'select-none',
        Number(unreadCount) !== 0 && 'mr-[10px]'
      ]"
    >
      <el-badge :value="Number(unreadCount) === 0 ? '' : unreadCount" :max="99">
        <span class="dropdown-badge__icon">
          <IconifyIconOffline :icon="BellIcon" />
        </span>
      </el-badge>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <div class="notice-panel">
          <div class="notice-panel__head">
            <span class="notice-panel__title">站内通知</span>
            <button
              v-if="!loading && !error && unreadCount > 0"
              type="button"
              class="notice-panel__action"
              @click="onReadAll"
            >
              全部已读
            </button>
          </div>

          <!-- 三态：加载 / 失败 / 数据。失败态不显示 0 条，只说取不到。 -->
          <p v-if="loading" class="notice-panel__state" role="status">
            通知加载中…
          </p>
          <div v-else-if="error" class="notice-panel__state" role="alert">
            <span>暂时无法加载通知</span>
            <button
              type="button"
              class="notice-panel__action"
              @click="fetchList"
            >
              重试
            </button>
          </div>
          <el-tabs
            v-else
            v-model="activeKey"
            :stretch="true"
            class="notice-panel__tabs"
          >
            <template v-for="item in notices" :key="item.key">
              <el-tab-pane :label="getLabel(item)" :name="`${item.key}`">
                <el-scrollbar max-height="330px">
                  <div class="notice-panel__list">
                    <NoticeList
                      :list="item.list"
                      :empty-text="item.emptyText"
                      @read="onRead"
                    />
                  </div>
                </el-scrollbar>
              </el-tab-pane>
            </template>
          </el-tabs>
        </div>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.dropdown-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 48px;
  cursor: pointer;

  &__icon {
    font-size: 18px;
  }
}

.notice-panel {
  width: 330px;

  /* 窄屏留出左右余量，330px 在 375 视口会贴住屏幕边缘。
     ⚠️ 位置必须压在 `width` 之后、嵌套规则之前：媒体查询不改变特异性，靠「后写的胜出」
     覆盖上面的 330px；挪到 `width` 之前这条覆盖会静默失效（同理 MetricGrid 那次，
     见 stylelint.config.js 的 order/order 注解）。 */
  @include bp.below("sm") {
    width: 300px;
  }

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--space-3) var(--space-standard) 0;
  }

  &__title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__action {
    padding: 0;
    font-size: 12px;
    color: var(--brand-ink);
    cursor: pointer;
    background: none;
    border: none;
  }

  &__action:hover {
    opacity: 0.8;
  }

  &__action:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }

  &__state {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    justify-content: center;
    padding: var(--space-6) var(--space-standard);
    font-size: 13px;
    color: var(--text-secondary);
  }

  &__tabs {
    :deep(.el-tabs__header) {
      margin: 0;
    }

    /* 留白与上方标题、下方列表同为一个 --space-standard，三者左边对齐 */
    :deep(.el-tabs__nav-wrap) {
      padding: 0 var(--space-standard);
    }

    :deep(.el-tabs__nav-wrap)::after {
      height: 1px;
    }
  }

  &__list {
    padding: var(--space-3) var(--space-standard) 0;
  }
}
</style>
