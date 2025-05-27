<script setup lang="ts">
import { NSpin, NAlert, NSpace } from 'naive-ui'

defineProps<{
	isLoading: boolean
	error: string | null
	isGitHubFileLoading: boolean
	gitHubFileError: string | null
	currentFileSource: 'local' | 'github' | null
}>()
</script>

<template>
	<!-- General Loading for local file or initial device data -->
	<n-space
		v-if="isLoading && currentFileSource !== 'github' && !isGitHubFileLoading"
		align="center"
		justify="center"
		style="margin-top: 20px"
	>
		<n-spin size="large" />
		<p>Loading session data...</p>
	</n-space>

	<!-- General Error for local file or initial device data -->
	<n-alert
		v-if="error && !isLoading && currentFileSource !== 'github' && !isGitHubFileLoading"
		title="Error Loading Data"
		type="error"
		closable
	>
		{{ error }}
	</n-alert>

	<!-- GitHub File Specific Loading -->
	<n-space v-if="isGitHubFileLoading" align="center" justify="center" style="margin-top: 20px">
		<n-spin size="large" />
		<p>Loading selected GitHub log file...</p>
	</n-space>

	<!-- GitHub File Specific Error -->
	<n-alert v-if="gitHubFileError && !isGitHubFileLoading" title="Error Loading GitHub File" type="error" closable>
		{{ gitHubFileError }}
	</n-alert>
</template>

<style scoped>
p {
	margin-left: 8px;
}
</style>
