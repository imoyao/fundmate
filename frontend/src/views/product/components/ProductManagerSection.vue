<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getManagerProfile, type ManagerProfileResult } from "@/api/products";
import { productRoute } from "@/utils/productIdentity";

/**
 * 详情页「基金经理」区块（#1970 · 设计 §6 品类矩阵）。
 *
 * 取数：`GET /api/products/manager-profile/`（本卡新增）一次拿到经理资料 + 任职基金列表。
 * funds 域此前**没有**任何端点能回答「某位经理管过哪些基金」——`/api/funds/managers/search/`
 * 是按姓名模糊搜，与本问题无关；关系本身在 `fund_managers` 关联表里是完整的。
 *
 * 入参是 **mgr_code 而非姓名**：库内实测 119 组重名（最多「吴昊」6 位），
 * 姓名不是唯一键；详情页路由 `/manager/<symbol>` 传下来的就是它。
 *
 * 口径与降级（设计 §6「诚实降级」的实证依据）：
 * 生产库 4267 位经理实测——`appointment_date` / `sum_scale` / `best_return` / `avatar_url`
 * 与 `fund_managers.start_date` / `end_date` **填充率全为 0%**，故这些字段一律显示「—」。
 * **不用 mock 顶替**（G1 教训），也不在本卡越界去爬数据源。
 *
 * 不展示代码（设计 §6）：经理类靠「姓名 + 公司」识别——库内重名严重，展示
 * 12 位哈希对用户毫无意义。
 */
const props = defineProps<{
  /** 经理编码 mgr_code（12 位哈希），非姓名 */
  mgrCode: string;
}>();

const loading = ref(false);
const profile = ref<ManagerProfileResult | null>(null);
const failed = ref(false);

const DASH = "—";

/** 是否展示「任期字段暂未落库」的定调说明 */
const hasTenureData = computed(() => {
  const p = profile.value;
  if (!p) return false;
  return (
    p.appointment_date != null ||
    p.sum_scale != null ||
    p.funds.some(f => f.start_date != null)
  );
});

/** 任职基金是否被 fund_limit 截断（后端上限 20，实测最多 42 只） */
const fundsTruncated = computed(() => {
  const p = profile.value;
  return !!p && p.fund_count > p.funds.length;
});

async function load() {
  if (!props.mgrCode) return;
  loading.value = true;
  failed.value = false;
  try {
    const res = await getManagerProfile({ mgr_code: props.mgrCode });
    profile.value = res.data;
  } catch {
    // 非经理编码 / 未收录 / 网络异常：统一降级为空态，不影响详情页其余区块
    profile.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.mgrCode, load, { immediate: true });
</script>

<template>
  <CardBlock class="mgr-section">
    <SectionHeader title="基金经理" />

    <p v-if="loading" class="mgr-section__hint">正在读取基金经理资料…</p>

    <p v-else-if="failed || !profile" class="mgr-section__hint">
      暂无可展示的基金经理资料
    </p>

    <template v-else>
      <!-- 资料：仅姓名与公司有真实数据（重名靠公司消歧），其余逐项降级 -->
      <dl class="mgr-section__facts">
        <div class="mgr-section__fact">
          <dt class="mgr-section__label">姓名</dt>
          <dd class="mgr-section__value">{{ profile.name || DASH }}</dd>
        </div>
        <div class="mgr-section__fact">
          <dt class="mgr-section__label">所属公司</dt>
          <dd class="mgr-section__value mgr-section__value--wrap">
            {{ profile.company || DASH }}
          </dd>
        </div>
        <div class="mgr-section__fact">
          <dt class="mgr-section__label">任职起始</dt>
          <dd class="mgr-section__value">
            {{ profile.appointment_date || DASH }}
          </dd>
        </div>
        <div class="mgr-section__fact">
          <dt class="mgr-section__label">管理规模</dt>
          <dd class="mgr-section__value">
            <template v-if="profile.sum_scale != null">
              {{ profile.sum_scale.toFixed(2) }} 亿元
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <div class="mgr-section__fact">
          <dt class="mgr-section__label">任期回报</dt>
          <dd class="mgr-section__value">
            <template v-if="profile.best_return != null">
              {{ profile.best_return.toFixed(2) }}%
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <div class="mgr-section__fact">
          <dt class="mgr-section__label">任职基金</dt>
          <dd class="mgr-section__value">{{ profile.fund_count }} 只</dd>
        </div>
      </dl>

      <!-- 任期类字段整片为空时给出定调说明，避免用户以为加载失败 -->
      <p v-if="!hasTenureData" class="mgr-section__note">
        任职起止、管理规模与任期回报尚未同步，当前仅展示任职基金名单。
      </p>

      <!-- 任职基金列表：点条目跳该基金详情页 -->
      <div v-if="profile.funds.length" class="mgr-section__funds">
        <h4 class="mgr-section__subtitle">任职基金</h4>
        <ul class="mgr-section__fund-list">
          <li v-for="f in profile.funds" :key="f.fund_code">
            <RouterLink
              class="mgr-section__fund-link"
              :to="productRoute({ assetType: 'fund', symbol: f.fund_code })"
            >
              {{ f.name }}
              <span v-if="f.is_classic" class="mgr-section__badge">代表作</span>
            </RouterLink>
          </li>
        </ul>
        <p v-if="fundsTruncated" class="mgr-section__note">
          共 {{ profile.fund_count }} 只，当前仅显示前
          {{ profile.funds.length }} 只。
        </p>
      </div>
      <p v-else class="mgr-section__hint">暂无关联的任职基金</p>
    </template>
  </CardBlock>
</template>

<style lang="scss" scoped>
.mgr-section {
  &__facts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: var(--space-3) var(--space-6);
    margin: 0;
  }

  &__fact {
    min-width: 0;
  }

  &__label {
    margin: 0 0 4px;
    font-size: 12px;
    color: var(--text-tertiary-ink);
  }

  &__value {
    margin: 0;
    font-size: 14px;
    color: var(--text-primary);
  }

  &__value--wrap {
    word-break: break-word;
  }

  &__hint {
    margin: 0;
    font-size: 13px;
    color: var(--text-tertiary);
  }

  &__note {
    padding: var(--space-2) var(--space-3);
    margin: var(--space-3) 0 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-secondary);
    background: var(--bg-soft);
    border-radius: var(--radius-sm);
  }

  &__funds {
    margin-top: var(--space-5);
  }

  &__subtitle {
    margin: 0 0 var(--space-2);
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__fund-list {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    padding: 0;
    margin: 0;
    list-style: none;
  }

  &__fund-link {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    padding: 4px 10px;
    font-size: 13px;
    color: var(--text-primary);
    text-decoration: none;
    background: var(--bg-muted);
    border-radius: var(--radius-sm);
    transition: background-color 0.2s ease;

    &:hover,
    &:focus-visible {
      background: var(--bg-hover);
    }

    /* 键盘焦点必须可见（#1838 可访问性） */
    &:focus-visible {
      outline: 2px solid var(--brand-700);
      outline-offset: 2px;
    }
  }

  &__badge {
    padding: 0 4px;
    font-size: 11px;
    color: var(--brand-700);
    background: var(--brand-100);
    border-radius: var(--radius-sm);
  }
}
</style>
