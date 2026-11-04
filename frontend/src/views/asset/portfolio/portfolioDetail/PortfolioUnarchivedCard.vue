<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { useEnumLabels } from "@/composables/useEnumLabels";
import { getPositions, updatePosition } from "@/api/positions";
import {
  type LinkedLedger,
  type PortfolioHolding,
  unwrapList
} from "./portfolioDetailModel";
import PortfolioTableEmpty from "./PortfolioTableEmpty.vue";

/**
 * 未归档持仓（ledger_id=null，如探市录入）：就地归档到本组合账户。
 *
 * 取数与归档对话框都在本组件内：归档成功后要同时刷新「未归档」与「已归档持仓」，
 * 前者是自己的数据，后者通过 `archived` 事件交给父层重取——父层因此不需要知道
 * 这里有几张表、更不需要拿着 unarchived 数组转一圈（#980）。
 */
defineOptions({ name: "PortfolioUnarchivedCard" });

const props = defineProps<{
  /** 本组合关联的账户（归档目标候选） */
  ledgers: LinkedLedger[];
}>();

const emit = defineEmits<{
  /** 归档成功；父层据此重取已归档持仓 */
  (e: "archived"): void;
}>();

// 同 PortfolioHoldingsCard：`enums` ref 每实例一份，读标签就得自己 ensure
const { ensure: ensureEnums, positionSourceLabel } = useEnumLabels();

const unarchived = ref<PortfolioHolding[]>([]);
const archiveVisible = ref(false);
const archiveTargetId = ref<number | null>(null);
const archiveLedgerId = ref<number | null>(null);
const archiving = ref(false);

async function fetchUnarchived() {
  try {
    const res = await getPositions({ ledger_id: "null" });
    unarchived.value = unwrapList<PortfolioHolding>(res);
  } catch {
    unarchived.value = [];
  }
}

function openArchive(id: number) {
  archiveTargetId.value = id;
  archiveLedgerId.value = props.ledgers[0]?.id ?? null;
  archiveVisible.value = true;
}

async function confirmArchive() {
  if (!archiveTargetId.value || !archiveLedgerId.value) {
    ElMessage.warning("请选择归档目标账户");
    return;
  }
  archiving.value = true;
  try {
    await updatePosition(archiveTargetId.value, {
      ledger_id: archiveLedgerId.value
    });
    ElMessage.success("已归档");
    archiveVisible.value = false;
    await fetchUnarchived();
    emit("archived");
  } catch {
    ElMessage.error("归档失败");
  } finally {
    archiving.value = false;
  }
}

onMounted(() => {
  void ensureEnums();
  void fetchUnarchived();
});
</script>

<template>
  <CardBlock class="mb-6">
    <SectionHeader title="未归档持仓">
      <template #action>
        <el-button size="small" :loading="false" @click="fetchUnarchived">
          <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新
        </el-button>
      </template>
    </SectionHeader>
    <el-table v-if="unarchived.length > 0" :data="unarchived" border>
      <el-table-column label="产品信息" min-width="180">
        <template #default="{ row }">
          <ProductDisplay
            :name="row.name || ''"
            :symbol="row.symbol || ''"
            :type-label="row.type_label || ''"
          />
        </template>
      </el-table-column>
      <el-table-column label="来源" width="110">
        <template #default="{ row }">
          <el-tag
            v-if="positionSourceLabel(row.source)"
            size="small"
            type="info"
          >
            {{ positionSourceLabel(row.source) }}
          </el-tag>
          <span v-else style="color: var(--text-tertiary-ink)">—</span>
        </template>
      </el-table-column>
      <el-table-column label="市值" width="130" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.market_value || 0"
            :show-sign="false"
            :auto-color="false"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openArchive(row.id)">
            归档
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <PortfolioTableEmpty v-else>
      暂无未归档持仓。探市录入或导入未绑定账户的持仓会出现在这里。
    </PortfolioTableEmpty>
  </CardBlock>

  <!-- 归档对话框：将未归档持仓绑定到本组合下某账户 -->
  <el-dialog v-model="archiveVisible" title="归档到账户" width="420px">
    <el-form label-width="80px">
      <el-form-item label="目标账户">
        <el-select
          v-model="archiveLedgerId"
          placeholder="选择账户"
          style="width: 100%"
        >
          <el-option
            v-for="l in ledgers"
            :key="l.id"
            :label="l.name"
            :value="l.id"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="archiveVisible = false">取消</el-button>
      <el-button type="primary" :loading="archiving" @click="confirmArchive">
        确定归档
      </el-button>
    </template>
  </el-dialog>
</template>
