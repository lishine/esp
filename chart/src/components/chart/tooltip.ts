import { formatInTimeZone } from 'date-fns-tz'
import { CANONICAL_SERIES_CONFIG } from '../../stores'
import type { EChartTooltipParam, ChartFormattedDataRef } from './types' // Import ChartFormattedDataRef
import type { YAxisConfig } from './axes' // Assuming YAxisConfig will be defined in axes.ts

export function createTooltipFormatter(
	yAxesConfig: YAxisConfig[], // Pass yAxesConfig if needed for axis label formatting
	visibleYAxisIds: Set<string>, // Pass visibleYAxisIds if needed
	chartFormattedData: ChartFormattedDataRef // Pass the formatted data
) {
	return {
		trigger: 'axis', // Explicitly set trigger type
		axisPointer: {
			type: 'cross',
			label: {
				padding: [3, 10, 3, 10],
				formatter: (params: { axisDimension?: string; axisIndex?: number; value: number | string | Date }) => {
					if (params.axisDimension === 'x' && params.value !== undefined) {
						const date = new Date(params.value as number)
						if (!isNaN(date.getTime())) {
							return formatInTimeZone(date, 'Asia/Jerusalem', 'HH:mm:ss')
						}
						return 'Invalid Date'
					}
					if (
						params.axisDimension === 'y' &&
						params.axisIndex !== undefined &&
						params.value !== undefined &&
						yAxesConfig && // Check if yAxesConfig is available
						visibleYAxisIds // Check if visibleYAxisIds is available
					) {
						const yAxisDefinition = yAxesConfig[params.axisIndex]
						if (yAxisDefinition && visibleYAxisIds.has(yAxisDefinition.id) && yAxisDefinition.show) {
							return typeof params.value === 'number' ? params.value.toFixed(1) : String(params.value)
						}
					}
					return ''
				},
			},
		},
		formatter: (params: EChartTooltipParam[]): string => {
			if (!Array.isArray(params) || params.length === 0 || !chartFormattedData.value) return '' // Add check for chartFormattedData

			const firstPoint = params[0]
			let tooltipHtml = ''
			const timestampMillis = firstPoint.axisValue as number // Get the timestamp from the axis pointer

			if (timestampMillis !== undefined && !isNaN(timestampMillis)) {
				const xAxisDate = new Date(timestampMillis)
				if (!isNaN(xAxisDate.getTime())) {
					tooltipHtml += `<div style="margin-bottom: -15px;text-align: center;">${formatInTimeZone(xAxisDate, 'Asia/Jerusalem', 'HH:mm:ss')}</div><br/>`
				} else {
					tooltipHtml += '<div style="text-align: center;">Invalid Date</div><br/>'
				}
			} else {
				tooltipHtml += '<div style="text-align: center;">Time N/A</div><br/>'
			}

			const tooltipSeriesConfig = CANONICAL_SERIES_CONFIG.map((csc) => ({
				displayName: csc.displayName,
				originalName: csc.displayName,
				unit: csc.unit,
				decimals: csc.decimals,
			}))

			// Create a map from the ECharts params for easy access to marker colors
			const paramsMap = new Map<string, EChartTooltipParam>()
			params.forEach((p: EChartTooltipParam) => {
				paramsMap.set(p.seriesName, p)
			})

			tooltipSeriesConfig.forEach((config) => {
				// Find the series data in the store's formatted data
				const seriesDataInStore = chartFormattedData.value?.series.find((s) => s.name === config.originalName)

				let displayValue: string = '-'
				let unitToShow = config.unit || ''
				let marker = '' // Initialize marker

				if (seriesDataInStore) {
					// Find the data point for the current timestamp
					const dataPoint = seriesDataInStore.data.find(([date]) => date.getTime() === timestampMillis)

					if (dataPoint) {
						const numericValue = dataPoint[1] // The value is the second element of the tuple [Date, value]

						if (numericValue !== null && typeof numericValue === 'number' && !isNaN(numericValue)) {
							displayValue = numericValue.toFixed(config.decimals)
							// Get the marker from the original params array if available
							const param = paramsMap.get(config.originalName)
							if (param) {
								marker = param.marker || ''
							}
						} else {
							displayValue = '-'
							unitToShow = ''
						}
					} else {
						// Data point not found at this exact timestamp in the formatted data
						displayValue = '-'
						unitToShow = ''
					}
				} else {
					// Series not found in chartFormattedData (shouldn't happen if config is based on available data)
					displayValue = '-'
					unitToShow = ''
				}

				tooltipHtml += `<div style="display: flex; justify-content: space-between; width: 100%;"><span>${marker}${config.displayName}:</span><span style="font-weight: bold; margin-left: 10px;">${displayValue}${unitToShow ? ' ' + unitToShow : ''}</span></div>`
			})
			return tooltipHtml
		},
	}
}
