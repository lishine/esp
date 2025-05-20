import globals from 'globals'
import pluginJs from '@eslint/js'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'
import eslintConfigPrettier from 'eslint-config-prettier'

export default tseslint.config(
	{
		// Global ignores
		ignores: [
			'dist/',
			'node_modules/',
			'.DS_Store',
			'*.log',
			'*.cjs', // Ignoring old .eslintrc.cjs
			'vite.config.ts', // Often good to ignore build tool configs from general linting
			'tailwind.config.js',
			'postcss.config.js',
			'eslint.config.js', // Ignore self
		],
	},
	pluginJs.configs.recommended, // Base JS rules

	// TypeScript files configuration
	{
		files: ['**/*.ts', '**/*.tsx', '**/*.mts', '**/*.cts'],
		extends: tseslint.configs.strictTypeChecked, // Apply strict TS rules
		languageOptions: {
			// parser: tseslint.parser, // This should be set by extends
			parserOptions: {
				project: ['./tsconfig.app.json'], // Path relative to eslint.config.js
				tsconfigRootDir: import.meta.dirname, // Root for tsconfig.json resolution
			},
		},
		// Rules specific to TS files can be added here to override/extend
		rules: {
			'@typescript-eslint/no-explicit-any': 'warn',
			'@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
		},
	},

	// Vue files configuration
	{
		files: ['**/*.vue'],
		extends: pluginVue.configs['flat/recommended'], // Apply Vue recommended rules
		languageOptions: {
			// The parser for .vue files is vue-eslint-parser (set by extends)
			// We configure the parser *it* uses for <script lang="ts">
			parserOptions: {
				parser: tseslint.parser, // TypeScript parser for script blocks
				project: ['./tsconfig.app.json'], // Path relative to eslint.config.js
				tsconfigRootDir: import.meta.dirname, // Root for tsconfig.json resolution
				extraFileExtensions: ['.vue'], // Allow TS parser to see .vue files
			},
		},
		// Rules specific to Vue files can be added here
		rules: {
			'vue/html-self-closing': ['error', { html: { void: 'always', normal: 'always', component: 'always' } }],
			'vue/component-name-in-template-casing': ['error', 'kebab-case', { registeredComponentsOnly: true }],
			'vue/custom-event-name-casing': ['error', 'kebab-case'],
			'vue/no-v-html': 'warn',
		},
	},

	// General rules applicable to all linted files (JS, TS, Vue script)
	{
		languageOptions: {
			ecmaVersion: 'latest',
			sourceType: 'module',
			globals: {
				...globals.browser,
				...globals.es2021,
				...globals.node,
			},
		},
		rules: {
			'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
			'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
			eqeqeq: ['error', 'always'],
			'no-implicit-coercion': 'error',
		},
	},

	// Workaround for https://github.com/vuejs/vue-eslint-parser/issues/104
	// Disable no-unsafe-assignment for .vue files and specific .ts files importing them
	// where type resolution issues with Vue components are common.
	{
		files: ['**/*.ts'],
		rules: {
			'@typescript-eslint/no-unsafe-assignment': 'off',
			'@typescript-eslint/no-unsafe-argument': 'off',
			// If other no-unsafe-* rules trigger, they can be added here too for these files
			// e.g., '@typescript-eslint/no-unsafe-call': 'off',
			// '@typescript-eslint/no-unsafe-member-access': 'off',
		},
	},

	eslintConfigPrettier // Must be last to turn off conflicting rules
)
