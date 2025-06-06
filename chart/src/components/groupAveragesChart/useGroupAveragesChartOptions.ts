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
			groupAverageSeriesVisibility.value,
			finalYAxes
		)

		// Add connectNulls: false to each series
		const finalSeriesData = seriesData.map((series) => ({
			...series,
			connectNulls: true,
		}))

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
				top: '20%', // Further increased top margin for legend
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
			series: finalSeriesData, // Use the modified series data
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
					label: {
						show: true, // General visibility for axis pointer labels
						formatter: (params: AxisPointerLabelFormatterParams) => {
							// params contains value, axisDimension, axisIndex, seriesData etc.
							if (params.axisDimension === 'y') {
								return '' // Hide label for y-axis
							}
							// For x-axis, ECharts will use its default time formatting if params.value is returned.
							// Or, you can format it explicitly here:
							// if (params.axisDimension === 'x' && typeof params.value === 'number') {
							// return formatInTimeZone(new Date(params.value), 'Asia/Jerusalem', 'HH:mm:ss');
							// }
							return typeof params.value === 'number'
								? formatInTimeZone(new Date(params.value), 'Asia/Jerusalem', 'HH:mm:ss')
								: String(params.value) // Fallback for other types
						},
					},
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
					xAxisIndex: [0], // Zoom linked to the first x-axis
					yAxisIndex: false, // Explicitly disable zooming on y-axes
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

// Interface for the axisPointer label formatter params
interface AxisPointerLabelFormatterParams {
	value: number | string // The value of the axis
	axisDimension: 'x' | 'y' | 'z' | 'radius' | 'angle' // Dimension of the axis
	axisIndex: number // Index of the axis
	// seriesData: Array<{ componentType: string, seriesType: string, seriesIndex: number, dataIndex: number, data: any, value: any, color: string, name: string, marker: string }>
	// Add other properties if needed based on ECharts documentation for this formatter
}
