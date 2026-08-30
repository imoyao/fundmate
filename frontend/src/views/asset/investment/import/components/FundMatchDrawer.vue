<!-- frontend/src/views/asset/investment/import/components/FundMatchDrawer.vue -->
<template>
  <el-drawer
    :model-value="visible"
    title="匹配基金代码"
    size="540px"
    direction="rtl"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="fund-match-body">
      <p class="match-desc">
        以下基金缺少代码，请根据名称搜索匹配。选中后将自动应用到所有同名记录。
      </p>

      <div v-for="item in missingFundNames" :key="item.name" class="match-card">
        <div class="match-card-header">
          <span class="match-fund-name">{{ item.name }}</span>
          <el-tag size="small" type="info">{{ item.count }} 条记录</el-tag>
        </div>

        <!-- 未匹配状态：显示搜索框 -->
        <div v-if="!matchedMap[item.name]" class="match-row">
          <el-select
            :model-value="searchInputs[item.name] || ''"
            filterable
            remote
            reserve-keyword
            placeholder="输入代码或名称搜索"
            :remote-method="(keyword: string) => searchFund(keyword, item.name)"
            :loading="searchLoading[item.name]"
            default-first-option
            class="match-select"
            @change="(code: string) => applyMatch(item.name, code)"
          >
            <el-option
              v-for="fund in searchResults[item.name] || []"
              :key="fund.code"
              :label="`${fund.name} (${fund.code})`"
              :value="fund.code"
            />
          </el-select>
        </div>

        <!-- 已匹配状态：显示结果和清除按钮 -->
        <div v-else class="match-row matched">
          <div class="matched-info">
            <IconifyIconOffline
              icon="ep:circle-check-filled"
              class="matched-icon"
            />
            <span>{{ matchedMap[item.name].code }}</span>
            <span class="matched-name">{{ matchedMap[item.name].name }}</span>
          </div>
          <el-button
            type="danger"
            text
            size="small"
            @click="clearMatch(item.name)"
          >
            <IconifyIconOffline icon="ep:delete" class="mr-1" />
            清除选择
          </el-button>
        </div>
      </div>

      <div v-if="allMatched" class="all-matched-tip">
        <el-alert
          title="所有基金已匹配完成"
          type="success"
          :closable="false"
          show-icon
        />
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import { searchFunds } from "@/api/funds";
import { navCache } from "@/composables/useNavCache";

interface MissingItem {
  name: string;
  count: number;
}

const props = defineProps<{
  visible: boolean;
  missingFundNames: MissingItem[];
  previewData: any[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  "match-complete": [];
}>();

// 搜索状态
const searchResults = reactive<Record<string, any[]>>({});
const searchLoading = reactive<Record<string, boolean>>({});
const searchInputs = reactive<Record<string, string>>({});

// 已匹配状态: { 基金名称 → 匹配到的基金对象 }
const matchedMap = reactive<
  Record<string, { code: string; name: string } | null>
>({});

const allMatched = computed(() => {
  if (!props.missingFundNames.length) return false;
  return props.missingFundNames.every(item => matchedMap[item.name]);
});

// 使用 computed 双向绑定
const drawerVisible = computed({
  get: () => props.visible,
  set: val => emit("update:modelValue", val)
});

// 搜索基金
async function searchFund(keyword: string, fundName: string) {
  searchInputs[fundName] = keyword;
  if (!keyword || keyword.length < 1) {
    searchResults[fundName] = [];
    return;
  }
  searchLoading[fundName] = true;
  try {
    const res: any = await searchFunds(keyword);
    searchResults[fundName] = res?.data ?? [];
  } catch {
    searchResults[fundName] = [];
  } finally {
    searchLoading[fundName] = false;
  }
}

// 应用匹配
async function applyMatch(fundName: string, code: string) {
  const selected = (searchResults[fundName] || []).find(
    (f: any) => f.code === code
  );
  if (!selected) return;

  // 1. 批量更新 previewData 中同名的记录，并收集需要填充净值的行
  const matchedRows: any[] = [];
  props.previewData.forEach(row => {
    if (row.name === fundName && !row.symbol) {
      row.symbol = code;
      matchedRows.push(row);
    }
  });

  // 2. 为这些行自动填充净值（如果日期和金额有效）
  if (matchedRows.length) {
    // 按日期分组
    const dateGroups: Record<string, string[]> = {};
    matchedRows.forEach(row => {
      const dt = row.trade_date;
      if (!dt || !row.amount || row.amount <= 0) return; // 无日期或无金额无法计算
      if (!dateGroups[dt]) dateGroups[dt] = [];
      if (!dateGroups[dt].includes(row.symbol)) {
        dateGroups[dt].push(row.symbol);
      }
    });

    // 逐日请求净值
    for (const [date, symbols] of Object.entries(dateGroups)) {
      try {
        // 经 useNavCache：本地缓存优先，未命中再 JSONP 直连（#1133）
        const navMap = await navCache.getNavs(symbols, date);

        // 填回行数据
        matchedRows.forEach(row => {
          if (row.trade_date === date && symbols.includes(row.symbol)) {
            const nav = navMap[row.symbol];
            if (nav && nav > 0) {
              row.price = nav;
              row.quantity = row.amount / nav;
              row.is_calculated = true;
            }
          }
        });
      } catch {
        // 静默失败，不影响匹配
      }
    }
  }

  matchedMap[fundName] = { code: selected.code, name: selected.name };
  ElMessage.success(
    `已为「${fundName}」匹配 ${selected.code}，应用 ${matchedRows.length} 条`
  );

  // 检查是否所有缺失基金都已匹配，如果是则自动关闭抽屉
  if (props.missingFundNames.every(item => matchedMap[item.name])) {
    ElMessage.success("所有基金已匹配完成，抽屉即将关闭");
    setTimeout(() => {
      drawerVisible.value = false;
    }, 800);
  }

  emit("match-complete");
}
// 清除匹配
function clearMatch(fundName: string) {
  props.previewData.forEach(row => {
    if (row.name === fundName && row.symbol) {
      row.symbol = "";
    }
  });
  delete matchedMap[fundName];
  searchInputs[fundName] = fundName;
  ElMessage.info(`已清除「${fundName}」的匹配`);
  emit("match-complete");
}

// 打开抽屉时初始化：预填搜索框、清空旧状态
watch(
  () => props.visible,
  val => {
    if (val) {
      // 重置搜索状态
      Object.keys(searchResults).forEach(k => delete searchResults[k]);
      Object.keys(searchLoading).forEach(k => delete searchLoading[k]);
      Object.keys(matchedMap).forEach(k => delete matchedMap[k]);

      // 预填搜索框
      props.missingFundNames.forEach(item => {
        searchInputs[item.name] = item.name;
      });
    }
  }
);

watch(allMatched, val => {
  if (val) {
    ElMessage.success("所有基金已匹配完成");
    // 稍微延迟后关闭，让用户看到所有卡片都已完成
    setTimeout(() => {
      drawerVisible.value = false;
    }, 800);
  }
});
</script>

<style scoped>
.fund-match-body {
  padding: 0 4px;
}

.match-desc {
  margin-bottom: 20px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.match-card {
  padding: 16px;
  margin-bottom: 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 10px;
}

.match-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.match-fund-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.match-row {
  display: flex;
  gap: 10px;
  align-items: center;
}

.match-select {
  width: 100%;
}

.matched {
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--bg-muted);
  border-radius: 6px;
}

.matched-info {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  color: var(--text-primary);
}

.matched-icon {
  font-size: 16px;
  color: var(--color-success);
}

.matched-name {
  color: var(--text-secondary);
}

.all-matched-tip {
  margin-top: 12px;
}
</style>
