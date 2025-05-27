<script setup lang="ts">
import { NCard, NSpace } from 'naive-ui'
import type { SessionMetadata } from '../stores/sessionData'

defineProps<{
	sessionMetadata: SessionMetadata | null
	currentFileSource: 'local' | 'github' | null
	currentGitHubFileName: string | null
}>()
</script>

<template>
	<n-card v-if="sessionMetadata" title="Session Info" style="margin-top: 16px">
		<n-space vertical>
			<span v-if="currentFileSource === 'github' && currentGitHubFileName">
				Source: {{ currentGitHubFileName }}
			</span>
			<span v-else-if="currentFileSource === 'local'">Source: Local Upload</span>
			<span v-else-if="currentFileSource === null && sessionMetadata?.device_description">
				Source: Device (Live/Fetched)
			</span>
			<span>Device: {{ sessionMetadata.device_description || 'N/A' }}</span>
			<span>Date: {{ sessionMetadata.date || 'N/A' }}</span>
			<span>Restart Count: {{ sessionMetadata.restart || 'N/A' }}</span>
			<span>Fan: {{ sessionMetadata.fan_enabled ? 'Enabled' : 'Disabled' }}</span>
		</n-space>
	</n-card>
</template>
