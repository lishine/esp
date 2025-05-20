module.exports = {
  root: true,
  env: {
    browser: true,
    es2021: true,
    node: true,
  },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/strict-type-checked', // Strictest TypeScript rules requiring type information
    'plugin:vue/vue3-recommended', // Strictest recommended Vue3 rules
    'plugin:prettier/recommended', // Integrates Prettier with ESLint (must be last in extends)
  ],
  parser: 'vue-eslint-parser', // Primary parser for .vue files
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    parser: '@typescript-eslint/parser', // Parser for <script> blocks
    project: ['./tsconfig.json', './tsconfig.app.json'], // Crucial for type-aware linting
    extraFileExtensions: ['.vue'],
  },
  plugins: [
    '@typescript-eslint',
    'vue', // Already implicitly added by plugin:vue/vue3-recommended but good to be explicit
    // 'prettier' is implicitly added by plugin:prettier/recommended
  ],
  rules: {
    // --- TypeScript Specific Strict Rules (Examples, adjust as needed) ---
    '@typescript-eslint/no-explicit-any': 'warn', // Warn on 'any' type, consider 'error' for max strictness
    '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }], // Warn on unused vars

    // --- Vue Specific Strict Rules (Examples, adjust as needed) ---
    'vue/html-self-closing': ['error', {
      html: { void: 'always', normal: 'always', component: 'always' },
      svg: 'always',
      math: 'always',
    }],
    'vue/component-name-in-template-casing': ['error', 'kebab-case', {
      registeredComponentsOnly: true,
      ignores: []
    }],
    'vue/custom-event-name-casing': ['error', 'kebab-case'],
    'vue/no-v-html': 'warn', // Using v-html can be a security risk

    // --- General Strictness ---
    'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    'eqeqeq': ['error', 'always'], // Enforce === and !==
    'no-implicit-coercion': 'error',

    // You can override or add more rules here for maximum strictness
    // For example, to make 'any' an error:
    // '@typescript-eslint/no-explicit-any': 'error',
  },
  ignorePatterns: ['dist', 'node_modules', '.eslintrc.cjs', 'vite.config.ts', 'tailwind.config.js', 'postcss.config.js'],
};