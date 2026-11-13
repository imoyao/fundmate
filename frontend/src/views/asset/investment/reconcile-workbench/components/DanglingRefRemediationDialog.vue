<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="min(560px, 92vw)"
    append-to-body
    @update:model-value="close"
  >
    <div class="dr-body">
      <div v-if="result" class="dr-done">
        <p class="dr-done__title">
          {{ mode === "enrich" ? "已补全信息" : "已删除" }}
        </p>
        <p>
          {{ result.summary }}，日志编号 <strong>#{{ result.log_id }}</strong>
        </p>
        <p>可凭日志编号撤销本次处理。</p>
        <el-button
          v-if="!undone"
          type="danger"
          plain
          :loading="undoing"
          @click="undo"
        >
          撤销本次处理
        </el-button>
        <p v-else class="dr-done__undone">本次处理已撤销</p>
      </div>
      <template v-else>
        <!-- 说明分两层：一句说清「现在是什么问题」，小字说清「补完会怎样」 -->
        <div class="dr-intro">
          <p v-if="mode === 'enrich' && needsFill" class="dr-intro__main">
            这些交易缺标的代码或交易日期，找不到对应的持仓。
          </p>
          <p v-else-if="mode === 'enrich'" class="dr-intro__main">
            这些交易找不到对应的持仓，但标的代码与交易日期都已填写。
          </p>
          <p v-else class="dr-intro__main">
            这些交易找不到对应的持仓记录，删除前请先核对明细。
          </p>
          <p v-if="mode === 'enrich'" class="dr-intro__sub">
            本组共 {{ txnCount }} 条交易。
          </p>
          <p v-if="mode === 'enrich'" class="dr-intro__sub dr-intro__sub--note">
            补全后系统会重新核查；若仍缺持仓，还需补建持仓或补录流水。
          </p>
          <p v-else class="dr-intro__sub">删除会写入日志，可凭日志编号撤销。</p>
        </div>
        <p v-if="mode === 'delete'" class="dr-static-warn">
          删除这些交易会影响已实现盈亏与收益统计；现存持仓份额不会改变；可凭日志编号撤销本次处理。
        </p>
        <template v-if="mode === 'enrich'">
          <!--
            表单只渲染「真正要补的字段」：分组键是 (ledger_id, symbol)，组内代码必然
            相同 ⇒ 对有代码的组，代码输入框永远补 0 条（owner 2026-11-12 截图里那个
            `SZ128021 → SZ128021`）。齐了的那一项改成只读一行，让人看见这组的键是什么。
          -->
          <el-form v-if="needsFill" label-width="90px" size="default">
            <el-form-item v-if="needs.needSymbol > 0" label="标的代码">
              <el-input
                v-model="symbolInput"
                placeholder="例如 600519"
                maxlength="30"
              />
              <p class="dr-hint">{{ symbolHint }}</p>
            </el-form-item>
            <el-form-item v-else label="标的代码">
              <span class="dr-static-value">{{ symbolStatic }}</span>
            </el-form-item>
            <el-form-item v-if="needs.needDate > 0" label="交易日期">
              <el-date-picker
                v-model="tradeDateInput"
                type="date"
                value-format="YYYY-MM-DD"
                format="YYYY-MM-DD"
                placeholder="选择成交当天"
                style="width: 100%"
              />
              <p class="dr-hint">{{ dateHint }}</p>
            </el-form-item>
            <el-form-item v-else label="交易日期">
              <span class="dr-static-value">{{ dateStatic }}</span>
            </el-form-item>
            <el-form-item label="原因（选填）">
              <el-input
                v-model="reason"
                placeholder="例如：按交割单核对后补全"
              />
            </el-form-item>
          </el-form>
          <!-- 可补 0 条：如实说明，并指向真正能处理它的两条路径 -->
          <p v-else class="dr-static-warn">{{ noFieldNote }}</p>
          <template v-if="needsFill">
            <DanglingRefEnrichSteps
              :state="stepState"
              :previewing="previewing"
              :can-preview="hasField"
              @preview="runEnrichPreview"
            />
            <DanglingRefRemediationPreview
              :mode="mode"
              :enrich-preview="enrichPreview"
              :delete-preview="deletePreview"
              :previewing="previewing"
            />
            <el-checkbox v-model="confirmed" class="dr-confirm">
              我已核对，确认补全
            </el-checkbox>
          </template>
        </template>
        <template v-else>
          <DanglingRefRemediationPreview
            :mode="mode"
            :enrich-preview="enrichPreview"
            :delete-preview="deletePreview"
            :previewing="previewing"
          />
          <el-form label-width="90px" size="default">
            <el-form-item label="确认词">
              <el-input
                v-model="confirmPhrase"
                placeholder="请输入「删除」二字确认"
              />
            </el-form-item>
            <el-form-item label="原因（选填）">
              <el-input v-model="reason" placeholder="例如：重复导入的流水" />
            </el-form-item>
          </el-form>
        </template>
      </template>
    </div>
    <template #footer>
      <el-button @click="close(false)">{{
        result ? "关闭" : "取消"
      }}</el-button>
      <!-- 缺什么只在悬浮时说明，不再一打开就把报错挂在左下角 -->
      <el-tooltip
        v-if="!result"
        :content="footerHint"
        :disabled="canSubmit"
        placement="top"
      >
        <span class="dr-footer__submit">
          <el-button
            :type="mode === 'delete' ? 'danger' : 'primary'"
            :disabled="!canSubmit"
            :loading="submitting"
            @click="submit"
          >
            {{ mode === "enrich" ? "确认补全" : "确认删除" }}
          </el-button>
        </span>
      </el-tooltip>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, toRef } from "vue";
import type { DanglingRefGroup } from "@/api/reconciliation";
import { useNestedDialog } from "../composables/useNestedDialog";
import { useDanglingRefRemediation } from "../composables/useDanglingRefRemediation";
import { reconGroupTitle } from "../utils/reconDisplay";
import DanglingRefEnrichSteps from "./DanglingRefEnrichSteps.vue";
import DanglingRefRemediationPreview from "./DanglingRefRemediationPreview.vue";

/** 数据缺失分组「补全信息 / 删除」向导：准入判据全走 guard，写路径全走 composable。 */
const props = defineProps<{
  modelValue: boolean;
  group: DanglingRefGroup | null;
  mode: "enrich" | "delete";
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
}>();

const {
  symbolInput,
  tradeDateInput,
  reason,
  confirmed,
  confirmPhrase,
  enrichPreview,
  deletePreview,
  previewing,
  submitting,
  undoing,
  undone,
  result,
  txnCount,
  needs,
  needsFill,
  hasField,
  stepState,
  blockReason,
  canSubmit,
  runEnrichPreview,
  submit,
  undo
} = useDanglingRefRemediation({
  group: toRef(props, "group"),
  mode: toRef(props, "mode"),
  open: toRef(props, "modelValue"),
  onSubmitted: () => emit("submitted")
});

/** 抽屉内打开时登记给抽屉，避免两层遮罩叠加；不在抽屉内则静默跳过。 */
useNestedDialog(toRef(props, "modelValue"));

const dialogTitle = computed(() => {
  // 标题一律 reconGroupTitle（名称优先，代码兜底），不裸插值 symbol
  const subject = props.group
    ? reconGroupTitle(props.group.symbol, props.group.display_name)
    : "数据缺失";
  return props.mode === "enrich"
    ? `补全信息 · ${subject}`
    : `删除交易 · ${subject}`;
});
const footerHint = computed(() =>
  props.mode === "enrich"
    ? stepState.value.guide
    : blockReason.value || "可以提交"
);

/** 字段说明回答「这个字段填什么、填了会怎样」，比 placeholder 更具体。 */
const symbolHint = computed(
  () =>
    `组内 ${needs.value.needSymbol} 条没有标的代码，填一次统一补上；已有代码的不改。`
);
const dateHint = computed(
  () =>
    `组内 ${needs.value.needDate} 条没有交易日期。这里填的是成交当天，会统一写入这 ${needs.value.needDate} 条；若它们不是同一天成交，这个入口补不了。`
);
/** 该字段已齐：改成只读事实，让人看见这组的键是什么，而不是给一个永远补 0 条的输入框。 */
const symbolStatic = computed(
  () => `${needs.value.symbol ?? "—"} · 组内 ${needs.value.txnCount} 条都已填写`
);
const dateStatic = computed(
  () => `组内 ${needs.value.txnCount} 条都已有交易日期`
);
const noFieldNote = computed(
  () =>
    `这组 ${txnCount.value} 条流水的标的代码与交易日期都已填写，没有可补的字段。要继续处理，需补建持仓或补录交易流水。`
);

function close(value: boolean): void {
  emit("update:modelValue", value);
}
</script>

<style scoped>
/* 本弹窗内输入框焦点用中性主墨色：品牌红与 danger 红同色系，
   聚焦红边会被误读成校验失败。只覆盖容器令牌，不碰输入基线选择器。 */
.dr-body {
  --input-hover-border-color: var(--color-primary-ink);
  --input-focus-shadow:
    0 0 0 1px var(--color-primary-ink) inset,
    0 0 0 3px color-mix(in srgb, var(--color-primary-ink) 12%, transparent);
}

.dr-intro__main {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  line-height: 1.6;
  color: var(--text-primary);
}

.dr-intro__sub,
.dr-done p {
  margin: 4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.dr-intro__sub--note {
  margin-top: -8px;
}

.dr-static-warn {
  padding: 8px 10px;
  margin: 8px 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-danger-ink);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.dr-confirm {
  margin-top: 4px;
}

/* 字段说明必须独占一行：`el-form-item__content` 是 flex+wrap，输入框占满宽度后
   说明文字会落在下一行，但不给 100% 就会跟输入框挤成一段。 */
.dr-hint {
  width: 100%;
  margin: 4px 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

/* 不需要补的字段改成只读事实：告诉人「这组的键是什么」，而不是给一个空输入框 */
.dr-static-value {
  font-size: var(--text-body);
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.dr-footer__submit {
  display: inline-flex;
  margin-left: 8px;
}

.dr-done__title {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-success-ink);
}

.dr-done__undone {
  font-weight: 600;
  color: var(--color-info-ink);
}
</style>
