<template>
  <div
    class="strategies-page p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="mb-6">
      <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">
        策略视图
      </h2>
      <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">
        按投资风格标签分组查看持仓表现。此为纯分析功能，不参与组合收益率计算。
      </p>
    </div>

    <!-- 风险提示横幅 -->
    <div
      class="bg-orange-50 border border-orange-200 rounded-xl p-4 mb-6 text-sm flex items-start gap-2"
      :style="{ color: 'var(--text-secondary)' }"
    >
      <IconifyIconOffline
        icon="ep:warning-filled"
        class="text-orange-400 mt-0.5 shrink-0"
      />
      <span
        >注：策略视图为持仓风格分析，非独立投资组合收益率。若需独立计算收益率，请创建投资组合并关联账户。</span
      >
    </div>

    <!-- 加载状态 -->
    <div
      v-if="loading"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary)' }"
    >
      <p>加载中...</p>
    </div>

    <template v-else>
      <!-- 顶部操作栏 -->
      <div class="flex justify-between items-center mb-6">
        <div class="flex gap-4">
          <el-card shadow="never" class="summary-card">
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              总持仓
            </p>
            <p
              class="text-xl font-bold"
              :style="{ color: 'var(--color-primary)' }"
            >
              {{ totalHoldings }} 项
            </p>
          </el-card>
          <el-card shadow="never" class="summary-card">
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              标签数
            </p>
            <p
              class="text-xl font-bold"
              :style="{ color: 'var(--color-primary)' }"
            >
              {{ allTags.length }} 个
            </p>
          </el-card>
          <el-card shadow="never" class="summary-card">
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              总市值
            </p>
            <p
              class="text-xl font-bold"
              :style="{ color: 'var(--color-primary)' }"
            >
              <MoneyDisplay
                :value="totalMarketValue"
                :show-sign="false"
                :auto-color="false"
              />
            </p>
          </el-card>
          <el-card shadow="never" class="summary-card">
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              总盈亏
            </p>
            <p class="text-xl font-bold">
              <MoneyDisplay :value="totalPnl" />
            </p>
          </el-card>
        </div>
        <el-button @click="openTagManager">
          <IconifyIconOffline icon="ep:setting" class="mr-1" /> 管理标签
        </el-button>
      </div>

      <!-- 分组列表 -->
      <div v-for="group in strategyGroups" :key="group.tag" class="mb-8">
        <div class="flex items-baseline justify-between mb-4">
          <h3
            class="font-bold text-lg"
            :style="{ color: 'var(--text-primary)' }"
          >
            {{ group.tag }}
            <span
              class="text-sm font-normal ml-2"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              {{ group.holdings.length }} 只持仓 · 市值
              <MoneyDisplay
                :value="group.totalMarketValue"
                :show-sign="false"
                :auto-color="false"
                size="xs"
              />
              <MoneyDisplay
                :value="group.totalPnl"
                size="xs"
                class="ml-1 font-medium"
              />
            </span>
          </h3>
        </div>

        <el-table
          v-if="group.holdings.length"
          :data="getPagedHoldings(group.tag)"
          stripe
          size="default"
        >
          <!-- 产品信息：名称/代码 + 类型标签 -->
          <el-table-column label="名称 / 代码" min-width="180">
            <template #default="{ row }">
              <div class="product-cell">
                <span class="product-name">{{
                  row.name || row.symbol || "--"
                }}</span>
                <div class="product-code-row">
                  <span class="product-code"># {{ row.symbol || "--" }}</span>
                  <span
                    v-if="row.type_label"
                    class="type-tag-inline ml-2 px-2 py-0.5 rounded-full text-xs"
                    :style="{
                      backgroundColor: 'var(--bg-page)',
                      color: 'var(--text-secondary)'
                    }"
                  >
                    {{ row.type_label }}
                  </span>
                </div>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="市值" width="130" align="right">
            <template #default="{ row }">
              <MoneyDisplay
                :value="row.marketValue || 0"
                :show-sign="false"
                :auto-color="false"
                size="sm"
              />
            </template>
          </el-table-column>

          <el-table-column label="盈亏" width="120" align="right">
            <template #default="{ row }">
              <MoneyDisplay :value="row.pnl || 0" size="sm" />
            </template>
          </el-table-column>

          <el-table-column label="盈亏率" width="90" align="right">
            <template #default="{ row }">
              <MoneyDisplay
                :value="row.pnlRate || 0"
                :precision="2"
                suffix="%"
                size="sm"
              />
            </template>
          </el-table-column>

          <el-table-column label="所属账户" width="120">
            <template #default="{ row }">{{ row.account_name }}</template>
          </el-table-column>

          <!-- 策略标签列：点击弹出多选，可增删 -->
          <el-table-column label="策略标签" width="180">
            <template #default="{ row }">
              <el-popover
                placement="bottom"
                :width="240"
                trigger="click"
                :teleported="true"
              >
                <template #reference>
                  <div class="tag-trigger">
                    <template v-if="row._tags && row._tags.length">
                      <el-tag
                        v-for="tag in row._tags"
                        :key="tag"
                        size="small"
                        class="mr-1 mb-1"
                        closable
                        @close="unbindTag(row, tag)"
                        >{{ tag }}</el-tag
                      >
                    </template>
                    <span
                      v-else
                      class="text-xs"
                      :style="{ color: 'var(--text-tertiary)' }"
                    >
                      未设置
                    </span>
                    <IconifyIconOffline
                      icon="ep:arrow-down"
                      class="ml-1 text-xs"
                      :style="{ color: 'var(--text-tertiary)' }"
                    />
                  </div>
                </template>
                <div class="tag-selector">
                  <div
                    class="text-xs mb-2"
                    :style="{ color: 'var(--text-secondary)' }"
                  >
                    为「{{ row.name || row.symbol }}」选择标签
                  </div>
                  <el-checkbox-group
                    :model-value="row._tags || []"
                    size="small"
                    @update:model-value="
                      (vals: string[]) => updateTags(row, vals)
                    "
                  >
                    <el-checkbox
                      v-for="tag in allTags"
                      :key="tag.id"
                      :label="tag.name"
                      class="block mb-1"
                    />
                  </el-checkbox-group>
                  <el-input
                    v-model="newTagNames[row.id]"
                    size="small"
                    placeholder="输入新标签名称"
                    class="mt-3"
                    @keyup.enter="createTagForRow(row)"
                  >
                    <template #append>
                      <el-button @click="createTagForRow(row)">添加</el-button>
                    </template>
                  </el-input>
                </div>
              </el-popover>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分组内分页 -->
        <div
          v-if="group.holdings.length > groupPageSize"
          class="flex justify-end mt-4"
        >
          <el-pagination
            v-model:current-page="groupPages[group.tag]"
            :page-size="groupPageSize"
            :total="group.holdings.length"
            layout="prev, pager, next"
            small
            background
          />
        </div>
      </div>

      <!-- 无数据时 -->
      <div
        v-if="strategyGroups.length === 0"
        class="text-center py-20"
        :style="{ color: 'var(--text-tertiary)' }"
      >
        <IconifyIconOffline
          icon="ep:collection"
          class="text-5xl mb-3 opacity-30"
        />
        <p class="text-lg">暂无持仓，请先导入或录入交易数据</p>
      </div>
    </template>

    <!-- 标签管理对话框 -->
    <el-dialog
      v-model="tagManagerVisible"
      title="管理策略标签"
      width="440px"
      destroy-on-close
    >
      <div class="flex items-center gap-2 mb-4">
        <el-input
          v-model="newGlobalTag"
          placeholder="输入新标签名（如：成长、价值）"
          size="small"
          @keyup.enter="createGlobalTag"
        />
        <el-button type="primary" size="small" @click="createGlobalTag"
          >添加</el-button
        >
      </div>
      <el-table :data="allTags" size="small" max-height="300">
        <el-table-column prop="name" label="标签名称" />
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-popconfirm
              title="删除后相关持仓将解绑此标签"
              @confirm="deleteGlobalTag(row.id)"
            >
              <template #reference>
                <el-button type="danger" size="small" text>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import {
  getStrategyTags,
  createStrategyTag,
  deleteStrategyTag,
  bindPositionTag,
  unbindPositionTag,
  getStrategyOverview,
  type StrategyTag
} from "@/api/strategy";

defineOptions({ name: "Strategies" });

interface EnrichedHolding {
  id: number;
  name?: string;
  symbol?: string;
  type_label?: string;
  account_name?: string;
  marketValue: number;
  pnl: number;
  pnlRate: number;
  _tags: string[];
  [key: string]: any;
}

const loading = ref(true);
const allTags = ref<StrategyTag[]>([]);
const positionTagMap = ref<Record<number, string[]>>({});
const rawHoldings = ref<EnrichedHolding[]>([]);

const tagManagerVisible = ref(false);
const newGlobalTag = ref("");
const newTagNames = ref<Record<number, string>>({});

// 分组内分页相关
const groupPageSize = 20; // 每个标签分组每页显示20条
const groupPages = ref<Record<string, number>>({}); // 标签名 -> 当前页码

async function fetchAll() {
  loading.value = true;
  try {
    const res = await getStrategyOverview();
    const { holdings = [], tags = [], relations = {} } = res.data ?? {};

    rawHoldings.value = holdings.map((h: any) => ({
      ...h,
      marketValue: (h.quantity || 0) * (h.current_price || 0),
      pnl: ((h.current_price || 0) - (h.avg_price || 0)) * (h.quantity || 0),
      pnlRate: h.avg_price
        ? ((h.current_price - h.avg_price) / h.avg_price) * 100
        : 0,
      _tags: relations[h.id] || []
    }));

    allTags.value = tags;
    positionTagMap.value = relations;

    // 初始化每个标签的页码为1
    const newPages: Record<string, number> = {};
    tags.forEach((t: StrategyTag) => {
      newPages[t.name] = 1;
    });
    newPages["未分类"] = 1;
    groupPages.value = newPages;
  } catch (e) {
    ElMessage.error("加载策略视图失败");
  } finally {
    loading.value = false;
  }
}

// 汇总数据
const totalHoldings = computed(() => rawHoldings.value.length);
const totalMarketValue = computed(() =>
  rawHoldings.value.reduce((sum, h) => sum + (h.marketValue || 0), 0)
);
const totalPnl = computed(() =>
  rawHoldings.value.reduce((sum, h) => sum + (h.pnl || 0), 0)
);

// 附加标签后的持仓
const enrichedHoldings = computed<EnrichedHolding[]>(() =>
  rawHoldings.value.map(h => ({
    ...h,
    _tags: positionTagMap.value[h.id] || []
  }))
);

// 按标签分组
const strategyGroups = computed(() => {
  const groups: Record<string, EnrichedHolding[]> = {};

  enrichedHoldings.value.forEach(h => {
    const tags = h._tags.length ? h._tags : ["未分类"];
    tags.forEach((tag: string) => {
      if (!groups[tag]) groups[tag] = [];
      groups[tag].push(h);
    });
  });

  const entries: [string, EnrichedHolding[]][] = Object.entries(groups);
  entries.sort(([a], [b]) => {
    if (a === "未分类") return 1;
    if (b === "未分类") return -1;
    return a.localeCompare(b, "zh-Hans");
  });

  return entries.map(([tag, items]) => ({
    tag,
    holdings: items,
    totalMarketValue: items.reduce(
      (sum, item) => sum + (item.marketValue || 0),
      0
    ),
    totalPnl: items.reduce((sum, item) => sum + (item.pnl || 0), 0)
  }));
});

// 获取某个标签分组的当前页数据
function getPagedHoldings(tag: string) {
  const group = strategyGroups.value.find(g => g.tag === tag);
  if (!group) return [];
  const page = groupPages.value[tag] || 1;
  const start = (page - 1) * groupPageSize;
  return group.holdings.slice(start, start + groupPageSize);
}

// ---------- 标签操作（局部更新）----------
async function unbindTag(row: EnrichedHolding | any, tagName: string) {
  const r = row as EnrichedHolding;
  const tag = allTags.value.find(t => t.name === tagName);
  if (!tag) return;
  try {
    await unbindPositionTag(tag.id, r.id);
    if (positionTagMap.value[r.id]) {
      positionTagMap.value[r.id] = positionTagMap.value[r.id].filter(
        (n: string) => n !== tagName
      );
    }
    ElMessage.success("已移除标签");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "操作失败");
  }
}

async function updateTags(row: EnrichedHolding | any, selected: string[]) {
  const r = row as EnrichedHolding;
  const current = positionTagMap.value[r.id] || [];
  const toAdd = selected.filter(t => !current.includes(t));
  const toRemove = current.filter(t => !selected.includes(t));

  for (const tagName of toAdd) {
    const tag = allTags.value.find(t => t.name === tagName);
    if (tag) {
      try {
        await bindPositionTag(tag.id, r.id);
      } catch (e) {}
    }
  }
  for (const tagName of toRemove) {
    const tag = allTags.value.find(t => t.name === tagName);
    if (tag) {
      try {
        await unbindPositionTag(tag.id, r.id);
      } catch (e) {}
    }
  }

  positionTagMap.value[r.id] = selected;
  ElMessage.success("标签已更新");
}

async function createTagForRow(row: EnrichedHolding | any) {
  const r = row as EnrichedHolding;
  const name = (newTagNames.value[r.id] || "").trim();
  if (!name) return;
  try {
    const res: any = await createStrategyTag({ name });
    const newTag: StrategyTag = res?.data;
    if (!newTag?.id) throw new Error("创建标签失败");

    allTags.value.push(newTag);
    await bindPositionTag(newTag.id, r.id);
    if (!positionTagMap.value[r.id]) positionTagMap.value[r.id] = [];
    positionTagMap.value[r.id] = [...positionTagMap.value[r.id], name];

    newTagNames.value[r.id] = "";
    ElMessage.success("标签已添加并绑定");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "创建失败");
  }
}

function openTagManager() {
  tagManagerVisible.value = true;
}

async function createGlobalTag() {
  const name = newGlobalTag.value.trim();
  if (!name) return;
  try {
    const res: any = await createStrategyTag({ name });
    const newTag: StrategyTag = res?.data;
    if (!newTag?.id) throw new Error("创建失败");

    allTags.value.push(newTag);
    newGlobalTag.value = "";
    ElMessage.success("标签已创建");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "创建失败");
  }
}

async function deleteGlobalTag(id: number) {
  try {
    await deleteStrategyTag(id);
    const deletedTag = allTags.value.find(t => t.id === id);
    allTags.value = allTags.value.filter(t => t.id !== id);

    if (deletedTag) {
      const tagName = deletedTag.name;
      Object.keys(positionTagMap.value).forEach(posId => {
        const idx = positionTagMap.value[Number(posId)]?.indexOf(tagName);
        if (idx !== undefined && idx > -1) {
          positionTagMap.value[Number(posId)].splice(idx, 1);
        }
      });
    }
    ElMessage.success("标签已删除");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "删除失败");
  }
}

onMounted(() => {
  fetchAll();
});
</script>

<style scoped>
.strategies-page {
  /* 继承全局字体 token，避免与站内其它页面字体不一致（design-tokens.css --font-ui） */
  font-family: var(--font-ui);

  /* 数字等宽对齐：消除金额/计数宽度抖动（design.md「数字等宽对齐」） */
  font-variant-numeric: tabular-nums;
}

/* 汇总卡片 */
.summary-card {
  min-width: 120px;
  padding: 8px 16px;
  border-radius: 12px;
}

/* 产品单元格 */
.product-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.3;
}

.product-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.product-code-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.product-code {
  font-size: 12px;
  color: var(--text-tertiary);
}

.type-tag-inline {
  height: 20px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 20px;
  color: #fff;
  background-color: var(--bg-page);
  border: none;
}

/* 标签触发器 */
.tag-trigger {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  min-height: 24px;
  cursor: pointer;
}

.tag-trigger:hover {
  opacity: 0.8;
}

.tag-selector {
  padding: 8px 0;
}

.tag-selector :deep(.el-checkbox) {
  display: block;
  margin-bottom: 4px;
}
</style>
