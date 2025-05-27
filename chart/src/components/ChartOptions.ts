import { computed } from 'vue'
import type { EChartsCoreOption as ECOption } from 'echarts/core'
import { formatInTimeZone } from 'date-fns-tz'
import type { ChartFormattedDataRef, VisibleSeriesSetRef, LogEntriesRef, IsMobileRef } from './chart/types'
import { createTooltipFormatter } from './chart/tooltip'
import {
	calculateDynamicMaxValues,
	defineYAxesConfig,
	calculateVisibleYAxisIds,
	buildYAxisOptions,
	type YAxisConfig,
} from './chart/axes'
import { buildSeriesOptions } from './chart/series'
import type { ChartSeriesData } from '../stores/sessionData' // Keep this if ChartSeriesData is used directly here

export function useChartOptions(
	chartFormattedData: ChartFormattedDataRef,
	visibleSeriesSet: VisibleSeriesSetRef,
	logEntries: LogEntriesRef,
	isMobile: IsMobileRef
) {
	const chartsHeight = computed(() => (isMobile.value ? '460px' : '600px'))

	const chartOptions = computed((): ECOption | null => {
		if (
			!chartFormattedData.value ||
			!chartFormattedData.value.series ||
			chartFormattedData.value.series.length === 0 ||
			!logEntries.value || // Added null check for logEntries.value
			logEntries.value.length === 0
		) {
			return null
		}

		// Define yAxesConfig and visibleYAxisIds first as they are needed by the tooltip formatter
		const { finalMaxCurrent, finalMaxTemp, minTemp } = calculateDynamicMaxValues(logEntries.value)
		const yAxesConfig: YAxisConfig[] = defineYAxesConfig(finalMaxCurrent, finalMaxTemp, minTemp)

		const currentVisibleSeries = chartFormattedData.value.series.filter((s: ChartSeriesData) =>
			visibleSeriesSet.value.has(s.name)
		)

		const visibleYAxisIds = calculateVisibleYAxisIds(currentVisibleSeries, yAxesConfig)

		// Now create the tooltip object with the necessary context
		const tooltip = createTooltipFormatter(yAxesConfig, visibleYAxisIds)

		const baseChartOptions: ECOption = {
			title: { text: '' },
			tooltip: tooltip, // Use the created tooltip object
			legend: {
				orient: 'horizontal' as const,
				bottom: 10,
				type: 'scroll' as const,
				data: [] as string[], // Explicitly define data here
			},
			grid: {
				left: '8%', // Adjusted for maximizing chart area
				right: '12%', // Adjusted for maximizing chart area
				bottom: '20%', // Adjusted for maximizing chart area
				top: '5%', // Adjusted for maximizing chart area, was 2%
				containLabel: true,
			},
			xAxis: {
				type: 'time',
				useUTC: true, // ECharts should still treat input data as UTC
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
			yAxis: [], // Will be populated by buildYAxisOptions
			series: [], // Will be populated by buildSeriesOptions
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
		}

		if (currentVisibleSeries.length === 0) {
			return {
				...baseChartOptions,
				legend: {
					...(baseChartOptions.legend || {}), // Spread an empty object if legend is undefined
					data: [],
				} as ECOption['legend'], // Assert the final type
				series: [],
				yAxis: [],
			}
		}

		// The legend object and its data property are already defined in baseChartOptions
		// So, we can directly assign to it.
		if (baseChartOptions.legend && Array.isArray((baseChartOptions.legend as { data?: string[] }).data)) {
			;(baseChartOptions.legend as { data: string[] }).data = currentVisibleSeries.map(
				(s: ChartSeriesData) => s.name
			)
		}

		const finalYAxisOptions = buildYAxisOptions(yAxesConfig, visibleYAxisIds)
		baseChartOptions.yAxis = finalYAxisOptions
		baseChartOptions.series = buildSeriesOptions(currentVisibleSeries, yAxesConfig, finalYAxisOptions)

		return baseChartOptions
	})

	return {
		chartsHeight,
		chartOptions,
	}
}
