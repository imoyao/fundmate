<!--
  PositionMaturityDialog · 持仓「到期日 / 手工标的标识」编辑弹窗（#931 / D121）

  为什么不是一个完整的「编辑持仓」弹窗：本仓目前没有这样东西，而到期日与手工标的的
  名称/编码都是既不属于买入表单、也没有任何入口的字段（PR4 只开了到期日 API）。
  表单侧 `BuyForm.vue` 已到 399/400 行体量门禁，塞不进去；到期日更是买入之后才会被
  修正的值「录错了」，本来就该在持仓上改。

  银行理财多两个输入框（名称 / 登记编码）：首录时只有一个输入框，容易把产品名当编码
  填进去，而这条记录没有中心目录可校对（D121）——不给改，那串错码就永久留在持仓列表里。

  口径说明由 `positionMaturity.maturityHint` 按品类分叉：逆回购到期转现金会影响总资产
  分类，银行理财只记录——两类共用一句文案会误导其中一类。
-->
<template>
  <el-dialog
    :model-value="visible"
    :title="maturityDialogTitle(assetType)"
    width="480px"
    :close-on-click-modal="false"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <!-- 非手工标的：产品只做回显。银行理财下面用可编辑表单顶替，正文不重复一遍 -->
    <p v-if="!canEditIdentity(assetType)" class="dialog-product">
      {{ name || "--" }}<span v-if="symbol">（{{ symbol }}）</span>
    </p>
    <el-form v-else label-width="84px" @submit.prevent>
      <el-form-item label="产品名称">
        <el-input
          v-model="draftName"
          placeholder="如：招银理财朝朝宝"
          maxlength="60"
          clearable
        />
      </el-form-item>
      <el-form-item label="登记编码">
        <!-- el-form-item 的 content 是 flex 容器：输入框与提示语必须包在一个块里，
             否则提示会被挤到输入框右边同一行 -->
        <div class="field-stack">
          <el-input
            v-model="draftSymbol"
            placeholder="如 Z7001234ABCD"
            maxlength="32"
            clearable
          />
          <p class="dialog-hint">
            理财登记编码，同一账户内唯一；改这里会连同该持仓的流水一起改。
          </p>
        </div>
      </el-form-item>
    </el-form>

    <el-date-picker
      v-model="value"
      type="date"
      value-format="YYYY-MM-DD"
      placeholder="选择到期日"
      clearable
      style="width: 100%"
    />
    <p class="dialog-hint">{{ maturityHint(assetType) }}</p>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="submit"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  canEditIdentity,
  maturityDialogTitle,
  maturityHint,
  type PositionEditPayload
} from "./positionMaturity";

const props = withDefaults(
  defineProps<{
    visible: boolean;
    /** 产品名（弹窗里回显，避免用户记错在改哪一条） */
    name?: string | null;
    symbol?: string | null;
    /** 品类：决定提示语、可编辑性与标题 */
    assetType?: string | null;
    /** 当前值（`YYYY-MM-DD`），空 = 未设 */
    maturityDate?: string | null;
    loading?: boolean;
  }>(),
  { name: "", symbol: "", assetType: "", maturityDate: null, loading: false }
);

const emit = defineEmits<{
  (e: "update:visible", value: boolean): void;
  /** 提交：空串归一成 null（= 清空），后端 `parse_maturity_date` 认这个语义 */
  (e: "submit", payload: PositionEditPayload): void;
}>();

const value = ref<string>("");
const draftName = ref<string>("");
const draftSymbol = ref<string>("");

// 每次打开都从行上重置：直接复用上次的值会让「这条没设、那条设了」互相污染
watch(
  () => [props.visible, props.maturityDate] as const,
  ([visible]) => {
    if (visible) value.value = props.maturityDate ?? "";
  },
  { immediate: true }
);

// 名称/编码同理。分两个 watch 是有意的：合成一个的话，打开时任意 prop 变化都会把
// 用户正在编辑的另一半冲掉。
watch(
  () => [props.visible, props.name, props.symbol] as const,
  ([visible]) => {
    if (!visible) return;
    draftName.value = props.name ?? "";
    draftSymbol.value = props.symbol ?? "";
  },
  { immediate: true }
);

function submit() {
  const payload: PositionEditPayload = { maturity_date: value.value || null };
  if (canEditIdentity(props.assetType)) {
    // 编码是持仓身份：空值放过去只会在后端 400，前端先拦住（还能省一次往返）
    const symbol = draftSymbol.value.trim().toUpperCase();
    if (!symbol) {
      ElMessage.error("登记编码不能为空");
      return;
    }
    payload.symbol = symbol;
    payload.name = draftName.value.trim();
  }
  emit("submit", payload);
}
</script>

<style lang="scss" scoped>
.dialog-product {
  margin: 0 0 12px;
  font-weight: 600;
}

.dialog-hint {
  margin: 12px 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.field-stack {
  display: flex;
  flex-direction: column;
  width: 100%;
}

/* 字段内提示与输入框贴紧（外层提示语要 12px 间距，两者不是同一层级） */
.field-stack .dialog-hint {
  margin-top: 4px;
}
</style>
