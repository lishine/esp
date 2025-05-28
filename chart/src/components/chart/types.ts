import type { ChartSeriesData, LogEntry } from '../../stores'

export type EChartTooltipParam = {
	seriesName: string
	value: [number | string | Date, number | null] | number | null
	marker?: string
	color?: string
	axisValue?: number | string | Date
}

export type ChartFormattedDataRef = {
	value: {
		series: ChartSeriesData[]
	} | null
}

export type VisibleSeriesSetRef = {
	value: Set<string>
}

export type LogEntriesRef = {
	value: LogEntry[]
}

export type IsMobileRef = {
	value: boolean
}
