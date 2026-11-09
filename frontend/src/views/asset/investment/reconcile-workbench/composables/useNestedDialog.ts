/**
 * 抽屉内嵌弹窗的遮罩协调（对账工作台）。
 *
 * `el-drawer` 与 `el-dialog` 各自带 modal：抽屉还开着就弹二级弹窗时，两层遮罩
 * 叠加会把页面压暗两次，抽屉内容半死不活地透出来，三层信息同时抢注意力。
 * 这里让抽屉感知「内部有没有弹窗打开」：有则关掉自己的遮罩、把内容淡出到背景，
 * 只留弹窗这一层。
 *
 * 走组件树而非 DOM 树：弹窗 `append-to-body` 只搬 DOM，provide / inject 仍生效；
 * 弹窗不在抽屉内时 inject 为 null，静默跳过，不改变原有行为。
 */
import {
  inject,
  onBeforeUnmount,
  provide,
  ref,
  watch,
  type InjectionKey,
  type Ref
} from "vue";

type SetNestedOpen = (key: string, open: boolean) => void;
const NESTED_DIALOG_KEY: InjectionKey<SetNestedOpen> = Symbol(
  "recon-nested-dialog"
);
let dialogSeq = 0;

/** 抽屉调用：返回「内部是否有弹窗打开」；多个弹窗用各自 key 去重。 */
export function provideNestedDialog(): Readonly<Ref<boolean>> {
  const nestedOpen = ref(false);
  const openKeys = new Set<string>();
  const setOpen: SetNestedOpen = (key, open) => {
    if (open) openKeys.add(key);
    else openKeys.delete(key);
    nestedOpen.value = openKeys.size > 0;
  };
  provide(NESTED_DIALOG_KEY, setOpen);
  return nestedOpen;
}

/** 抽屉内的弹窗调用：把自己的可见状态登记给抽屉，卸载时注销。 */
export function useNestedDialog(visible: Ref<boolean>): void {
  const setOpen = inject(NESTED_DIALOG_KEY, null);
  if (!setOpen) return;
  const key = `nested-dialog-${++dialogSeq}`;
  watch(visible, open => setOpen(key, open), { immediate: true });
  onBeforeUnmount(() => setOpen(key, false));
}
