import { computed, type Ref } from 'vue'
// import type { EChartsCoreOption as ECOption } from 'echarts/core' // ECOption is no longer used
import type { EChartsOption } from 'echarts' // Import full EChartsOption
// Removed unused TooltipComponentOption
import { formatInTimeZone } from 'date-fns-tz'
import type { GroupAggregate } from '@/stores/types'
// Removed useSessionDataStore and findActiveGroupName as they are now used in common tooltip
import { createTooltipFormatter, type TooltipSeriesDisplayConfig } from '../chart/tooltip' // Import common tooltip
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

		const yAxesConfig: YAxisConfig[] = groupAverageSeriesConfigRef.value.map((config) => {
			let overallMinMetricValue: number | undefined = undefined
			let overallMaxMetricValue: number | undefined = undefined

			// Calculate global min/max for the metric associated with this y-axis config
			if (groupAggregates.value && groupAggregates.value.length > 0) {
				groupAggregates.value.forEach((group) => {
					const value = group.metrics[config.dataKey]
					if (value !== undefined && value !== null && typeof value === 'number') {
						if (overallMinMetricValue === undefined || value < overallMinMetricValue) {
							overallMinMetricValue = value
						}
						if (overallMaxMetricValue === undefined || value > overallMaxMetricValue) {
							overallMaxMetricValue = value
						}
					}
				})
			}

			let finalAxisMin: number | undefined = undefined
			let finalAxisMax: number | undefined = undefined

			if (typeof overallMinMetricValue === 'number' && typeof overallMaxMetricValue === 'number') {
				// Both overallMinMetricValue and overallMaxMetricValue are numbers here
				const range = overallMaxMetricValue - overallMinMetricValue
				// Ensure padding is non-zero if range is zero to create a small visible range
				const padding = range === 0 ? 0.5 : range * 0.05

				const calculatedMin = overallMinMetricValue - padding
				const calculatedMax = overallMaxMetricValue + padding

				// Adjust if padding made min > max or if initial values were very close.
				if (calculatedMin >= calculatedMax) {
					// Use >= to handle the case where they become equal after padding
					// If range was 0, min/max were equal. Reset to a small interval around the value.
					if (range === 0) {
						finalAxisMin = overallMinMetricValue - (padding > 0 ? padding : 0.5) // Ensure some sensible default padding
						finalAxisMax = overallMaxMetricValue + (padding > 0 ? padding : 0.5)
					} else {
						// Fallback: if padding somehow inverted or made them equal, use original values
						// This case should ideally be rare with positive padding on a non-zero range.
						finalAxisMin = overallMinMetricValue
						finalAxisMax = overallMaxMetricValue
					}
				} else {
					finalAxisMin = calculatedMin
					finalAxisMax = calculatedMax
				}
			}
			// If overallMinMetricValue or overallMaxMetricValue remained undefined (e.g., no data for this metric),
			// finalAxisMin and finalAxisMax will also be undefined, letting ECharts decide the scale.

			return {
				id: config.internalId,
				name: `${config.displayName} (${config.unit})`,
				min: finalAxisMin,
				max: finalAxisMax,
				position: (config.yAxisIndex || 0) % 2 === 0 ? 'left' : 'right',
				axisLabel: {
					formatter: (value: string | number) =>
						typeof value === 'number' ? value.toFixed(config.decimals) : value,
					show: false, // Requirement: hide Y-axis labels
				},
				show: false, // Requirement: hide Y-axes
				seriesNames: [config.displayName],
				_color: config.color,
				_originalYAxisIndex: config.yAxisIndex === undefined ? 0 : config.yAxisIndex,
			}
		})

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
			// groupAverageSeriesVisibility.value, // Removed argument
			finalYAxes
		)

		// Data now includes a segmentType. Set connectNulls to true.
		const finalSeriesData = seriesData.map((series) => ({
			...series,
			connectNulls: false, // Revert: Main series will use nulls for breaks
		}))

		// If finalYAxes is empty (e.g., all series are hidden), return null to avoid rendering issues.
		if (!finalYAxes || (Array.isArray(finalYAxes) && finalYAxes.length === 0)) {
			return null
		}

		const optionsObject: EChartsOption = {
			group: 'groupSync', // Added for explicit connection
			grid: {
				left: '8%',
				right: '12%',
				bottom: '15%',
				top: '20%', // Further increased top margin for legend
				containLabel: true,
			},
			xAxis: {
				type: 'time',
				// useUTC: true, // Removed: ECharts handles UTC by default for time axis
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
			series: finalSeriesData, // Use the modified series data
			legend: {
				orient: 'horizontal' as const,
				top: '5px', // Position legend clearly above the chart
				left: 'center',
				data: groupAverageSeriesConfigRef.value.map((s) => s.displayName),
				selected: groupAverageSeriesVisibility.value,
			},
			tooltip: createTooltipFormatter(
				groupAverageSeriesConfigRef.value.map(
					(gasc: GroupAverageSeriesConfig): TooltipSeriesDisplayConfig => ({
						seriesName: gasc.displayName, // Assuming ECharts series name matches displayName for this chart
						displayName: gasc.displayName,
						unit: gasc.unit,
						decimals: gasc.decimals,
					})
				),
				{
					// yAxesConfig: undefined, // Pass if needed
					// visibleYAxisIds: undefined, // Pass if needed
					groupAggregates: groupAggregates.value,
				}
			), // Ensure comma here
			dataZoom: [
				{
					type: 'inside',
					xAxisIndex: [0], // Zoom linked to the first x-axis
					yAxisIndex: undefined, // Correct way to disable y-axis zooming
					start: dataZoomStart.value,
					end: dataZoomEnd.value,
					filterMode: 'none', // Changed to 'none'
				},
			],
			// visualMap component removed
		}
		return optionsObject // Cast to full EChartsOption
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
