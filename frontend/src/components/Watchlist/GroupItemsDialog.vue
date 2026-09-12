<!--
  GroupItemsDialog · 自定义分组「组内产品增删」抽屉（issue #987 / #1449）

  与 GroupManagerDialog 的分工：
  - GroupManagerDialog 管理「分组本身」（新建 / 改名 / 改色 / 删除）；
  - 本抽屉管理「某个自定义分组里有哪些产品」，二者语义不同，不合并。

  交互演进（#1449）：原上下两区弹窗改为右侧抽屉双栏——左「本组产品」、
  右「全部自选」picker，空间大、可搜索、不挡表格，适合产品较多的场景。

  Bug 2 根因修复（#1449）：「本组产品」不再依赖 _enrich_item 填的 group_ids，
  而是直接调 getWatchlistItems({group_id})——与主列表同源（后端 SQL JOIN
  group_links），杜绝「主列表有、弹窗空」的数据源不一致。「全部自选」池翻页
  以「本页行数 < per_page」为终止条件，不依赖 res.total，避免 total 缺失时
  只拉第一页导致候选不全。

  props：modelValue(显隐)、group(目标自定义分组，null 时不展示内容)。
  emits：update:modelValue、changed(增删成功后触发，父组件刷新分组与列表)。
-->
<template>
  <el-drawer
    :model-value="modelValue"
    :title="title"
    direction="rtl"
    size="760px"
    class="group-items-drawer"
    :close-on-click-modal="false"
    @update:model-value="handleVisibleChange"
  >
    <div v-loading="loading" class="group-items">
      <el-input
        v-model="keyword"
        placeholder="搜索代码或名称（同时过滤左右两栏）..."
        clearable
        class="gi-search"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

      <div class="gi-cols">
        <!-- 左栏：本组产品（与列表同源：后端按 group_id SQL JOIN 取数） -->
        <section class="gi-col">
          <header class="gi-col__head">
            <span class="gi-col__title">本组产品</span>
            <span class="gi-count">{{ inGroup.length }} 项</span>
          </header>
          <div class="gi-card">
            <p v-if="inGroup.length === 0" class="gi-empty">
              {{
                keyword
                  ? "本组无匹配的产品"
                  : "本组暂无产品，可从右侧「全部自选」中添加"
              }}
            </p>
            <ul v-else class="gi-list">
              <li v-for="item in inGroup" :key="itemKey(item)" class="gi-row">
                <div class="gi-row__main">
                  <span class="gi-name">{{ item.display_name }}</span>
                  <span v-if="showCode(item)" class="gi-code">{{
                    item.symbol
                  }}</span>
                  <span v-else-if="subtitleOf(item)" class="gi-code">{{
                    subtitleOf(item)
                  }}</span>
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

        <!-- 右栏：全部自选 picker（搜索 + 勾选/点击即加入本组） -->
        <section class="gi-col">
          <header class="gi-col__head">
            <span class="gi-col__title">全部自选</span>
            <span class="gi-count">{{ candidates.length }} 项可添加</span>
          </header>
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
                <!-- 勾选即加入：勾选后该行随即进入左栏「本组产品」，
                     故 checkbox 恒为未勾选态、只作一次性动作触发器 -->
                <el-checkbox
                  class="gi-check"
                  :model-value="false"
                  @click.stop
                  @change="addItem(item)"
                />
                <div class="gi-row__main" @click="addItem(item)">
                  <span class="gi-name">{{ item.display_name }}</span>
                  <span v-if="showCode(item)" class="gi-code">{{
                    item.symbol
                  }}</span>
                  <span v-else-if="subtitleOf(item)" class="gi-code">{{
                    subtitleOf(item)
                  }}</span>
                </div>
              </li>
            </ul>
          </div>
        </section>
      </div>
    </div>

    <template #footer>
      <el-button type="primary" @click="close">完成</el-button>
    </template>
  </el-drawer>
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
import { buildAssetSubtitle, shouldShowAssetCode } from "@/utils/assetDisplay";

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
/** 本组产品：直接按 group_id 拉取（后端 SQL JOIN group_links，与主列表同源，确保一致） */
const inGroupItems = ref<WatchlistItem[]>([]);
/** 「全部自选」全量池：不带分组过滤，候选判定纯前端按 id 排除本组 */
const pool = ref<WatchlistItem[]>([]);

const groupId = computed(() => props.group?.id ?? null);
const title = computed(() =>
  props.group ? `管理分组 · ${props.group.name}` : "管理分组"
);

/** 虚拟持仓行无自选记录 id，无法作为列表 key，退回 symbol */
function itemKey(item: WatchlistItem): string | number {
  return item.id ?? item.symbol;
}

function subtitleOf(item: WatchlistItem): string {
  return buildAssetSubtitle(item);
}

function showCode(item: WatchlistItem): boolean {
  return shouldShowAssetCode(item);
}

function matchKeyword(item: WatchlistItem, kw: string): boolean {
  const haystack = [item.symbol, item.display_name, subtitleOf(item)]
    .filter((v): v is string => Boolean(v))
    .join(" ")
    .toLowerCase();
  return haystack.includes(kw);
}

/** 本组产品（受搜索词过滤，便于大分组内定位） */
const inGroup = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  return inGroupItems.value.filter(item =>
    kw ? matchKeyword(item, kw) : true
  );
});

/** 可添加候选：排除本组成员、以及无自选记录 id 的虚拟持仓行 */
const candidates = computed(() => {
  const memberIds = new Set(
    inGroupItems.value.map(i => i.id).filter((id): id is number => id != null)
  );
  const kw = keyword.value.trim().toLowerCase();
  return pool.value.filter(item => {
    if (item.id == null) return false; // 虚拟持仓行无法加入分组
    if (memberIds.has(item.id)) return false;
    return kw ? matchKeyword(item, kw) : true;
  });
});

/** 拉取本组成员：按 group_id（SQL JOIN，与主列表同源），杜绝「列表有、弹窗空」 */
async function fetchInGroup(): Promise<void> {
  const gid = groupId.value;
  if (gid == null) {
    inGroupItems.value = [];
    return;
  }
  const all: WatchlistItem[] = [];
  const perPage = 200;
  const MAX_PAGES = 50; // 安全阀：防止极端数量下无限翻页
  let page = 1;
  let fetched = 0;
  let total = Infinity;
  while (page <= MAX_PAGES && fetched < total) {
    const res = await getWatchlistItems({
      group_id: gid,
      page,
      per_page: perPage
    });
    const rows = (res.data ?? []) as WatchlistItem[];
    if (rows.length === 0) break;
    all.push(...rows);
    fetched += rows.length;
    total = res.total ?? fetched;
    page++;
  }
  inGroupItems.value = all;
}

/**
 * 拉取「全部自选」全量池（不带 group_id）。
 * 翻页以「本页行数 < perPage」为终止条件，不依赖 res.total，
 * 避免 total 缺失时只拉第一页导致候选区不全（#1449 Bug 2 加固）。
 */
async function fetchPool(): Promise<void> {
  const all: WatchlistItem[] = [];
  const perPage = 200;
  const MAX_PAGES = 50;
  let page = 1;
  while (page <= MAX_PAGES) {
    const res = await getWatchlistItems({ page, per_page: perPage });
    const rows = (res.data ?? []) as WatchlistItem[];
    if (rows.length === 0) break;
    all.push(...rows);
    if (rows.length < perPage) break; // 末页已取尽，停止翻页
    page++;
  }
  pool.value = all;
}

async function addItem(item: WatchlistItem): Promise<void> {
  const gid = groupId.value;
  if (gid == null || item.id == null) return;
  try {
    await addItemToGroup(item.id, gid);
    // 乐观更新：本组成员列表直接加，pool 内对应 item.group_ids 同步，避免整表重拉
    if (!inGroupItems.value.some(i => i.id === item.id)) {
      inGroupItems.value.push(item);
    }
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
    inGroupItems.value = inGroupItems.value.filter(i => i.id !== item.id);
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

// 每次打开重新拉取（分组名单可能在本抽屉外被改动），并清空搜索词
watch([() => props.modelValue, () => props.group?.id], ([visible]) => {
  if (visible) {
    keyword.value = "";
    loading.value = true;
    Promise.all([fetchInGroup(), fetchPool()])
      .catch(e => {
        ElMessage.error("获取自选列表失败");
        console.error("获取自选列表错误：", e);
      })
      .finally(() => {
        loading.value = false;
      });
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
.group-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
}

.gi-search {
  flex-shrink: 0;
}

/* 双栏：左右等宽，间距统一用 --space-compact（design.md 间距令牌，禁硬编码） */
.gi-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-compact);
  min-height: 0;
}

.gi-col {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.gi-col__head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
}

.gi-col__title {
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

/* 列表容器：细边卡片，与 TagManagerDialog 的「白底卡片列表」同语言；
   抽屉内高度受限，用 60vh 留出搜索框与表头空间 */
.gi-card {
  max-height: 60vh;
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
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
  white-space: nowrap;
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
