<script setup lang="ts">
/**
 * 转入腿（转换表单右栏，#980 拆分自 ConversionForm.vue）。
 *
 * 与左栏对称的三块内容 + 两个「快选」入口：
 * - 「从持仓选择」文字链接（与买入表单同一搜索源，不做第二套搜索框）；
 * - 转入基金 remote 搜索，货基已在搜索层滤掉。
 *
 * 金额 / 份额的口径开关内嵌在输入框右端：它修饰的是**这个数字的含义**，
 * 独立成一排会比输入框本身更抢眼（#2348 第二轮）。
 */
import type { FundSearchItem } from "@/api/funds";
import type { Position } from "@/api/types";
import { IconifyIconOffline } from "@/components/ReIcon";
import { IN_MODE_OPTIONS, type InMode } from "../conversionFormModel";

defineProps<{
  /** 当前持有可快选的基金（已排除转出基金本身） */
  candidates: Position[];
  /** 搜索结果 */
  options: FundSearchItem[];
  searchLoading: boolean;
  /** 已选转入基金的标签兜底（快选项不在搜索结果里，靠它接住代码） */
  pickedOption: { value: string; label: string } | null;
  inSymbol: string;
  inMode: InMode;
  /** 当前口径下的输入值（金额或份额，同一个输入框承载） */
  inValue: number | undefined;
}>();

const emit = defineEmits<{
  (e: "pick", symbol: string, name: string): void;
  (e: "search", query: string): void;
  (e: "update:inSymbol", value: string): void;
  /** 选中搜索结果里的基金：父页据此回填 `inName` */
  (e: "inFundChange", code: string): void;
  (e: "update:inMode", value: InMode): void;
  (e: "update:inValue", value: number | undefined): void;
}>();
</script>

<template>
  <section class="lg:col-span-6 soft-col-divider">
    <h3 class="convert-col__title">转入（申购）</h3>
    <el-form label-position="top" size="large" class="flex flex-col gap-4">
      <!-- 当前账户已持有的置顶快选（与 BuyForm 同一搜索源；不做两套搜索框） -->
      <!-- 快选用「文字链接」而不是胶囊按钮（#2348 视觉审计）：
           白底 + 1px 描边 + 20px 圆角的胶囊在 40px 白底输入框旁边，
           读者分不清它是「可点的快捷项」还是「一个没填的空输入框」。 -->
      <el-form-item v-if="candidates.length" label="从持仓选择">
        <div class="pick-links">
          <el-button
            v-for="pos in candidates"
            :key="pos.id"
            text
            size="small"
            class="pick-link"
            :class="{ 'is-picked': inSymbol === pos.symbol }"
            @click="emit('pick', pos.symbol, pos.name || pos.symbol)"
          >
            {{ pos.name || pos.symbol }}
          </el-button>
        </div>
      </el-form-item>

      <el-form-item label="转入基金">
        <el-select
          :model-value="inSymbol"
          class="w-full"
          filterable
          remote
          :remote-method="q => emit('search', q)"
          :loading="searchLoading"
          placeholder="搜索基金代码或名称"
          @update:model-value="v => emit('update:inSymbol', v)"
          @change="code => emit('inFundChange', code)"
        >
          <!-- 「当前持有」快选不经过搜索结果，选项里没有它 ⇒ el-select 会把
               绑定的代码原样显示成「002340」。补一个只含标签的选项把它接住，
               不伪造 `FundSearchItem` 的 type / subscription_rate 字段。 -->
          <el-option
            v-if="
              pickedOption && !options.some(f => f.code === pickedOption?.value)
            "
            :key="pickedOption.value"
            :value="pickedOption.value"
            :label="pickedOption.label"
          />
          <el-option
            v-for="f in options"
            :key="f.code"
            :value="f.code"
            :label="`${f.name}（${f.code}）`"
          >
            <div class="flex justify-between items-center w-full">
              <span class="truncate">{{ f.name }}</span>
              <span
                class="text-xs"
                :style="{ color: 'var(--text-tertiary-ink)' }"
                >{{ f.code }}</span
              >
            </div>
          </el-option>
        </el-select>
      </el-form-item>

      <el-form-item label="转入">
        <!-- 口径切换收进输入框右端（#2348 第二轮）：
             独立一排的胶囊比它要修饰的输入框更抢眼，读者会先看到「切换器」
             再看到「要填什么」。做成输入框内的文字开关后，两级结构变成
             一级：先读输入框，需要时再注意右端的口径。 -->
        <div class="in-amount-field">
          <el-input-number
            :model-value="inValue"
            style="width: 100%"
            :controls="false"
            :min="0"
            :step="0.01"
            :precision="2"
            :placeholder="
              inMode === 'amount'
                ? '留空 = 净额全部转入'
                : '留空 = 净额全部买入'
            "
            @update:model-value="v => emit('update:inValue', v ?? undefined)"
          >
            <template #suffix>
              <div class="unit-toggle" role="group" aria-label="转入口径">
                <button
                  v-for="opt in IN_MODE_OPTIONS"
                  :key="opt.value"
                  type="button"
                  class="unit-toggle__item"
                  :class="{ 'is-on': inMode === opt.value }"
                  :aria-pressed="inMode === opt.value"
                  @click="emit('update:inMode', opt.value)"
                >
                  {{ opt.label }}
                </button>
              </div>
            </template>
          </el-input-number>
          <div class="helper">
            {{
              inMode === "amount"
                ? "留空表示净额（转出金额 − 费用）全部买入转入基金；指定更小金额时，差额需选去向"
                : "按份额转入：金额由「份额 × 转入净值」派生，差额同样需选去向"
            }}
          </div>
        </div>
      </el-form-item>

      <!-- 差额规则紧贴「转入」输入框（#2348 视觉审计）：
           原先横跨两栏挂在卡片最底部，离它约束的那个输入框最远，
           填表时根本注意不到。金额要试算才知道，所以「选哪一档」
           仍留在下一步，但规则本身在这里就该看见。 -->
      <div class="convert-note">
        <IconifyIconOffline icon="ep:info-filled" class="convert-note__icon" />
        <span>
          转入金额小于「转出金额 −
          费用」时会产生差额，差额退回账户绑定的货币基金
          （账户未绑定则退回账户现金），下一步可改——不会凭空消失。
        </span>
      </div>
    </el-form>
  </section>
</template>

<style scoped>
/* 栏头：与左栏同一实现（两栏顶端对齐靠它统一），刻意各留一份——
   样式在 scoped 里，跨组件复用只能靠全局类，而这是栏内语义不是通用工具 */
.convert-col__title {
  margin: 0 0 8px;
  font-size: var(--text-label);
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-secondary);
}

/* 转入金额区：输入框整行吃满，口径开关在框内右端 */
.in-amount-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

/* 输入框内的口径开关：无底无边，只有当前项是实心文字。
   用小号字 + 细分隔线，读作「单位换算」而不是「一个独立控件」。
   分隔线用 `--border-subtle`（卡片内部降权分割线）而不是 `--border-light`：
   这是字段内部的软分隔，不是栏与栏之间的分割线（后者唯一走 `.soft-col-divider`）。 */
.unit-toggle {
  display: inline-flex;
  gap: 2px;
  align-items: center;
  padding-left: 8px;
  margin-left: 4px;
  border-left: 1px solid var(--border-subtle);
}

/* 命中区补到 24px 高（WCAG 2.2 AA 目标尺寸）：12px 字 + 2px 内距只有 20px，
   在触屏上等于要精准点到一行字。 */
.unit-toggle__item {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 24px;
  padding: 0 4px;
  font-size: var(--text-label);
  line-height: 1;
  color: var(--text-tertiary-ink);
  cursor: pointer;
  background: none;
  border: 0;
  border-radius: var(--radius-xs);
  transition: color 0.15s ease;
}

/* 焦点环用 inset：外扩的 `--focus-ring` 会被输入框的圆角裁掉一圈，
   裁剩半环比没有更糟。inset 2px 实环在同一个矩形里，不受裁切影响。 */
.unit-toggle__item:focus-visible {
  color: var(--brand-800);
  outline: none;
  box-shadow: inset 0 0 0 2px var(--brand-700);
}

.unit-toggle__item:hover {
  color: var(--text-secondary);
}

.unit-toggle__item.is-on {
  font-weight: 500;
  color: var(--brand-ink);
}

/* 差额去向提示：与既有告警块同一视觉层级（bg-soft 底、无边框），
   只是常驻而不是出错才出现 */
.convert-note {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  padding: 0;
  font-size: var(--text-label);
  line-height: 1.5;

  /* 说明文案是次要元素：不铺底、不用 secondary 字色，靠 ⓘ 与缩进表达从属关系。
     旧实现是一块 --bg-soft 色块，在暖白卡上比输入框还显眼（#2348 视觉审计）。 */
  color: var(--text-tertiary-ink);
  background: transparent;
}

.convert-note__icon {
  flex: none;
  margin-top: 1px;
  color: var(--text-tertiary-ink);
}

/* 「当前持有」快选：选中态走软按钮（浅红底 + 红字），不占实底主按钮的供能位 */
.pick-links {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}

/* 文字链接形态：无底无边，靠颜色与下划线表达「可点」。
   选中项加下划线而不是加底色——底色会被读成输入框（旧实现的问题）。 */
.pick-link.el-button {
  height: auto;
  padding: 0;
  font-size: var(--text-label);
  color: var(--brand-ink);
}

.pick-link.el-button:hover {
  color: var(--brand-ink);
  text-decoration: underline;
}

.is-picked.el-button {
  color: var(--brand-700);
  text-decoration: underline;
}

.is-picked.el-button:hover {
  color: var(--brand-700);
  background-color: transparent;
}

/* 辅助说明：与主文案拉开行高，避免贴脸；宽度 100% 保证在 form-item 内换行 */
.helper {
  width: 100%;
  margin-top: 6px;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}
</style>
