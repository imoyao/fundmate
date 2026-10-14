// src/composables/echarts/useEchartsLifecycle.ts
import { onMounted, onBeforeUnmount, onActivated, watch, type Ref } from "vue";
import type echarts from "@/plugins/echarts";
import { useThemeTick } from "./theme";

/** ECharts 实例类型（取 echarts.init 的返回类型，避免版本差异导致的类型名不匹配） */
export type EChartsInstance = ReturnType<typeof echarts.init>;

/** 单个图表的规格：模板 ref + 构建函数（+ 可选的复用态更新函数） */
export interface ChartSpec {
  /** 图表容器的模板 ref */
  ref: Ref<HTMLElement | null>;
  /**
   * 构建函数：接收容器 DOM，返回 ECharts 实例（内部应调用 echarts.init + setOption）。
   * 例：(el) => { const c = echarts.init(el); c.setOption(option); return c; }
   */
  build: (el: HTMLElement) => EChartsInstance;
  /**
   * 复用模式（`options.reuse === true`）下的更新入口：实例已存在时**只调它**，
   * 不再 dispose + 重建。数据频繁变化的图表必须用它，否则每次更新都重建实例 →
   * ECharts 重新布局 + 肉眼可见的闪烁。
   *
   * 典型用法是三段式：`update` 里先判空数据（空则 `chart.dispose()` 交回收，
   * composable 下次 render 会因 `isDisposed()` 为真而重新 `build`），有数据才 setOption。
   */
  update?: (chart: EChartsInstance) => void;
}

export interface EchartLifecycleOptions {
  /** 是否为 keepAlive 页。true 时会在 onActivated 触发 resize，解决缓存页图表空白/尺寸错乱。默认 false。 */
  keepAlive?: boolean;
  /**
   * 挂载后是否自动渲染。默认 true。
   * 异步数据页（初始无数据）设 false，等数据就绪后手动调用返回的 render()。
   */
  autoRenderOnMount?: boolean;
  /**
   * 复用已有实例、只跑 `spec.update`。**默认 false**（= 每次 dispose + 重建），
   * 与本 composable 最初的行为一致，故既有调用方（`AssetAllocationDonut`）不受影响。
   *
   * 什么时候该开：`options.reuse = true` 的判据是「图表数据会频繁变化」——
   * 重建实例会丢失动画状态并触发重新布局，桑基图 / 多图表仪表类页面尤其明显。
   */
  reuse?: boolean;
}

/**
 * 统一的 ECharts 生命周期管理，取代各页面手写的 echarts.init / getCSSColor /
 * window resize 监听 / onBeforeUnmount dispose，集中收口避免内存泄漏与
 * keepAlive 缓存页图表空白。
 *
 * 职责：
 * - 自动 render（支持挂载时自动或手动触发）
 * - window resize 自动 resize
 * - 卸载时 dispose，杜绝内存泄漏
 * - keepAlive 页在 onActivated 自动 resize，修复缓存回来图表空白/尺寸错乱
 *
 * @example
 * const pieRef = ref<HTMLElement | null>(null);
 * const { render } = useEchartsLifecycle([{
 *   ref: pieRef,
 *   build: (el) => {
 *     const c = echarts.init(el);
 *     c.setOption({ ... });
 *     return c;
 *   }
 * }], { keepAlive: true, autoRenderOnMount: false });
 * // 异步数据就绪后：render();
 */
export function useEchartsLifecycle(
  specs: ChartSpec[],
  options: EchartLifecycleOptions = {}
) {
  const charts: EChartsInstance[] = [];

  const render = () => {
    // 复用模式：实例还在就只跑 spec.update，保留动画状态、不重建 DOM 上的实例。
    // `isDisposed()` 是关键 —— `spec.update` 可能自己 dispose（如「空数据不画图」），
    // 此时 charts[i] 仍指向已释放的实例，靠它判断才能在下次 render 时正确重建。
    if (options.reuse) {
      specs.forEach((spec, i) => {
        const el = spec.ref.value;
        if (!el) return;
        const existing = charts[i];
        if (existing && !existing.isDisposed()) {
          spec.update?.(existing);
        } else {
          charts[i] = spec.build(el);
        }
      });
      return;
    }
    // 默认模式：先释放旧实例，避免同一 DOM 上重复 init 触发 ECharts 警告
    charts.forEach(c => c?.dispose());
    charts.length = 0;
    specs.forEach((spec, i) => {
      const el = spec.ref.value;
      if (!el) return;
      charts[i] = spec.build(el);
    });
  };

  const themeTick = useThemeTick();
  // 主题切换（暗色）时 CSS 变量已变，重绘所有图表使其重新读取颜色（#976）
  watch(themeTick, render);

  const resize = () => {
    charts.forEach(c => c?.resize());
  };

  const handleResize = () => resize();

  onMounted(() => {
    if (options.autoRenderOnMount !== false) render();
    window.addEventListener("resize", handleResize);
  });

  if (options.keepAlive) {
    onActivated(() => resize());
  }

  onBeforeUnmount(() => {
    window.removeEventListener("resize", handleResize);
    charts.forEach(c => c?.dispose());
    charts.length = 0;
  });

  return { render, resize, charts };
}
