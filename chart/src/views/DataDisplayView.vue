<script setup lang="ts">
import { onMounted, computed, ref, watch } from 'vue' // Added watch
import { useRoute, useRouter } from 'vue-router' // Added vue-router imports
import {
	useSessionDataStore,
	type EscValues,
	type DsValues,
	type LogEntry,
	type ChartSeriesData,
	CANONICAL_SERIES_CONFIG, // Import the centralized config
} from '../stores/sessionData'
import SensorChart from '../components/SensorChart.vue'
import SeriesToggle from '../components/SeriesToggle.vue' // Import the new component
import type { EChartsCoreOption as ECOption } from 'echarts/core' // Changed EChartsOption to EChartsCoreOption
import { NSpin, NAlert, NCard, NSpace, NGrid, NGi, NButton, NUpload, type UploadFileInfo } from 'naive-ui' // Added NUpload and UploadFileInfo type
import { formatInTimeZone } from 'date-fns-tz' // Import formatInTimeZone

const sessionDataStore = useSessionDataStore()
const route = useRoute()
const router = useRouter()

const isLoading = computed(() => sessionDataStore.isLoading)
const error = computed(() => sessionDataStore.error)
const sessionMetadata = computed(() => sessionDataStore.sessionMetadata)
const logEntries = computed(() => sessionDataStore.logEntries)
const chartFormattedData = computed(() => sessionDataStore.getChartFormattedData)
const visibleSeriesSet = computed(() => sessionDataStore.visibleSeries)

// Define a type for the ECharts params object for clarity, used in tooltip.formatter
type EChartTooltipParam = {
	seriesName: string
	value: [number | string | Date, number | null] | number | null // value can be [timestamp, actualValue] or just actualValue
	marker?: string
	color?: string
	axisValue?: number | string | Date // Added axisValue for the firstPoint
	// Add other properties if needed, like componentType, seriesType, dataIndex
}

const screenWidth = ref(window.innerWidth)
const isMobile = computed(() => screenWidth.value < 1024)
const chartsHeight = computed(() => (isMobile.value ? '460px' : '600px')) // Adjust height based on screen size

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
					padding: [3, 10, 3, 10], // Increased horizontal padding
					formatter: (params: {
						axisDimension?: string
						axisIndex?: number
						value: number | string | Date
					}) => {
						if (params.axisDimension === 'x' && params.value !== undefined) {
							const date = new Date(params.value as number)
							if (!isNaN(date.getTime())) {
								return formatInTimeZone(date, 'Asia/Jerusalem', 'HH:mm:ss') // Changed format
							}
							return 'Invalid Date'
						}
						if (
							params.axisDimension === 'y' &&
							params.axisIndex !== undefined &&
							params.value !== undefined
						) {
							// yAxesConfig and visibleYAxisIds are defined later in the chartOptions computed property.
							// This formatter will be part of the options object that ECharts uses.
							// We rely on the yAxesConfig structure and the dynamically built visibleYAxisIds.
							const yAxisDefinition = yAxesConfig[params.axisIndex] // yAxesConfig is in the outer scope
							if (yAxisDefinition && visibleYAxisIds.has(yAxisDefinition.id) && yAxisDefinition.show) {
								return typeof params.value === 'number' ? params.value.toFixed(1) : String(params.value)
							}
						}
						return '' // Default to empty
					},
				},
			},
			formatter: (params: EChartTooltipParam[]) => {
				// This is the main tooltip formatter
				// This is the main tooltip formatter
				// Typed params as EChartTooltipParam[]
				if (!Array.isArray(params) || params.length === 0) {
					return '' // No data to display
				}

				// 1. Format the timestamp (first line of tooltip)
				const firstPoint = params[0]
				let tooltipHtml = ''
				if (firstPoint.axisValue !== undefined) {
					const xAxisDate = new Date(firstPoint.axisValue)
					if (!isNaN(xAxisDate.getTime())) {
						// Display only HH:MM:SS, centered
						tooltipHtml += `<div style="margin-bottom: -15px;text-align: center;">${formatInTimeZone(xAxisDate, 'Asia/Jerusalem', 'HH:mm:ss')}</div><br/>`
					} else {
						tooltipHtml += '<div style="text-align: center;">Invalid Date</div><br/>'
					}
				} else {
					tooltipHtml += '<div style="text-align: center;">Time N/A</div><br/>'
				}

				// 2. Derive tooltipSeriesConfig from CANONICAL_SERIES_CONFIG
				// This ensures the tooltip uses the exact same names and order.
				const tooltipSeriesConfig = CANONICAL_SERIES_CONFIG.map((csc) => ({
					displayName: csc.displayName,
					originalName: csc.displayName, // seriesName from ECharts params will be this displayName
					unit: csc.unit,
					decimals: csc.decimals,
				}))

				// 3. Create a map of params for easy lookup by seriesName
				const paramsMap = new Map<string, EChartTooltipParam>()
				params.forEach((p: EChartTooltipParam) => {
					// No need for 'as EChartTooltipParam[]' here as params is already typed
					paramsMap.set(p.seriesName, p)
				})

				// 4. Build tooltip content based on the defined order and names
				tooltipSeriesConfig.forEach((config) => {
					const seriesData = paramsMap.get(config.originalName)
					if (seriesData) {
						// Extract the actual numeric value. For line charts, seriesData.value is typically [timestamp, value].
						const numericValue = Array.isArray(seriesData.value) ? seriesData.value[1] : seriesData.value

						let displayValue: string
						let unitToShow = config.unit || ''

						if (numericValue !== null && typeof numericValue === 'number' && !isNaN(numericValue)) {
							displayValue = numericValue.toFixed(config.decimals)
						} else {
							// For any series, if data is not a valid number, display '-' and no unit.
							displayValue = '-'
							unitToShow = ''
						}

						tooltipHtml += `<div style="display: flex; justify-content: space-between; width: 100%;"><span>${seriesData.marker || ''}${config.displayName}:</span><span style="font-weight: bold; margin-left: 10px;">${displayValue}${unitToShow ? ' ' + unitToShow : ''}</span></div>`
					} else {
						// If seriesData is not found in paramsMap (e.g. it's hidden or no data for this exact timestamp)
						// Display series name and '-' as its value, no unit.
						tooltipHtml += `<div style="display: flex; justify-content: space-between; width: 100%;"><span>${config.displayName}:</span><span style="font-weight: bold; margin-left: 10px;">-</span></div>`
					}
				})

				return tooltipHtml
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
		yAxis: [] as ECOption['yAxis'], // Use ECharts' YAXisOption array type
		series: [] as ECOption['series'], // Use ECharts' SeriesOption array type
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
		// toolbox: { // Removed toolbox
		// 	feature: {
		// 		saveAsImage: {},
		// 		dataZoom: {
		// 			yAxisIndex: 'none',
		// 		},
		// 		restore: {},
		// 		dataView: { readOnly: false },
		// 	},
		// },
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
	baseChartOptions.legend.data = currentVisibleSeries.map((s: ChartSeriesData) => s.name)

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

	// const finalMaxCurrent = maxObservedCurrent > 0 ? Math.ceil((maxObservedCurrent * 1.1) / 10) * 10 : 100
	// const finalMaxTemp = maxObservedTemp > 0 ? Math.ceil((maxObservedTemp * 1.1) / 10) * 10 : 120
	const finalMaxCurrent = 100
	const finalMaxTemp = 100
	const minTemp = 0 // Or 10 if preferred

	const yAxesConfig = [
		// Visible Axes
		{
			id: 'yCurrent',
			name: 'I',
			position: 'right',
			min: 0,
			max: finalMaxCurrent,
			seriesNames: ['Bat current', 'Motor current'], // Updated series names
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
			seriesNames: ['TEsc', 'TAmbient', 'TAlum', 'TMosfet'], // Updated series names, removed seriesNamePrefix
			axisLabel: { show: true },
			nameTextStyle: { padding: [0, -35, 0, 0] },
			show: true,
		},
		// Hidden Axes for other series
		{
			id: 'yThrottle',
			seriesNames: ['Throttle'], // No change
			min: 990, // Original fixed min
			max: 4500, // Original fixed max
			show: false, // This axis will not be displayed
		},
		{
			id: 'yEscVoltage',
			seriesNames: ['V'], // Updated series name
			min: 0,
			max: 50.5,
			show: false,
		},
		{
			id: 'yEscRpm',
			seriesNames: ['RPM'], // Updated series name
			min: 0,
			max: 9000,
			show: false,
		},
		{
			id: 'yGpsSpeed',
			name: 'GPS',
			position: 'left',
			seriesNames: ['Speed'], // Updated series name
			min: 0,
			max: 35,
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
		tooltip: baseChartOptions.tooltip, // USE THE CORRECT TOOLTIP CONFIG WITH CUSTOM FORMATTER
		// legend: { // This whole block is now part of baseChartOptions and dynamically set
		// 	data: chartFormattedData.value.series.map((s: any) => s.name),
		// 	orient: 'horizontal',
		// 	bottom: 10, // Legend's bottom edge 10px from container bottom
		// 	type: 'scroll',
		// },
		// The legend is now part of baseChartOptions and its 'data' property is updated based on currentVisibleSeries
		legend: baseChartOptions.legend,
		grid: {
			left: '0.5%', // Adjusted for maximizing chart area
			right: '0.5%', // Adjusted for maximizing chart area
			bottom: '18%', // Adjusted for maximizing chart area
			top: '2%', // Adjusted for maximizing chart area
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
		series: currentVisibleSeries.map((s: ChartSeriesData) => {
			const seriesName = s.name
			let yAxisIndex = yAxesConfig.length - 1 // Default to the last 'yOther' hidden axis

			const colorMap: Record<string, string> = {
				'Bat current': '#0000b3', // Updated key
				'Motor current': '#8080ff', // Updated key (case)
				TEsc: ' #ff0000', // Updated key
				V: 'grey', // Updated key
				Speed: '#ccff66',
				RPM: 'darkorange',
				Throttle: 'green', // Updated key
				// RPM, Speed, Throttle will get default colors or can be added
			}
			// More distinguishable shades of red for DS temps
			const dsTempColors = ['#ff9933', '#ffcccc', '#660000', '#F44336', '#EF5350', '#E57373']

			let itemStyle = {}
			if (colorMap[seriesName]) {
				itemStyle = { color: colorMap[seriesName] }
			} else if (seriesName === 'TAmbient' || seriesName === 'TAlum' || seriesName === 'TMosfet') {
				// Cycle through dsTempColors for different DS Temp series
				const dsTempSeriesInOrder = currentVisibleSeries.filter(
					(cs) => cs.name === 'TAmbient' || cs.name === 'TAlum' || cs.name === 'TMosfet'
				)
				const colorIndex = dsTempSeriesInOrder.indexOf(s)
				itemStyle = { color: dsTempColors[colorIndex % dsTempColors.length] }
			}

			const axisConfigIndex = yAxesConfig.findIndex(
				(axCfg) => axCfg.seriesNames && axCfg.seriesNames.includes(seriesName)
				// Removed seriesNamePrefix check as it's no longer used in yAxesConfig for temperature
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
					return formatInTimeZone(date, 'Asia/Jerusalem', 'HH:mm:ss') // Changed format
				},
			},
			{
				type: 'inside',
				xAxisIndex: [0],
				start: 0,
				end: 100,
			},
		],
		// toolbox: { // Removed toolbox
		// 	feature: {
		// 		saveAsImage: {},
		// 		dataZoom: {
		// 			yAxisIndex: 'none',
		// 		},
		// 		restore: {},
		// 		dataView: { readOnly: false },
		// 	},
		// },
	}
	// Dynamically configure yAxes based on VISIBLE series
	const visibleYAxisIds = new Set<string>()
	currentVisibleSeries.forEach((s) => {
		const seriesName = s.name as string
		const axisConfig = yAxesConfig.find(
			(axCfg) => axCfg.seriesNames && axCfg.seriesNames.includes(seriesName)
			// Removed seriesNamePrefix check
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
	sessionDataStore.loadVisibilityPreferences()
	// Initial fetch based on current query params
	// const initialPrev = Number(route.query.prev) || 0
	// sessionDataStore.fetchSessionData(initialPrev > 0 ? initialPrev : undefined)
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

const isNextDisabled = computed(() => {
	return currentPrev.value <= 0
})

const handlePreviousClick = () => {
	const newPrev = currentPrev.value + 1
	router.push({ query: { ...route.query, prev: newPrev.toString() } })
}

const handleNextClick = () => {
	if (currentPrev.value <= 0) return // Should be disabled, but as a safeguard
	const newPrev = currentPrev.value - 1
	if (newPrev <= 0) {
		// Create a new query object without 'prev'
		const newQuery = { ...route.query }
		delete newQuery.prev
		router.push({ query: newQuery })
	} else {
		router.push({ query: { ...route.query, prev: newPrev.toString() } })
	}
}

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
</script>

<template>
	<n-space vertical class="data-display-container" style="padding: 0px; padding-top: 0px">
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
					<n-card style="margin-top: 0px">
						<div v-if="!isLoading && !error && chartFormattedData && chartFormattedData.series.length > 0">
							<sensor-chart :options="chartOptions" :height="chartsHeight" />
						</div>
						<div v-else-if="!isLoading && !error">
							<p>No chart data available or data is still processing.</p>
						</div>
					</n-card>
				</n-gi>
				<n-gi :span="'1 s:1 m:1 l:1 xl:1'">
					<SeriesToggle />
				</n-gi>
			</n-grid>

			<!-- Navigation Buttons Row -->
			<div style="display: flex; justify-content: space-between; margin-top: 16px; margin-bottom: 16px">
				<n-button @click="handlePreviousClick" type="default"> &lt; Previous </n-button>
				<n-button @click="handleNextClick" type="default" :disabled="isNextDisabled"> Next &gt; </n-button>
			</div>

			<n-card v-if="sessionMetadata" title="Session Info" style="margin-top: 16px">
				<n-space vertical>
					<span>Device: {{ sessionMetadata.device_description || 'N/A' }}</span>
					<span>Date: {{ sessionMetadata.date || 'N/A' }}</span>
					<span>Restart Count: {{ sessionMetadata.restart || 'N/A' }}</span>
					<span>Fan: {{ sessionMetadata.fan_enabled ? 'Enabled' : 'Disabled' }}</span>
				</n-space>
			</n-card>
			<n-space vertical style="width: 100%; margin-top: 16px; margin-bottom: 16px">
				<n-button @click="handleRefreshData" type="primary" block>
					Fetch/Refresh Data (Current: {{ currentPrev === 0 ? 'Live' : `Prev ${currentPrev}` }})
				</n-button>
				<n-upload accept=".jsonl" :max="1" :show-file-list="false" @change="handleFileChange">
					<n-button block>Upload JSONL File</n-button>
				</n-upload>
			</n-space>
		</div>
	</n-space>
</template>

<style scoped>
/* Scoped styles for DataDisplayView */
/* Scoped styles for DataDisplayView */

/* Apply height adjustments only on screens smaller than 768px (typical tablet/desktop breakpoint) */
@media (max-width: 767px) {
	.data-display-container {
		min-height: 100vh; /* Make container at least viewport height */
		display: flex;
		flex-direction: column;
	}

	.n-grid {
		flex-grow: 1; /* Allow grid to take available space */
		height: 100%; /* Ensure grid fills parent height */
	}

	.n-gi {
		height: 100%; /* Ensure grid item fills parent height */
		display: flex; /* Use flex to make card fill gi */
		flex-direction: column;
	}

	.n-card {
		flex-grow: 1; /* Allow card to take available space */
		height: 100%; /* Ensure card fills parent height */
		display: flex; /* Use flex to make content fill card */
		flex-direction: column;
	}

	/* Target the div containing the sensor-chart */
	.n-card > div {
		flex-grow: 1; /* Allow the div containing the chart to take space */
		height: 100%; /* Ensure it fills card height */
	}
}

p {
	margin-left: 8px;
}
</style>
