<script setup lang="ts">
/**
 * 持仓「所属组合」单元格 + 改派浮层（D20 二期 UI）。
 *
 * ## 为什么单独一列，而不是塞进「归属账户」
 * 账户维度（钱在哪）与组合维度（钱为什么而投）是**正交的两轴**。D20 之前两者被强制绑定
 * （组合 = 账户集合），界面上一律只显示组合名，于是看不出「这条持仓归到这里，是因为
 * 账户默认组合带的，还是我显式指定的」——而这正是「同一账户里固收+与成长混在一起、
 * 归类却是错的」这一痛点的根。
 *
 * 故本单元格的核心职责**不是显示组合名，而是显示归属方式**：
 * 显式指派（实心点 + 常规字色）vs 账户继承（灰点 + 常规字色 + 「随账户」标签）。
 *
 * ## 纯展示 + 事件（与父表格同一纪律）
 * 本组件不发请求：改派由页面数据层 `useInventoryData.reassignPosition` 执行。
 * 归属解析（`ledger_id` → 账户默认组合 → 组合名）也**不在本组件做**——
 * 「显式指派压过继承」是服务端口径（`portfolio_service.portfolio_position_conditions`），
 * 前端复制第二份必然漂移，故由数据层算好后经 `mode` / `labelText` 注入。
 *
 * ## 点即生效，不做二次确认
 * 改派是低风险可逆操作（再点一次就改回来），加确认框会让「一次归类 3 只基金」变成
 * 6 次点击。代价是必须给足反馈：成功 toast 里点名目标组合，并说明年化会重算——
 * 组合收益按持仓买卖流水计算（决策 D71），改派会让两端组合的本金序列同时变，
 * 不提示的话，用户看到年化数字跳变会当成 bug。
 *
 * ## 触发按钮必须 `@click.stop`
 * 本组件同时用于两张表：盘点页（表格无行点击）与账户详情页（`@row-click` 打开
 * 持仓明细抽屉）。在后者里，一次未阻断的点击会**先改派、再顺手弹出抽屉**——
 * 用户想选组合，却看到抽屉盖上来把浮层挡在下面。单元格里的可交互控件不吞掉
 * 冒泡，是表格类界面的通病，故在按钮上就地收口；浮层本体 teleport 到 body，
 * 天然不在行的冒泡链上，不必额外处理。
 */

import { computed, ref } from "vue";
import type { PortfolioItem } from "@/api/portfolio";

defineOptions({ name: "PortfolioAssignCell" });

/**
 * 「跟随账户」在单选组里的哨兵值。
 *
 * 组合 id 是自增正整数，所以字符串哨兵不会与它冲突。**不能用 `null` / `0`**：
 * `el-radio-group` 的 `model-value` 不接受 `null`（会让整组无选中），而 `0` 与
 * 「未选」难分辨。
 */
const FOLLOW_LEDGER = "__follow_ledger__";

const props = defineProps<{
  /**
   * 当前持仓行。
   *
   * 只声明本组件**实际读取**的三个字段（组合 id + 两个用于文案的名称），而不是
   * 直接要求 `Position`：账户详情页的持仓行是 `LedgerHoldingRow`（后端
   * `get_positions_paginated` 手工拼的字典，字段集与 `Position` 不同），
   * 若按整型 `Position` 约束，那边只能靠 `as Position` 强转——类型检查就再也
   * 拦不住真实的字段错配了。
   */
  row: {
    name?: string | null;
    symbol?: string | null;
    portfolio_id?: number | null;
  };
  /** 可改派的目标组合列表 */
  portfolios: PortfolioItem[];
  /**
   * 归属状态（由页面数据层解析后注入，见文件头注释）：
   * - `explicit`：显式指派到某组合；
   * - `inherited`：未指派，按账户默认组合归属；
   * - `none`：既未指派、账户也没有默认组合 → 不属于任何组合；
   * - `unknown`：响应里没有 `portfolio_id` 字段（接口未升级），**不能当成「继承」渲染**，
   *   否则会把「不知道」谎报成「随账户」。
   */
  mode: "explicit" | "inherited" | "none" | "unknown";
  /** 当前归属的组合名（`explicit` / `inherited` 时有值） */
  labelText: string | null;
}>();

const emit = defineEmits<{
  /** 选定新归属：`null` = 退回账户默认组合（后端置 `portfolio_id = NULL`） */
  select: [portfolioId: number | null];
}>();

const visible = ref(false);

/** 单选组当前值：继承 / 无归属都落在「跟随账户」这一档 */
const currentValue = computed<string | number>(() => {
  if (props.mode === "explicit" && props.row.portfolio_id != null) {
    return props.row.portfolio_id;
  }
  return FOLLOW_LEDGER;
});

/** 触发按钮的无障碍名称：说清「改谁的、现在归哪」 */
const triggerLabel = computed(() => {
  const who = props.row.name || props.row.symbol;
  const where = props.labelText
    ? `当前归入「${props.labelText}」${props.mode === "inherited" ? "（随账户）" : ""}`
    : "当前未归入任何组合";
  return `改派组合：${who}，${where}`;
});

/**
 * 点击「当前已选中的那一项」。
 *
 * Element Plus 的 `el-radio` 变更事件来自原生 `<input type=radio>` 的 `change`，
 * 而原生 radio **在已选中状态下再点不会触发 `change`**（`radio.vue` 里就只挂了
 * `onChange`）。于是 `onPick` 根本不会被调用 —— 浮层既不提交也不关闭，
 * 用户点了却什么反应都没有（2026-10-29 走查实测：静默无响应，只能点浮层外面退出）。
 *
 * 这里补一条兜底：点当前项就直接收起浮层，让「点一下总要有反应」成立。
 * 值真的不同时本函数什么都不做 —— 提交仍走 `change → onPick` 那一条路，
 * 不会出现一次点击提交两遍。
 */
function onPickSame(value: string | number) {
  if (value === currentValue.value) visible.value = false;
}

/**
 * 选定处理。
 *
 * **未变化不提交**：点当前已选项也打一次 PATCH 会既浪费请求又弹一次「已改派」toast，
 * 让用户以为发生了变更。（正常点击下 `onPick` 拿不到「未变化」的值——那一路由
 * `onPickSame` 收起浮层；此处保留判断是为了防重复提交，不是主路径。）
 */
function onPick(value: string | number | boolean) {
  visible.value = false;
  const next = value === FOLLOW_LEDGER ? null : Number(value);
  const unchanged =
    next === null ? props.mode !== "explicit" : next === props.row.portfolio_id;
  if (unchanged) return;
  emit("select", next);
}
</script>

<template>
  <el-popover
    v-model:visible="visible"
    trigger="click"
    placement="bottom-start"
    :width="292"
  >
    <template #reference>
      <button
        type="button"
        class="own-btn"
        :aria-label="triggerLabel"
        aria-haspopup="dialog"
        :aria-expanded="visible"
        @click.stop
      >
        <span v-if="mode === 'unknown'" class="own own-muted">—</span>
        <span v-else-if="mode === 'none'" class="own own-muted">未归属</span>
        <span v-else class="own" :class="`own-${mode}`">
          <i class="own-dot" aria-hidden="true" />
          <span class="own-name">{{ labelText }}</span>
          <span v-if="mode === 'inherited'" class="own-suffix">随账户</span>
        </span>
      </button>
    </template>

    <div class="reassign">
      <p class="reassign-head">{{ row.name || row.symbol }} · 改派到</p>

      <el-radio-group
        :model-value="currentValue"
        class="reassign-list"
        @change="onPick"
      >
        <el-radio
          :value="FOLLOW_LEDGER"
          class="reassign-item follow"
          @click="onPickSame(FOLLOW_LEDGER)"
        >
          <span class="reassign-label">跟随账户</span>
          <span class="reassign-hint">按账户默认组合</span>
        </el-radio>
        <el-radio
          v-for="p in portfolios"
          :key="p.id"
          :value="p.id"
          class="reassign-item"
          @click="onPickSame(p.id)"
        >
          <span class="reassign-label">{{ p.name }}</span>
        </el-radio>
      </el-radio-group>

      <p v-if="portfolios.length === 0" class="reassign-empty">
        还没有任何投资组合，改派前需要先创建一个。
      </p>

      <p class="reassign-foot">
        改派后相关组合的年化会重算：组合收益按持仓买卖流水计算，不含账户入金。
      </p>
    </div>
  </el-popover>
</template>

<style lang="scss" scoped>
/* 触发区：整格可点，但要看起来像文本而不是按钮（表格里不该出现一排按钮框） */
.own-btn {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 2px 4px;
  margin-left: -4px;
  font: inherit;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  transition: background 150ms ease;

  &:hover {
    background: var(--bg-hover);
  }

  &:focus-visible {
    outline: 2px solid var(--brand-700);
    outline-offset: 1px;
  }
}

.own {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  min-width: 0;
  font-size: inherit;
}

.own-dot {
  flex: 0 0 auto;
  width: 5px;
  height: 5px;
  border-radius: 50%;
}

/* 显式指派：用户明确指定过 → 常规字色 + 品牌色实心点（可被一眼认出「这是我设的」） */
.own-explicit {
  color: var(--text-primary);

  .own-dot {
    background: var(--brand-700);
  }
}

/* 账户继承：没有人指定过，只是账户默认组合带着 → 辅助字色 + 空心灰点 */
.own-inherited {
  color: var(--text-tertiary-ink);

  .own-dot {
    background: var(--text-disabled);
  }
}

/* 无归属 / 未知：不显示组合名，避免与「归到某个组合」混淆 */
.own-muted {
  font-size: 0.9em;
  color: var(--text-tertiary-ink);
}

.own-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.own-suffix {
  flex: 0 0 auto;
  padding: 0 4px;
  font-size: 0.8em;
  line-height: 16px;
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
  border-radius: 3px;
}

/* ---------- 浮层 ---------- */
.reassign {
  padding: 2px 0;
}

.reassign-head {
  padding: 0 2px 8px;
  margin: 0 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.9em;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
  border-bottom: 1px solid var(--border-subtle);
}

.reassign-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 260px;
  overflow-y: auto;
}

.reassign-item {
  display: flex;
  align-items: center;
  width: 100%;
  height: auto;
  padding: 7px 8px;
  margin-right: 0;
  border-radius: var(--radius-sm);

  &:hover {
    background: var(--bg-hover);
  }

  /* 「跟随账户」不是「某一个组合」，而是「不指定」这个状态：
     与下方组合列表之间必须有视觉分隔，否则会被读成「一个名叫跟随账户的组合」。 */
  &.follow {
    margin-bottom: 4px;
    border-bottom: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  }
}

.reassign-label {
  font-size: var(--text-label);
  color: var(--text-primary);
}

.reassign-hint {
  margin-left: 6px;
  font-size: 0.85em;
  color: var(--text-tertiary-ink);
}

.reassign-empty {
  margin: 6px 2px 0;
  font-size: 0.9em;
  color: var(--text-tertiary-ink);
}

.reassign-foot {
  padding: 8px 2px 0;
  margin: 8px 0 0;
  font-size: 0.85em;
  line-height: 1.55;
  color: var(--text-tertiary-ink);
  border-top: 1px solid var(--border-subtle);
}
</style>
