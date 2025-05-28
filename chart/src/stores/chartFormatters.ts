import type { LogEntry, ChartSeriesData, FormattedChartData } from './types'
import { BATTERY_CURRENT_THRESHOLD_AMPS } from './sessionDataStore'
import { CANONICAL_SERIES_CONFIG, type SeriesConfig } from './seriesConfig'
import type { GpsValues, EscValues, DsValues } from './types'

const MIN_BAT_DURATION = 3

export interface ChartFormatterContext {
	logEntries: LogEntry[]
	filterSeriesByBatCurrent: boolean // Added for battery current filtering
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
					const escIValue = escValues.i !== undefined ? escValues.i : null
					escISensorDataMap.set(entry.preciseTimestamp.getTime(), escIValue)
				}
			})

			// Apply duration-based filtering to escISensorDataMap
			const minDurationMs = MIN_BAT_DURATION * 1000
			const modifiedEscISensorDataMap = new Map(escISensorDataMap)

			// Find continuous segments above threshold and check their duration
			let segmentStart = -1
			let segmentTimestamps: number[] = []

			for (let i = 0; i < sortedUniqueTimestampMillis.length; i++) {
				const tsMillis = sortedUniqueTimestampMillis[i]
				const escIValue = escISensorDataMap.get(tsMillis)

				if (escIValue !== null && escIValue !== undefined && escIValue > BATTERY_CURRENT_THRESHOLD_AMPS) {
					// Start or continue a segment above threshold
					if (segmentStart === -1) {
						segmentStart = tsMillis
						segmentTimestamps = [tsMillis]
					} else {
						segmentTimestamps.push(tsMillis)
					}
				} else {
					// End of segment above threshold (or no data)
					if (segmentStart !== -1) {
						// Check if segment duration is less than minimum
						const segmentDuration = tsMillis - segmentStart
						if (segmentDuration < minDurationMs) {
							// Mark all timestamps in this segment as below threshold
							segmentTimestamps.forEach((segmentTs) => {
								modifiedEscISensorDataMap.set(segmentTs, BATTERY_CURRENT_THRESHOLD_AMPS - 0.1)
							})
						}
						segmentStart = -1
						segmentTimestamps = []
					}
				}
			}

			// Handle case where segment extends to the end
			if (segmentStart !== -1) {
				const lastTs = sortedUniqueTimestampMillis[sortedUniqueTimestampMillis.length - 1]
				const segmentDuration = lastTs - segmentStart
				if (segmentDuration < minDurationMs) {
					segmentTimestamps.forEach((segmentTs) => {
						modifiedEscISensorDataMap.set(segmentTs, BATTERY_CURRENT_THRESHOLD_AMPS - 0.1)
					})
				}
			}

			// Apply reverse logic: short interruptions below threshold surrounded by above threshold
			segmentStart = -1
			segmentTimestamps = []

			for (let i = 0; i < sortedUniqueTimestampMillis.length; i++) {
				const tsMillis = sortedUniqueTimestampMillis[i]
				const escIValue = modifiedEscISensorDataMap.get(tsMillis)

				if (escIValue !== null && escIValue !== undefined && escIValue <= BATTERY_CURRENT_THRESHOLD_AMPS) {
					// Start or continue a segment below/at threshold
					if (segmentStart === -1) {
						segmentStart = tsMillis
						segmentTimestamps = [tsMillis]
					} else {
						segmentTimestamps.push(tsMillis)
					}
				} else {
					// End of segment below threshold (or no data)
					if (segmentStart !== -1) {
						// Check if this segment is surrounded by above-threshold periods
						const prevIndex = sortedUniqueTimestampMillis.indexOf(segmentTimestamps[0]) - 1
						const nextIndex = i

						const prevValue =
							prevIndex >= 0
								? modifiedEscISensorDataMap.get(sortedUniqueTimestampMillis[prevIndex])
								: null
						const nextValue =
							nextIndex < sortedUniqueTimestampMillis.length
								? modifiedEscISensorDataMap.get(sortedUniqueTimestampMillis[nextIndex])
								: null

						const prevAboveThreshold =
							prevValue !== null && prevValue !== undefined && prevValue > BATTERY_CURRENT_THRESHOLD_AMPS
						const nextAboveThreshold =
							nextValue !== null && nextValue !== undefined && nextValue > BATTERY_CURRENT_THRESHOLD_AMPS

						// Check if segment duration is less than minimum and surrounded by above-threshold values
						const segmentDuration = tsMillis - segmentStart
						if (segmentDuration < minDurationMs && prevAboveThreshold && nextAboveThreshold) {
							// Mark all timestamps in this segment as above threshold
							segmentTimestamps.forEach((segmentTs) => {
								modifiedEscISensorDataMap.set(segmentTs, BATTERY_CURRENT_THRESHOLD_AMPS + 0.1)
							})
						}
						segmentStart = -1
						segmentTimestamps = []
					}
				}
			}

			let shouldCurrentlyNullify = false
			sortedUniqueTimestampMillis.forEach((tsMillis) => {
				const escIValue = modifiedEscISensorDataMap.get(tsMillis)

				if (escIValue !== null && escIValue !== undefined) {
					if (escIValue < BATTERY_CURRENT_THRESHOLD_AMPS) {
						shouldCurrentlyNullify = true
					} else if (escIValue > BATTERY_CURRENT_THRESHOLD_AMPS) {
						shouldCurrentlyNullify = false
					}
					// If escIValue is exactly BATTERY_CURRENT_THRESHOLD_AMPS, shouldCurrentlyNullify remains unchanged
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
							const current = directValue !== undefined ? directValue : null

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
									const checkedSpeedKnots =
										speedKnots !== undefined && speedKnots !== null ? speedKnots : null

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
							const checkedDirectValue = directValue !== undefined ? directValue : null

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
						const current = directValue !== undefined ? directValue : null

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
								const checkedSpeedKnots =
									speedKnots !== undefined && speedKnots !== null ? speedKnots : null

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
						const checkedDirectValue = directValue !== undefined ? directValue : null

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
