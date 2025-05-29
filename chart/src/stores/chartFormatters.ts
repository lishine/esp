import type { LogEntry, ChartSeriesData, FormattedChartData } from './types'
import { BATTERY_CURRENT_THRESHOLD_AMPS } from './sessionDataStore'
import { CANONICAL_SERIES_CONFIG } from './seriesConfig'
import type { GpsValues, EscValues, DsValues } from './types'

export interface ChartFormatterContext {
	logEntries: LogEntry[]
	filterSeriesByBatCurrent: boolean
}

export const chartFormatters = {
	getChartFormattedData(this: ChartFormatterContext): FormattedChartData {
		if (this.logEntries.length === 0) {
			return { series: [] }
		}
		console.time('getChartFormattedData')

		let culledLogEntries: LogEntry[] = [...this.logEntries]

		// Step 1: Pre-filter logEntries based on ESC Current
		if (this.filterSeriesByBatCurrent) {
			const escCurrentPerSecond = new Map<number, number | null>()
			// Determine the last ESC current for each second
			this.logEntries.forEach((entry) => {
				if (entry.n === 'esc') {
					const escValues = entry.v as EscValues
					const escIValue = escValues.i !== undefined ? escValues.i : null
					escCurrentPerSecond.set(entry.preciseTimestamp.getTime(), escIValue)
				}
			})

			// Get all unique 1-second timestamps present in the original log
			const sortedOriginalSecondTimestamps = Array.from(
				new Set(this.logEntries.map((entry) => entry.preciseTimestamp.getTime()))
			).sort((a, b) => a - b)

			const isSecondNullified = new Map<number, boolean>()
			let shouldCurrentlyNullifyState = false

			sortedOriginalSecondTimestamps.forEach((tsMillis) => {
				const currentEscI = escCurrentPerSecond.get(tsMillis)
				if (currentEscI !== null && currentEscI !== undefined) {
					if (currentEscI < BATTERY_CURRENT_THRESHOLD_AMPS) {
						shouldCurrentlyNullifyState = true
					} else if (currentEscI > BATTERY_CURRENT_THRESHOLD_AMPS) {
						shouldCurrentlyNullifyState = false
					}
					// If currentEscI is exactly BATTERY_CURRENT_THRESHOLD_AMPS, shouldCurrentlyNullifyState remains unchanged
				}
				// If currentEscI is null or undefined (e.g., a second with no ESC data but other data),
				// shouldCurrentlyNullifyState also remains unchanged, propagating the previous state.
				isSecondNullified.set(tsMillis, shouldCurrentlyNullifyState)
			})

			culledLogEntries = this.logEntries.filter((entry) => {
				const secondOfEntry = entry.preciseTimestamp.getTime()
				// If the second is marked for nullification, filter out the entry
				return !(isSecondNullified.get(secondOfEntry) || false)
			})
		}

		if (culledLogEntries.length === 0) {
			console.timeEnd('getChartFormattedData')
			return { series: [] }
		}

		// Step 2: Main Chart Data Formatting (using culledLogEntries)
		type ProcessedPoint = {
			chartTimestamp: number
			sensorName: string
			dataKey: string
			value: number | null
		}
		const processedPoints: ProcessedPoint[] = []
		const escSubSecondCounts = new Map<number, { total: number; current: number }>()

		// First pass over culledLogEntries to count ESC entries per second for sub-second timing
		culledLogEntries.forEach((entry) => {
			if (entry.n === 'esc') {
				const originalSecondTs = entry.preciseTimestamp.getTime()
				if (!escSubSecondCounts.has(originalSecondTs)) {
					escSubSecondCounts.set(originalSecondTs, { total: 0, current: 0 })
				}
				escSubSecondCounts.get(originalSecondTs)!.total++
			}
		})

		// Second pass over culledLogEntries to create processedPoints with sub-second timestamps for ESC
		culledLogEntries.forEach((entry) => {
			const originalSecondTs = entry.preciseTimestamp.getTime()
			let chartTs = originalSecondTs

			if (entry.n === 'esc') {
				const escTiming = escSubSecondCounts.get(originalSecondTs)
				if (escTiming && escTiming.total > 0) {
					// Ensure offset is within 0-999 to stay within the original second
					const millisecondOffset =
						escTiming.total === 1 ? 0 : Math.floor((escTiming.current / escTiming.total) * 999)
					chartTs = originalSecondTs + millisecondOffset
					escTiming.current++
				}
				const escValues = entry.v as EscValues
				for (const key in escValues) {
					if (Object.prototype.hasOwnProperty.call(escValues, key)) {
						const value = escValues[key as keyof EscValues]
						processedPoints.push({
							chartTimestamp: chartTs,
							sensorName: entry.n,
							dataKey: key,
							value: typeof value === 'number' ? value : null,
						})
					}
				}
			} else if (entry.n === 'gps') {
				const gpsValues = entry.v as GpsValues
				for (const key in gpsValues) {
					// We handle 'fix' separately during series generation for gps_speed
					if (Object.prototype.hasOwnProperty.call(gpsValues, key) && key !== 'fix') {
						const value = gpsValues[key as keyof Omit<GpsValues, 'fix'>]
						processedPoints.push({
							chartTimestamp: chartTs, // GPS uses original second timestamp
							sensorName: entry.n,
							dataKey: key,
							value: typeof value === 'number' ? value : null,
						})
					}
				}
			} else if (entry.n === 'ds') {
				const dsValues = entry.v as DsValues
				for (const key in dsValues) {
					if (Object.prototype.hasOwnProperty.call(dsValues, key)) {
						const value = dsValues[key]
						processedPoints.push({
							chartTimestamp: chartTs, // DS uses original second timestamp
							sensorName: entry.n,
							dataKey: key,
							value: typeof value === 'number' ? value : null,
						})
					}
				}
			} else if (entry.n === 'mc' || entry.n === 'th') {
				const value = entry.v as number | null
				// Find the canonical config to get the dataKey, as mc/th have simple values
				const sensorConfig = CANONICAL_SERIES_CONFIG.find((c) => c.sensorType === entry.n)
				if (sensorConfig) {
					processedPoints.push({
						chartTimestamp: chartTs, // MC/TH uses original second timestamp
						sensorName: entry.n,
						dataKey: sensorConfig.dataKey, // e.g. 'current' for mc_i, 'temp' for th_temp
						value: typeof value === 'number' ? value : null,
					})
				}
			}
		})

		const finalUniqueChartTimestamps = Array.from(new Set(processedPoints.map((p) => p.chartTimestamp))).sort(
			(a, b) => a - b
		)

		if (finalUniqueChartTimestamps.length === 0) {
			// This can happen if culledLogEntries was not empty but resulted in no processable points
			// (e.g. only GPS 'fix' data, or all values were non-numeric for selected series)
			// Or if culledLogEntries was empty to begin with.
			if (culledLogEntries.length > 0) {
				console.warn(
					'No final unique chart timestamps to plot, though culled log entries existed. Culled entries:',
					culledLogEntries.length
				)
			}
			console.timeEnd('getChartFormattedData')
			return { series: [] }
		}

		const activeSeriesConfigs = CANONICAL_SERIES_CONFIG.filter((config) =>
			// A series is active if its sensorType and dataKey combination exists in processedPoints
			processedPoints.some((p) => p.sensorName === config.sensorType && p.dataKey === config.dataKey)
		)

		const finalSeries: ChartSeriesData[] = []
		// For GPS speed logic, we need quick access to the GpsValues (especially 'fix') for each original second
		const gpsFixDataPerSecond = new Map<number, GpsValues>()
		culledLogEntries.forEach((entry) => {
			if (entry.n === 'gps') {
				gpsFixDataPerSecond.set(entry.preciseTimestamp.getTime(), entry.v as GpsValues)
			}
		})

		activeSeriesConfigs.forEach((config) => {
			const seriesDataMap = new Map<number, number | null>()
			processedPoints.forEach((p) => {
				if (p.sensorName === config.sensorType && p.dataKey === config.dataKey) {
					seriesDataMap.set(p.chartTimestamp, p.value)
				}
			})

			const seriesChartData: Array<[Date, number | null]> = []
			let lastValidValueForInterpolation: number | null = null
			// GPS speed needs its own interpolation memory due to 'fix' dependency
			let lastValidSpeedWithFixForInterpolation: number | null = null

			finalUniqueChartTimestamps.forEach((ts) => {
				let pointValue: number | null = null
				const originalSecondOfTs = Math.floor(ts / 1000) * 1000 // Get the original second for this point

				if (seriesDataMap.has(ts)) {
					pointValue = seriesDataMap.get(ts)! // Direct value from processedPoints

					// Apply series-specific transformations
					if (config.internalId === 'mc_i' && pointValue !== null) {
						pointValue = pointValue * 1.732
					} else if (config.internalId === 'gps_speed') {
						const gpsForThisSecond = gpsFixDataPerSecond.get(originalSecondOfTs)
						const hasGpsFix = gpsForThisSecond?.fix || false

						if (!hasGpsFix) {
							pointValue = null // No speed if no fix in this original second
							lastValidSpeedWithFixForInterpolation = null // Reset interpolation memory for speed
						} else if (pointValue !== null) {
							// Speed value exists (from seriesDataMap) AND fix is true
							pointValue = pointValue * 1.852 // Knots to km/h
						}
						// If pointValue was null from seriesDataMap but fix is true, it remains null (no data for speed)
					}
					// Update interpolation memory if we got a valid, non-null point
					if (pointValue !== null) {
						lastValidValueForInterpolation = pointValue
						if (config.internalId === 'gps_speed') {
							// Only update if it wasn't nulled by fix
							lastValidSpeedWithFixForInterpolation = pointValue
						}
					}
				} else {
					// Interpolate
					if (config.internalId === 'gps_speed') {
						const gpsForThisSecond = gpsFixDataPerSecond.get(originalSecondOfTs)
						const hasGpsFix = gpsForThisSecond?.fix || false
						if (!hasGpsFix) {
							pointValue = null // Don't interpolate speed if no fix in the original second of this interpolated point
						} else {
							pointValue = lastValidSpeedWithFixForInterpolation
						}
					} else {
						pointValue = lastValidValueForInterpolation
					}
				}
				seriesChartData.push([new Date(ts), pointValue])
			})

			finalSeries.push({
				name: config.displayName,
				type: 'line',
				data: seriesChartData,
				showSymbol: false,
				connectNulls: false, // Important: do not connect across nulls created by filtering or no fix
			})
		})

		console.timeEnd('getChartFormattedData')
		return { series: finalSeries }
	},
}
