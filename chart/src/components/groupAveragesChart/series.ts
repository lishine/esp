import type { EChartsOption, SeriesOption as EchartsSeriesOption } from 'echarts' // Added EchartsSeriesOption
import type { GroupAggregate } from '@/stores/types'
import type { GroupAverageSeriesConfig } from './seriesConfig' // Adjusted import path

// Removed local SeriesOption helper type, will use EchartsSeriesOption directly

export function buildSeriesOptionsForGroupChart(
	groupAggregates: GroupAggregate[],
	groupAverageSeriesConfig: ReadonlyArray<GroupAverageSeriesConfig>,
	// groupAverageSeriesVisibility: Record<string, boolean>, // No longer needed here
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
		// if (groupAverageSeriesVisibility[config.displayName]) { // REMOVED: Series objects are always created
		const mainSeriesDataPoints: Array<[number, number | null]> = [] // Renamed for clarity, back to 2D
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
				console.warn(`Series "${config.displayName}" could not reliably map to a yAxis. Defaulting to index 0.`)
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
					mainSeriesDataPoints.push([group.startTime.getTime(), metricValue])
					mainSeriesDataPoints.push([group.endTime.getTime(), metricValue])
				} else {
					// Metric value is null/undefined for this group for this series
					mainSeriesDataPoints.push([group.startTime.getTime(), null])
					mainSeriesDataPoints.push([group.endTime.getTime(), null])
				}

				// Check for a time gap to the next group to insert a null point in the main series
				// and create a separate connector series.
				if (i < sortedGroupAggregates.length - 1) {
					const nextGroup = sortedGroupAggregates[i + 1]
					if (
						nextGroup.startTime &&
						group.endTime &&
						group.endTime.getTime() < nextGroup.startTime.getTime()
					) {
						// Gap detected. Add a null point to the current main series to break it.
						mainSeriesDataPoints.push([group.endTime.getTime(), null])

						// Create a new series for the connector line.
						const currentGroupMetricValue = group.metrics[config.dataKey]
						const nextGroupMetricValue = nextGroup.metrics[config.dataKey]

						// Only create a connector if both points are valid numbers.
						// Or, decide if you want to draw connectors to/from null points.
						// For now, let's assume we only connect valid points, or extend from a valid point to a null start of next.
						// If currentGroupMetricValue is null/undefined, the connector would start from nowhere.
						// If nextGroupMetricValue is null/undefined, the connector would end nowhere.
						// A simple connector:
						if (
							currentGroupMetricValue !== undefined &&
							currentGroupMetricValue !== null &&
							nextGroupMetricValue !== undefined &&
							nextGroupMetricValue !== null
						) {
							const connectorSeries: EchartsSeriesOption = {
								name: `${config.displayName}_connector_${i}`, // Unique name, won't show in legend by default
								type: 'line',
								data: [
									[group.endTime.getTime(), currentGroupMetricValue],
									[nextGroup.startTime.getTime(), nextGroupMetricValue],
								],
								yAxisIndex: yAxisIndexToUse,
								showSymbol: false,
								smooth: false,
								sampling: 'lttb', // Added sampling
								lineStyle: {
									width: 2, // Use a fixed width for connectors
									color: config.color, // Use color from the series config
									opacity: 0.3, // Desired opacity
								},
								itemStyle: {
									color: config.color, // Match item color with line color
								},
								silent: true, // Makes the series not respond to mouse events, good for connectors
								legendHoverLink: false, // Optional: disable legend hover effect
								animation: false, // Optional: disable animation for connectors
							}
							seriesOutput.push(connectorSeries)
						}
					}
				}
			} else {
				console.warn(
					`Group missing startTime or endTime, cannot plot segment for series "${config.displayName}". Group:`,
					group
				)
			}
		}

		// Sort data points by time to ensure lines are drawn correctly for the main series
		mainSeriesDataPoints.sort((a, b) => a[0] - b[0])

		// Always create the main series object. Its visibility will be controlled by legend.selected.
		if (mainSeriesDataPoints.length > 0) {
			seriesOutput.push({
				name: config.displayName,
				type: 'line',
				data: mainSeriesDataPoints, // Use the 2D data points
				yAxisIndex: yAxisIndexToUse,
				showSymbol: false, // Hide symbols as per feedback
				smooth: false,
				sampling: 'lttb', // Added sampling
				itemStyle: {
					color: config.color,
				},
				lineStyle: {
					width: 2,
					color: config.color,
				},
			})
		} else {
			// Optionally, push an empty series object so the legend item still appears,
			// though it won't have data. Or, ensure legend.data includes all series names
			// regardless of whether they have data points.
			// For now, consistent with previous: if no data, no series object.
			// This means if a series *never* has data, its legend item might not appear
			// if legend.data is derived from seriesOutput.
			console.log(`[buildSeriesOptionsForGroupChart] No data points for series: ${config.displayName}`)
		}
		// } // REMOVED: Corresponding closing brace for the removed if
	})
	return seriesOutput as EchartsSeriesOption[] // Ensure cast to the correct EchartsSeriesOption array
}
