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

			// Ensure groupAggregates is sorted by startTime to correctly identify gaps.
			const sortedGroupAggregates = [...groupAggregates].sort((a, b) => {
				const timeA = a.startTime ? a.startTime.getTime() : 0
				const timeB = b.startTime ? b.startTime.getTime() : 0
				if (!a.startTime && !b.startTime) return 0
				if (!a.startTime) return 1 // Sort groups without startTime to the end
				if (!b.startTime) return -1
				return timeA - timeB
			})

			for (let i = 0; i < sortedGroupAggregates.length; i++) {
				const group = sortedGroupAggregates[i]

				if (group.startTime && group.endTime) {
					const metricValue = group.metrics[config.dataKey]

					if (metricValue !== undefined && metricValue !== null) {
						seriesDataPoints.push([group.startTime.getTime(), metricValue])
						seriesDataPoints.push([group.endTime.getTime(), metricValue])
					} else {
						// Metric value is null/undefined for this group for this series
						seriesDataPoints.push([group.startTime.getTime(), null])
						seriesDataPoints.push([group.endTime.getTime(), null])
					}

					// Check for a time gap to the next group
					if (i < sortedGroupAggregates.length - 1) {
						const nextGroup = sortedGroupAggregates[i + 1]
						// Ensure nextGroup times are valid before comparing
						if (nextGroup.startTime && group.endTime.getTime() < nextGroup.startTime.getTime()) {
							// Insert a null point at the current group's endTime if there's a gap before the next group.
							// This explicitly tells ECharts to break the line here when connectNulls is false.
							seriesDataPoints.push([group.endTime.getTime(), null])
						}
					}
				} else {
					console.warn(
						`Group missing startTime or endTime, cannot plot segment for series "${config.displayName}". Group:`,
						group
					)
				}
			}

			// Sort data points by time to ensure lines are drawn correctly
			seriesDataPoints.sort((a, b) => a[0] - b[0])

			if (seriesDataPoints.length > 0) {
				seriesOutput.push({
					name: config.displayName,
					type: 'line', // Could also be 'bar' if x-axis was categorical for segments
					data: seriesDataPoints,
					yAxisIndex: yAxisIndexToUse,
					showSymbol: false, // Hide symbols as per feedback
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
