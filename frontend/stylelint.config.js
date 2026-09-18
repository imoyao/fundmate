// @ts-check

/** @type {import("stylelint").Config} */
export default {
  extends: [
    "stylelint-config-standard",
    "stylelint-config-html/vue",
    "stylelint-config-recess-order"
  ],
  plugins: ["stylelint-scss", "stylelint-order", "stylelint-prettier"],
  overrides: [
    {
      files: ["**/*.(css|html|vue)"],
      customSyntax: "postcss-html"
    },
    {
      files: ["*.scss", "**/*.scss"],
      customSyntax: "postcss-scss",
      extends: [
        "stylelint-config-standard-scss",
        "stylelint-config-recommended-vue/scss"
      ]
    }
  ],
  rules: {
    "prettier/prettier": true,
    "selector-class-pattern": null,
    "no-descending-specificity": null,
    "scss/dollar-variable-pattern": null,
    "selector-pseudo-class-no-unknown": [
      true,
      {
        ignorePseudoClasses: ["deep", "global"]
      }
    ],
    "selector-pseudo-element-no-unknown": [
      true,
      {
        ignorePseudoElements: ["v-deep", "v-global", "v-slotted"]
      }
    ],
    "at-rule-no-unknown": [
      true,
      {
        ignoreAtRules: [
          "tailwind",
          "apply",
          "variants",
          "responsive",
          "screen",
          "function",
          "if",
          "else",
          "each",
          "include",
          "mixin",
          "use",
          "error",
          "warn",
          "debug",
          "return",
          "extend",
          "forward",
          "at-root"
        ]
      }
    ],
    "rule-empty-line-before": [
      "always",
      {
        ignore: ["after-comment", "first-nested"]
      }
    ],
    "unit-no-unknown": [true, { ignoreUnits: ["rpx"] }],
    "value-keyword-case": [
      "lower",
      {
        // Vue SFC 的 CSS v-bind() 参数是 <script> 变量名，区分大小写；
        // postcss-html 把参数解析成独立 keyword 节点，standard 预设会将其
        // 强制小写导致绑定失效（SankeyChart containerHeightPx 曾被打断）。
        // 凡含大写字母的关键字一律视为标识符豁免，纯小写关键字不受影响。
        ignoreKeywords: ["/[A-Z]/"]
      }
    ],
    "function-no-unknown": [
      true,
      {
        // Vue SFC 的 v-bind() 是编译期函数（绑定 <script> 变量到样式），
        // 并非标准 CSS 函数，stylelint 会误报 unknown function，故在此豁免。
        ignoreFunctions: ["v-bind"]
      }
    ],
    "order/order": [
      [
        "dollar-variables",
        "custom-properties",
        "at-rules",
        "declarations",
        {
          type: "at-rule",
          name: "supports"
        },
        // `include` 与 `media` 同槽（声明之后）：断点 mixin（#1571 的 bp.below/above、
        // sidebar.scss 的 merge-style）**编译产物就是 @media**。而媒体查询不改变特异性，
        // 同特异性下后写的规则胜出——一旦被 `stylelint --fix` 挪到基础声明**之前**，
        // 这些覆盖就会静默失效（MetricGrid 的 --metric-basis 两档正是这么死的，
        // 见 scripts/guard_breakpoints.py 与 docs/spec/decisions.md 2026-09-17 条目）。
        // 故此处必须让 include 与 media 同槽：位置就是语义，不能只按「长得像不像 at-rule」排。
        {
          type: "at-rule",
          name: "include"
        },
        {
          type: "at-rule",
          name: "media"
        },
        "rules"
      ],
      { severity: "warning" }
    ]
  },
  ignoreFiles: ["**/*.js", "**/*.ts", "**/*.jsx", "**/*.tsx", "report.html"]
};
