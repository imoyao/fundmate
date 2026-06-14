<template>
  <el-dialog
    :model-value="visible"
    title="删除账户"
    width="400px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <p class="mb-4" :style="{ color: 'var(--text-primary)' }">
      确定删除账户「<strong>{{ ledgerName }}</strong>」吗？
    </p>
    <el-checkbox v-model="deletePositions" class="mb-2">
      同时删除该账户下的全部持仓（共 {{ positionCount }} 项）
    </el-checkbox>
    <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
      不勾选时，持仓将保留为"未归置"状态，可稍后迁移到其他账户。
    </p>
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="danger" :loading="loading" @click="handleConfirm">
        确认删除
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { deleteLedgerWithOptions } from "@/api/ledger";
import { ElMessage } from "element-plus";

const props = defineProps<{
  visible: boolean;
  ledgerId: number;
  ledgerName: string;
  positionCount: number;
}>();

const emit = defineEmits<{
  'update:visible': [value: boolean];
  'deleted': [];
}>();

const deletePositions = ref(false);
const loading = ref(false);

// 每次弹窗打开时重置状态
watch(() => props.visible, (val) => {
  if (val) {
    deletePositions.value = false;
    loading.value = false;
  }
});

async function handleConfirm() {
  loading.value = true;
  try {
    await deleteLedgerWithOptions(props.ledgerId, deletePositions.value);
    ElMessage.success("账户已删除");
    emit('update:visible', false);
    emit('deleted');
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "删除失败");
  } finally {
    loading.value = false;
  }
}
</script>
