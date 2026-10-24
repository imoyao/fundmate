<template>
  <!-- 账户 + 持仓两级选择：#980 拆分自 SellForm.vue。
       只列「有持仓」的账户；持仓按当前账户的 ledger_id 分组取，切账户即重取。 -->
  <template v-if="!hideAccountSelect">
    <el-form-item label="选择账户" prop="ledger_id">
      <el-select
        v-model="accountModel"
        class="w-full"
        placeholder="选择交易账户"
        filterable
        @change="emit('account-change')"
      >
        <el-option
          v-for="acc in accounts"
          :key="acc.id"
          :label="acc.name"
          :value="acc.id"
        >
          <div class="flex items-center justify-between w-full">
            <span>{{ acc.name }}</span>
            <AssetTypeBadge :type="acc.ledger_type" variant="tag" />
          </div>
        </el-option>
      </el-select>
      <div
        v-if="accounts.length === 0"
        class="mt-2 p-3 bg-gray-50 rounded-lg text-xs"
        style="color: var(--text-secondary)"
      >
        暂无拥有持仓的账户。如需卖出，请先前往
        <a
          class="text-[var(--color-primary)] cursor-pointer"
          @click="emit('go-to-inventory')"
          >全面盘点</a
        >
        导入或录入持仓。
      </div>
    </el-form-item>
  </template>

  <!-- 选择持仓 -->
  <template v-if="ledgerId">
    <el-form-item label="选择持仓" prop="positionId">
      <el-select
        v-if="showPositionSelect"
        :key="selectKey"
        v-model="positionModel"
        class="w-full"
        filterable
        placeholder="选择持仓"
        @change="onPositionChange"
      >
        <el-option
          v-for="pos in positions"
          :key="pos.id"
          :value="pos.id"
          :label="pos.name || pos.symbol"
        >
          <div class="flex justify-between items-center w-full">
            <span class="truncate" :style="{ color: 'var(--text-primary)' }">{{
              pos.name || pos.symbol
            }}</span>
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
        v-if="positions.length === 0"
        class="text-xs mt-1"
        style="color: var(--text-tertiary-ink)"
      >
        当前账户无可用持仓，无法执行卖出/赎回操作。
      </div>
    </el-form-item>
  </template>
</template>

<script setup lang="ts">
import { computed } from "vue";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";

const props = defineProps<{
  /** 拥有持仓的账户（父层已过滤） */
  accounts: any[];
  ledgerId: number | null;
  positionId: number | null;
  /** 当前账户下的持仓 */
  positions: any[];
  hideAccountSelect?: boolean;
  showPositionSelect: boolean;
  /** 换 key 强制重建持仓下拉（清空/切换账户后的复位手段） */
  selectKey: number;
}>();
const emit = defineEmits<{
  "update:ledgerId": [value: number | null];
  "update:positionId": [value: number | null];
  /** 账户切换：父层清空持仓相关字段 */
  "account-change": [];
  /** 选中持仓：父层回填 symbol/type/价格并重算费率 */
  "position-change": [positionId: number];
  "go-to-inventory": [];
}>();

const accountModel = computed({
  get: () => props.ledgerId,
  set: val => emit("update:ledgerId", val)
});
const positionModel = computed({
  get: () => props.positionId,
  set: val => emit("update:positionId", val)
});

function onPositionChange(positionId: number) {
  emit("position-change", positionId);
}
</script>
