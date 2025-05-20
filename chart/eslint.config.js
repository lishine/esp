import globals from 'globals'
import pluginJs from '@eslint/js'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'
import eslintConfigPrettier from 'eslint-config-prettier' // Used to disable conflicting rules

export default [
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
	// Base JavaScript/ESLint recommended rules
	pluginJs.configs.recommended,

	// TypeScript configurations
	...tseslint.configs.strictTypeChecked, // Strictest, requires type info

	// Vue 3 configurations
	...pluginVue.configs['flat/recommended'], // Use flat config version for Vue

	// Configuration for all files (global language options, etc.)
	{
		languageOptions: {
			ecmaVersion: 'latest',
			sourceType: 'module',
			globals: {
				...globals.browser,
				...globals.es2021,
				...globals.node,
				// Define any custom globals if needed, e.g.
				// 'myGlobal': 'readonly',
			},
		},
	},

	// Configuration specific to .vue files
	{
		files: ['**/*.vue'],
		languageOptions: {
			parserOptions: {
				parser: tseslint.parser, // Use typescript-eslint parser for <script> in .vue
				project: ['./tsconfig.json', './tsconfig.app.json'],
				extraFileExtensions: ['.vue'],
			},
		},
		rules: {
			// --- Vue Specific Strict Rules (Examples, adjust as needed) ---
			'vue/html-self-closing': [
				'error',
				{
					html: { void: 'always', normal: 'always', component: 'always' },
					svg: 'always',
					math: 'always',
				},
			],
			'vue/component-name-in-template-casing': [
				'error',
				'kebab-case',
				{
					registeredComponentsOnly: true,
					ignores: [],
				},
			],
			'vue/custom-event-name-casing': ['error', 'kebab-case'],
			'vue/no-v-html': 'warn', // Using v-html can be a security risk
			// Add more Vue specific rules here
		},
	},

	// Configuration specific to .ts, .tsx, .mts, .cts files
	{
		files: ['**/*.ts', '**/*.tsx', '**/*.mts', '**/*.cts'],
		languageOptions: {
			parserOptions: {
				project: ['./tsconfig.json', './tsconfig.app.json'],
			},
		},
		rules: {
			// --- TypeScript Specific Strict Rules (Examples, adjust as needed) ---
			'@typescript-eslint/no-explicit-any': 'warn', // Warn on 'any' type, consider 'error' for max strictness
			'@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }], // Warn on unused vars
			// Add more TS specific rules here
		},
	},

	// General strictness rules applicable to JS/TS/Vue script parts
	{
		rules: {
			'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
			'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
			eqeqeq: ['error', 'always'], // Enforce === and !==
			'no-implicit-coercion': 'error',
			// You can override or add more rules here for maximum strictness
			// For example, to make 'any' an error:
			// '@typescript-eslint/no-explicit-any': 'error',
		},
	},

	// Prettier compatibility: This should be the LAST configuration object.
	// It turns off ESLint rules that would conflict with Prettier.
	eslintConfigPrettier,
]
