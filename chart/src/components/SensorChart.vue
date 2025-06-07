<script setup lang="ts">
import { computed, ref, defineExpose } from 'vue' // Added ref, defineExpose
import { useSessionDataStore } from '../stores'
import VChart from 'vue-echarts'
import { type EChartsCoreOption as ECOption, use, type EChartsType } from 'echarts/core' // Changed EChartsOption to EChartsCoreOption, re-added EChartsType
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts' // Common chart types
import {
	TitleComponent,
	TooltipComponent,
	LegendComponent,
	GridComponent,
	DataZoomComponent, // For zooming and scrolling
	ToolboxComponent, // For utility box (save image, data view, etc.)
	MarkLineComponent, // For auxiliary marking lines
	MarkPointComponent, // For auxiliary marking points
	// Consider adding others if commonly used, e.g., VisualMapComponent
} from 'echarts/components'
import type { DataZoomComponentOption } from 'echarts/components' // For typing dataZoom options

// Register the ECharts components and renderers
use([
	CanvasRenderer,
	LineChart,
	BarChart,
	TitleComponent,
	TooltipComponent,
	LegendComponent,
	GridComponent,
	DataZoomComponent,
	ToolboxComponent,
	MarkLineComponent,
	MarkPointComponent,
])

const sessionDataStore = useSessionDataStore()
const chartRef = ref<InstanceType<typeof VChart> | null>(null) // Use InstanceType

// Define component props
const props = withDefaults(
	defineProps<{
		options?: ECOption | null // Allow null to handle cases where options are not ready
		height?: string
		width?: string
		theme?: string // e.g., 'light', 'dark', or a registered theme name
	}>(),
	{
		height: '400px',
		width: '100%',
		options: null, // Default options to null
		theme: 'light',
	}
)

const chartStyle = computed(() => ({
	height: props.height,
	width: props.width,
}))

const handleLegendSelectChanged = (params: { name: string; selected: Record<string, boolean> }) => {
	// params.name is the series that was clicked
	// params.selected is an object with the new selected status for ALL series

	// Update the store for persistence and to keep other parts of the app in sync.
	// The main chartOptions computed property will react to this store change,
	// and should re-render the chart with the correct legend selection and dataZoom state.
	for (const seriesName in params.selected) {
		sessionDataStore.setSeriesVisibility(seriesName, params.selected[seriesName])
	}
}

interface DataZoomEventBatchItem {
	dataZoomId?: string
	start?: number // Percentage
	end?: number // Percentage
	startValue?: number // Data value (can be timestamp for time axis)
	endValue?: number // Data value
}

interface DataZoomEventParams {
	type: 'datazoom'
	// For direct event from a specific dataZoom component (e.g., slider interaction)
	dataZoomId?: string
	start?: number // Percentage for direct event
	end?: number // Percentage for direct event
	// For batch events (e.g., linked dataZoom components, or toolbox zoom)
	batch?: DataZoomEventBatchItem[]
}
// Debounce utility
let debounceTimer: number
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const debounce = <T extends (...args: any[]) => void>(func: T, delay: number) => {
	return (...args: Parameters<T>) => {
		clearTimeout(debounceTimer)
		debounceTimer = window.setTimeout(() => {
			func(...args)
		}, delay)
	}
}

const debouncedSetDataZoomState = debounce((start: number, end: number) => {
	sessionDataStore.setDataZoomState({ start, end })
}, 300)

const handleDataZoom = (params: DataZoomEventParams) => {
	let newStartPercent: number | undefined = undefined
	let newEndPercent: number | undefined = undefined

	const currentOption = chartRef.value?.getOption() as ECOption | undefined // Cast for easier access
	let sliderDataZoomConfig: DataZoomComponentOption | undefined = undefined

	if (currentOption?.dataZoom) {
		const dataZooms = Array.isArray(currentOption.dataZoom) ? currentOption.dataZoom : [currentOption.dataZoom]
		sliderDataZoomConfig = dataZooms.find((dz) => dz && dz.type === 'slider') as DataZoomComponentOption | undefined
	}

	if (params.batch) {
		const relevantBatchEntry = sliderDataZoomConfig?.id
			? params.batch.find((b) => b.dataZoomId === sliderDataZoomConfig!.id)
			: params.batch.find((b) => typeof b.start === 'number' && typeof b.end === 'number') // Fallback

		if (
			relevantBatchEntry &&
			typeof relevantBatchEntry.start === 'number' &&
			typeof relevantBatchEntry.end === 'number'
		) {
			newStartPercent = relevantBatchEntry.start
			newEndPercent = relevantBatchEntry.end
		}
	} else if (params.dataZoomId === sliderDataZoomConfig?.id || (!params.dataZoomId && sliderDataZoomConfig)) {
		// If it's a direct event from our main slider, or if no ID specified assume it's for the main one
		if (typeof params.start === 'number' && typeof params.end === 'number') {
			newStartPercent = params.start
			newEndPercent = params.end
		}
	}

	if (typeof newStartPercent === 'number' && typeof newEndPercent === 'number') {
		// Check if the values actually changed to prevent redundant updates before debouncing
		if (newStartPercent !== sessionDataStore.dataZoomStart || newEndPercent !== sessionDataStore.dataZoomEnd) {
			debouncedSetDataZoomState(newStartPercent, newEndPercent)
		}
	}
}

const getEchartsInstance = (): EChartsType | undefined => {
	// Assuming VChart instance has a .chart property which is the EChartsType instance
	// This makes it consistent with GroupAveragesChart.vue
	return chartRef.value?.chart
}

defineExpose({
	getEchartsInstance,
})
</script>
<template>
	<div :style="chartStyle">
		<v-chart
			v-if="props.options"
			ref="chartRef"
			class="chart"
			:option="props.options"
			:theme="props.theme"
			autoresize
			:style="{ height: '100%', width: '100%' }"
			@legendselectchanged="handleLegendSelectChanged"
			@datazoom="handleDataZoom"
		/>
		<div v-else class="no-options-placeholder" :style="{ height: '100%', width: '100%' }">
			<p>Chart options are being prepared or are not available.</p>
		</div>
	</div>
</template>

<style scoped>
.no-options-placeholder {
	display: flex;
	align-items: center;
	justify-content: center;
	border: 1px dashed #ccc; /* Optional: visual cue for placeholder */
	color: #888;
	height: 100%;
	width: 100%;
}
</style>
