<template>
	<v-chart
		ref="chartRef"
		:option="chartOption"
		:style="{ height, width }"
		:theme="theme"
		autoresize
		@legendselectchanged="handleLegendSelectChanged"
	/>
</template>

<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import VChart, { THEME_KEY } from 'vue-echarts'
import type { EChartsOption } from 'echarts' // ECharts type removed from here
import { use, type EChartsType } from 'echarts/core' // Added EChartsType
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts' // Assuming line or bar for averages
import {
	TitleComponent,
	TooltipComponent,
	LegendComponent,
	GridComponent,
	DataZoomComponent,
	ToolboxComponent,
} from 'echarts/components'
import { useSessionDataStore } from '@/stores/sessionDataStore'

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
])

const props = defineProps<{
	options: EChartsOption | null
	height: string
	width: string
	theme: string
}>()

const chartOption = computed(() => props.options as EChartsOption | undefined)

const sessionDataStore = useSessionDataStore()
const chartRef = ref<InstanceType<typeof VChart> | null>(null) // Changed to VChart instance type

function handleLegendSelectChanged(params: { selected: Record<string, boolean> }) {
	// params.selected is an object where keys are series display names and values are their new boolean visibility status
	for (const seriesName in params.selected) {
		sessionDataStore.setGroupAverageSeriesVisibility(seriesName, params.selected[seriesName])
	}
}

// Expose ECharts instance
const getEchartsInstance = (): EChartsType | undefined => {
	// Changed return type to EChartsType
	return chartRef.value?.chart
}

defineExpose({
	getEchartsInstance,
})

// Provide theme for ECharts components
import { provide } from 'vue'
provide(THEME_KEY, toRef(props, 'theme'))
</script>
