import { provide, inject, type InjectionKey } from "vue";
import type { useImportWizard } from "./useImportWizard";

export type ImportWizardContext = ReturnType<typeof useImportWizard>;

const IMPORT_WIZARD_KEY: InjectionKey<ImportWizardContext> =
  Symbol("importWizard");

export function provideWizard(ctx: ImportWizardContext): void {
  provide(IMPORT_WIZARD_KEY, ctx);
}

export function useImportWizardContext(): ImportWizardContext {
  const ctx = inject(IMPORT_WIZARD_KEY);
  if (!ctx) {
    throw new Error(
      "未找到导入向导上下文，请确认 ImportIndex 已通过 provideWizard 提供",
    );
  }
  return ctx;
}
