<!--
  口径切换条 · 分析类页面的主控（#3287）

  「用哪个范围看这份分析」——全家庭 / 单账户 / 组合。三档不是三种视图，而是同一批
  端点的三种作用域；切档等于换一份数据，所以它是**页级**主控，不归某个区块。

  ## 为什么不塞进 PageHeaderBar 的 action 槽

  页头会滚走。复盘页有 7 段、合并后 9~10 段，用户滚到第 5 段时已经不记得自己选的是
  哪个账户——而口径错了整页都是错的，它必须**一直在视野里**。故由宿主页把它放进
  吸顶容器（见 `docs/design/components.md` 的登记条目），本组件只管控件本身、不带
  定位样式：同一组件在抽屉 / 弹窗里复用时不希望被 sticky 绑架。

  ## 为什么档位是可配置的

  **档位只能在「整页每一块都算得出来」时才摆出来。** 摆出组合档而页面上有 4 块
  返回「不支持」，用户读到的是半成品；反过来偷偷让那几块退回家庭级，就是 #2595
  那类静默错口径。`kinds` 让宿主页显式声明「本页现在支持到哪一档」——
  收窄是诚实，不是功能缺失。

  ## 视觉

  - 档位用 `SegmentedControl`（全站唯一的分段控制器实现，`guard_segmented.py` 拦回潮）。
    **不用 `el-radio-group`**：它的选中态是实心品牌底，本仓实测 3.02:1 不达 AA，
    且与同页真实主按钮撞脸（`SegmentedControl` 文件头有完整裁决）。
  - 当前口径用一行 mono 小字贴在右侧（`hint`）：档位按钮只说明「我要按什么看」，
    「实际是多少」需要宿主页给（如「16 个账户」「该账户快照 68 天」）。
  - 窄屏整行折行、不横向滚动：三档加一个下拉不会溢出，硬塞滚动会让最后一项点不到。
-->
<template>
  <div class="scope-bar" :class="{ 'scope-bar--stacked': stacked }">
    <SegmentedControl
      :model-value="kind"
      :options="kindOptions"
      size="default"
      aria-label="口径"
      @change="onKindChange"
    />

    <!-- `v-if` 必须带 `options.length`：深链（`?scope=ledger&scope_id=3`）时
         modelValue 在 setup 阶段就有值，而账户列表要等接口回来。若先渲染一个
         「有值但无对应 option」的 el-select，Element Plus 会把原始值当标签显示
         —— 实测选择框里出现一个光秃秃的「3」而不是「微众银行」。等 options 到位
         再渲染，两者同批匹配，标签才对得上。 -->
    <el-select
      v-if="kind !== 'family' && options.length > 0"
      class="scope-bar__select"
      :model-value="id ?? undefined"
      :placeholder="placeholder"
      :loading="loading"
      :disabled="loading"
      clearable
      filterable
      @update:model-value="onSelect"
    >
      <el-option
        v-for="opt in options"
        :key="opt.id"
        :label="opt.name"
        :value="opt.id"
      />
    </el-select>

    <span
      v-if="kind !== 'family' && !loading && options.length === 0"
      class="scope-bar__empty"
    >
      {{ kind === "ledger" ? "暂无账户" : "暂无组合" }}
    </span>

    <span v-if="hint" class="scope-bar__hint">{{ hint }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import {
  SCOPE_KIND_LABELS,
  type ScopeKind,
  type ScopeOption
} from "@/composables/analysisScope/toScopeProps";

defineOptions({ name: "ScopeBar" });

const props = withDefaults(
  defineProps<{
    /** 当前档位（配合 `@update:kind`） */
    kind: ScopeKind;
    /** 当前选中的账户 / 组合 id；家庭档为 null */
    id?: number | null;
    /** 本页支持的档位（有序）。默认三档全开 */
    kinds?: readonly ScopeKind[];
    /** 账户列表（档位为账户时用） */
    ledgers?: readonly ScopeOption[];
    /** 组合列表（档位为组合时用） */
    portfolios?: readonly ScopeOption[];
    /** 选项正在加载 */
    loading?: boolean;
    /** 右侧「当前口径」说明：档位按钮说明意图，这里说明实际取到的是什么 */
    hint?: string;
    /** 强制纵向堆叠（窄容器 / 抽屉里用） */
    stacked?: boolean;
  }>(),
  {
    id: null,
    kinds: () => ["family", "ledger", "portfolio"],
    ledgers: () => [],
    portfolios: () => [],
    loading: false,
    hint: "",
    stacked: false
  }
);

const emit = defineEmits<{
  (e: "update:kind", value: ScopeKind): void;
  (e: "update:id", value: number | null): void;
  /** 档位或对象任一变化（宿主页只需接这一个就能重取） */
  (e: "change", value: { kind: ScopeKind; id: number | null }): void;
}>();

const kindOptions = computed(() =>
  props.kinds.map(k => ({ label: SCOPE_KIND_LABELS[k], value: k }))
);

const options = computed<readonly ScopeOption[]>(() =>
  props.kind === "ledger" ? props.ledgers : props.portfolios
);

const placeholder = computed(() =>
  props.kind === "ledger" ? "选择账户" : "选择组合"
);

/**
 * 切档必须**同时清空对象**：`portfolio` 档带着上一档的账户 id 是脏口径，
 * 而面板对「档位与 id 不匹配」不做校验（它只看到 props），会照 id 取数。
 */
function onKindChange(next: ScopeKind) {
  emit("update:kind", next);
  emit("update:id", null);
  emit("change", { kind: next, id: null });
}

/** el-select 清空时给的是 `undefined`，统一成 `null`：面板侧只认一种「空」 */
function onSelect(value: unknown) {
  const next = typeof value === "number" ? value : null;
  emit("update:id", next);
  emit("change", { kind: props.kind, id: next });
}
</script>

<style scoped lang="scss">
.scope-bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-compact);
  align-items: center;
}

/* 纵向堆叠：档位一行、对象一行、说明一行。窄容器（抽屉 / 侧栏）里横排会把
   下拉压到 100px 以下，选中项名称被截断成「招…」 */
.scope-bar--stacked {
  flex-direction: column;
  align-items: stretch;
}

/* el-select 的默认宽度是 100%（EP 2.4+ 的 `--el-select-width`），在 flex 行里会把
   整行吃掉、把档位与说明挤到上下两行（2026-11-28 走查实测切换条变成 3 行、高 105px）。
   固定 200px 并禁止伸缩：档位按钮的宽度由文案决定，账户名超出就靠下拉展开看全。 */
.scope-bar__select {
  flex: 0 0 auto;
  width: 200px;
}

.scope-bar__empty {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 「当前口径」贴右：它是注释不是控件，不该跟档位抢视觉重量。
   用 `margin-inline-start: auto` 而不是 `margin-left` —— RTL 下同样贴尾侧。 */
.scope-bar__hint {
  margin-inline-start: auto;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.scope-bar--stacked .scope-bar__hint {
  margin-inline-start: 0;
  white-space: normal;
}
</style>
