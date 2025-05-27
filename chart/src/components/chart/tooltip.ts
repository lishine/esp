import { formatInTimeZone } from 'date-fns-tz'
import { CANONICAL_SERIES_CONFIG } from '../../stores/sessionData'
import type { EChartTooltipParam } from './types'
import type { YAxisConfig } from './axes' // Assuming YAxisConfig will be defined in axes.ts

export function createTooltipFormatter(
	yAxesConfig: YAxisConfig[], // Pass yAxesConfig if needed for axis label formatting
	visibleYAxisIds: Set<string> // Pass visibleYAxisIds if needed
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
			if (!Array.isArray(params) || params.length === 0) return ''

			const firstPoint = params[0]
			let tooltipHtml = ''
			if (firstPoint.axisValue !== undefined) {
				const xAxisDate = new Date(firstPoint.axisValue)
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

			const paramsMap = new Map<string, EChartTooltipParam>()
			params.forEach((p: EChartTooltipParam) => {
				paramsMap.set(p.seriesName, p)
			})

			tooltipSeriesConfig.forEach((config) => {
				const seriesData = paramsMap.get(config.originalName)
				if (seriesData) {
					const numericValue = Array.isArray(seriesData.value) ? seriesData.value[1] : seriesData.value
					let displayValue: string
					let unitToShow = config.unit || ''

					if (numericValue !== null && typeof numericValue === 'number' && !isNaN(numericValue)) {
						displayValue = numericValue.toFixed(config.decimals)
					} else if (
						seriesData.seriesName === 'Speed' &&
						Array.isArray(seriesData.value) &&
						seriesData.value[1] === null
					) {
						displayValue = '-'
						unitToShow = ''
					} else {
						displayValue = numericValue?.toFixed(config.decimals) || '-'
						if (displayValue === '-') {
							unitToShow = ''
						}
					}
					tooltipHtml += `<div style="display: flex; justify-content: space-between; width: 100%;"><span>${seriesData.marker || ''}${config.displayName}:</span><span style="font-weight: bold; margin-left: 10px;">${displayValue}${unitToShow ? ' ' + unitToShow : ''}</span></div>`
				} else {
					tooltipHtml += `<div style="display: flex; justify-content: space-between; width: 100%;"><span>${config.displayName}:</span><span style="font-weight: bold; margin-left: 10px;">-</span></div>`
				}
			})
			return tooltipHtml
		},
	}
}
