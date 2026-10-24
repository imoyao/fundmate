<script setup lang="ts">
/**
 * 第 3 步：结果回执（#980 拆分自 ConversionForm.vue）。
 *
 * 结果页是「回执」，不是把确认页再念一遍：确认页回答「对不对」，
 * 结果页回答「成了吗、接下来等什么、去哪看」。
 * 原先是居中 5xl 对勾 + 四行等权键值对：居中大图标是空状态/弹窗的语言，
 * 与前两步的左对齐表单语言打架；四行等权又是改版前确认页那个毛病——
 * 看上去什么都有，实际没有重点。三个数与确认页同字段同版式（共用
 * `ConversionFigures`），用户在这里核对的正是「和刚才确认的那三个数一不一样」。
 */
import type { ConversionSubmitResult } from "@/api/positions";
import { IconifyIconOffline } from "@/components/ReIcon";
import ConversionFigures from "./ConversionFigures.vue";

defineProps<{
  result: ConversionSubmitResult | null;
}>();

const emit = defineEmits<{
  /** 再记一笔 */
  (e: "again"): void;
  /** 去交易流水 */
  (e: "list"): void;
}>();
</script>

<template>
  <div class="flex flex-col gap-4" role="status" aria-live="polite">
    <div class="result-status">
      <IconifyIconOffline
        icon="ep:success-filled"
        class="result-status__icon"
      />
      <span class="result-status__title">转换已提交</span>
      <span class="result-status__no">
        申请单号 {{ result?.group_no || "--" }}
      </span>
    </div>

    <template v-if="result">
      <p class="confirm-sentence">
        用「{{ result.out.name || result.out.symbol }}」的
        <span class="confirm-sentence__num">{{
          result.out.quantity.toFixed(2)
        }}</span>
        份，换成了「{{ result.in.name || result.in.symbol }}」
      </p>

      <ConversionFigures
        :out="result.out"
        :net-amount="result.in.amount"
        :in-quantity="result.in.quantity"
      />

      <div class="confirm-meta">
        <el-tag size="small" type="info" effect="plain">待确认</el-tag>
        <span>
          {{ result.trade_date }} 提交 · T+1 确认 · T+2 可赎回
          <!-- 幂等命中（409）走的是拼装结果，confirm_date 可能为空 -->
          <template v-if="result.confirm_date">
            · 预计 {{ result.confirm_date }} 确认
          </template>
        </span>
      </div>

      <!-- 差额已经落定了，只需告知去向，不再提供选项（确认页才有得选） -->
      <div v-if="result.refund.amount > 0" class="result-refund">
        <span class="result-refund__label">差额</span>
        <span class="result-refund__amount"
          >¥{{ result.refund.amount.toFixed(2) }}</span
        >
        <span class="result-refund__text">
          已回到
          {{ result.refund.mode === "money_fund" ? "类现金产品" : "账户现金" }}
        </span>
      </div>

      <!-- 提交前给过的提醒，在这里只是复述：确认页的 blocker 是「按钮点不动的原因」，
           有底色、有 role=alert；这里若沿用那套样式，两条提示会变成第三、第四个
           数据块，比三个数还显眼。降成无底色的一行字，权重回到「附带说明」。 -->
      <ul v-if="result.warnings.length" class="result-warnings">
        <li v-for="w in result.warnings" :key="w" class="result-warning">
          <IconifyIconOffline
            icon="ep:warning-filled"
            class="result-warning__icon"
          />
          <span>{{ w }}</span>
        </li>
      </ul>
    </template>

    <div class="confirm-actions">
      <span class="confirm-actions__note">
        已记入交易流水；份额以 T 日净值清算结果为准
      </span>
      <div class="result-actions">
        <el-button text @click="emit('again')">继续记一笔</el-button>
        <el-button type="primary" @click="emit('list')">查看交易流水</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 一句话指令：与确认页同一版式（回执要能和确认单逐字对照） */
.confirm-sentence {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 500;
  line-height: 1.65;
  color: var(--text-primary);
}

.confirm-sentence__num {
  font-variant-numeric: tabular-nums;
}

.confirm-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

/* 底部动作行：说明在左、出口按钮在右 */
.confirm-actions {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  padding-top: 4px;
}

.confirm-actions__note {
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}

/* 状态行：一行说清「成没成 + 单号是多少」。
   原先是居中 5xl 对勾，那是空状态/弹窗的语言——它假设页面里没有别的信息，
   而这里是三步向导的收尾，前面两步都是左对齐的表单，插入一个居中大图标
   等于把整页的对齐轴打断。图标降到 18px 内联，标题与单号共用一条基线。 */
.result-status {
  display: flex;
  gap: 8px;
  align-items: center;
  min-height: 24px;
}

/* 图标尺寸走字阶令牌 `--text-num-strong`（本文件曾以字面值 18px 登记在
   #2323 存量例外清单里，拆分时顺手令牌化） */
.result-status__icon {
  font-size: var(--text-num-strong);
  color: var(--color-success-ink);
}

.result-status__title {
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--text-primary);
}

.result-status__no {
  margin-left: auto;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* 提交后提示：无底色的一行字，权重低于三个数 */
.result-warnings {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.result-warning {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.result-warning__icon {
  margin-top: 2px;
  color: var(--color-warning-ink);
}

/* 差额去向：确认页要选，这里只需告知已落在哪，所以是一行文字而非带框的控件 */
.result-refund {
  display: flex;
  gap: 6px;
  align-items: baseline;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.result-refund__label {
  color: var(--text-secondary);
}

.result-refund__amount {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.result-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
