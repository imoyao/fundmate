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
          <p v-if="mode === 'enrich'" class="dr-intro__main">
            这些交易缺标的代码或交易日期，找不到对应的持仓。
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
          <el-form label-width="90px" size="default">
            <el-form-item label="标的代码">
              <el-input
                v-model="symbolInput"
                placeholder="例如 600519"
                maxlength="30"
              />
            </el-form-item>
            <el-form-item label="交易日期">
              <el-date-picker
                v-model="tradeDateInput"
                type="date"
                value-format="YYYY-MM-DD"
                format="YYYY-MM-DD"
                placeholder="选择交易日期"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="原因（选填）">
              <el-input
                v-model="reason"
                placeholder="例如：按交割单核对后补全"
              />
            </el-form-item>
          </el-form>
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
