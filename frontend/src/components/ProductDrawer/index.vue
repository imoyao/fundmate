<!--
  ProductDrawer · 产品详情抽屉的唯一外壳（docs/design/product-detail-drawer.md）

  三个入口（自选速览 / 持仓明细 / 聚合产品详情）共用这一套骨架：
    #header 产品名（20/600）+ 识别信息行（代码 · 品类胶囊 · 平台/主理人）+ 关闭
    锚点    主数值（24/600）+ 副行，恰好一个；`#anchor` 不传则整块不渲染
    区块    调用方默认 slot（用 `DrawerSection` 起标题）
    #footer 说明文案（13 左）+「查看详情」（36px 描边按钮，右）

  差异只允许存在于「抽屉内容」，不允许存在于「抽屉形状」；宽度、两条线、
  区块标题语言都收在外壳与 `_pd.scss` 里，调用方不再自绘。

  壳的行为约定：
  - 抽屉宽度唯一来源是 `--drawer-width`（style/colors.css），组件内不写字面量；
  - 打开时焦点进 `.pd-head`（`tabindex="-1"`），关闭时归还给打开前的元素
    （元素已被销毁则不归还，避免把焦点丢到 body）。
-->
<template>
  <el-drawer
    :model-value="modelValue"
    :size="'var(--drawer-width)'"
    direction="rtl"
    destroy-on-close
    class="product-drawer"
    data-testid="product-drawer"
    @update:model-value="emit('update:modelValue', $event)"
    @open="onOpen"
    @closed="onClosed"
  >
    <template #header>
      <div ref="headRef" class="pd-head" tabindex="-1">
        <h2 class="pd-name" :title="displayName">{{ displayName }}</h2>
        <!-- 识别信息行：顺序固定，缺失项整段不渲染（不写「—」占位） -->
        <p v-if="metaParts.length" class="pd-meta">
          <template
            v-for="(part, index) in metaParts"
            :key="`${part.kind}-${index}`"
          >
            <span v-if="index > 0" class="pd-meta__sep" aria-hidden="true"
              >·</span
            >
            <span v-if="part.kind === 'code'" class="pd-meta__code">{{
              part.text
            }}</span>
            <span v-else-if="part.kind === 'type'" class="pd-type">{{
              part.text
            }}</span>
            <span v-else class="pd-meta__text">{{ part.text }}</span>
          </template>
        </p>
      </div>
    </template>

    <div class="pd-body">
      <div v-if="$slots.anchor" class="pd-anchor" data-testid="num-anchor">
        <slot name="anchor" />
      </div>

      <div class="pd-sections">
        <slot />
      </div>

      <p v-if="disclaimer" class="pd-disclaimer">{{ disclaimer }}</p>
    </div>

    <template #footer>
      <div class="pd-footer" data-testid="drawer-footer">
        <p class="pd-footer__note">
          <slot name="footer-note">{{ note }}</slot>
        </p>
        <!-- 品类无详情页时**不渲染**按钮：灰按钮会制造「即将可用」的假期待 -->
        <el-button
          v-if="detailAvailable"
          class="pd-footer__btn"
          :loading="detailLoading"
          @click="emit('detail')"
        >
          查看详情<IconifyIconOffline
            icon="ep:arrow-right"
            class="pd-footer__icon"
          />
        </el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { isCompositeAssetType } from "@/constants/advisorPlatform";

defineOptions({ name: "ProductDrawer" });

interface MetaPart {
  /** code = 代码（组合类不渲染）；type = 品类胶囊；text = 平台 / 主理人等 */
  kind: "code" | "type" | "text";
  text: string;
}

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    /** 产品名（抽屉标题即产品名，不再写「速览」「持仓明细」这类泛化标题） */
    name?: string | null;
    /** 代码；组合类标的（portfolio / manager）由外壳自己隐藏 */
    symbol?: string | null;
    assetType?: string | null;
    /** 品类标签（「混合型」「投顾组合」） */
    typeLabel?: string | null;
    /** 识别信息行其余项（平台 / 主理人 / 策略），空串整段跳过 */
    meta?: string[] | null;
    /** 是否有详情页可跳；false 时 footer 不渲染按钮，只留原因文案 */
    detailAvailable?: boolean;
    /** footer 左侧说明；不可用时写原因 */
    detailHint?: string;
    detailLoading?: boolean;
    /** 免责声明（取 `ProductDrawer/disclaimer.ts` 的常量） */
    disclaimer?: string | null;
  }>(),
  {
    name: null,
    symbol: null,
    assetType: null,
    typeLabel: null,
    meta: () => [],
    detailAvailable: true,
    detailHint: "",
    detailLoading: false,
    disclaimer: null
  }
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  /** 点击「查看详情」——跳转与取数留在调用方（要动路由 / 拉品类） */
  detail: [];
}>();

const displayName = computed(() => props.name || "--");

/**
 * 识别信息行的片段序列。
 *
 * 顺序固定（§3）：代码 → 品类胶囊 → 平台/主理人。组合类标的（portfolio / manager）
 * 不渲染代码——它们的「代码」是内部主键，对用户没有识别价值。分隔符按**实际渲染的
 * 项**算，所以缺失项不会留下孤立的「·」。
 */
const metaParts = computed<MetaPart[]>(() => {
  const parts: MetaPart[] = [];
  if (props.symbol && !isCompositeAssetType(props.assetType)) {
    parts.push({ kind: "code", text: `#${props.symbol}` });
  }
  if (props.typeLabel) parts.push({ kind: "type", text: props.typeLabel });
  for (const item of props.meta ?? []) {
    if (item) parts.push({ kind: "text", text: item });
  }
  return parts;
});

const note = computed(
  () => props.detailHint || (props.detailAvailable ? "" : "该品类暂无详情页")
);

const headRef = ref<HTMLElement | null>(null);
/** 打开抽屉前持有焦点的元素：关闭后要还给它（§10 已知限制：行级 tabindex 另开卡） */
let opener: HTMLElement | null = null;

// watch 在渲染前触发，此时 activeElement 还是触发元素本身（不是抽屉内的焦点陷阱）
watch(
  () => props.modelValue,
  (visible, was) => {
    if (!visible || was) return;
    const active = document.activeElement;
    opener = active instanceof HTMLElement ? active : null;
  }
);

function onOpen() {
  // 抽屉内容刚渲染，等一帧再聚焦（否则 ref 还是 null）
  nextTick(() => headRef.value?.focus());
}

function onClosed() {
  const target = opener;
  opener = null;
  // 元素可能已随行一起被销毁（例如点「查看详情」跳走）——只有还在 DOM 才归还
  if (target?.isConnected) target.focus();
}
</script>

<style lang="scss">
@use "./pd";
</style>
