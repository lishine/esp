<script setup lang="ts">
import { NSpace, NButton, NUpload, NCard, NList, NListItem, NAlert, NSpin } from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import type { LogFileListItem } from '../stores/sessionData'

defineProps<{
	currentPrev: number // This prop needs to be restored
	isGitHubListLoading: boolean
	gitHubListError: string | null
	gitHubFiles: LogFileListItem[]
}>()

const emit = defineEmits<{
	(
		e: 'fileChange',
		options: { file: Required<UploadFileInfo>; fileList: Required<UploadFileInfo>[]; event?: Event }
	): void
	(e: 'refreshData'): void // This emit needs to be present
	(e: 'gitHubFileClick', file: LogFileListItem): void
}>()

const handleFileChange = (options: {
	file: Required<UploadFileInfo>
	fileList: Required<UploadFileInfo>[]
	event?: Event
}) => {
	emit('fileChange', options)
}

const handleRefreshData = () => {
	// This function needs to be restored
	emit('refreshData')
}

const handleGitHubFileClick = (file: LogFileListItem) => {
	emit('gitHubFileClick', file)
}
</script>

<template>
	<n-space vertical style="width: 100%; margin-top: 16px; margin-bottom: 16px">
		<n-button v-if="false" @click="handleRefreshData" type="primary" block>
			Fetch/Refresh Data (Current: {{ currentPrev === 0 ? 'Live' : `Prev ${currentPrev}` }})
		</n-button>
		<n-upload accept=".jsonl" :max="1" :show-file-list="false" @change="handleFileChange">
			<n-button block>Upload Local JSONL File</n-button>
		</n-upload>
	</n-space>

	<!-- GitHub Files Section -->
	<n-card title="Load Log from GitHub" style="margin-top: 16px; margin-bottom: 16px">
		<n-space v-if="isGitHubListLoading" align="center" justify="center">
			<n-spin size="medium" />
			<p>Loading GitHub file list...</p>
		</n-space>
		<n-alert
			v-if="gitHubListError && !isGitHubListLoading"
			title="Error Loading GitHub File List"
			type="error"
			closable
		>
			{{ gitHubListError }}
		</n-alert>
		<n-list v-if="!isGitHubListLoading && !gitHubListError && gitHubFiles.length > 0" hoverable clickable bordered>
			<n-list-item v-for="file in gitHubFiles" :key="file.name" @click="handleGitHubFileClick(file)">
				{{ file.name }}
			</n-list-item>
		</n-list>
		<p v-if="!isGitHubListLoading && !gitHubListError && gitHubFiles.length === 0">
			No .jsonl files found in the GitHub directory or failed to load list.
		</p>
	</n-card>
</template>

<style scoped>
p {
	margin-left: 8px;
}
</style>
