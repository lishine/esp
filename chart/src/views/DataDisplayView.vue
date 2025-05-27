<script setup lang="ts">
import { onMounted, computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useSessionDataStore, type SessionMetadata } from '../stores/sessionData'
import SensorChart from '../components/SensorChart.vue'
import SeriesToggle from '../components/SeriesToggle.vue'
import LoadingStates from '../components/LoadingStates.vue'
import SessionInfo from '../components/SessionInfo.vue'
import FileHandling from '../components/FileHandling.vue'
import { useChartOptions } from '../components/ChartOptions'
import { NGrid, NGi, NCard, NSpace } from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import type { LogFileListItem } from '../stores/sessionData'

const sessionDataStore = useSessionDataStore()
const route = useRoute()
const isLoading = computed(() => sessionDataStore.isLoading)
const error = computed(() => sessionDataStore.error)
const sessionMetadata = computed((): SessionMetadata | null => {
	if (!sessionDataStore.sessionMetadata) return null
	const metadata = sessionDataStore.sessionMetadata
	return {
		device_description: metadata.device_description,
		date: metadata.date,
		restart: metadata.restart ? String(metadata.restart) : undefined,
		fan_enabled: metadata.fan_enabled,
		ds_associations: metadata.ds_associations || [],
	}
})
const logEntries = computed(() => sessionDataStore.logEntries)
const chartFormattedData = computed(() => sessionDataStore.getChartFormattedData)
const visibleSeriesSet = computed(() => sessionDataStore.visibleSeries)

// GitHub related computed properties
const gitHubFiles = computed(() => sessionDataStore.gitHubFiles)
const isGitHubListLoading = computed(() => sessionDataStore.isGitHubListLoading)
const gitHubListError = computed(() => sessionDataStore.gitHubListError)
const isGitHubFileLoading = computed(() => sessionDataStore.isGitHubFileLoading)
const gitHubFileError = computed(() => sessionDataStore.gitHubFileError)
const currentFileSource = computed(() => sessionDataStore.currentFileSource)
const currentGitHubFileName = computed(() => sessionDataStore.currentGitHubFileName)

const screenWidth = ref(window.innerWidth)
const isMobile = computed(() => screenWidth.value < 1024)

const { chartsHeight, chartOptions } = useChartOptions(chartFormattedData, visibleSeriesSet, logEntries, isMobile)

onMounted(() => {
	sessionDataStore.loadVisibilityPreferences()
	sessionDataStore.fetchAndSetGitHubLogFilesList()
})

// Watch for changes in the 'prev' query parameter
watch(
	() => route.query.prev,
	(newPrevQuery, oldPrevQuery) => {
		if (newPrevQuery !== oldPrevQuery) {
			const prevValue = Number(newPrevQuery) || 0
			sessionDataStore.fetchSessionData(prevValue > 0 ? prevValue : undefined)
		}
	}
)

const currentPrev = computed(() => {
	const prev = Number(route.query.prev)
	return isNaN(prev) || prev < 0 ? 0 : prev
})

const handleRefreshData = () => {
	const prevValue = Number(route.query.prev) || 0
	sessionDataStore.fetchSessionData(prevValue > 0 ? prevValue : undefined)
}

const handleFileChange = async (options: {
	file: Required<UploadFileInfo>
	fileList: Required<UploadFileInfo>[]
	event?: Event
}) => {
	const file = options.file.file
	if (file) {
		await sessionDataStore.handleFileUpload(file)
	}
}

const handleGitHubFileClick = async (file: LogFileListItem) => {
	await sessionDataStore.loadLogFileFromGitHub(file)
}
</script>

<template>
	<n-space vertical class="data-display-container" style="padding: 0px; padding-top: 0px">
		<loading-states
			:is-loading="isLoading"
			:error="error"
			:is-git-hub-file-loading="isGitHubFileLoading"
			:git-hub-file-error="gitHubFileError"
			:current-file-source="currentFileSource"
		/>

		<div v-if="(!isLoading || currentFileSource === 'github') && !isGitHubFileLoading">
			<n-grid :x-gap="12" :y-gap="8" :cols="'1 s:1 m:4 l:4 xl:4'">
				<n-gi :span="'1 s:1 m:3 l:3 xl:3'">
					<n-card style="margin-top: 0px">
						<div v-if="chartFormattedData && chartFormattedData.series.length > 0 && !isGitHubFileLoading">
							<sensor-chart :options="chartOptions" :height="chartsHeight" />
						</div>
						<div v-else-if="!isGitHubFileLoading && !isLoading && !error && !gitHubFileError">
							<p>No chart data available. Upload a local file or select one from GitHub below.</p>
						</div>
					</n-card>
				</n-gi>
				<n-gi :span="'1 s:1 m:1 l:1 xl:1'">
					<series-toggle />
				</n-gi>
			</n-grid>

			<session-info
				:session-metadata="sessionMetadata"
				:current-file-source="currentFileSource"
				:current-git-hub-file-name="currentGitHubFileName"
			/>

			<file-handling
				:current-prev="currentPrev"
				:is-git-hub-list-loading="isGitHubListLoading"
				:git-hub-list-error="gitHubListError"
				:git-hub-files="gitHubFiles"
				@file-change="handleFileChange"
				@refresh-data="handleRefreshData"
				@git-hub-file-click="handleGitHubFileClick"
			/>
		</div>
	</n-space>
</template>

<style scoped>
@media (max-width: 767px) {
	.data-display-container {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}

	.n-grid {
		flex-grow: 1;
		height: 100%;
	}

	.n-gi {
		height: 100%;
		display: flex;
		flex-direction: column;
	}

	.n-card {
		flex-grow: 1;
		height: 100%;
		display: flex;
		flex-direction: column;
	}

	.n-card > div {
		flex-grow: 1;
		height: 100%;
	}
}

p {
	margin-left: 8px;
}
</style>
