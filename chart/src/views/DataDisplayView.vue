<script setup lang="ts">
import { onMounted, computed, ref, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionDataStore, type SessionMetadata, type LogFile } from '../stores'
import SensorChart from '../components/SensorChart.vue'
import GroupAveragesChart from '../components/groupAveragesChart/GroupAveragesChart.vue' // Updated import path
import LoadingStates from '../components/LoadingStates.vue'
import SessionInfo from '../components/SessionInfo.vue'
import FileHandling from '../components/FileHandling.vue'
import { useChartOptions } from '../components/ChartOptions'
import { useGroupAveragesChartOptions } from '../components/groupAveragesChart/useGroupAveragesChartOptions' // Updated import path
import { NGrid, NGi, NCard, NSpace, NSwitch, NDivider, NText } from 'naive-ui' // Added NSwitch, NDivider, NText
import type { UploadFileInfo } from 'naive-ui'
import { GROUP_AVERAGE_SERIES_CONFIG } from '../components/groupAveragesChart/seriesConfig' // Updated import path
import * as echarts from 'echarts/core' // Re-imported for explicit connect/disconnect
// import type { EChartsOption } from 'echarts' // EChartsOption is not used directly in this file after recent changes.

const sessionDataStore = useSessionDataStore()
const route = useRoute()
const router = useRouter()
const isLoading = computed(() => sessionDataStore.isLoading)
const error = computed(() => sessionDataStore.error)
const sessionMetadata = computed((): SessionMetadata => {
	const metadata = sessionDataStore.sessionMetadata
	return {
		device_description: metadata.device_description,
		date: metadata.date,
		restart: metadata.restart,
		fan_enabled: metadata.fan_enabled,
		ds_associations: metadata.ds_associations || [],
	}
})
const logEntries = computed(() => sessionDataStore.logEntries)
const chartFormattedData = computed(() => sessionDataStore.getChartFormattedData)
const hiddenSeriesSet = computed(() => sessionDataStore.hiddenSeries)
const totalGpsDistance = computed(() => sessionDataStore.getTotalGpsDistance)
const totalTimeOnFoil = computed(() => sessionDataStore.getTotalTimeOnFoil)

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

const dataZoomStart = computed(() => sessionDataStore.dataZoomStart)
const dataZoomEnd = computed(() => sessionDataStore.dataZoomEnd)

// Main chart options
const { chartsHeight, chartOptions: chartOptionsMain } = useChartOptions(
	// Renamed chartOptions to chartOptionsMain
	chartFormattedData,
	hiddenSeriesSet,
	logEntries,
	isMobile,
	dataZoomStart,
	dataZoomEnd
)

// Group Averages Chart options
const groupAggregates = computed(() => sessionDataStore.getGroupAggregates)
const groupAverageSeriesConfigConst = ref(GROUP_AVERAGE_SERIES_CONFIG) // Make it a ref for the composable
const groupAverageSeriesVisibility = computed(() => sessionDataStore.getGroupAverageSeriesVisibility)
const showGroupAveragesMaster = computed({
	get: () => sessionDataStore.getShowGroupAveragesMaster,
	set: (value) => sessionDataStore.setShowGroupAveragesMaster(value),
})

const { chartOptionsGroupAverages } = useGroupAveragesChartOptions(
	groupAggregates,
	groupAverageSeriesConfigConst, // Pass the ref
	groupAverageSeriesVisibility,
	dataZoomStart, // Share dataZoom state
	dataZoomEnd // Share dataZoom state
)

const sensorChartRef = ref<InstanceType<typeof SensorChart> | null>(null)
const groupAveragesChartRef = ref<InstanceType<typeof GroupAveragesChart> | null>(null)

// const connectCharts = () => { // Explicit connect call might be redundant if 'group' property is used
// 	const mainChartInstance = sensorChartRef.value?.getEchartsInstance()
// 	const groupChartInstance = groupAveragesChartRef.value?.getEchartsInstance()
//
// 	if (mainChartInstance && groupChartInstance && showGroupAveragesMaster.value) {
// 		echarts.connect([groupChartInstance, mainChartInstance])
// 		console.log('ECharts instances connected via explicit call')
// 	} else if (mainChartInstance && !showGroupAveragesMaster.value) {
// 		const mainChartGroupId = mainChartInstance.group
// 		if (mainChartGroupId && groupChartInstance && mainChartGroupId === groupChartInstance.group) {
// 			// To disconnect, we might need to remove them from the group or connect to a different/null group.
// 			// ECharts should handle this if the 'group' property is correctly managed in options.
// 			// console.log('Attempting to disconnect charts due to master toggle OFF.');
// 			// echarts.disconnect('groupSync'); // Disconnect the entire group
// 		}
// 	}
// }

// Watcher for chart readiness and visibility - now using explicit connect/disconnect
watch(
	[sensorChartRef, groupAveragesChartRef, showGroupAveragesMaster, chartOptionsMain, chartOptionsGroupAverages],
	async () => {
		await nextTick() // Ensure DOM is updated and refs are available

		// Check if chart components are mounted before attempting to connect/disconnect
		// This is important because getEchartsInstance() might be called on null refs initially
		const mainChartReady = !!sensorChartRef.value?.getEchartsInstance()
		const groupChartReady = !!groupAveragesChartRef.value?.getEchartsInstance()

		if (showGroupAveragesMaster.value) {
			// Connect if both charts are ready and master toggle is on
			if (mainChartReady && groupChartReady) {
				// console.log("Attempting to connect charts in group 'groupSync'")
				echarts.connect('groupSync')
			} else {
				// console.log('Charts not ready for connection or groupAveragesChartRef is null')
			}
		} else {
			// Disconnect the group if master toggle is off
			// console.log("Attempting to disconnect charts in group 'groupSync'")
			echarts.disconnect('groupSync')
		}
	},
	{ immediate: true, deep: true }
)

// Function to load GitHub file based on route parameter
const loadGitHubFileFromRouteParam = async () => {
	const filenameFromRoute = route.params.filename as string
	if (filenameFromRoute) {
		sessionDataStore.isGitHubFileLoading = true
		sessionDataStore.gitHubFileError = null
		while (sessionDataStore.isGitHubListLoading) {
			await new Promise((resolve) => setTimeout(resolve, 100))
		}
		if (sessionDataStore.gitHubListError) {
			sessionDataStore.gitHubFileError = `Cannot display file: GitHub file list failed to load. Error: ${sessionDataStore.gitHubListError}`
			sessionDataStore.isGitHubFileLoading = false
			return
		}
		const fileToLoad = sessionDataStore.gitHubFiles.find((f) => f.name === filenameFromRoute)
		if (fileToLoad) {
			await sessionDataStore.loadLogFileFromGitHub(fileToLoad)
		} else {
			sessionDataStore.gitHubFileError = `File "${filenameFromRoute}" not found in the GitHub repository.`
			sessionDataStore.isGitHubFileLoading = false
		}
	}
}

onMounted(async () => {
	sessionDataStore.loadVisibilityPreferences()
	sessionDataStore.fetchAndSetGitHubLogFilesList()
	await loadGitHubFileFromRouteParam()

	// The watcher with immediate: true handles the initial connection attempt.
})

watch(
	() => route.query.prev,
	(newPrevQuery, oldPrevQuery) => {
		if (newPrevQuery !== oldPrevQuery) {
			const prevValue = Number(newPrevQuery) || 0
			sessionDataStore.fetchSessionData(prevValue > 0 ? prevValue : undefined)
		}
	},
	{ immediate: true }
)

watch(
	() => route.params.filename,
	async (newFilename, oldFilename) => {
		if (newFilename && newFilename !== oldFilename) {
			await loadGitHubFileFromRouteParam()
		} else if (!newFilename && oldFilename && sessionDataStore.currentFileSource === 'github') {
			sessionDataStore.clearGitHubData()
		}
	},
	{ immediate: false }
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
		if (!sessionDataStore.error) {
			router.push('/')
		}
	}
}

const handleGitHubFileClick = (file: LogFile) => {
	router.push(`/github/${file.name}`)
}

// const handleGroupAverageSeriesToggle = (seriesName: string, value: boolean) => { // Removed unused function
// 	sessionDataStore.setGroupAverageSeriesVisibility(seriesName, value)
// }
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
						<!-- Group Averages Chart Toggles -->
						<n-space align="center" style="margin-bottom: 10px">
							<n-text>Show Group Averages:</n-text>
							<n-switch v-model:value="showGroupAveragesMaster" />
						</n-space>
						<n-divider v-if="showGroupAveragesMaster" />

						<div
							v-if="
								chartFormattedData &&
								(chartFormattedData.series.length > 0 || showGroupAveragesMaster) &&
								!isGitHubFileLoading
							"
						>
							<group-averages-chart
								v-if="showGroupAveragesMaster && chartOptionsGroupAverages"
								ref="groupAveragesChartRef"
								:options="chartOptionsGroupAverages"
								height="375px"
								width="100%"
								theme="light"
							/>
							<sensor-chart ref="sensorChartRef" :options="chartOptionsMain" :height="chartsHeight" />
						</div>
						<div v-else-if="!isGitHubFileLoading && !isLoading && !error && !gitHubFileError">
							<p>No chart data available. Upload a local file or select one from GitHub below.</p>
						</div>
					</n-card>
				</n-gi>
				<n-gi :span="'1 s:1 m:1 l:1 xl:1'">
					<!-- Potential space for main chart series toggles or other controls -->
				</n-gi>
			</n-grid>

			<session-info
				:session-metadata="sessionMetadata"
				:current-file-source="currentFileSource"
				:current-git-hub-file-name="currentGitHubFileName"
				:total-gps-distance="totalGpsDistance"
				:total-time-on-foil="totalTimeOnFoil"
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
