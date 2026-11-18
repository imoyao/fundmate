// src/composables/usePrivacyMode.ts
/**
 * 隐私模式（「鸵鸟模式」）：只藏金额，保留百分比与涨跌色。
 *
 * ## 为什么是「藏金额 + 留百分比」，而不是全藏
 *
 * 用户开这个模式的真实动机有两个，且都不是「不想看到亏损」：
 * 1. **场合**：办公室 / 共享屏幕 / 咖啡厅，旁边有人能看到 7 位数；
 * 2. **心情**：行情不好时不想被绝对值刺激，但仍想知道**今天红了还是绿了**。
 * 所以百分比、涨跌色、日期、估/确认徽标一律保留——它们才是「今天怎么样」的答案，
 * 金额只是「我有多少钱」，后者与当日判断无关。
 *
 * ## 三条硬规则（违反其中任何一条，这个功能就是假的）
 *
 * 1. **必须在渲染层换掉文本，不能用 CSS `filter: blur()` / `opacity`**：
 *    模糊只是视觉遮罩，DOM 里仍是真数字，屏幕共享、截图、审查元素、读屏
 *    全都能拿到——那是最坏的形态：用户以为藏了，其实没藏。
 * 2. **占位符不带位数**：统一 `••••`，不写 `¥••,•••.••`。位数本身就是信息
 *    （1.6M 与 16M 是两个隐私等级）。
 * 3. **真值不得出现在 `title` / `aria-label` / `data-*` 里**：悬浮提示和读屏
 *    是最常见的泄漏口，比视觉泄漏更隐蔽。
 *
 * ## 状态是全局单例
 *
 * 模块级 `ref`，不是每次调用新建——否则「这张卡藏了、那张没藏」比不藏更糟：
 * 看板上出现半遮半掩，反而提示了「被遮的那个数很大」。
 *
 * ## 长按窥视
 *
 * 银行类 App 的通行手势：按住看真值，松手复原。延迟 {@link PEEK_HOLD_MS}
 * 才揭开——移动端按下即揭会与滚动、点按冲突（手指一碰整页数字闪一下）。
 */

import { computed, ref } from "vue";

/** localStorage 键：与设备的「我这个人在哪儿看」绑定，不跨设备同步 */
const STORAGE_KEY = "fundmate:privacy:mask-amounts";

/** 长按多少毫秒才揭示（低于此视为滚动 / 误触） */
const PEEK_HOLD_MS = 180;

function readStored(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    // 隐私模式下 localStorage 可能被禁用：按「不遮」处理，不阻塞页面
    return false;
  }
}

function persist(masked: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, masked ? "1" : "0");
  } catch {
    // 写不进去就只在本页生效，不影响功能
  }
}

/** 全局单例：所有消费方共享同一份状态 */
const masked = ref(readStored());
/** 长按窥视中（仅影响渲染，不写 localStorage） */
const peeking = ref(false);

let peekTimer: number | null = null;

function clearPeekTimer(): void {
  if (peekTimer !== null) {
    window.clearTimeout(peekTimer);
    peekTimer = null;
  }
}

export function usePrivacyMode() {
  /** 真值是否可见：没开遮罩，或正在长按窥视 */
  const visible = computed(() => !masked.value || peeking.value);

  /** 切换遮罩（持久化）；切换时立即结束窥视，避免「刚点了按钮还看得见」 */
  function toggle(): void {
    masked.value = !masked.value;
    peeking.value = false;
    clearPeekTimer();
    persist(masked.value);
  }

  /** 显式设置（供设置项 / 跨组件联动） */
  function setMasked(value: boolean): void {
    if (masked.value === value) return;
    masked.value = value;
    peeking.value = false;
    clearPeekTimer();
    persist(value);
  }

  /** 长按开始：延迟若干毫秒才揭，规避滚动误触 */
  function startPeek(): void {
    if (!masked.value || typeof window === "undefined") return;
    clearPeekTimer();
    peekTimer = window.setTimeout(() => {
      peeking.value = true;
      peekTimer = null;
    }, PEEK_HOLD_MS);
  }

  /** 松手 / 移出 / 取消：无条件复原（宁可早一秒藏回去） */
  function endPeek(): void {
    clearPeekTimer();
    peeking.value = false;
  }

  return { masked, peeking, visible, toggle, setMasked, startPeek, endPeek };
}
