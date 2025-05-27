<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useSessionDataStore } from './stores/sessionData'
import {
	NCheckbox,
	NInput,
	NSpace,
	NButton,
	NMessageProvider,
	NConfigProvider,
	type GlobalThemeOverrides, // Added type keyword here
} from 'naive-ui' // Added NButton, NMessageProvider, NConfigProvider

const sessionDataStore = useSessionDataStore()

// --- UI State for Custom IP ---
const userApiIpLocal = ref(sessionDataStore.userApiIp)
const useUserApiIpLocal = ref(sessionDataStore.useUserApiIp)

watch(userApiIpLocal, (newValue) => {
	sessionDataStore.setUserApiIp(newValue)
})
watch(useUserApiIpLocal, (newValue) => {
	sessionDataStore.setUseUserApiIp(newValue)
})

// --- Responsive UI for settings visibility ---
const screenWidth = ref(window.innerWidth)
const isMobile = computed(() => screenWidth.value < 1024)

const updateScreenWidth = () => {
	screenWidth.value = window.innerWidth
}

onMounted(() => {
	window.addEventListener('resize', updateScreenWidth)
	// Initialize store values from potential persisted state if that was implemented
	userApiIpLocal.value = sessionDataStore.userApiIp
	useUserApiIpLocal.value = sessionDataStore.useUserApiIp
})

onBeforeUnmount(() => {
	window.removeEventListener('resize', updateScreenWidth)
})

const handleRefresh = () => {
	sessionDataStore.fetchSessionData()
}

// Theme overrides for Naive UI (optional, for consistency)
const themeOverrides: GlobalThemeOverrides = {
	common: {
		// primaryColor: '#FF0000', // Example
	},
	// You can add overrides for specific components too
	// Button: {
	//   textColor: '#FF0000'
	// }
}
</script>

<template>
	<n-config-provider :theme-overrides="themeOverrides">
		<n-message-provider>
			<div class="app-container">
				<main class="app-main">
					<router-view />
				</main>
				<footer class="app-footer" v-if="isMobile">
					<!-- Mobile specific refresh button or other controls -->
					<n-button @click="handleRefresh" type="primary" block style="margin-top: 10px">
						Fetch/Refresh Data
					</n-button>
				</footer>
				<div v-if="!isMobile && false" style="padding: 10px 20px; margin-top: auto">
					<h4>Advanced Settings</h4>
					<n-space vertical style="margin-bottom: 10px; border: 1px solid #ccc; padding: 10px">
						<n-checkbox v-model:checked="useUserApiIpLocal"> Use Custom ESP32 IP Address </n-checkbox>
						<n-input
							v-model:value="userApiIpLocal"
							placeholder="Enter ESP32 IP (e.g., 192.168.1.100)"
							:disabled="!useUserApiIpLocal"
							style="max-width: 300px"
						/>
					</n-space>
				</div>
			</div>
		</n-message-provider>
	</n-config-provider>
</template>

<style>
/* Global styles */
body,
html {
	margin: 0;
	padding: 0;
	height: 100%;
	font-family:
		Inter,
		-apple-system,
		BlinkMacSystemFont,
		'Segoe UI',
		Roboto,
		Oxygen,
		Ubuntu,
		Cantarell,
		'Fira Sans',
		'Droid Sans',
		'Helvetica Neue',
		sans-serif;
}

.app-container {
	display: flex;
	flex-direction: column;
	min-height: 100vh; /* Ensure it takes at least full viewport height */
}

.app-header {
	padding: 10px 20px;
	/* background-color: #f8f8f8; */
	/* border-bottom: 1px solid #eee; */
}

.app-main {
	flex-grow: 1; /* Allows main content to take available space */
	padding: 0px; /* Adjust padding as needed, DataDisplayView has its own */
	padding-top: 0px;
}
.app-footer {
	padding: 10px 20px;
	/* background-color: #f8f8f8; */
	/* border-top: 1px solid #eee; */
}

/* Reset or global styles can be linked from main.ts or style.css */
/* For now, ensure style.css is imported in main.ts if it contains Tailwind directives */
/* #app { max-width: 1280px; margin: 0 auto; padding: 2rem; font-weight: normal; } */
</style>
