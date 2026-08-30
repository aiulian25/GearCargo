import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

// Flat config (eslint 9). Replaces the orphaned .eslintrc-audit.json, which
// eslint never auto-discovered — `npm run lint` had been failing to find any
// config at all.
//
// Scope: correctness rules only. eslint-plugin-react-hooks v7 also ships the
// React Compiler ruleset (set-state-in-effect, immutability, purity,
// static-components); those flag ~65 places and are a separate refactor, so
// they are deliberately not enabled here.
export default [
  { ignores: ['dist/**', 'dev-dist/**', 'coverage/**', 'public/**'] },
  js.configs.recommended,
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.serviceworker },
      parserOptions: { ecmaVersion: 'latest', ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: 'detect' } },
    plugins: { react, 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      // Ported from .eslintrc-audit.json.
      'no-unused-vars': ['warn', {
        vars: 'all', args: 'none', ignoreRestSiblings: true, varsIgnorePattern: '^_',
      }],
      'react/jsx-uses-vars': 'warn',
      'react/jsx-uses-react': 'warn',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
  {
    files: ['**/*.test.{js,jsx}', '**/test/**', '**/__tests__/**', 'vitest.setup.js'],
    languageOptions: { globals: { ...globals.node, ...globals.vitest } },
  },
]
