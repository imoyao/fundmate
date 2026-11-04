<script setup lang="ts">
/**
 * 模块一：账户选择区（#980 拆分）。
 *
 * 刻意**多根**（账户栏 + 折叠创建面板两个平级 div）：它们在大卡片里是兄弟节点，
 * 中间夹着模块二/三/四。给它们套一层 wrapper 会插出一个新的 flex/间距上下文，
 * 卡片是 `flex flex-col gap-8`，多一个 wrapper 就等于多一道 32px 间隙——
 * 视觉上凭空长出一段空白。多根片段让 DOM 与盒模型保持原样。
 */
import { IconifyIconOffline } from "@/components/ReIcon";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";

import { useManualQuickAdd } from "./useManualQuickAdd";

/** 下拉项只需要这几个字段，不引入 Ledger 全量类型（`useQuickEntry` 给的是 any[]）。
 *  `channel_category` 是标签展示的唯一来源（渠道类别），`ledger_type` 只作兜底——
 *  后端模型注释 §2.3：类型标签一律只读 channel_category。 */
export interface ManualLedgerOption {
  id: number;
  name: string;
  ledger_type: string;
  channel_category?: string;
}

withDefaults(
  defineProps<{
    /** 当前可交易的账户（已按「卖出类 / 转换」过滤掉不可用的） */
    options: ManualLedgerOption[];
    /** 是否允许「新建账户」入口：卖出类与转换场景下隐藏 */
    canCreate?: boolean;
  }>(),
  { canCreate: true }
);

/** 选中的账户 id */
const selectedLedgerId = defineModel<number | null>("selectedLedgerId", {
  required: true
});

const emit = defineEmits<{
  /** 建账成功后刷新账户列表 */
  (e: "reload"): void;
}>();

const {
  showQuickAdd,
  newAccountName,
  newAccountType,
  creatingAccount,
  quickAddTypeOptions,
  resetQuickAdd,
  quickCreateAccount
} = useManualQuickAdd(id => {
  selectedLedgerId.value = id;
});

function submit() {
  void quickCreateAccount(() => emit("reload"));
}
</script>

<template>
  <!-- 账户栏：下边框分区，不铺整块底色。
       原先用 --bg-soft 大色块铺底，在本页「卡片 + 表单」的层级里像一块补丁：
       账户是上下文、不是内容容器。改用一条 --border-subtle 分隔线划开，
       select 回到输入基线契约的常规外观（不再 :deep 清底色/描边，见 design.md #1772）。 -->
  <div
    class="account-bar flex flex-col sm:flex-row sm:items-center justify-between gap-4"
  >
    <div class="flex-1 flex items-center gap-3">
      <span
        class="text-xs font-medium"
        :style="{ color: 'var(--color-danger)' }"
        >*</span
      >
      <span
        class="text-sm font-medium"
        :style="{ color: 'var(--text-secondary)' }"
        >交易账户</span
      >
      <el-select
        v-model="selectedLedgerId"
        class="flex-1 account-select"
        style="min-width: 200px"
        placeholder="请选择交易账户以开始记账"
        filterable
        size="large"
      >
        <el-option
          v-for="ledger in options"
          :key="ledger.id"
          :label="ledger.name"
          :value="ledger.id"
        >
          <div class="flex items-center justify-between w-full">
            <span>{{ ledger.name }}</span>
            <!-- 账户标签读渠道类别，不读 ledger_type（后者是内部口径键且不可变，见 AssetTypeBadge 注释） -->
            <AssetTypeBadge
              :channel-category="ledger.channel_category"
              variant="tag"
            />
          </div>
        </el-option>
      </el-select>
    </div>

    <!-- 快捷创建按钮（非卖出/赎回/转换时显示）
         次按钮语义：不用 `type="primary" text`——theme.scss 把主按钮文字色定为
         --text-inverse（白），text 变体又是透明底，白字透明底＝整颗按钮隐身。 -->
    <el-button
      v-if="!showQuickAdd && canCreate"
      class="account-create-btn"
      size="small"
      @click="showQuickAdd = true"
    >
      <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新建账户
    </el-button>
  </div>

  <!-- 极简创建账户的折叠面板 -->
  <div
    v-if="showQuickAdd"
    class="mt-2 p-3 border rounded-lg transition-all"
    :style="{ borderColor: 'var(--border-default)' }"
  >
    <el-input
      v-model="newAccountName"
      placeholder="输入账户名称，如：华泰证券"
      size="small"
      @keyup.enter="submit"
    />
    <el-select
      v-model="newAccountType"
      class="w-full mt-2"
      size="small"
      placeholder="选择账户类型"
    >
      <el-option
        v-for="opt in quickAddTypeOptions"
        :key="opt.value"
        :label="opt.label"
        :value="opt.value"
      />
    </el-select>
    <div class="flex justify-end gap-2 mt-2">
      <el-button size="small" @click="resetQuickAdd">取消</el-button>
      <el-button
        size="small"
        type="primary"
        :loading="creatingAccount"
        :disabled="!newAccountName.trim() || !newAccountType"
        @click="submit"
      >
        创建并选择
      </el-button>
    </div>
  </div>
</template>

<style scoped>
/* 账户栏「新建账户」：次按钮（描边 + 卡片底），不能与主按钮抢焦点 */
.account-create-btn {
  flex-shrink: 0;
  height: 32px;
  padding: 0 12px;
  color: var(--text-primary);
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  transition:
    background-color 150ms ease,
    border-color 150ms ease,
    color 150ms ease;
}

.account-create-btn:hover {
  color: var(--brand-ink);
  background-color: var(--bg-hover);
  border-color: var(--brand-400);
}

/* 账户栏：不加底色，用一条分割线与表单区划开（design.md「边框与分割线」） */
.account-bar {
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-subtle);
}
</style>
