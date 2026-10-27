<template>
  <!-- 分组操作区（#2354）：新建分组「+」+ 管理分组「📁」+ 管理本组产品「🗂」。
       三个入口管的都是「分组」，故同区同规格；放在分组列表之后，符合
       「分组列表 → 分组的图标 → 筛选条件 → 筛选入口」的认知顺序。
       此前「管理本组产品」挂在右段筛选区，与它自己的语义（分组维度）分离，
       是 #2354 顺序诉求里剩下的最后一项错位。 -->
  <div class="group-actions">
    <el-tooltip content="新建分组" placement="bottom">
      <el-button
        class="group-tab-add"
        circle
        aria-label="新建分组"
        @click="emit('add')"
      >
        <el-icon><Plus /></el-icon>
      </el-button>
    </el-tooltip>
    <el-tooltip content="管理分组" placement="bottom">
      <el-button
        class="manage-groups-btn"
        circle
        aria-label="管理分组"
        @click="emit('manage-groups')"
      >
        <el-icon><Folder /></el-icon>
      </el-button>
    </el-tooltip>
    <!-- 「管理本组产品」（issue #987）：仅当前选中**自定义**分组时出现——
         与「管理分组」是两件事：后者管分组本身（新建/改名/删除），本入口管
         「这个组里有哪些产品」；系统分组由后端规律维护，故不提供。
         显隐沿用「常驻 DOM + .is-hidden」：分组操作区紧邻弹性横滑的分组 Tab，
         条件渲染会让该区宽度随选中分组变化，切换分组时整行抖动（同 .clear-filters-btn）。 -->
    <el-tooltip content="管理本组产品" placement="bottom">
      <el-button
        class="manage-group-items-btn"
        :class="{ 'is-hidden': !canManageItems }"
        circle
        aria-label="管理本组产品"
        @click="emit('manage-group-items')"
      >
        <el-icon><Files /></el-icon>
      </el-button>
    </el-tooltip>
  </div>
</template>

<script setup lang="ts">
import { Files, Folder, Plus } from "@element-plus/icons-vue";

/**
 * 自选筛选行的「分组操作」三按钮（#980 批 B2 拆分自 WatchlistFilterBar，
 * 零视觉/行为变更）：样式随模板原样迁入，保持 scoped 作用域不变。
 *
 * 组件化理由：三按钮的尺寸/描边/悬停/隐藏态高度同构（28×28 正圆 + 线框 +
 * 150ms 过渡），此前与右段「清除筛选」的样式四份并列在同一个 style 块里，
 * 改一处规格要同步四处。现在「分组维度」的三枚图标共居一个组件，右段的
 * 「筛选维度」图标留在父级，边界与 #2354 的语义分区一致。
 *
 * 纯展示 + 事件上抛：不持有任何业务状态（分组列表、弹窗开关都在父级）。
 */
defineProps<{
  /** 当前是否选中自定义分组（决定「管理本组产品」可见性，见模板注释） */
  canManageItems: boolean;
}>();

const emit = defineEmits<{
  /** 新建分组 → 父级打开 GroupFormDialog */
  (e: "add"): void;
  /** 管理分组本身（新建/改名/删除）→ GroupManagerDialog */
  (e: "manage-groups"): void;
  /** #987：管理当前自定义分组「里有哪些产品」→ GroupItemsDialog */
  (e: "manage-group-items"): void;
}>();
</script>

<style scoped>
/* 分组操作区：新建分组「+」+ 管理分组「📁」——紧跟分组 Tab 之后，
   与分组区同一垂直基线，不参与左右两大弹性区的宽度争夺。 */
.group-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

/* 新建分组按钮：原文字按钮简化为「+」图标（2026-08-21）。
   尺寸规范（2026-09-05）：纯图标按钮统一 28×28，与文字按钮（32）区分层级 */
.group-tab-add {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-tertiary-ink);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: 50%;
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.group-tab-add:hover {
  color: var(--text-secondary);
  background-color: var(--bg-hover);
}

/* 管理分组按钮：文件夹图标 = 分组管理语义（非通用齿轮）。
   尺寸规范（2026-09-05）：纯图标按钮统一 28×28 */
.manage-groups-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-tertiary-ink);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.manage-groups-btn:hover {
  color: var(--brand-700);
  background-color: var(--bg-hover);
}

/* 管理本组产品按钮（#987）：与「管理分组」同尺寸同语言（28×28 圆形线框），
   仅图标不同（多文件 = 组内产品清单，文件夹 = 分组本身），避免两个入口混淆。
   #2354：随语义从「右段筛选区」移入「分组操作区」，与 + / 📁 同排。 */
.manage-group-items-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-tertiary-ink);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);

  /* 含 opacity / visibility：与下方 .is-hidden 配成双向过渡（同 .clear-filters-btn），
     否则从隐藏恢复时走的是本条（无 opacity 过渡），淡入不生效 */
  transition:
    opacity 150ms ease,
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease,
    visibility 0s linear 0s;
}

.manage-group-items-btn:hover {
  color: var(--brand-700);
  background-color: var(--bg-hover);
  border-color: var(--brand-400);
}

/* 非自定义分组（系统分组 / 全部）下的隐藏态：与 .clear-filters-btn.is-hidden
   同机制（常驻 DOM、只隐不撤）——切换分组时分组操作区宽度恒定，整行不抖。
   ⚠️ 禁止改回 v-if / display:none：槽位塌缩会让右侧类型胶囊区整体左移。 */
.manage-group-items-btn.is-hidden {
  visibility: hidden;
  pointer-events: none;
  opacity: 0;
  transition:
    opacity 150ms ease,
    visibility 0s linear 150ms;
}
</style>
