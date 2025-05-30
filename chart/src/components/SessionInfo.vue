<script setup lang="ts">
import type { SessionMetadata } from '../stores'

defineProps<{
	sessionMetadata: SessionMetadata
	currentFileSource: 'local' | 'github' | null
	currentGitHubFileName: string | null
	totalGpsDistance: number
	totalTimeOnFoil: number
}>()

const getSourceIcon = (source: 'local' | 'github' | null) => {
	if (source === 'github') return '🐙'
	if (source === 'local') return '📁'
	return '📡'
}

const getSourceColor = (source: 'local' | 'github' | null) => {
	if (source === 'github') return '#6366f1'
	if (source === 'local') return '#10b981'
	return '#f59e0b'
}

const formatTimeOnFoil = (seconds: number): string => {
	if (seconds < 60) {
		return `${Math.round(seconds)}s`
	}

	const minutes = Math.floor(seconds / 60)
	const remainingSeconds = Math.round(seconds % 60)

	if (minutes < 60) {
		return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
	}

	const hours = Math.floor(minutes / 60)
	const remainingMinutes = minutes % 60

	if (remainingMinutes > 0) {
		return `${hours}h ${remainingMinutes}m`
	}
	return `${hours}h`
}
</script>

<template>
	<div v-if="sessionMetadata" class="session-info-container">
		<div class="session-header">
			<h3 class="session-title">
				<span class="session-icon">📊</span>
				Session Info
			</h3>
		</div>

		<div class="info-grid">
			<div class="info-item source-item" :style="{ '--source-color': getSourceColor(currentFileSource) }">
				<div class="info-label">
					<span class="info-icon">{{ getSourceIcon(currentFileSource) }}</span>
					Source
				</div>
				<div class="info-value">
					<span v-if="currentFileSource === 'github' && currentGitHubFileName">
						{{ currentGitHubFileName }}
					</span>
					<span v-else-if="currentFileSource === 'local'">Local Upload</span>
					<span v-else-if="currentFileSource === null && sessionMetadata?.device_description">
						Device (Live/Fetched)
					</span>
				</div>
			</div>

			<div class="info-item">
				<div class="info-label">
					<span class="info-icon">🔧</span>
					Device
				</div>
				<div class="info-value">{{ sessionMetadata.device_description || 'N/A' }}</div>
			</div>

			<div class="info-item">
				<div class="info-label">
					<span class="info-icon">📅</span>
					Date
				</div>
				<div class="info-value">{{ sessionMetadata.date || 'N/A' }}</div>
			</div>

			<div class="info-item">
				<div class="info-label">
					<span class="info-icon">🔄</span>
					Restart Count
				</div>
				<div class="info-value">{{ sessionMetadata.restart || 'N/A' }}</div>
			</div>

			<div class="info-item">
				<div class="info-label">
					<span class="info-icon">🌀</span>
					Fan
				</div>
				<div
					class="info-value"
					:class="{
						'status-enabled': sessionMetadata.fan_enabled,
						'status-disabled': !sessionMetadata.fan_enabled,
					}"
				>
					{{ sessionMetadata.fan_enabled ? 'Enabled' : 'Disabled' }}
				</div>
			</div>

			<div class="info-item">
				<div class="info-label">
					<span class="info-icon">🗺️</span>
					GPS Distance on foil with motor
				</div>
				<div class="info-value">{{ totalGpsDistance.toFixed(2) }} m</div>
			</div>

			<div class="info-item">
				<div class="info-label">
					<span class="info-icon">🏄</span>
					Time on Foil with motor
				</div>
				<div class="info-value">{{ formatTimeOnFoil(totalTimeOnFoil) }}</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.session-info-container {
	background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
	border-radius: 16px;
	padding: 24px;
	box-shadow:
		0 4px 6px -1px rgba(0, 0, 0, 0.1),
		0 2px 4px -1px rgba(0, 0, 0, 0.06);
	border: 1px solid #e2e8f0;
	margin-top: 20px;
}

.session-header {
	margin-bottom: 20px;
}

.session-title {
	display: flex;
	align-items: center;
	gap: 8px;
	margin: 0;
	font-size: 1.25rem;
	font-weight: 600;
	color: #1e293b;
}

.session-icon {
	font-size: 1.5rem;
}

.info-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
	gap: 16px;
}

.info-item {
	background: white;
	border-radius: 12px;
	padding: 16px;
	box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
	border: 1px solid #f1f5f9;
	transition: all 0.2s ease;
}

.info-item:hover {
	transform: translateY(-1px);
	box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.source-item {
	border-left: 4px solid var(--source-color, #6b7280);
}

.info-label {
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: 0.875rem;
	font-weight: 600;
	color: #6b7280;
	margin-bottom: 8px;
}

.info-icon {
	font-size: 1rem;
}

.info-value {
	font-size: 0.95rem;
	font-weight: 500;
	color: #374151;
	word-break: break-word;
}

.status-enabled {
	color: #10b981;
	font-weight: 600;
}

.status-disabled {
	color: #ef4444;
	font-weight: 600;
}

@media (max-width: 768px) {
	.info-grid {
		grid-template-columns: 1fr;
	}

	.session-info-container {
		padding: 16px;
	}
}
</style>
