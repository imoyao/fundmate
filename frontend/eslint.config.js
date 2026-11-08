import js from "@eslint/js";
import tseslint from "typescript-eslint";
import pluginVue from "eslint-plugin-vue";
import * as parserVue from "vue-eslint-parser";
import configPrettier from "eslint-config-prettier";
import pluginPrettier from "eslint-plugin-prettier";
import { defineConfig, globalIgnores } from "eslint/config";

export default defineConfig([
  globalIgnores([
    "**/.*",
    "dist/*",
    "*.d.ts",
    "public/*",
    "src/assets/**",
    "src/**/iconfont/**"
  ]),
  {
    ...js.configs.recommended,
    languageOptions: {
      globals: {
        // types/index.d.ts
        RefType: "readonly",
        EmitType: "readonly",
        TargetContext: "readonly",
        ComponentRef: "readonly",
        ElRef: "readonly",
        ForDataType: "readonly",
        AnyFunction: "readonly",
        PropType: "readonly",
        Writable: "readonly",
        Nullable: "readonly",
        NonNullable: "readonly",
        Recordable: "readonly",
        ReadonlyRecordable: "readonly",
        Indexable: "readonly",
        DeepPartial: "readonly",
        Without: "readonly",
        Exclusive: "readonly",
        TimeoutHandle: "readonly",
        IntervalHandle: "readonly",
        Effect: "readonly",
        ChangeEvent: "readonly",
        WheelEvent: "readonly",
        ImportMetaEnv: "readonly",
        Fn: "readonly",
        PromiseFn: "readonly",
        ComponentElRef: "readonly",
        parseInt: "readonly",
        parseFloat: "readonly"
      }
    },
    plugins: {
      prettier: pluginPrettier
    },
    rules: {
      ...configPrettier.rules,
      ...pluginPrettier.configs.recommended.rules,
      "no-debugger": "off",
      "no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_"
        }
      ],
      "prettier/prettier": [
        "error",
        {
          endOfLine: "auto"
        }
      ]
    }
  },
  ...tseslint.config({
    extends: [...tseslint.configs.recommended],
    files: ["**/*.?([cm])ts", "**/*.?([cm])tsx"],
    rules: {
      "@typescript-eslint/no-redeclare": "error",
      "@typescript-eslint/ban-ts-comment": "off",
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/prefer-as-const": "warn",
      "@typescript-eslint/no-empty-function": "off",
      "@typescript-eslint/no-non-null-assertion": "off",
      "@typescript-eslint/no-unused-expressions": "off",
      "@typescript-eslint/no-unsafe-function-type": "off",
      "@typescript-eslint/no-import-type-side-effects": "error",
      "@typescript-eslint/explicit-module-boundary-types": "off",
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { disallowTypeAnnotations: false, fixStyle: "inline-type-imports" }
      ],
      "@typescript-eslint/prefer-literal-enum-member": [
        "error",
        { allowBitwiseExpressions: true }
      ],
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_"
        }
      ]
    }
  }),
  // #2879：已清零文件的显式 any 零容忍区。守卫负责全仓「只减不增」，这里让
  // 已清零文件在本地 eslint 阶段就报错；每收敛一批就在数组里补一批，
  // 待全仓存量清零后把全局的 no-explicit-any 从 off 改成 error 并删除本块。
  {
    files: [
      "src/components/Aggregation/AggregationBreakdownDonut.vue",
      "src/components/CashFlowPanel/index.vue",
      "src/components/Charts/sankeyOption.ts",
      "src/components/Watchlist/SettingsDrawer.vue",
      "src/composables/useEnumOptions.ts",
      "src/composables/useLedgerDetail.ts",
      "src/composables/useSupabaseAuth.ts",
      "src/directives/ripple/index.ts",
      "src/utils/globalPolyfills.ts",
      "src/utils/message.ts",
      "src/utils/print.ts",
      "src/utils/theme.ts",
      "src/views/asset/investment/eaccount-import/composables/useEaccountImport.ts",
      "src/views/asset/investment/manual/conversion/useConversionEstimate.ts",
      "src/views/asset/investment/manual/conversion/useConversionSubmit.ts",
      "src/views/asset/investment/reconcile-workbench/components/DanglingRefFixDialog.vue",
      "src/views/asset/investment/reconcile-workbench/components/SupplementDialog.vue",
      "src/views/asset/ledgers/components/DeleteLedgerDialog.vue",
      "src/views/asset/recurring/components/PlanFormDialog.vue",
      "src/views/asset/recurring/index.vue",
      "src/views/asset/transactionList/TransactionTableView.vue",
      "src/views/explore/components/IndustryCrowdingTrend.vue",
      "src/views/explore/components/IndustryPbroeScatter.vue",
      "src/views/explore/components/TemperatureTrendChart.vue",
      "src/views/profile/composables/useProfileData.ts",
      "src/types/chart.ts",
      "src/utils/errorMessage.ts"
    ],
    plugins: {
      "@typescript-eslint": tseslint.plugin
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error"
    }
  },
  {
    files: ["**/*.d.ts"],
    rules: {
      "eslint-comments/no-unlimited-disable": "off",
      "import/no-duplicates": "off",
      "no-restricted-syntax": "off",
      "unused-imports/no-unused-vars": "off"
    }
  },
  {
    files: ["**/*.?([cm])js"],
    rules: {
      "@typescript-eslint/no-require-imports": "off"
    }
  },
  {
    files: ["**/*.vue"],
    languageOptions: {
      globals: {
        $: "readonly",
        $$: "readonly",
        $computed: "readonly",
        $customRef: "readonly",
        $ref: "readonly",
        $shallowRef: "readonly",
        $toRef: "readonly"
      },
      parser: parserVue,
      parserOptions: {
        ecmaFeatures: {
          jsx: true
        },
        extraFileExtensions: [".vue"],
        parser: tseslint.parser,
        sourceType: "module"
      }
    },
    plugins: {
      "@typescript-eslint": tseslint.plugin,
      vue: pluginVue
    },
    processor: pluginVue.processors[".vue"],
    rules: {
      ...pluginVue.configs.base.rules,
      ...pluginVue.configs.essential.rules,
      ...pluginVue.configs.recommended.rules,
      "no-undef": "off",
      "no-unused-vars": "off",
      "vue/no-v-html": "off",
      "vue/require-default-prop": "off",
      "vue/require-explicit-emits": "off",
      "vue/multi-word-component-names": "off",
      "vue/no-setup-props-reactivity-loss": "off",
      "vue/html-self-closing": [
        "error",
        {
          html: {
            void: "always",
            normal: "always",
            component: "always"
          },
          svg: "always",
          math: "always"
        }
      ]
    }
  }
]);
