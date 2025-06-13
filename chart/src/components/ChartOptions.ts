import { computed, type Ref } from 'vue' // Added Ref
import type { EChartsCoreOption as ECOption } from 'echarts/core'
import { formatInTimeZone } from 'date-fns-tz'
import type { ChartFormattedDataRef, VisibleSeriesSetRef, LogEntriesRef, IsMobileRef } from './chart/types'
import { createTooltipFormatter, type TooltipSeriesDisplayConfig } from './chart/tooltip'
import { CANONICAL_SERIES_CONFIG, type CanonicalSeriesConfig } from '../stores/seriesConfig' // Corrected import and added type
import {
	calculateDynamicMaxValues,
	defineYAxesConfig,
	calculateVisibleYAxisIds,
	buildYAxisOptions,
	type YAxisConfig,
} from './chart/axes'
import { buildSeriesOptions } from './chart/series'
import type { ChartSeriesData } from '../stores' // Keep this if ChartSeriesData is used directly here

export function useChartOptions(
	chartFormattedData: ChartFormattedDataRef,
	hiddenSeriesSet: VisibleSeriesSetRef, // Renamed from visibleSeriesSet
	logEntries: LogEntriesRef,
	isMobile: IsMobileRef,
	dataZoomStart: Ref<number>, // Added
	dataZoomEnd: Ref<number> // Added
) {
	const chartsHeight = computed(() => (isMobile.value ? '460px' : '600px'))

	const chartOptions = computed((): ECOption | null => {
		if (
			!chartFormattedData.value ||
			!chartFormattedData.value.series ||
			// Removed chartFormattedData.value.series.length === 0 here, will check later
			!logEntries.value ||
			logEntries.value.length === 0
		) {
			return null
		}

		// Define yAxesConfig and visibleYAxisIds first as they are needed by the tooltip formatter
		const { finalMaxCurrent, finalMaxTemp, minTemp } = calculateDynamicMaxValues(logEntries.value)
		const yAxesConfig: YAxisConfig[] = defineYAxesConfig(finalMaxCurrent, finalMaxTemp, minTemp)

		// currentVisibleSeries is used to determine which Y-axes should be active
		const currentVisibleSeries = chartFormattedData.value.series.filter(
			(s: ChartSeriesData) => !hiddenSeriesSet.value.has(s.name) // Inverted logic
		)

		const visibleYAxisIds = calculateVisibleYAxisIds(currentVisibleSeries, yAxesConfig)

		// Prepare seriesDisplayConfigs for the tooltip
		const sensorChartDisplayConfigs: TooltipSeriesDisplayConfig[] = CANONICAL_SERIES_CONFIG.map(
			(csc: CanonicalSeriesConfig): TooltipSeriesDisplayConfig => ({
				seriesName: csc.displayName, // ECharts series.name is typically set to displayName
				displayName: csc.displayName,
				unit: csc.unit,
				decimals: csc.decimals,
			})
		)

		// Now create the tooltip object with the necessary context
		const tooltip = createTooltipFormatter(sensorChartDisplayConfigs, yAxesConfig, visibleYAxisIds)

		const baseChartOptions: ECOption = {
			title: { text: '' },
			tooltip: tooltip, // Use the created tooltip object
			legend: {
				// Initialize legend with all series data and current selection state
				orient: 'horizontal' as const,
				bottom: -5, // Position at the bottom
				// type: 'scroll' as const, // Remove scroll to allow wrapping
				left: 'center', // Center the legend block
				// We can also use 'left' and 'right' to define width e.g. left: '10%', right: '10%'
				// ECharts will attempt to wrap items if they exceed the legend's width.
				// Default itemGap is 10. If more spacing is needed between items:
				// itemGap: 15,
				data: chartFormattedData.value.series.map((s: ChartSeriesData) => s.name), // All series names
				selected: chartFormattedData.value.series.reduce(
					(acc, series: ChartSeriesData) => {
						acc[series.name] = !hiddenSeriesSet.value.has(series.name) // Inverted logic
						return acc
					},
					{} as Record<string, boolean>
				),
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
					start: dataZoomStart.value, // Use reactive value
					end: dataZoomEnd.value, // Use reactive value
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
					start: dataZoomStart.value, // Use reactive value
					end: dataZoomEnd.value, // Use reactive value
				},
			],
		}

		// If there's truly no series data at all (e.g. no log file loaded or processed into series)
		if (chartFormattedData.value.series.length === 0) {
			return {
				...baseChartOptions, // Retain most base options like grid, xAxis, dataZoom
				legend: {
					// Explicitly clear legend if no series data
					...(baseChartOptions.legend || {}), // Keep structure but clear data/selected
					data: [],
					selected: {},
				} as ECOption['legend'],
				series: [], // No series data to plot
				yAxis: [], // No yAxes needed (or default empty ones from base)
			}
		}

		// Ensure legend data and selected state are always up-to-date based on all available series
		// and the current visibility state from the store. This is important if chartFormattedData.value.series
		// or visibleSeriesSet.value changes, as baseChartOptions is computed.
		if (
			baseChartOptions.legend &&
			typeof baseChartOptions.legend === 'object' &&
			!Array.isArray(baseChartOptions.legend)
		) {
			const legendOption = baseChartOptions.legend as import('echarts/components').LegendComponentOption
			legendOption.data = chartFormattedData.value.series.map((s: ChartSeriesData) => s.name)
			legendOption.selected = chartFormattedData.value.series.reduce(
				(acc, series: ChartSeriesData) => {
					acc[series.name] = !hiddenSeriesSet.value.has(series.name) // Inverted logic
					return acc
				},
				{} as Record<string, boolean>
			)
		} else {
			// Fallback if legend was somehow not an object (highly unlikely given initialization)
			// This re-establishes the legend object correctly.
			baseChartOptions.legend = {
				orient: 'horizontal' as const,
				bottom: 10,
				type: 'scroll' as const,
				data: chartFormattedData.value.series.map((s: ChartSeriesData) => s.name),
				selected: chartFormattedData.value.series.reduce(
					(acc, series: ChartSeriesData) => {
						acc[series.name] = !hiddenSeriesSet.value.has(series.name) // Inverted logic
						return acc
					},
					{} as Record<string, boolean>
				),
			}
		}

		// visibleYAxisIds is correctly calculated based on currentVisibleSeries (series intended to be shown)
		const finalYAxisOptions = buildYAxisOptions(yAxesConfig, visibleYAxisIds)
		baseChartOptions.yAxis = finalYAxisOptions

		// IMPORTANT: Pass ALL series data to ECharts.
		// Visibility is controlled by the `legend.selected` mapping.
		baseChartOptions.series = buildSeriesOptions(chartFormattedData.value.series, yAxesConfig, finalYAxisOptions)

		return baseChartOptions
	})

	return {
		chartsHeight,
		chartOptions,
	}
}
