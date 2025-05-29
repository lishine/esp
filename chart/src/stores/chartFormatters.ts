import type { LogEntry, ChartSeriesData, FormattedChartData } from './types'
import { CANONICAL_SERIES_CONFIG, type SeriesConfig } from './seriesConfig'
import type { GpsValues, EscValues, DsValues } from './types'

export interface ChartFormatterContext {
	logEntries: LogEntry[]
}

const createValueExtractor = (config: SeriesConfig) => {
	if (config.sensorType === 'esc') {
		return (entry: LogEntry) => (entry.v as EscValues)[config.dataKey as keyof EscValues]
	} else if (config.sensorType === 'gps') {
		return (entry: LogEntry) => {
			const gpsEntry = entry.v as GpsValues
			const val = gpsEntry[config.dataKey as keyof GpsValues]
			return typeof val === 'number' ? val : null
		}
	} else if (config.sensorType === 'ds') {
		return (entry: LogEntry) => (entry.v as DsValues)[config.dataKey]
	} else if (config.sensorType === 'mc' || config.sensorType === 'th') {
		return (entry: LogEntry) => entry.v as number
	}
	return () => undefined
}

// Helper function to check if there's valid (non-null) data within the previous 5 seconds
const hasValidDataWithin5Seconds = (
	currentTimestamp: number,
	sensorDataMap: Map<number, number | null>,
	sortedTimestamps: number[]
): boolean => {
	const fiveSecondsMs = 5000
	const cutoffTime = currentTimestamp - fiveSecondsMs

	// Check timestamps in reverse order (most recent first)
	for (let i = sortedTimestamps.length - 1; i >= 0; i--) {
		const ts = sortedTimestamps[i]
		if (ts >= currentTimestamp) continue // Skip future timestamps
		if (ts < cutoffTime) break // Stop if we've gone back too far

		const value = sensorDataMap.get(ts)
		if (value !== null && value !== undefined) {
			return true
		}
	}
	return false
}

// Helper function to check if GPS has valid data within 5 seconds
const hasValidGpsDataWithin5Seconds = (
	currentTimestamp: number,
	gpsSensorEntries: Map<number, LogEntry>,
	sortedTimestamps: number[]
): boolean => {
	const fiveSecondsMs = 5000
	const cutoffTime = currentTimestamp - fiveSecondsMs

	// Check timestamps in reverse order (most recent first)
	for (let i = sortedTimestamps.length - 1; i >= 0; i--) {
		const ts = sortedTimestamps[i]
		if (ts >= currentTimestamp) continue // Skip future timestamps
		if (ts < cutoffTime) break // Stop if we've gone back too far

		const gpsEntry = gpsSensorEntries.get(ts)
		if (gpsEntry) {
			const gpsValues = gpsEntry.v as GpsValues
			const speedKnots = gpsValues.speed
			if (speedKnots !== undefined && speedKnots !== null) {
				return true
			}
		}
	}
	return false
}

export const chartFormatters = {
	getChartFormattedData(this: ChartFormatterContext): FormattedChartData {
		if (this.logEntries.length === 0) {
			return { series: [] }
		}

		console.time('getChartFormattedData')

		// 1. Collect all unique preciseTimestamps and sort them
		const uniqueTimestampMillis = new Set<number>()
		this.logEntries.forEach((entry) => {
			uniqueTimestampMillis.add(entry.preciseTimestamp.getTime())
		})
		const sortedUniqueTimestampMillis = Array.from(uniqueTimestampMillis).sort((a, b) => a - b)

		const finalSeries: ChartSeriesData[] = []

		// 2. Build series configurations from CANONICAL_SERIES_CONFIG
		const activeSeriesConfigs = CANONICAL_SERIES_CONFIG.map((config) => ({
			seriesName: config.displayName,
			internalId: config.internalId,
			sensorName: config.sensorType,
			valueExtractor: createValueExtractor(config),
		})).filter((config) => this.logEntries.some((logEntry) => logEntry.n === config.sensorName))

		// 3. Process data for each series
		activeSeriesConfigs.forEach((config) => {
			const sensorDataMap = new Map<number, number | null>()
			const gpsSensorEntries = new Map<number, LogEntry>()

			this.logEntries.forEach((entry) => {
				if (entry.n === config.sensorName) {
					const value = config.valueExtractor(entry)
					if (typeof value === 'number' || value === null) {
						sensorDataMap.set(entry.preciseTimestamp.getTime(), value)
					}
				}
				if (entry.n === 'gps') {
					gpsSensorEntries.set(entry.preciseTimestamp.getTime(), entry)
				}
			})

			const seriesChartData: Array<[Date, number | null]> = []
			let currentSeriesLastValidValue: number | null = null
			let currentLastValidSpeedWithFix: number | null = null

			sortedUniqueTimestampMillis.forEach((tsMillis) => {
				let valueToPushForChart: number | null

				if (config.internalId === 'mc_i') {
					const directValue = sensorDataMap.get(tsMillis)
					const current = directValue !== undefined ? directValue : null

					if (current !== null) {
						const actual = current * 1.732
						currentSeriesLastValidValue = actual
						valueToPushForChart = actual
					} else {
						// Check if there's valid data within the previous 5 seconds
						if (hasValidDataWithin5Seconds(tsMillis, sensorDataMap, sortedUniqueTimestampMillis)) {
							valueToPushForChart = currentSeriesLastValidValue
						} else {
							// No valid data within 5 seconds, don't interpolate
							currentSeriesLastValidValue = null
							valueToPushForChart = null
						}
					}
				} else if (config.internalId === 'gps_speed') {
					const gpsLogEntry = gpsSensorEntries.get(tsMillis)
					if (!gpsLogEntry) {
						// Check if there's valid GPS data within the previous 5 seconds
						if (hasValidGpsDataWithin5Seconds(tsMillis, gpsSensorEntries, sortedUniqueTimestampMillis)) {
							valueToPushForChart = currentLastValidSpeedWithFix
						} else {
							// No valid GPS data within 5 seconds, don't interpolate
							currentLastValidSpeedWithFix = null
							valueToPushForChart = null
						}
					} else {
						const gpsValues = gpsLogEntry.v as GpsValues

						const speedKnots = gpsValues.speed
						const checkedSpeedKnots = speedKnots !== undefined && speedKnots !== null ? speedKnots : null

						if (checkedSpeedKnots !== null) {
							const speedKmh = checkedSpeedKnots * 1.852
							valueToPushForChart = speedKmh
							currentLastValidSpeedWithFix = speedKmh
						} else {
							// Check if there's valid GPS data within the previous 5 seconds
							if (
								hasValidGpsDataWithin5Seconds(tsMillis, gpsSensorEntries, sortedUniqueTimestampMillis)
							) {
								valueToPushForChart = currentLastValidSpeedWithFix
							} else {
								// No valid GPS data within 5 seconds, don't interpolate
								currentLastValidSpeedWithFix = null
								valueToPushForChart = null
							}
						}
					}
				} else {
					const directValue = sensorDataMap.get(tsMillis)
					const checkedDirectValue = directValue !== undefined ? directValue : null

					if (checkedDirectValue !== null) {
						currentSeriesLastValidValue = checkedDirectValue
						valueToPushForChart = checkedDirectValue
					} else {
						// Check if there's valid data within the previous 5 seconds
						if (hasValidDataWithin5Seconds(tsMillis, sensorDataMap, sortedUniqueTimestampMillis)) {
							valueToPushForChart = currentSeriesLastValidValue
						} else {
							// No valid data within 5 seconds, don't interpolate
							currentSeriesLastValidValue = null
							valueToPushForChart = null
						}
					}
				}
				seriesChartData.push([new Date(tsMillis), valueToPushForChart])
			})

			finalSeries.push({
				name: config.seriesName,
				type: 'line',
				data: seriesChartData,
				showSymbol: false,
				connectNulls: false,
			})
		})

		console.timeEnd('getChartFormattedData')
		return { series: finalSeries }
	},
}
