import type { YAXisComponentOption } from 'echarts' // Changed from EChartsCoreOption, added YAXisComponentOption

export interface YAxisConfig {
	id: string
	name?: string
	position?: 'left' | 'right'
	min?: number | 'dataMin' // Allow string 'dataMin'
	max?: number | 'dataMax' // Allow string 'dataMax'
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
	// Allow for custom properties passed from useGroupAveragesChartOptions
	// These are prefixed with _ to denote they are custom and might not be part of standard YAxisConfig
	_color?: string
	_originalYAxisIndex?: number
	// [key: string]: any // Removed index signature, explicit properties cover known use cases
}

export function buildYAxisOptionsForGroupChart(
	yAxesConfigsWithCustomProps: YAxisConfig[],
	visibleYAxisOriginalIndices: number[]
): YAXisComponentOption[] {
	// Changed return type to use the local YAxisOption derived from EChartsOption
	if (!yAxesConfigsWithCustomProps) {
		// Check only if the array itself is undefined
		return []
	}

	const returnedAxes: YAXisComponentOption[] = []

	let leftAxesCount = 0
	let rightAxesCount = 0

	// Create a map to store axes based on their originalYAxisIndex to group them
	const axesByOriginalIndex = new Map<number, YAxisConfig[]>()
	yAxesConfigsWithCustomProps.forEach((config) => {
		const originalIndex = typeof config._originalYAxisIndex === 'number' ? config._originalYAxisIndex : -1
		if (visibleYAxisOriginalIndices.includes(originalIndex)) {
			if (!axesByOriginalIndex.has(originalIndex)) {
				axesByOriginalIndex.set(originalIndex, [])
			}
			axesByOriginalIndex.get(originalIndex)?.push(config)
		}
	})

	// Sort the original indices to process axes in order
	const sortedOriginalIndices = Array.from(axesByOriginalIndex.keys()).sort((a, b) => a - b)

	sortedOriginalIndices.forEach((originalIndex) => {
		const configsForThisIndex = axesByOriginalIndex.get(originalIndex) || []
		configsForThisIndex.forEach((config) => {
			const position = config.position || (originalIndex % 2 === 0 ? 'left' : 'right')
			let offset = 0
			if (position === 'left') {
				offset = leftAxesCount * 65 // Increased offset
				leftAxesCount++
			} else {
				offset = rightAxesCount * 65 // Increased offset
				rightAxesCount++
			}

			returnedAxes.push({
				id: config.id,
				type: 'value',
				name: config.name || '',
				min: config.min as number | 'dataMin',
				max: config.max as number | 'dataMax',
				position: position,
				offset: offset,
				show: config.show, // Use the 'show' property from the config
				axisLabel: config.axisLabel || { show: false, formatter: '{value}' }, // Ensure axisLabel is also hidden by default if not specified
				splitLine: { show: true, lineStyle: { type: 'dashed' } },
				axisLine: { show: true, onZero: false, lineStyle: { color: config._color } },
				nameTextStyle: { ...config.nameTextStyle, color: config._color },
			})
		})
	}) // Closes sortedOriginalIndices.forEach

	// Define base for empty axes and add them if no other visible axes exist on a side
	const emptyAxisBase: YAXisComponentOption = {
		type: 'value',
		show: true,
		name: '',
		min: 0,
		max: 1, // Minimal default range
		axisLabel: { show: true },
		splitLine: { show: false },
		axisLine: { show: true, onZero: false },
		offset: 0,
	}

	const hasVisibleLeftAxis = returnedAxes.some((axis) => axis.position === 'left' && axis.show === true)
	if (!hasVisibleLeftAxis) {
		returnedAxes.push({
			...emptyAxisBase,
			id: 'emptyLeftAxis',
			position: 'left',
		})
	}

	const hasVisibleRightAxis = returnedAxes.some((axis) => axis.position === 'right' && axis.show === true)
	if (!hasVisibleRightAxis) {
		returnedAxes.push({
			...emptyAxisBase,
			id: 'emptyRightAxis',
			position: 'right',
		})
	}

	return returnedAxes // Cast removed as returnedAxes is now strongly typed
}
