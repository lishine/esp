<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useSessionDataStore } from '../stores/sessionData'
import SensorChart from '../components/SensorChart.vue'
import type { ECOption } from 'vue-echarts'
import { NSpin, NAlert, NCard, NButton, NSpace } from 'naive-ui'

const sessionDataStore = useSessionDataStore()

const isLoading = computed(() => sessionDataStore.isLoading)
const error = computed(() => sessionDataStore.error)
const sessionMetadata = computed(() => sessionDataStore.sessionMetadata)
const logEntries = computed(() => sessionDataStore.logEntries)
const chartFormattedData = computed(() => sessionDataStore.getChartFormattedData)

const chartOptions = computed((): ECOption | null => {
	if (!chartFormattedData.value || !chartFormattedData.value.series || chartFormattedData.value.series.length === 0) {
		return null
	}

	// const xAxisTimestamps = chartFormattedData.value.series[0]?.data.map((d: any) => d[0]) || [] // No longer needed for time axis

	const yAxesConfig = [
		{ id: 'yGpsSpeed', min: 0, max: 20, seriesNames: ['GPS Speed'] },
		{ id: 'yEscRpm', min: 0, max: 3000, seriesNames: ['ESC RPM'] },
		{ id: 'yEscMah', min: 0, max: 15000, seriesNames: ['ESC mAh'] },
		{ id: 'yEscTemp', min: 10, max: 120, seriesNames: ['ESC Temp'] },
		{ id: 'yEscCurrent', min: 0, max: 200, seriesNames: ['ESC Current'] },
		{ id: 'yEscVoltage', min: 30, max: 55, seriesNames: ['ESC Voltage'] },
		{ id: 'yDsTemps', min: 10, max: 60, seriesNamePrefix: 'DS Temp' }, // Catches DS Temp aq, DS Temp bq etc.
		{ id: 'yThrottle', min: 990, max: 1500, seriesNames: ['Throttle'] },
		{ id: 'yMotorCurrent', min: 0, max: 200, seriesNames: ['Motor Current'] },
	]

	const optionsToReturn = {
		title: {
			text: 'Sensor Data Over Time',
		},
		tooltip: {
			trigger: 'axis',
			axisPointer: {
				type: 'cross',
				label: {
					formatter: (params: any) => {
						if (params.axisDimension === 'x') {
							const date = new Date(params.value)
							if (isNaN(date.getTime())) {
								console.error('Tooltip formatter - Invalid Date from params.value:', params.value)
								return 'Invalid Date'
							}
							// Manual UTC formatting
							const year = date.getUTCFullYear()
							const month = (date.getUTCMonth() + 1).toString().padStart(2, '0')
							const day = date.getUTCDate().toString().padStart(2, '0')
							const hours = date.getUTCHours().toString().padStart(2, '0')
							const minutes = date.getUTCMinutes().toString().padStart(2, '0')
							const seconds = date.getUTCSeconds().toString().padStart(2, '0')
							const formatted = `${year}-${month}-${day} ${hours}:${minutes}:${seconds} UTC`
							// console.log('Tooltip formatter - manually formatted:', formatted); // Keep for debugging if needed
							return formatted
						}
						return typeof params.value === 'number' ? params.value.toFixed(2) : params.value
					},
				},
			},
		},
		legend: {
			data: chartFormattedData.value.series.map((s: any) => s.name),
			orient: 'horizontal',
			bottom: 10,
			type: 'scroll',
		},
		grid: {
			left: '3%',
			right: '4%',
			bottom: '15%', // Adjusted to accommodate legend
			containLabel: true,
		},
		xAxis: {
			type: 'time', // X-axis type set to time
			useUTC: true, // Add this line to display time in UTC
			axisLabel: { show: false }, // Hide x-axis tick labels
			axisLine: { show: true }, // Ensure x-axis line is visible
			splitLine: { show: true, lineStyle: { type: 'dashed' } }, // Vertical grid lines
			// boundaryGap: false, // Not typically needed for time axis, data points define boundaries
		},
		yAxis: yAxesConfig.map((config) => ({
			type: 'value',
			name: '', // Remove name or set to empty
			min: config.min,
			max: config.max,
			axisLabel: { show: false }, // Hide y-axis tick labels
			splitLine: { show: false }, // Hide horizontal grid lines from this y-axis
			axisLine: { show: true }, // Ensure y-axis line is visible
			// id: config.id // Optional: if you need to reference by ID later
		})),
		series: chartFormattedData.value.series.map((s: any) => {
			let yAxisIndex = 0 // Default to the first y-axis
			const seriesName = s.name
			for (let i = 0; i < yAxesConfig.length; i++) {
				const config = yAxesConfig[i]
				if (
					config.seriesNames?.includes(seriesName) ||
					(config.seriesNamePrefix && seriesName.startsWith(config.seriesNamePrefix))
				) {
					yAxisIndex = i
					break
				}
			}
			return {
				...s,
				yAxisIndex: yAxisIndex,
				showSymbol: false, // Ensure symbols are off for line series
				smooth: false,
				type: 'line',
				connectNulls: true, // Add this line
			}
		}),
		dataZoom: [
			{
				type: 'slider',
				xAxisIndex: [0],
				start: 0,
				end: 100,
				labelFormatter: (value: number) => {
					const date = new Date(value)
					if (isNaN(date.getTime())) {
						console.error('DataZoom formatter - Invalid Date from value:', value)
						return 'Invalid Date'
					}
					// Manual UTC formatting
					const year = date.getUTCFullYear()
					const month = (date.getUTCMonth() + 1).toString().padStart(2, '0')
					const day = date.getUTCDate().toString().padStart(2, '0')
					const hours = date.getUTCHours().toString().padStart(2, '0')
					const minutes = date.getUTCMinutes().toString().padStart(2, '0')
					const seconds = date.getUTCSeconds().toString().padStart(2, '0')
					const formatted = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
					// console.log('DataZoom formatter - manually formatted:', formatted); // Keep for debugging if needed
					return formatted // No "UTC" text for dataZoom for brevity
				},
			},
			{
				type: 'inside',
				xAxisIndex: [0],
				start: 0,
				end: 100,
			},
		],
		toolbox: {
			feature: {
				saveAsImage: {},
				dataZoom: {
					yAxisIndex: 'none',
				},
				restore: {},
				dataView: { readOnly: false },
			},
		},
	}
	console.log('Chart xAxis config:', JSON.parse(JSON.stringify(optionsToReturn.xAxis)))
	return optionsToReturn
})

onMounted(() => {
	sessionDataStore.fetchSessionData()
})
</script>

<template>
	<n-space vertical style="padding: 20px">
		<n-button :loading="isLoading" type="primary" @click="sessionDataStore.fetchSessionData()">
			Fetch/Refresh Data
		</n-button>

		<n-space v-if="isLoading" align="center" justify="center" style="margin-top: 20px">
			<n-spin size="large" />
			<p>Loading session data...</p>
		</n-space>

		<n-alert v-if="error && !isLoading" title="Error Loading Data" type="error" closable>
			{{ error }}
		</n-alert>

		<div v-if="!isLoading && !error">
			<p v-if="!sessionMetadata && logEntries.length === 0">No data available yet. Click 'Fetch/Refresh Data'.</p>

			<n-card v-if="sessionMetadata" title="Session Info" style="margin-top: 16px">
				<n-space>
					<span>Device: {{ sessionMetadata.device_description || 'N/A' }}</span>
					<span>Fan: {{ sessionMetadata.fan_enabled ? 'Enabled' : 'Disabled' }}</span>
				</n-space>
			</n-card>

			<!-- Raw Log Display Removed -->
			<!--
			<n-card v-if="logEntries.length > 0" title="Log Entries (Sample - First 10)" style="margin-top: 16px">
				<n-list hoverable bordered>
					<n-list-item v-for="(entry, index) in logEntries.slice(0, 10)" :key="index">
						<n-code :code="JSON.stringify(entry, null, 2)" language="json" word-wrap />
					</n-list-item>
				</n-list>
				<p v-if="logEntries.length > 10">... and {{ logEntries.length - 10 }} more entries.</p>
			</n-card>
			-->

			<n-card title="Sensor Charts" style="margin-top: 16px">
				<div v-if="!isLoading && !error && chartFormattedData && chartFormattedData.series.length > 0">
					<sensor-chart :options="chartOptions" height="500px" />
				</div>
				<div v-else-if="!isLoading && !error">
					<p>No chart data available or data is still processing.</p>
				</div>
			</n-card>
		</div>
	</n-space>
</template>

<style scoped>
/* Scoped styles for DataDisplayView */
p {
	margin-left: 8px;
}
</style>
