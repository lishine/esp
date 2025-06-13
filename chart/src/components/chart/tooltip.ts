import { formatInTimeZone } from 'date-fns-tz'
import { useSessionDataStore } from '../../stores'
import type { EChartTooltipParam } from './types'
import type { YAxisConfig } from './axes' // Assuming YAxisConfig will be defined in axes.ts
import { findActiveGroupName, parseTimeToSeconds } from '@/utils/tooltipHelpers'

// New interface for series display configuration
export interface TooltipSeriesDisplayConfig {
	seriesName: string // This should match seriesName in ECharts params (original series name)
	displayName: string // The name to show in the tooltip
	unit: string
	decimals: number
}

export function createTooltipFormatter(
	seriesDisplayConfigs: TooltipSeriesDisplayConfig[],
	yAxesConfig?: YAxisConfig[], // Optional: Pass yAxesConfig if needed for axis label formatting
	visibleYAxisIds?: Set<string> // Optional: Pass visibleYAxisIds if needed
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
			const timestampMillis = firstPoint.axisValue as number

			// Time header
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

			// Create a map from the ECharts params for easy access by seriesName, prioritizing entries with values.
			const paramsMap = new Map<string, EChartTooltipParam>()
			params.forEach((p: EChartTooltipParam) => {
				// Ensure p.seriesName is a string before trying to use it as a map key
				if (typeof p.seriesName === 'string') {
					const existingParam = paramsMap.get(p.seriesName)
					const pValue = Array.isArray(p.value) ? p.value[1] : p.value
					const existingPValue =
						existingParam &&
						(Array.isArray(existingParam.value) ? existingParam.value[1] : existingParam.value)

					if (!existingParam || (existingPValue === null && pValue !== null)) {
						paramsMap.set(p.seriesName, p)
					}
				}
			})

			// Iterate over the display configurations specific to this chart
			seriesDisplayConfigs.forEach((config) => {
				const param = paramsMap.get(config.seriesName) // config.seriesName is the ECharts series name

				let displayValue: string = '-'
				let unitToShow = config.unit || ''
				const marker = param?.marker || '' // Use marker from param if available

				if (param) {
					const valueFromParam = Array.isArray(param.value) ? param.value[1] : param.value
					if (
						valueFromParam !== null &&
						valueFromParam !== undefined &&
						typeof valueFromParam === 'number' &&
						!isNaN(valueFromParam)
					) {
						displayValue = valueFromParam.toFixed(config.decimals)
					} else {
						unitToShow = '' // No unit if value is not valid or not a number
					}
				} else {
					// No data from ECharts params for this configured series at this point
					unitToShow = ''
				}
				tooltipHtml += `<div style="display: flex; justify-content: space-between; width: 100%;"><span>${marker}${config.displayName}:</span><span style="font-weight: bold; margin-left: 10px;">${displayValue}${unitToShow ? ' ' + unitToShow : ''}</span></div>`
			})

			// Add active group name
			const sessionStore = useSessionDataStore()
			const groups = sessionStore.sessionMetadata?.groups

			// Get current chart time in seconds
			// Assuming firstPoint.axisValueLabel is "HH:mm:ss" or firstPoint.axisValue is a timestamp
			let chartTimeInSeconds = -1
			if (typeof firstPoint.axisValue === 'number') {
				// Typically a timestamp
				const date = new Date(firstPoint.axisValue)
				chartTimeInSeconds = date.getHours() * 3600 + date.getMinutes() * 60 + date.getSeconds()
			} else if (typeof firstPoint.axisValueLabel === 'string') {
				// Check if it's a "HH:MM:SS" string
				chartTimeInSeconds = parseTimeToSeconds(firstPoint.axisValueLabel)
			}

			if (chartTimeInSeconds !== -1 && groups) {
				const activeGroupName = findActiveGroupName(chartTimeInSeconds, groups)
				if (activeGroupName) {
					tooltipHtml += `<div style="margin-top: 5px; text-align: center; font-weight: bold;">${activeGroupName}</div>`
				}
			}

			return tooltipHtml
		},
	}
}
