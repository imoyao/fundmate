<script setup lang="ts">
/**
 * 转出腿（转换表单左栏，#980 拆分自 ConversionForm.vue）。
 *
 * 一条腿 = 三个字段（转出基金 / 交易日期 / 转出份额）+ 两条解释文案。
 * 拆出来的理由是**栏级等宽**：这栏的每个字段高度都会被右栏的 grid 拉齐，
 * 改动其中一项就要重看两栏对齐，放在 1702 行的表单里没有安全的修改边界。
 *
 * 表单值全部走 `v-model:*` 由父页持有：`transferAll`（全部转出）与
 * 试算参数都以父页的 `form` 为唯一真相源，子组件不留副本。
 */
import type { Position } from "@/api/types";
import TradeSlotSwitch from "@/components/TradeSlotSwitch/index.vue";
import QuickRatioPicker from "@/components/QuickRatioPicker/index.vue";
import { disabledTradeDate } from "@/utils/date";

defineProps<{
  /** 当前账户的基金持仓 */
  positions: Position[];
  /** 持仓是否仍在加载（决定"暂无持仓"提示出不出现） */
  loading: boolean;
  /** 转出份额上限（持仓精确值） */
  maxQuantity: number;
  /** 是否「全部转出」（由快捷档位派生，只影响文案与 payload） */
  transferAll: boolean;
  positionId: number | null;
  tradeDate: string;
  after15: boolean;
  quantity: number | undefined;
}>();

const emit = defineEmits<{
  (e: "update:positionId", value: number | null): void;
  (e: "update:tradeDate", value: string): void;
  (e: "update:after15", value: boolean): void;
  (e: "update:quantity", value: number | undefined): void;
  /** 换转出基金：父页据此清份额 / 作废人工修正的费用 */
  (e: "positionChange"): void;
  /** 手改份额：父页据此取消「全部转出」标记 */
  (e: "quantityInput"): void;
  /** 快捷档位命中：`ratio >= 1` 由父页翻成「全部转出」 */
  (e: "quickRatioSelect", payload: { ratio: number; quantity: number }): void;
}>();
</script>

<template>
  <section class="lg:col-span-6">
    <!-- 栏头不重复标签里的「转出基金」，而是交代这条腿在后台是什么动作：
         转换 = 赎回 + 申购，这一点用户从界面上看不出来 -->
    <h3 class="convert-col__title">转出（赎回）</h3>
    <!-- 半屏列宽放不下 90px 横排标签（输入框会被压成一条缝），故标签在上 -->
    <el-form label-position="top" size="large" class="flex flex-col gap-4">
      <el-form-item label="转出基金">
        <el-select
          :model-value="positionId"
          class="w-full"
          filterable
          placeholder="选择要转出的持仓"
          @update:model-value="v => emit('update:positionId', v)"
          @change="emit('positionChange')"
        >
          <el-option
            v-for="pos in positions"
            :key="pos.id"
            :value="pos.id"
            :label="pos.name || pos.symbol"
          >
            <div class="flex justify-between items-center w-full">
              <span
                class="truncate"
                :style="{ color: 'var(--text-primary)' }"
                >{{ pos.name || pos.symbol }}</span
              >
              <span
                class="text-xs whitespace-nowrap"
                :style="{ color: 'var(--text-tertiary-ink)' }"
              >
                可用 {{ Number(pos.quantity).toFixed(2) }} 份
              </span>
            </div>
          </el-option>
        </el-select>
        <div
          v-if="!loading && positions.length === 0"
          class="text-xs mt-1"
          style="color: var(--text-tertiary-ink)"
        >
          当前账户暂无基金持仓，无法转换。请先切换账户或记一笔申购。
        </div>
      </el-form-item>

      <!-- 未选转出基金时，「交易日期 / 转出份额」照常渲染但整体禁用（#2348 视觉审计）：
           原先用 v-if 藏起来，左栏只剩一个下拉框、右栏有四块内容，
           grid 拉齐后左栏下方空出 ~370px，整页读起来像「没加载完」。
           留着骨架既让两栏等高，也提前告诉用户这里还要填两项。 -->
      <el-form-item label="交易日期">
        <!-- 日期框吃满剩余宽度，右端与上方「转出基金」右边缘对齐；
            时点切换按 design.md「Segmented」走软按钮，不用实底 radio-button
            （实底品牌色会与主按钮撞脸、抢走页面唯一供能焦点，#1731）。 -->
        <div class="field-row">
          <!-- 外层 div 才是 flex item：EP 的 DatePicker 是 inheritAttrs:false，
             直接写在它上面的 class 不会落到渲染出来的 `.el-input.el-date-editor` 上
              （实测宽度仍是写死的 220px）。宽度走内联 100%，与外层 flex 配合。 -->
          <div class="field-row__grow">
            <el-date-picker
              :model-value="tradeDate"
              type="date"
              style="width: 100%"
              value-format="YYYY-MM-DD"
              :clearable="false"
              :disabled="!positionId"
              :disabled-date="disabledTradeDate"
              @update:model-value="v => emit('update:tradeDate', v as string)"
            />
          </div>
          <TradeSlotSwitch
            :model-value="after15"
            :disabled="!positionId"
            @update:model-value="v => emit('update:after15', v)"
          />
        </div>
        <div class="helper">15:00 后提交按下一交易日（T+1）净值计算</div>
      </el-form-item>

      <el-form-item label="转出份额">
        <div class="quantity-field">
          <!-- 宽度必须内联：EP 给 .el-input-number 写死 width:150px，
             且其样式在运行时注入、晚于构建产物里的 w-full，类名会被压掉。 -->
          <el-input-number
            :model-value="quantity"
            style="width: 100%"
            :controls="false"
            :min="0"
            :max="maxQuantity"
            :step="0.01"
            :precision="2"
            :disabled="!positionId"
            :placeholder="positionId ? '输入转出份额' : '请先选择要转出的持仓'"
            @update:model-value="v => emit('update:quantity', v ?? undefined)"
            @change="emit('quantityInput')"
          />
          <!-- 比例档位：与卖出表单同一组件（档位表 / 取整 / 选中态唯一实现）；
               选中态由 quantity 反算，手改数值自动掉高亮 -->
          <div class="quick-ratio-row">
            <QuickRatioPicker
              :model-value="quantity"
              :total="maxQuantity"
              type="fund"
              :disabled="!positionId"
              aria-label="转出份额比例"
              @update:model-value="v => emit('update:quantity', v)"
              @select="p => emit('quickRatioSelect', p)"
            />
            <span v-if="positionId" class="hold-hint">
              持有 {{ maxQuantity.toFixed(4) }} 份
            </span>
          </div>
          <div class="helper">
            {{
              transferAll
                ? "当前为全部转出：按持仓精确值清算，不抹零"
                : "份额最多 2 位小数；「全部」按持仓精确值转出"
            }}
          </div>
        </div>
      </el-form-item>
    </el-form>
  </section>
</template>

<style scoped>
/* 栏头：比输入框标签更轻，只交代"这一栏在做什么"；
   h3 默认的 margin/字号必须清掉，否则两栏顶端会错开一行 */
.convert-col__title {
  margin: 0 0 8px;
  font-size: var(--text-label);
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-secondary);
}

/* 一期一列的弹性行：右端控件贴住与其它输入框同一条垂直线 */
.field-row {
  display: flex;
  gap: 12px;
  align-items: center;
  width: 100%;
}

/* 日期框吃满剩余宽度。`flex-basis` 必须是 **0%**：EP 给 `.el-date-editor.el-input`
   写死 `width:220px`（(0,2,0) 压过本类的 (0,1,0)），而 `flex:1 1 auto` 会退回那个
   width 当基准——grow 分不到额外空间，实测仍是 220px；`1 1 0%` 才与 width 脱钩。 */
.field-row__grow {
  flex: 1 1 0%;
  min-width: 0;
}

.quantity-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

/* 快捷比例：紧凑贴左，右侧挂"持有"读数，不拉满整行 */
.quick-ratio-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.hold-hint {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
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
