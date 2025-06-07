import type { EChartsOption, SeriesOption as EchartsSeriesOption } from 'echarts' // Added EchartsSeriesOption
import type { GroupAggregate } from '@/stores/types'
import type { GroupAverageSeriesConfig } from './seriesConfig' // Adjusted import path

// Removed local SeriesOption helper type, will use EchartsSeriesOption directly

export function buildSeriesOptionsForGroupChart(
	groupAggregates: GroupAggregate[],
	groupAverageSeriesConfig: ReadonlyArray<GroupAverageSeriesConfig>,
	groupAverageSeriesVisibility: Record<string, boolean>,
	finalYAxes: EChartsOption['yAxis'] // Changed from EChartsCoreOption
): EchartsSeriesOption[] {
	// Return an array of specific series options
	const seriesOutput: EchartsSeriesOption[] = []

	if (
		!groupAggregates ||
		groupAggregates.length === 0 ||
		!finalYAxes ||
		!Array.isArray(finalYAxes) ||
		finalYAxes.length === 0
	) {
		return [] as EchartsSeriesOption[] // Ensure empty array matches return type
	}

	groupAverageSeriesConfig.forEach((config) => {
		if (groupAverageSeriesVisibility[config.displayName]) {
			const seriesDataPoints: Array<[number, number | null]> = []
			let yAxisIndexToUse = -1

			// Attempt to find the yAxisIndex based on internalId matching an axis id
			const yAxisDefinition = finalYAxes.find(
				(axis) => axis && typeof axis === 'object' && axis.id === config.internalId
			)
			if (yAxisDefinition) {
				yAxisIndexToUse = finalYAxes.indexOf(yAxisDefinition)
			} else {
				// Fallback to yAxisIndex from config if direct ID match failed (e.g. if finalYAxes was rebuilt differently)
				// This assumes config.yAxisIndex refers to the intended original index in a multi-axis setup.
				// For safety, ensure it's within bounds of finalYAxes.
				if (config.yAxisIndex !== undefined && config.yAxisIndex < finalYAxes.length) {
					yAxisIndexToUse = config.yAxisIndex
				} else {
					yAxisIndexToUse = 0 // Default to first y-axis if no match or out of bounds
					console.warn(
						`Series "${config.displayName}" could not reliably map to a yAxis. Defaulting to index 0.`
					)
				}
			}
			if (yAxisIndexToUse >= finalYAxes.length) {
				// final safety check
				console.warn(
					`Calculated yAxisIndex ${yAxisIndexToUse} is out of bounds for finalYAxes (length ${finalYAxes.length}). Defaulting to 0 for series "${config.displayName}".`
				)
				yAxisIndexToUse = 0
			}

			groupAggregates.forEach((segment) => {
				if (segment.startTime) {
					// Ensure startTime exists
					const value = segment.metrics[config.dataKey]
					if (value !== undefined && value !== null) {
						seriesDataPoints.push([segment.startTime.getTime(), value])
					} else {
						// Add null to maintain point correspondence if a segment lacks this metric
						seriesDataPoints.push([segment.startTime.getTime(), null])
					}
				}
			})

			// Sort data points by time to ensure lines are drawn correctly
			seriesDataPoints.sort((a, b) => a[0] - b[0])

			if (seriesDataPoints.length > 0) {
				seriesOutput.push({
					name: config.displayName,
					type: 'line', // Could also be 'bar' if x-axis was categorical for segments
					data: seriesDataPoints,
					yAxisIndex: yAxisIndexToUse,
					showSymbol: true, // Show symbols for distinct points
					smooth: false,
					itemStyle: {
						color: config.color,
					},
					lineStyle: {
						width: 2,
						color: config.color,
					},
				})
			} else {
				console.log(`[buildSeriesOptionsForGroupChart] No data points for series: ${config.displayName}`)
			}
		}
	})
	return seriesOutput as EchartsSeriesOption[] // Ensure cast to the correct EchartsSeriesOption array
}
