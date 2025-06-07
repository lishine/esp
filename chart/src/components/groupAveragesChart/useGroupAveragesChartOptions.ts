import { computed, type Ref } from 'vue'
// import type { EChartsCoreOption as ECOption } from 'echarts/core' // ECOption is no longer used
import type { EChartsOption } from 'echarts' // Import full EChartsOption
// Removed unused TooltipComponentOption
import { formatInTimeZone } from 'date-fns-tz'
import type { GroupAggregate } from '@/stores/types'
import type { GroupAverageSeriesConfig } from './seriesConfig' // Updated import path
import { buildYAxisOptionsForGroupChart, type YAxisConfig } from './axes'
import { buildSeriesOptionsForGroupChart } from './series'

export function useGroupAveragesChartOptions(
	groupAggregates: Ref<GroupAggregate[]>,
	groupAverageSeriesConfigRef: Ref<ReadonlyArray<GroupAverageSeriesConfig>>,
	groupAverageSeriesVisibility: Ref<Record<string, boolean>>,
	dataZoomStart: Ref<number>,
	dataZoomEnd: Ref<number>
) {
	const chartOptionsGroupAverages = computed((): EChartsOption | null => {
		// Changed return type
		if (!groupAggregates.value || groupAggregates.value.length === 0 || !groupAverageSeriesConfigRef.value) {
			return null
		}

		const yAxesConfig: YAxisConfig[] = groupAverageSeriesConfigRef.value.map((config) => ({
			id: config.internalId,
			name: `${config.displayName} (${config.unit})`,
			min: undefined,
			max: undefined,
			position: (config.yAxisIndex || 0) % 2 === 0 ? 'left' : 'right',
			axisLabel: {
				formatter: (value: string | number) =>
					typeof value === 'number' ? value.toFixed(config.decimals) : value,
				show: false, // Changed to false as per requirement to hide Y-axis labels
			},
			show: false, // Changed to false as per requirement to hide Y-axes
			seriesNames: [config.displayName],
			_color: config.color,
			_originalYAxisIndex: config.yAxisIndex === undefined ? 0 : config.yAxisIndex,
		}))

		const visibleYAxisOriginalIndices = new Set<number>()
		groupAverageSeriesConfigRef.value.forEach((config) => {
			if (groupAverageSeriesVisibility.value[config.displayName]) {
				visibleYAxisOriginalIndices.add(config.yAxisIndex === undefined ? 0 : config.yAxisIndex)
			}
		})

		const finalYAxes = buildYAxisOptionsForGroupChart(yAxesConfig, Array.from(visibleYAxisOriginalIndices))

		const seriesData = buildSeriesOptionsForGroupChart(
			groupAggregates.value,
			groupAverageSeriesConfigRef.value,
			groupAverageSeriesVisibility.value,
			finalYAxes
		)

		// If finalYAxes is empty (e.g., all series are hidden), return null to avoid rendering issues.
		if (!finalYAxes || (Array.isArray(finalYAxes) && finalYAxes.length === 0)) {
			return null
		}

		const optionsObject = {
			group: 'groupSync', // Added for explicit connection
			grid: {
				left: '8%',
				right: '12%',
				bottom: '15%',
				top: '10%',
				containLabel: true,
			},
			xAxis: {
				type: 'time',
				useUTC: true,
				axisLabel: {
					show: true,
					formatter: (value: number) => {
						const date = new Date(value)
						return formatInTimeZone(date, 'Asia/Jerusalem', 'HH:mm:ss')
					},
				},
				axisLine: { show: true, onZero: false }, // Explicitly set onZero: false
				splitLine: { show: true, lineStyle: { type: 'dashed' } },
			},
			yAxis: finalYAxes,
			series: seriesData,
			legend: {
				orient: 'horizontal' as const,
				top: '5px', // Position legend clearly above the chart
				left: 'center',
				data: groupAverageSeriesConfigRef.value.map((s) => s.displayName),
				selected: groupAverageSeriesVisibility.value,
			},
			tooltip: {
				trigger: 'axis',
				axisPointer: {
					type: 'cross',
				},
				formatter: (prms: EChartTooltipFormatterParams | EChartTooltipFormatterParams[]) => {
					const paramsArray = Array.isArray(prms) ? prms : [prms]
					if (paramsArray.length === 0) return ''

					const firstPoint = paramsArray[0]
					if (!firstPoint || firstPoint.axisValue == null || typeof firstPoint.axisValue !== 'number') {
						return ''
					}

					const time = formatInTimeZone(new Date(firstPoint.axisValue), 'Asia/Jerusalem', 'HH:mm:ss.SSS')
					let tooltipText = `${time}<br/>`

					paramsArray.forEach((param: EChartTooltipFormatterParams) => {
						if (param.seriesName && param.value && Array.isArray(param.value) && param.value[1] != null) {
							const config = groupAverageSeriesConfigRef.value.find(
								(c: GroupAverageSeriesConfig) => c.displayName === param.seriesName
							)
							const decimals = config ? config.decimals : 2
							tooltipText += `${param.marker} ${param.seriesName}: ${parseFloat(param.value[1] as string).toFixed(decimals)} ${config?.unit || ''}<br/>`
						}
					})
					return tooltipText
				},
			},
			dataZoom: [
				// Slider dataZoom removed as per requirement
				{
					type: 'inside',
					xAxisIndex: [0],
					start: dataZoomStart.value,
					end: dataZoomEnd.value,
				},
			],
		}
		return optionsObject as EChartsOption // Cast to full EChartsOption
	})

	// Log the final computed options
	if (chartOptionsGroupAverages.value) {
		console.log(
			'[useGroupAveragesChartOptions] Final computed chartOptionsGroupAverages:',
			JSON.stringify(chartOptionsGroupAverages.value, null, 2)
		)
	} else {
		console.log('[useGroupAveragesChartOptions] Final computed chartOptionsGroupAverages is null')
	}

	return {
		chartOptionsGroupAverages,
	}
}

interface EChartTooltipFormatterParams {
	seriesName?: string
	value?: [number, number | string | null] | number | string | null // value[1] is accessed
	marker?: string
	axisValue?: number | string
	// Not using other properties like componentType, seriesType, seriesIndex, dataIndex, data, color, name
}
