// src/composables/useEnumOptions.ts
import { computed, type Ref, unref } from "vue";

/**
 * 从数据数组中提取唯一的选项列表，适用于下拉框。
 * @param data 数据源（Ref 或普通数组）
 * @param field 作为选项 value 的字段名
 * @param labelField 作为选项 label 的字段名，若不传则使用 value 字段
 * @returns 去重后的选项数组，格式为 [{ value, label }]
 */
export function useEnumOptions<T extends Record<string, any>>(
  data: Ref<T[]> | T[],
  field: keyof T,
  labelField?: keyof T
) {
  return computed(() => {
    const dataSource = unref(data) ?? [];
    const seen = new Set<string>();
    const options: { value: string; label: string }[] = [];

    for (const item of dataSource) {
      const value = String(item[field] ?? "");
      if (!value || seen.has(value)) continue;
      seen.add(value);

      const label = labelField ? String(item[labelField] ?? value) : value;

      options.push({ value, label });
    }

    return options;
  });
}
