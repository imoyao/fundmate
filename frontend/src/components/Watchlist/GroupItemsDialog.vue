<!--
  GroupItemsDialog · 自定义分组「组内产品增删」弹窗（issue #987）

  与 GroupManagerDialog 的分工：
  - GroupManagerDialog 管理「分组本身」（新建 / 改名 / 改色 / 删除）；
  - 本弹窗管理「某个自定义分组里有哪些产品」（issue #987 的空白组快捷添加 +
    常规分组内增删），二者语义不同，不合并。

  为什么不用 el-transfer（issue #987 已论证）：
  自选产品数量可能较多，穿梭框一次性渲染全量列表有性能与可用性问题，且缺搜索时
  非常笨重。这里采用 issue 推荐的「搜索型 picker」：
  - 上区：本组已有产品，每行带「移除」；
  - 下区：全部自选，带搜索框 + 勾选式 picker，勾选即加入本组（随即上移到上区）。
  增删同屏、可搜索，且不随产品量增长而返工。

  props：modelValue(显隐)、group(目标自定义分组，null 时不展示内容)。
  emits：update:modelValue、changed(增删成功后触发，父组件刷新分组与列表)。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="680px"
    class="group-items-dialog"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
  >
    <div v-loading="loading" class="group-items">
      <!-- 上区：本组已有产品（每项可移除） -->
      <section class="gi-section">
        <header class="gi-section__head">
          <span class="gi-section__title">本组产品</span>
          <span class="gi-count">{{ inGroup.length }} 项</span>
        </header>
        <div class="gi-card">
          <p v-if="inGroup.length === 0" class="gi-empty">
            {{
              keyword
                ? "本组无匹配的产品"
                : "本组暂无产品，可从下方「全部自选」中添加"
            }}
          </p>
          <ul v-else class="gi-list">
            <li v-for="item in inGroup" :key="itemKey(item)" class="gi-row">
              <div class="gi-row__main">
                <span class="gi-name">{{ item.display_name }}</span>
                <span class="gi-code">{{ item.symbol }}</span>
              </div>
              <el-button
                class="gi-icon-btn"
                size="small"
                text
                :title="`从本组移除 ${item.display_name}`"
                @click="removeItem(item)"
              >
                <el-icon><Close /></el-icon>
              </el-button>
            </li>
          </ul>
        </div>
      </section>

      <!-- 下区：全部自选 picker（搜索 + 勾选即加入） -->
      <section class="gi-section">
        <header class="gi-section__head">
          <span class="gi-section__title">全部自选</span>
          <span class="gi-count">{{ candidates.length }} 项可添加</span>
        </header>
        <el-input
          v-model="keyword"
          placeholder="搜索代码或名称..."
          clearable
          class="gi-search"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <div class="gi-card gi-card--picker">
          <p v-if="candidates.length === 0" class="gi-empty">
            {{ keyword ? "未找到匹配的自选产品" : "全部自选均已在本组中" }}
          </p>
          <ul v-else class="gi-list">
            <li
              v-for="item in candidates"
              :key="itemKey(item)"
              class="gi-row gi-row--pick"
            >
              <!-- 勾选即加入：勾选后该行随即上移到「本组产品」，
                   故 checkbox 恒为未勾选态、只作一次性动作触发器 -->
              <el-checkbox
                class="gi-check"
                :model-value="false"
                @click.stop
                @change="addItem(item)"
              />
              <div class="gi-row__main" @click="addItem(item)">
                <span class="gi-name">{{ item.display_name }}</span>
                <span class="gi-code">{{ item.symbol }}</span>
              </div>
            </li>
          </ul>
        </div>
      </section>
    </div>

    <template #footer>
      <el-button type="primary" @click="close">完成</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { Search, Close } from "@element-plus/icons-vue";
import {
  getWatchlistItems,
  addItemToGroup,
  removeItemFromGroup,
  type WatchlistItem,
  type WatchlistGroup
} from "@/api/watchlist";

const props = defineProps<{
  modelValue: boolean;
  group: WatchlistGroup | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "changed"): void;
}>();

const loading = ref(false);
const keyword = ref("");
/** 「全部自选」全量池：不带分组过滤，成员判定纯前端按 group_ids 做 */
const pool = ref<WatchlistItem[]>([]);

const groupId = computed(() => props.group?.id ?? null);
const title = computed(() =>
  props.group ? `管理分组 · ${props.group.name}` : "管理分组"
);

/** 虚拟持仓行无自选记录 id，无法作为列表 key，退回 symbol */
function itemKey(item: WatchlistItem): string | number {
  return item.id ?? item.symbol;
}

function matchKeyword(item: WatchlistItem, kw: string): boolean {
  return (
    (item.symbol ?? "").toLowerCase().includes(kw) ||
    (item.display_name ?? "").toLowerCase().includes(kw)
  );
}

/** 本组已有产品（受搜索词过滤，便于大分组内定位） */
const inGroup = computed(() => {
  const gid = groupId.value;
  if (gid == null) return [];
  const kw = keyword.value.trim().toLowerCase();
  return pool.value.filter(item => {
    // 无自选记录 id 的虚拟持仓行无法执行移除（removeItem 会静默 return），
    // 故不应进入本组列表，否则会渲染出点了无反应的移除按钮
    if (item.id == null) return false;
    if (!item.group_ids?.includes(gid)) return false;
    return kw ? matchKeyword(item, kw) : true;
  });
});

/** 可添加候选：排除已在本组的、以及无自选记录 id 的虚拟持仓行 */
const candidates = computed(() => {
  const gid = groupId.value;
  const kw = keyword.value.trim().toLowerCase();
  return pool.value.filter(item => {
    if (item.id == null) return false;
    if (gid != null && item.group_ids?.includes(gid)) return false;
    return kw ? matchKeyword(item, kw) : true;
  });
});

/**
 * 拉取「全部自选」全量池。
 * 不带 group_id（否则只剩本组成员，候选区会为空）；后端分页信封含 total，
 * 据此精确翻页，避免总数为 perPage 整数倍时多发一页空请求。
 */
async function fetchPool(): Promise<void> {
  loading.value = true;
  try {
    const all: WatchlistItem[] = [];
    const perPage = 200;
    const MAX_PAGES = 50; // 安全阀：防止极端数量下无限翻页
    let page = 1;
    let fetched = 0;
    let total = Infinity;
    while (page <= MAX_PAGES && fetched < total) {
      const res = await getWatchlistItems({ page, per_page: perPage });
      const rows = (res.data ?? []) as WatchlistItem[];
      if (rows.length === 0) break;
      all.push(...rows);
      fetched += rows.length;
      total = res.total ?? fetched;
      page++;
    }
    pool.value = all;
  } catch (e) {
    ElMessage.error("获取自选列表失败");
    console.error("获取自选列表错误：", e);
  } finally {
    loading.value = false;
  }
}

async function addItem(item: WatchlistItem): Promise<void> {
  const gid = groupId.value;
  if (gid == null || item.id == null) return;
  try {
    await addItemToGroup(item.id, gid);
    // 乐观更新：就地改本池内的 group_ids，避免整表重拉造成列表跳动
    const target = pool.value.find(i => i.id === item.id);
    if (target) target.group_ids = [...(target.group_ids ?? []), gid];
    emit("changed");
  } catch (e) {
    ElMessage.error("添加失败，请重试");
    console.error("添加产品到分组失败：", e);
  }
}

async function removeItem(item: WatchlistItem): Promise<void> {
  const gid = groupId.value;
  if (gid == null || item.id == null) return;
  try {
    await removeItemFromGroup(item.id, gid);
    const target = pool.value.find(i => i.id === item.id);
    if (target) {
      target.group_ids = (target.group_ids ?? []).filter(id => id !== gid);
    }
    emit("changed");
  } catch (e) {
    ElMessage.error("移除失败，请重试");
    console.error("从分组移除产品失败：", e);
  }
}

// 每次打开重新拉取一次全量池（分组名单可能在本弹窗外被改动），并清空搜索词
watch([() => props.modelValue, () => props.group?.id], ([visible]) => {
  if (visible) {
    keyword.value = "";
    void fetchPool();
  }
});

function handleVisibleChange(value: boolean): void {
  emit("update:modelValue", value);
}

function close(): void {
  emit("update:modelValue", false);
}
</script>

<style scoped>
/* 两区纵向节奏用 --space-compact(16px)，与卡片内其它区块一致；
   区块内部元素间距取 --space-2(8px)（design.md 间距令牌，禁硬编码数值） */
.group-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
}

.gi-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.gi-section__head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
}

.gi-section__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

/* 计数：tabular-nums 防止数字变化时宽度抖动 */
.gi-count {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

/* 列表容器：细边卡片，与 TagManagerDialog 的「白底卡片列表」同语言 */
.gi-card {
  max-height: 220px;
  padding: var(--space-2);
  overflow-y: auto;
  background-color: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}

.gi-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.gi-row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-1) var(--space-2);
  background-color: var(--bg-card);
  border-radius: var(--radius-sm);
  transition: background-color 150ms ease;
}

.gi-row--pick:hover {
  background-color: var(--bg-hover);
}

/* 候选行：整行可点（点击 = 加入本组），光标提示可点 */
.gi-row--pick .gi-row__main {
  cursor: pointer;
}

.gi-row__main {
  display: flex;
  flex: 1;
  gap: var(--space-2);
  align-items: baseline;
  min-width: 0;
}

.gi-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
}

.gi-code {
  flex-shrink: 0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

/* 移除按钮：默认弱化可见，行 hover 才全亮（与表格操作列同一弱化语言） */
.gi-icon-btn {
  flex-shrink: 0;
  color: var(--text-tertiary);
  opacity: 0.55;
  transition:
    opacity 150ms ease,
    color 150ms ease,
    background-color 150ms ease;
}

.gi-row:hover .gi-icon-btn {
  opacity: 1;
}

.gi-icon-btn:hover {
  color: var(--color-danger);
  background-color: var(--bg-hover);
}

.gi-empty {
  padding: var(--space-3) 0;
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}

/* 勾选框：归零 EP 默认右边距，间距统一由行 gap 控制 */
.gi-check {
  flex-shrink: 0;
  height: auto;
  margin-right: 0;
}
</style>
