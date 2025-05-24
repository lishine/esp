<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useSessionDataStore, type EscValues, type DsValues, type LogEntry } from '../stores/sessionData'
import SensorChart from '../components/SensorChart.vue'
import SeriesToggle from '../components/SeriesToggle.vue' // Import the new component
import type { EChartsCoreOption as ECOption } from 'echarts/core' // Changed EChartsOption to EChartsCoreOption
import { NSpin, NAlert, NCard, NSpace, NGrid, NGi } from 'naive-ui' // Added NGrid and NGi for layout
import { formatInTimeZone } from 'date-fns-tz' // Import formatInTimeZone

const sessionDataStore = useSessionDataStore()

const isLoading = computed(() => sessionDataStore.isLoading)
const error = computed(() => sessionDataStore.error)
const sessionMetadata = computed(() => sessionDataStore.sessionMetadata)
const logEntries = computed(() => sessionDataStore.logEntries)
const chartFormattedData = computed(() => sessionDataStore.getChartFormattedData)
const visibleSeriesSet = computed(() => sessionDataStore.visibleSeries)

const chartOptions = computed((): ECOption | null => {
	if (
		!chartFormattedData.value ||
		!chartFormattedData.value.series ||
		chartFormattedData.value.series.length === 0 ||
		logEntries.value.length === 0
	) {
		return null
	}

	const baseChartOptions = {
		// Renamed from optionsToReturn to baseChartOptions
		title: {
			text: '',
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
							return formatInTimeZone(date, 'Asia/Jerusalem', 'yyyy-MM-dd HH:mm:ss zzz')
						}
						return typeof params.value === 'number' ? params.value.toFixed(2) : params.value
					},
				},
			},
		},
		legend: {
			// data will be dynamically set based on visible series
			orient: 'horizontal' as const, // Add 'as const' for stricter typing if needed by ECOption
			bottom: 10,
			type: 'scroll' as const, // Add 'as const'
			data: [] as string[], // Initialize with data property
		},
		grid: {
			left: '8%',
			right: '12%',
			bottom: '20%',
			containLabel: true,
		},
		xAxis: {
			type: 'time',
			useUTC: true,
			axisLabel: {
				show: true,
				formatter: (value: number) => {
					const date = new Date(value)
					if (isNaN(date.getTime())) {
						console.error('AxisLabel formatter - Invalid Date from value:', value)
						return 'Invalid Date'
					}
					return formatInTimeZone(date, 'Asia/Jerusalem', 'HH:mm:ss')
				},
			},
			axisLine: { show: true },
			splitLine: { show: true, lineStyle: { type: 'dashed' } },
		},
		yAxis: [] as any[], // Will be populated based on visible series and their axes
		series: [] as any[], // Will be populated based on visible series
		dataZoom: [
			{
				type: 'slider',
				xAxisIndex: [0],
				start: 0,
				end: 100,
				bottom: 50,
				labelFormatter: (value: number) => {
					const date = new Date(value)
					if (isNaN(date.getTime())) {
						console.error('DataZoom formatter - Invalid Date from value:', value)
						return 'Invalid Date'
					}
					return formatInTimeZone(date, 'Asia/Jerusalem', 'yyyy-MM-dd HH:mm:ss')
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

	// Filter series based on visibility
	const currentVisibleSeries = chartFormattedData.value.series.filter((s) => visibleSeriesSet.value.has(s.name))

	if (currentVisibleSeries.length === 0) {
		// If no series are visible, perhaps return a minimal chart or a message
		// For now, returning null will show the placeholder in SensorChart
		// Or, return baseChartOptions with empty series and legend
		return {
			...baseChartOptions,
			legend: { ...baseChartOptions.legend, data: [] }, // Empty legend
			series: [], // Empty series
			yAxis: [], // No yAxes if no series
		}
	}
	// Assign to the already existing data property
	baseChartOptions.legend.data = currentVisibleSeries.map((s: any) => s.name)

	// Calculate dynamic max values
	let maxObservedCurrent = 0
	let maxObservedTemp = 0

	logEntries.value.forEach((entry: LogEntry) => {
		if (entry.n === 'esc') {
			const escVal = entry.v as EscValues
			if (typeof escVal.i === 'number') {
				maxObservedCurrent = Math.max(maxObservedCurrent, escVal.i)
			}
			if (typeof escVal.t === 'number') {
				maxObservedTemp = Math.max(maxObservedTemp, escVal.t)
			}
		} else if (entry.n === 'mc') {
			const motorCurrentVal = entry.v as number
			if (typeof motorCurrentVal === 'number') {
				maxObservedCurrent = Math.max(maxObservedCurrent, motorCurrentVal)
			}
		} else if (entry.n === 'ds') {
			const dsVal = entry.v as DsValues
			for (const key in dsVal) {
				if (typeof dsVal[key] === 'number') {
					maxObservedTemp = Math.max(maxObservedTemp, dsVal[key])
				}
			}
		}
	})

	const finalMaxCurrent = maxObservedCurrent > 0 ? Math.ceil((maxObservedCurrent * 1.1) / 10) * 10 : 100
	const finalMaxTemp = maxObservedTemp > 0 ? Math.ceil((maxObservedTemp * 1.1) / 10) * 10 : 120
	const minTemp = 0 // Or 10 if preferred

	const yAxesConfig = [
		// Visible Axes
		{
			id: 'yCurrent',
			name: 'I',
			position: 'right',
			min: 0,
			max: finalMaxCurrent,
			seriesNames: ['ESC I', 'Motor Current'],
			axisLabel: { show: true, inside: true, align: 'right' },
			nameTextStyle: { padding: [0, 0, 0, -35] },
			show: true,
		},
		{
			id: 'yTemperature',
			name: 'T',
			position: 'right',
			min: minTemp,
			max: finalMaxTemp,
			seriesNames: ['ESC T'],
			seriesNamePrefix: 'DS Temp',
			axisLabel: { show: true },
			nameTextStyle: { padding: [0, -35, 0, 0] },
			show: true,
		},
		// Hidden Axes for other series
		{
			id: 'yThrottle',
			seriesNames: ['Throttle'],
			min: 990, // Original fixed min
			max: 4500, // Original fixed max
			show: false, // This axis will not be displayed
		},
		{
			id: 'yEscVoltage',
			seriesNames: ['ESC V'], // Note: sessionData produces 'ESC V'
			min: 0,
			max: 50.5,
			show: false,
		},
		{
			id: 'yEscRpm',
			seriesNames: ['ESC RPM'],
			min: 0,
			max: 9000,
			show: false,
		},
		{
			id: 'yGpsSpeed',
			name: 'GPS',
			position: 'left',
			seriesNames: ['GPS Speed'],
			min: 0,
			max: 20,
			show: true,
			axisLabel: { show: true },
			nameTextStyle: { padding: [0, 0, 0, -35] },
		},
		// Add a fallback hidden axis for any series not explicitly matched
		{ id: 'yOther', show: false },
	]

	const optionsToReturn = {
		title: {
			text: '',
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
							// Format date to Asia/Jerusalem time using date-fns-tz
							return formatInTimeZone(date, 'Asia/Jerusalem', 'yyyy-MM-dd HH:mm:ss zzz')
						}
						return typeof params.value === 'number' ? params.value.toFixed(2) : params.value
					},
				},
			},
		},
		// legend: { // This whole block is now part of baseChartOptions and dynamically set
		// 	data: chartFormattedData.value.series.map((s: any) => s.name),
		// 	orient: 'horizontal',
		// 	bottom: 10, // Legend's bottom edge 10px from container bottom
		// 	type: 'scroll',
		// },
		// The legend is now part of baseChartOptions and its 'data' property is updated based on currentVisibleSeries
		legend: baseChartOptions.legend,
		grid: {
			left: '8%', // Increased to make space for the new GPS Y-axis on the left
			right: '12%', // Increased to make space for both Y-axes on the right side
			bottom: '20%', // Adjusted to accommodate dataZoom and legend below it
			containLabel: true,
		},
		xAxis: {
			type: 'time', // X-axis type set to time
			useUTC: true, // ECharts should still treat input data as UTC
			axisLabel: {
				show: true, // Show x-axis tick labels
				formatter: (value: number) => {
					const date = new Date(value) // This is a UTC date from ECharts
					if (isNaN(date.getTime())) {
						console.error('AxisLabel formatter - Invalid Date from value:', value)
						return 'Invalid Date'
					}
					// Format date to Asia/Jerusalem time using date-fns-tz
					return formatInTimeZone(date, 'Asia/Jerusalem', 'HH:mm:ss')
				},
			},
			axisLine: { show: true }, // Ensure x-axis line is visible
			splitLine: { show: true, lineStyle: { type: 'dashed' } }, // Vertical grid lines
		},
		yAxis: yAxesConfig.map((config) => ({
			id: config.id,
			type: 'value',
			name: config.name || '',
			min: config.min,
			max: config.max,
			position: config.position,
			show: config.show !== undefined ? config.show : true, // Default to true if not specified
			axisLabel:
				config.axisLabel !== undefined
					? config.axisLabel
					: { show: config.show !== undefined ? config.show : true },
			splitLine: { show: config.show !== undefined ? config.show : true, lineStyle: { type: 'dashed' } }, // Show for visible axes
			axisLine: { show: config.show !== undefined ? config.show : true, onZero: false },
			nameTextStyle: config.nameTextStyle || {},
		})),
		series: currentVisibleSeries.map((s: any) => {
			const seriesName = s.name as string
			let yAxisIndex = yAxesConfig.length - 1 // Default to the last 'yOther' hidden axis

			const colorMap: Record<string, string> = {
				'ESC I': 'blue',
				'Motor Current': 'magenta', // Keeping magenta as it was changed
				'ESC T': '#E53935', // Material Design Red 600 for motor temp
				'ESC V': 'grey',
			}
			// More distinguishable shades of red for DS temps
			const dsTempColors = ['#D32F2F', '#C62828', '#B71C1C', '#F44336', '#EF5350', '#E57373']

			let itemStyle = {}
			if (colorMap[seriesName]) {
				itemStyle = { color: colorMap[seriesName] }
			} else if (seriesName.startsWith('DS Temp')) {
				// Cycle through dsTempColors for different DS Temp series
				const colorIndex = currentVisibleSeries // Use currentVisibleSeries for consistent coloring
					.filter((dsSeries: any) => dsSeries.name.startsWith('DS Temp'))
					.indexOf(s)
				itemStyle = { color: dsTempColors[colorIndex % dsTempColors.length] }
			}

			const axisConfigIndex = yAxesConfig.findIndex(
				(axCfg) =>
					(axCfg.seriesNames && axCfg.seriesNames.includes(seriesName)) ||
					(axCfg.seriesNamePrefix && seriesName.startsWith(axCfg.seriesNamePrefix))
			)

			if (axisConfigIndex !== -1) {
				yAxisIndex = axisConfigIndex
			} else {
				console.warn(
					`Series "${seriesName}" did not match any yAxesConfig. Defaulting to hidden yOther axis (index ${yAxisIndex}).`
				)
			}

			return {
				...s,
				yAxisIndex: yAxisIndex,
				showSymbol: false, // Ensure symbols are off for line series
				smooth: false,
				type: 'line',
				connectNulls: true,
				itemStyle: itemStyle, // Add this line
			}
		}),
		dataZoom: [
			{
				type: 'slider',
				xAxisIndex: [0],
				start: 0,
				end: 100,
				bottom: 50, // Position slider 50px from the bottom, above the legend
				labelFormatter: (value: number) => {
					const date = new Date(value) // This is a UTC date from ECharts
					if (isNaN(date.getTime())) {
						console.error('DataZoom formatter - Invalid Date from value:', value)
						return 'Invalid Date'
					}
					// Format date to Asia/Jerusalem time using date-fns-tz
					return formatInTimeZone(date, 'Asia/Jerusalem', 'yyyy-MM-dd HH:mm:ss')
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
	// Dynamically configure yAxes based on VISIBLE series
	const visibleYAxisIds = new Set<string>()
	currentVisibleSeries.forEach((s) => {
		const seriesName = s.name as string
		const axisConfig = yAxesConfig.find(
			(axCfg) =>
				(axCfg.seriesNames && axCfg.seriesNames.includes(seriesName)) ||
				(axCfg.seriesNamePrefix && seriesName.startsWith(axCfg.seriesNamePrefix))
		)
		if (axisConfig) {
			visibleYAxisIds.add(axisConfig.id)
		} else {
			visibleYAxisIds.add('yOther') // Default to yOther if no specific axis found
		}
	})

	baseChartOptions.yAxis = yAxesConfig
		.filter((axCfg) => visibleYAxisIds.has(axCfg.id) || axCfg.id === 'yOther') // Include 'yOther' only if used
		.map((config) => ({
			id: config.id,
			type: 'value',
			name: config.name || '',
			min: config.min,
			max: config.max,
			position: config.position,
			// Show axis only if it's configured to be shown AND it's associated with a visible series
			// OR if it's the 'yOther' axis and it's being used by a visible series.
			show:
				config.id === 'yOther'
					? visibleYAxisIds.has('yOther')
					: (config.show !== undefined ? config.show : false) && visibleYAxisIds.has(config.id),
			axisLabel:
				config.axisLabel !== undefined
					? config.axisLabel
					: { show: (config.show !== undefined ? config.show : false) && visibleYAxisIds.has(config.id) },
			splitLine: {
				show: (config.show !== undefined ? config.show : false) && visibleYAxisIds.has(config.id),
				lineStyle: { type: 'dashed' },
			},
			axisLine: {
				show: (config.show !== undefined ? config.show : false) && visibleYAxisIds.has(config.id),
				onZero: false,
			},
			nameTextStyle: config.nameTextStyle || {},
		}))

	// console.log('Chart xAxis config:', JSON.parse(JSON.stringify(optionsToReturn.xAxis)))
	// console.log('Final options being returned:', JSON.stringify(optionsToReturn, null, 2))
	return optionsToReturn
})

onMounted(() => {
	sessionDataStore.loadVisibilityPreferences() // Load preferences when component mounts
})
</script>

<template>
	<n-space vertical style="padding: 20px">
		<n-space v-if="isLoading" align="center" justify="center" style="margin-top: 20px">
			<n-spin size="large" />
			<p>Loading session data...</p>
		</n-space>

		<n-alert v-if="error && !isLoading" title="Error Loading Data" type="error" closable>
			{{ error }}
		</n-alert>

		<div v-if="!isLoading && !error">
			<p v-if="!sessionMetadata && logEntries.length === 0">No data available yet. Click 'Fetch/Refresh Data'.</p>

			<n-grid :x-gap="12" :y-gap="8" :cols="'1 s:1 m:4 l:4 xl:4'">
				<n-gi :span="'1 s:1 m:3 l:3 xl:3'">
					<n-card style="margin-top: 16px">
						<div v-if="!isLoading && !error && chartFormattedData && chartFormattedData.series.length > 0">
							<sensor-chart :options="chartOptions" height="600px" />
							<!-- Increased height -->
						</div>
						<div v-else-if="!isLoading && !error">
							<p>No chart data available or data is still processing.</p>
						</div>
					</n-card>
				</n-gi>
				<n-gi :span="'1 s:1 m:1 l:1 xl:1'">
					<SeriesToggle />
					<!-- Add the toggle component here -->
				</n-gi>
			</n-grid>

			<n-card v-if="sessionMetadata" title="Session Info" style="margin-top: 16px">
				<n-space>
					<span>Device: {{ sessionMetadata.device_description || 'N/A' }}</span>
					<span>Fan: {{ sessionMetadata.fan_enabled ? 'Enabled' : 'Disabled' }}</span>
				</n-space>
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
