import type { LogEntry, ChartSeriesData, FormattedChartData } from './types'
import { CANONICAL_SERIES_CONFIG, type SeriesConfig } from './seriesConfig'
import type { GpsValues, EscValues, DsValues } from './types'

export interface ChartFormatterContext {
	logEntries: LogEntry[]
	filterSeriesByBatCurrent: boolean // Added for battery current filtering
}

const applyRangeChecks = (internalId: string, value: number | null): number | null => {
	if (value === null || typeof value !== 'number' || isNaN(value)) return null

	let checkedValue: number | null = value
	if (internalId === 'esc_rpm') {
		if (checkedValue < 0 || checkedValue > 5000) checkedValue = null
	} else if (internalId === 'esc_v') {
		if (checkedValue < 30 || checkedValue > 55) checkedValue = null
	} else if (internalId === 'esc_i') {
		if (checkedValue < 0 || checkedValue > 200) checkedValue = null
	} else if (internalId === 'esc_t') {
		if (checkedValue < 10 || checkedValue > 140) checkedValue = null
	} else if (internalId === 'mc_i') {
		if (checkedValue < 0 || checkedValue > 200) checkedValue = null
	} else if (internalId === 'th_val') {
		if (checkedValue < 990 || checkedValue > 1900) checkedValue = null
	} else if (internalId.startsWith('ds_')) {
		if (checkedValue < 10 || checkedValue > 120) checkedValue = null
	} else if (internalId === 'gps_speed') {
		if (value === null || typeof value !== 'number' || isNaN(value)) {
			checkedValue = null
		} else if (value < 0 || value > 20) {
			checkedValue = null
		} else {
			checkedValue = value
		}
	}
	return checkedValue
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

		// Pre-calculate esc_i values and nullify flags if filtering is enabled
		const timestampNullifyFlags = new Map<number, boolean>()
		if (this.filterSeriesByBatCurrent) {
			const escISensorDataMap = new Map<number, number | null>()
			this.logEntries.forEach((entry) => {
				if (entry.n === 'esc') {
					const escValues = entry.v as EscValues
					const escIValue = applyRangeChecks('esc_i', escValues.i !== undefined ? escValues.i : null)
					escISensorDataMap.set(entry.preciseTimestamp.getTime(), escIValue)
				}
			})

			let shouldCurrentlyNullify = false
			sortedUniqueTimestampMillis.forEach((tsMillis) => {
				const escIValue = escISensorDataMap.get(tsMillis)

				if (escIValue !== null && escIValue !== undefined) {
					if (escIValue < 2) {
						shouldCurrentlyNullify = true
					} else if (escIValue > 2) {
						shouldCurrentlyNullify = false
					}
					// If escIValue is exactly 2, shouldCurrentlyNullify remains unchanged
				}
				// If escIValue is null or undefined, shouldCurrentlyNullify remains unchanged

				timestampNullifyFlags.set(tsMillis, shouldCurrentlyNullify)
			})
		}

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

				// Apply nullification if filter is enabled
				if (this.filterSeriesByBatCurrent) {
					const shouldNullify = timestampNullifyFlags.get(tsMillis)
					if (shouldNullify) {
						valueToPushForChart = null
					} else {
						// Proceed with normal value extraction if not nullifying
						if (config.internalId === 'mc_i') {
							const directValue = sensorDataMap.get(tsMillis)
							const current = applyRangeChecks(
								config.internalId,
								directValue !== undefined ? directValue : null
							)

							if (current !== null) {
								const actual = current * 1.732
								currentSeriesLastValidValue = actual
								valueToPushForChart = actual
							} else {
								valueToPushForChart = currentSeriesLastValidValue
							}
						} else if (config.internalId === 'gps_speed') {
							const gpsLogEntry = gpsSensorEntries.get(tsMillis)
							if (!gpsLogEntry) {
								valueToPushForChart = currentLastValidSpeedWithFix
							} else {
								const gpsValues = gpsLogEntry.v as GpsValues
								const hasGpsFix = gpsValues.fix

								if (!hasGpsFix) {
									valueToPushForChart = null
									currentLastValidSpeedWithFix = null
								} else {
									const speedKnots = gpsValues.speed
									const checkedSpeedKnots = applyRangeChecks(
										config.internalId,
										speedKnots !== undefined && speedKnots !== null ? speedKnots : null
									)

									if (checkedSpeedKnots !== null) {
										const speedKmh = checkedSpeedKnots * 1.852
										valueToPushForChart = speedKmh
										currentLastValidSpeedWithFix = speedKmh
									} else {
										valueToPushForChart = currentLastValidSpeedWithFix
									}
								}
							}
						} else {
							const directValue = sensorDataMap.get(tsMillis)
							const checkedDirectValue = applyRangeChecks(
								config.internalId,
								directValue !== undefined ? directValue : null
							)

							if (checkedDirectValue !== null) {
								currentSeriesLastValidValue = checkedDirectValue
								valueToPushForChart = checkedDirectValue
							} else {
								valueToPushForChart = currentSeriesLastValidValue
							}
						}
					}
				} else {
					// If filter is disabled, proceed with existing logic
					if (config.internalId === 'mc_i') {
						const directValue = sensorDataMap.get(tsMillis)
						const current = applyRangeChecks(
							config.internalId,
							directValue !== undefined ? directValue : null
						)

						if (current !== null) {
							const actual = current * 1.732
							currentSeriesLastValidValue = actual
							valueToPushForChart = actual
						} else {
							valueToPushForChart = currentSeriesLastValidValue
						}
					} else if (config.internalId === 'gps_speed') {
						const gpsLogEntry = gpsSensorEntries.get(tsMillis)
						if (!gpsLogEntry) {
							valueToPushForChart = currentLastValidSpeedWithFix
						} else {
							const gpsValues = gpsLogEntry.v as GpsValues
							const hasGpsFix = gpsValues.fix

							if (!hasGpsFix) {
								valueToPushForChart = null
								currentLastValidSpeedWithFix = null
							} else {
								const speedKnots = gpsValues.speed
								const checkedSpeedKnots = applyRangeChecks(
									config.internalId,
									speedKnots !== undefined && speedKnots !== null ? speedKnots : null
								)

								if (checkedSpeedKnots !== null) {
									const speedKmh = checkedSpeedKnots * 1.852
									valueToPushForChart = speedKmh
									currentLastValidSpeedWithFix = speedKmh
								} else {
									valueToPushForChart = currentLastValidSpeedWithFix
								}
							}
						}
					} else {
						const directValue = sensorDataMap.get(tsMillis)
						const checkedDirectValue = applyRangeChecks(
							config.internalId,
							directValue !== undefined ? directValue : null
						)

						if (checkedDirectValue !== null) {
							currentSeriesLastValidValue = checkedDirectValue
							valueToPushForChart = checkedDirectValue
						} else {
							valueToPushForChart = currentSeriesLastValidValue
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
