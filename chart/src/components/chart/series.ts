import type { EChartsCoreOption } from 'echarts/core'
import type { ChartSeriesData } from '../../stores'
import type { YAxisConfig } from './axes'

const SERIES_COLORS: Record<string, string> = {
	'Bat current': '#0000b3',
	'Motor current': '#8080ff',
	TEsc: '#ff0000', // Note: there's a leading space in the original, kept for now
	V: 'grey',
	Speed: '#fcad03',
	RPM: 'green',
	Throttle: '#03fcca',
	mAh: 'magenta',
}

const DS_TEMP_COLORS = ['#ff9933', '#ffcccc', '#660000', '#F44336', '#EF5350', '#E57373']

export function buildSeriesOptions(
	currentVisibleSeries: ChartSeriesData[],
	yAxesConfig: YAxisConfig[],
	finalYAxisOptions: EChartsCoreOption['yAxis'] // Pass the final yAxis array
): EChartsCoreOption['series'] {
	if (!finalYAxisOptions || !Array.isArray(finalYAxisOptions)) {
		console.error('finalYAxisOptions is undefined or not an array in buildSeriesOptions')
		return []
	}

	return currentVisibleSeries.map((s: ChartSeriesData) => {
		const seriesName = s.name
		let itemStyle = {}

		if (SERIES_COLORS[seriesName]) {
			itemStyle = { color: SERIES_COLORS[seriesName] }
		} else if (seriesName === 'TAmbient' || seriesName === 'TAlum' || seriesName === 'TMosfet') {
			const dsTempSeriesInOrder = currentVisibleSeries.filter(
				(cs) => cs.name === 'TAmbient' || cs.name === 'TAlum' || cs.name === 'TMosfet'
			)
			const colorIndex = dsTempSeriesInOrder.indexOf(s)
			itemStyle = { color: DS_TEMP_COLORS[colorIndex % DS_TEMP_COLORS.length] }
		}

		// Find the YAxisConfig for this series
		const yAxisConfigForSeries = yAxesConfig.find(
			(axCfg) => axCfg.seriesNames && axCfg.seriesNames.includes(seriesName)
		)

		let yAxisIndexToUse = -1

		if (yAxisConfigForSeries) {
			// Find the index of this yAxisConfig.id in the *final* finalYAxisOptions array
			const finalIndex = finalYAxisOptions.findIndex(
				(axisOpt: { id?: string }) => axisOpt.id === yAxisConfigForSeries.id
			)
			if (finalIndex !== -1) {
				yAxisIndexToUse = finalIndex
			} else {
				// Fallback: try to find the 'yOther' axis in the final array if it's used
				const otherAxisFinalIndex = finalYAxisOptions.findIndex(
					(axisOpt: { id?: string }) => axisOpt.id === 'yOther'
				)
				if (otherAxisFinalIndex !== -1) {
					yAxisIndexToUse = otherAxisFinalIndex
				}
			}
		} else {
			// If no specific yAxisConfig, try to find 'yOther' in the final array
			const otherAxisFinalIndex = finalYAxisOptions.findIndex(
				(axisOpt: { id?: string }) => axisOpt.id === 'yOther'
			)
			if (otherAxisFinalIndex !== -1) {
				yAxisIndexToUse = otherAxisFinalIndex
			}
		}

		if (yAxisIndexToUse === -1) {
			console.warn(
				`Series "${seriesName}" could not be mapped to a yAxis in the final yAxis options. Defaulting to yAxisIndex 0, but this might be incorrect.`
			)
			yAxisIndexToUse = 0 // Default, though potentially problematic
		}

		return {
			...s,
			yAxisIndex: yAxisIndexToUse,
			showSymbol: false,
			smooth: false,
			type: 'line',
			connectNulls: false,
			itemStyle: itemStyle,
		}
	})
}
