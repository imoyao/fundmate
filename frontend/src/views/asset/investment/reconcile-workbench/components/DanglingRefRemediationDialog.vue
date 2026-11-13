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
        <!-- 一行说清「现在是什么问题」就停：机制承诺与跨阶段指路句已删
             （design.md「先删，再重排」②、spec §3.6）；删除的影响在下方
             预览面板里逐条列出，不在这里复述。 -->
        <p v-if="mode === 'enrich'" class="dr-intro__main">
          这些交易缺标的代码或交易日期，找不到对应的持仓。
        </p>
        <p v-else class="dr-intro__main">这些交易找不到对应的持仓记录。</p>
        <template v-if="mode === 'enrich'">
          <!--
            表单只渲染「真正要补的字段」：分组键是 (ledger_id, symbol)，组内代码必然
            相同 ⇒ 对有代码的组，代码输入框永远补 0 条（owner 2026-11-12 截图里那个
            `SZ128021 → SZ128021`）。齐了的那一项改成只读一行，让人看见这组的键是什么。
            漏斗重构后（2026-11-13）只有 `fill` 阶段的组会进本弹窗，`needsFill === false`
            的分支不再渲染任何兜底块——`rebuild` / `reattach` 组各有自己的阶段面板与动作面。
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
      <!-- 缺什么只在悬浮时说明，不再一打开就把报错挂在左下角；
           「重建持仓」不再经由本弹窗（rebuild 组有自己的阶段，spec §3.5）。 -->
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

/** 数据缺失分组「补全信息 / 删除」向导：准入判据全走 guard，写路径全走 composable。
 *  漏斗重构（2026-11-13）：只有 `fill` 阶段的组走 enrich、删除只走 mode="delete"；
 *  `rebuild` 组不再进入本弹窗（弹窗不再抛 requestRebuild，重建入口只在阶段面板）。 */
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

.dr-done p {
  margin: 4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
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
