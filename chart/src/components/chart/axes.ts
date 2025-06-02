import type { EChartsCoreOption } from 'echarts/core'
import type { LogEntry, EscValues, DsValues, ChartSeriesData } from '../../stores'

export interface YAxisConfig {
	id: string
	name?: string
	position?: 'left' | 'right'
	min?: number
	max?: number
	seriesNames?: string[]
	axisLabel?: {
		show?: boolean
		inside?: boolean
		align?: 'left' | 'center' | 'right'
		formatter?: string | ((value: number | string, index: number) => string)
		// Add other ECharts axisLabel properties if needed
	}
	nameTextStyle?: {
		padding?: number | number[]
		// Add other ECharts nameTextStyle properties if needed
	}
	show: boolean
	// seriesNamePrefix?: string; // Removed as it's no longer used
}

export function calculateDynamicMaxValues(logEntries: LogEntry[]) {
	let maxObservedCurrent = 0
	let maxObservedTemp = 0

	logEntries.forEach((entry: LogEntry) => {
		if (entry.n === 'esc') {
			const escVal = entry.v as EscValues
			if (typeof escVal.i === 'number') {
				maxObservedCurrent = Math.max(maxObservedCurrent, escVal.i)
			}
			if (typeof escVal.t === 'number') {
				maxObservedTemp = Math.max(maxObservedTemp, escVal.t)
			}
		} else if (entry.n === 'mc') {
			const motorCurrentVal = entry.v as number
			if (typeof motorCurrentVal === 'number') {
				maxObservedCurrent = Math.max(maxObservedCurrent, motorCurrentVal)
			}
		} else if (entry.n === 'ds') {
			const dsVal = entry.v as DsValues
			for (const key in dsVal) {
				if (typeof dsVal[key] === 'number') {
					maxObservedTemp = Math.max(maxObservedTemp, dsVal[key])
				}
			}
		}
	})
	// const finalMaxCurrent = maxObservedCurrent > 0 ? Math.ceil((maxObservedCurrent * 1.1) / 10) * 10 : 100;
	// const finalMaxTemp = maxObservedTemp > 0 ? Math.ceil((maxObservedTemp * 1.1) / 10) * 10 : 120;
	const finalMaxCurrent = 100
	const finalMaxTemp = 100
	const minTemp = 0 // Or 10 if preferred

	return { finalMaxCurrent, finalMaxTemp, minTemp }
}

export function defineYAxesConfig(finalMaxCurrent: number, finalMaxTemp: number, minTemp: number): YAxisConfig[] {
	return [
		{
			id: 'yCurrent',
			name: 'I',
			position: 'right',
			min: 0,
			max: finalMaxCurrent,
			seriesNames: ['Bat current', 'Motor current'],
			axisLabel: { show: true, inside: true, align: 'right' },
			nameTextStyle: { padding: [0, 0, 0, -35] },
			show: true,
		},
		{
			id: 'yTemperature',
			name: 'T',
			position: 'right',
			min: minTemp,
			max: finalMaxTemp,
			seriesNames: ['TEsc', 'TAmbient', 'TAlum', 'TMosfet'],
			axisLabel: { show: true },
			nameTextStyle: { padding: [0, -35, 0, 0] },
			show: true,
		},
		{
			id: 'yThrottle',
			seriesNames: ['Throttle'],
			min: 990,
			max: 2100,
			show: false,
		},
		{
			id: 'ymAh',
			seriesNames: ['mAh'],
			min: 0,
			max: 15000,
			show: false,
		},
		{
			id: 'yEscVoltage',
			seriesNames: ['V'],
			min: 0,
			max: 50.5,
			show: false,
		},
		{
			id: 'yEscRpm',
			seriesNames: ['RPM'],
			min: 0,
			max: 5000,
			show: false,
		},
		{
			id: 'yGpsSpeed',
			name: 'GPS',
			position: 'left',
			seriesNames: ['Speed'],
			min: 0,
			max: 35,
			show: true,
			axisLabel: { show: true },
			nameTextStyle: { padding: [0, 0, 0, -35] },
		},
		{ id: 'yOther', show: false }, // Fallback hidden axis
	]
}

export function calculateVisibleYAxisIds(
	currentVisibleSeries: ChartSeriesData[],
	yAxesConfig: YAxisConfig[]
): Set<string> {
	const visibleYAxisIds = new Set<string>()
	currentVisibleSeries.forEach((s: ChartSeriesData) => {
		const seriesName = s.name as string // Assuming s.name is always a string
		const axisConfig = yAxesConfig.find(
			(axCfg) =>
				axCfg.seriesNames &&
				axCfg.seriesNames.some((axSeriesName) => axSeriesName.toLowerCase() === seriesName.toLowerCase())
		)
		if (axisConfig) {
			visibleYAxisIds.add(axisConfig.id)
		} else {
			visibleYAxisIds.add('yOther') // Default to yOther if no specific axis found
		}
	})
	return visibleYAxisIds
}

export function buildYAxisOptions(
	yAxesConfig: YAxisConfig[],
	visibleYAxisIds: Set<string>
): EChartsCoreOption['yAxis'] {
	return yAxesConfig
		.filter((axCfg) => visibleYAxisIds.has(axCfg.id) || axCfg.id === 'yOther') // Include 'yOther' only if used
		.map((config) => ({
			id: config.id,
			type: 'value',
			name: config.name || '',
			min: config.min,
			max: config.max,
			position: config.position,
			show:
				config.id === 'yOther'
					? visibleYAxisIds.has('yOther')
					: config.show === true && visibleYAxisIds.has(config.id),
			axisLabel:
				config.axisLabel !== undefined
					? config.axisLabel
					: {
							show:
								config.id === 'yOther'
									? visibleYAxisIds.has('yOther')
									: config.show === true && visibleYAxisIds.has(config.id),
						},
			splitLine: {
				show:
					config.id === 'yOther'
						? visibleYAxisIds.has('yOther')
						: config.show === true && visibleYAxisIds.has(config.id),
				lineStyle: { type: 'dashed' },
			},
			axisLine: {
				show:
					config.id === 'yOther'
						? visibleYAxisIds.has('yOther')
						: config.show === true && visibleYAxisIds.has(config.id),
				onZero: false,
			},
			nameTextStyle: config.nameTextStyle || {},
		}))
}
