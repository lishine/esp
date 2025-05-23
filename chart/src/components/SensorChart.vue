<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { type EChartsCoreOption as ECOption, use } from 'echarts/core' // Changed EChartsOption to EChartsCoreOption
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
</script>

<template>
	<div :style="chartStyle">
		<v-chart
			v-if="props.options"
			class="chart"
			:option="props.options"
			:theme="props.theme"
			autoresize
			:style="{ height: '100%', width: '100%' }"
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
