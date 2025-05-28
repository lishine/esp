<script setup lang="ts">
import type { UploadFileInfo } from 'naive-ui'
import type { LogFile } from '../stores'

defineProps<{
	currentPrev: number
	isGitHubListLoading: boolean
	gitHubListError: string | null
	gitHubFiles: LogFile[]
}>()

const emit = defineEmits<{
	(
		e: 'fileChange',
		options: { file: Required<UploadFileInfo>; fileList: Required<UploadFileInfo>[]; event?: Event }
	): void
	(e: 'refreshData'): void
	(e: 'gitHubFileClick', file: LogFile): void
}>()

const handleFileChange = (event: Event) => {
	const input = event.target as HTMLInputElement
	if (input.files && input.files[0]) {
		const file = input.files[0]
		const uploadFileInfo: Required<UploadFileInfo> = {
			id: Date.now().toString(),
			name: file.name,
			status: 'finished',
			file: file,
			percentage: 100,
			url: null,
			thumbnailUrl: null,
			type: file.type,
			fullPath: file.webkitRelativePath || file.name,
			batchId: null,
		}
		emit('fileChange', {
			file: uploadFileInfo,
			fileList: [uploadFileInfo],
			event,
		})
	}
}

const handleGitHubFileClick = (file: LogFile) => {
	emit('gitHubFileClick', file)
}
</script>

<template>
	<div class="file-handling-container">
		<!-- Upload Section -->
		<div class="upload-section">
			<div class="upload-card">
				<div class="upload-header">
					<span class="upload-icon">📁</span>
					<h4 class="upload-title">Upload Local File</h4>
				</div>
				<div class="upload-area">
					<input type="file" accept=".jsonl" @change="handleFileChange" class="file-input" id="file-upload" />
					<label for="file-upload" class="upload-button">
						<span class="upload-button-icon">⬆️</span>
						Upload Local JSONL File
					</label>
				</div>
			</div>
		</div>

		<!-- GitHub Files Section -->
		<div class="github-section">
			<div class="github-header">
				<h3 class="github-title">
					<span class="github-icon">🐙</span>
					Load Log from GitHub
				</h3>
			</div>

			<div class="github-content">
				<!-- Loading State -->
				<div v-if="isGitHubListLoading" class="loading-state">
					<div class="spinner"></div>
					<p class="loading-text">Loading GitHub file list...</p>
				</div>

				<!-- Error State -->
				<div v-if="gitHubListError && !isGitHubListLoading" class="error-state">
					<div class="error-icon">⚠️</div>
					<div class="error-content">
						<h4 class="error-title">Error Loading GitHub File List</h4>
						<p class="error-message">{{ gitHubListError }}</p>
					</div>
				</div>

				<!-- File List -->
				<div v-if="!isGitHubListLoading && !gitHubListError && gitHubFiles.length > 0" class="file-list">
					<div
						v-for="file in gitHubFiles"
						:key="file.name"
						class="file-item"
						@click="handleGitHubFileClick(file)"
					>
						<span class="file-icon">📄</span>
						<span class="file-name">{{ file.name }}</span>
						<span class="file-arrow">→</span>
					</div>
				</div>

				<!-- Empty State -->
				<div v-if="!isGitHubListLoading && !gitHubListError && gitHubFiles.length === 0" class="empty-state">
					<div class="empty-icon">📂</div>
					<p class="empty-text">No .jsonl files found in the GitHub directory</p>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.file-handling-container {
	display: flex;
	flex-direction: column;
	gap: 20px;
	margin: 20px 0;
}

.upload-section {
	background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
	border-radius: 16px;
	padding: 20px;
	box-shadow:
		0 4px 6px -1px rgba(0, 0, 0, 0.1),
		0 2px 4px -1px rgba(0, 0, 0, 0.06);
	border: 1px solid #e2e8f0;
}

.upload-card {
	background: white;
	border-radius: 12px;
	padding: 20px;
	box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.upload-header {
	display: flex;
	align-items: center;
	gap: 10px;
	margin-bottom: 16px;
}

.upload-icon {
	font-size: 1.25rem;
}

.upload-title {
	margin: 0;
	font-size: 1.1rem;
	font-weight: 600;
	color: #374151;
}

.upload-area {
	position: relative;
}

.file-input {
	position: absolute;
	opacity: 0;
	width: 100%;
	height: 100%;
	cursor: pointer;
}

.upload-button {
	display: flex;
	align-items: center;
	justify-content: center;
	gap: 8px;
	width: 100%;
	padding: 12px 20px;
	background: linear-gradient(135deg, #10b981 0%, #059669 100%);
	color: white;
	border-radius: 8px;
	font-weight: 600;
	cursor: pointer;
	transition: all 0.2s ease;
	border: none;
}

.upload-button:hover {
	transform: translateY(-1px);
	box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
}

.upload-button-icon {
	font-size: 1.1rem;
}

.github-section {
	background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
	border-radius: 16px;
	padding: 24px;
	box-shadow:
		0 4px 6px -1px rgba(0, 0, 0, 0.1),
		0 2px 4px -1px rgba(0, 0, 0, 0.06);
	border: 1px solid #e2e8f0;
}

.github-header {
	margin-bottom: 20px;
}

.github-title {
	display: flex;
	align-items: center;
	gap: 8px;
	margin: 0;
	font-size: 1.25rem;
	font-weight: 600;
	color: #1e293b;
}

.github-icon {
	font-size: 1.5rem;
}

.github-content {
	background: white;
	border-radius: 12px;
	padding: 20px;
	box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
	min-height: 120px;
}

.loading-state {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	gap: 16px;
	padding: 40px 20px;
}

.spinner {
	width: 32px;
	height: 32px;
	border: 3px solid #f3f4f6;
	border-top: 3px solid #6366f1;
	border-radius: 50%;
	animation: spin 1s linear infinite;
}

@keyframes spin {
	0% {
		transform: rotate(0deg);
	}
	100% {
		transform: rotate(360deg);
	}
}

.loading-text {
	margin: 0;
	color: #6b7280;
	font-weight: 500;
}

.error-state {
	display: flex;
	align-items: flex-start;
	gap: 12px;
	padding: 16px;
	background: #fef2f2;
	border: 1px solid #fecaca;
	border-radius: 8px;
}

.error-icon {
	font-size: 1.5rem;
	flex-shrink: 0;
}

.error-content {
	flex: 1;
}

.error-title {
	margin: 0 0 8px 0;
	font-size: 1rem;
	font-weight: 600;
	color: #dc2626;
}

.error-message {
	margin: 0;
	color: #7f1d1d;
	font-size: 0.9rem;
}

.file-list {
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.file-item {
	display: flex;
	align-items: center;
	gap: 12px;
	padding: 12px 16px;
	background: #f8fafc;
	border: 1px solid #e2e8f0;
	border-radius: 8px;
	cursor: pointer;
	transition: all 0.2s ease;
}

.file-item:hover {
	background: #f1f5f9;
	border-color: #6366f1;
	transform: translateX(4px);
}

.file-icon {
	font-size: 1.1rem;
	flex-shrink: 0;
}

.file-name {
	flex: 1;
	font-weight: 500;
	color: #374151;
	font-size: 0.9rem;
}

.file-arrow {
	color: #6b7280;
	font-weight: bold;
	transition: transform 0.2s ease;
}

.file-item:hover .file-arrow {
	transform: translateX(4px);
	color: #6366f1;
}

.empty-state {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	gap: 12px;
	padding: 40px 20px;
}

.empty-icon {
	font-size: 2rem;
	opacity: 0.5;
}

.empty-text {
	margin: 0;
	color: #6b7280;
	text-align: center;
}

@media (max-width: 768px) {
	.file-handling-container {
		margin: 16px 0;
	}

	.upload-section,
	.github-section {
		padding: 16px;
	}

	.upload-card,
	.github-content {
		padding: 16px;
	}
}
</style>
