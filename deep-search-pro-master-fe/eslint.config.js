import vue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'
export default [
  { ignores: ['dist/**', 'node_modules/**', 'playwright-report/**', 'test-results/**'] },
  ...tseslint.configs.recommended,
  ...vue.configs['flat/recommended'],
  { files: ['**/*.vue'], languageOptions: { parserOptions: { parser: tseslint.parser } },
    rules: { 'vue/multi-word-component-names': 'off', 'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off', 'vue/html-self-closing': 'off' } },
]
