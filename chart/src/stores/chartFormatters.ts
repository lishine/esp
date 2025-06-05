import type { LogEntry, ChartSeriesData, FormattedChartData, GpsValues, EscValues, DsValues } from './types'
import { CANONICAL_SERIES_CONFIG } from './seriesConfig'
import type { SeriesConfig } from './seriesConfig' // Import SeriesConfig for casting
import { haversineDistance } from '../utils/gpsDistance'
import { applyRangeChecks } from './rangeChecks'

// Interface to hold all relevant data for a single timestamp
interface AggregatedDataPoint {
	// Raw ESC values
	esc_v?: number | null
	esc_mah?: number | null
	esc_i?: number | null
	esc_rpm?: number | null
	esc_t?: number | null
	// Raw GPS values
	gps_lat?: number | null
	gps_lon?: number | null
	gps_speed?: number | null // Original speed in knots (value from log)
	gps_speed_kmh?: number | null // Speed converted to km/h (used for display and w_per_speed calc)
	// Raw DS values
	ds_ambient?: number | null
	ds_alum?: number | null
	ds_mosfet?: number | null
	// Raw MC value
	mc_i_raw?: number | null // Raw motor current before multiplication
	mc_i?: number | null // Motor current after multiplication
	// Raw Throttle value
	th_val?: number | null
	// Calculated values
	wh_per_km?: number | null
	w_per_speed?: number | null
}

export interface ChartFormatterContext {
	logEntries: LogEntry[]
}

// Helper to get or create an AggregatedDataPoint for a timestamp
const getOrCreateDataPoint = (map: Map<number, AggregatedDataPoint>, timestamp: number): AggregatedDataPoint => {
	if (!map.has(timestamp)) {
		map.set(timestamp, {})
	}
	return map.get(timestamp)!
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

		// 2. Aggregate all sensor data into dataPointsMap
		const dataPointsMap = new Map<number, AggregatedDataPoint>()

		this.logEntries.forEach((entry) => {
			const tsMillis = entry.preciseTimestamp.getTime()
			const dp = getOrCreateDataPoint(dataPointsMap, tsMillis)

			switch (entry.n) {
				case 'esc':
					const escVals = entry.v as EscValues
					if (escVals.v !== undefined) dp.esc_v = escVals.v
					if (escVals.mah !== undefined) dp.esc_mah = escVals.mah
					if (escVals.i !== undefined) dp.esc_i = escVals.i
					if (escVals.rpm !== undefined) dp.esc_rpm = escVals.rpm
					if (escVals.t !== undefined) dp.esc_t = escVals.t
					break
				case 'gps':
					const gpsVals = entry.v as GpsValues
					if (gpsVals.lat !== undefined) dp.gps_lat = gpsVals.lat
					if (gpsVals.lon !== undefined) dp.gps_lon = gpsVals.lon
					if (gpsVals.speed !== undefined) dp.gps_speed = gpsVals.speed // Store raw knots
					break
				case 'ds':
					const dsVals = entry.v as DsValues
					// Assuming ds_associations in metadata correctly maps keys like 'ambient'
					if (dsVals.ambient !== undefined) dp.ds_ambient = dsVals.ambient
					if (dsVals.alum !== undefined) dp.ds_alum = dsVals.alum
					if (dsVals.mosfet !== undefined) dp.ds_mosfet = dsVals.mosfet
					break
				case 'mc':
					dp.mc_i_raw = entry.v as number
					break
				case 'th':
					dp.th_val = entry.v as number
					break
			}
		})

		// 3. Interpolate and perform initial calculations (like mc_i, gps_speed_kmh)
		// This loop also handles filling gaps for up to 5 seconds
		const tempSensorMapsForInterpolation = new Map<string, Map<number, number | null>>()
		CANONICAL_SERIES_CONFIG.forEach((config) => {
			if (config.sensorType !== 'calculated') {
				// only for non-calculated direct sensor values initially
				tempSensorMapsForInterpolation.set(config.internalId, new Map<number, number | null>())
			}
		})

		sortedUniqueTimestampMillis.forEach((tsMillis) => {
			const dp = getOrCreateDataPoint(dataPointsMap, tsMillis)
			// Populate temp maps for interpolation logic
			CANONICAL_SERIES_CONFIG.forEach((config) => {
				if (config.sensorType !== 'calculated') {
					const map = tempSensorMapsForInterpolation.get(config.internalId)!
					let val: number | null | undefined = undefined
					if (config.sensorType === 'esc')
						val = dp[`esc_${config.dataKey}` as keyof AggregatedDataPoint] as number | null
					else if (config.internalId === 'gps_speed')
						val = dp.gps_speed // use raw knots for gps_speed's own interpolation
					else if (config.sensorType === 'ds')
						val = dp[`ds_${config.dataKey}` as keyof AggregatedDataPoint] as number | null
					else if (config.internalId === 'mc_i') val = dp.mc_i_raw
					else if (config.internalId === 'th_val') val = dp.th_val
					map.set(tsMillis, typeof val === 'number' ? val : null)
				}
			})
		})

		// Apply interpolation and special calculations
		const lastValidValues = new Map<string, number | null>() // Stores last known good value for each series for interpolation
		const lastValidGpsDataTimestamp = new Map<string, number>() // Tracks last timestamp with any GPS data for gps_speed interpolation

		sortedUniqueTimestampMillis.forEach((tsMillis) => {
			const dp = getOrCreateDataPoint(dataPointsMap, tsMillis)

			// mc_i: current * 1.732
			const mcRaw = dp.mc_i_raw
			if (mcRaw !== null && mcRaw !== undefined) {
				dp.mc_i = mcRaw * 1.732
				lastValidValues.set('mc_i', dp.mc_i)
			} else if (
				lastValidValues.has('mc_i') &&
				hasValidDataWithin5Seconds(
					tsMillis,
					tempSensorMapsForInterpolation.get('mc_i')!,
					sortedUniqueTimestampMillis,
					lastValidValues.get('mc_i')!
				)
			) {
				dp.mc_i = lastValidValues.get('mc_i')!
			} else {
				lastValidValues.delete('mc_i') // Clear if no valid data in window
				dp.mc_i = null
			}

			// gps_speed_kmh: speedKnots * 1.852
			const speedKnots = dp.gps_speed
			// const gpsMapForSpeed = tempSensorMapsForInterpolation.get('gps_speed')! // Unused

			if (speedKnots !== null && speedKnots !== undefined) {
				dp.gps_speed_kmh = speedKnots * 1.852
				lastValidValues.set('gps_speed_kmh', dp.gps_speed_kmh)
				if (dp.gps_lat !== undefined && dp.gps_lon !== undefined) {
					// Consider it valid GPS data if lat/lon also present
					lastValidGpsDataTimestamp.set('gps_speed_kmh', tsMillis)
				}
			} else {
				const lastSeenGpsTs = lastValidGpsDataTimestamp.get('gps_speed_kmh')
				if (lastValidValues.has('gps_speed_kmh') && lastSeenGpsTs && tsMillis - lastSeenGpsTs <= 5000) {
					dp.gps_speed_kmh = lastValidValues.get('gps_speed_kmh')!
				} else {
					lastValidValues.delete('gps_speed_kmh')
					lastValidGpsDataTimestamp.delete('gps_speed_kmh')
					dp.gps_speed_kmh = null
				}
			}

			// Interpolate other direct sensor values
			CANONICAL_SERIES_CONFIG.forEach((sConfig) => {
				if (
					sConfig.internalId !== 'mc_i' &&
					sConfig.internalId !== 'gps_speed' &&
					sConfig.sensorType !== 'calculated'
				) {
					const key = sConfig.internalId as keyof AggregatedDataPoint
					let valToProcess: number | null | undefined = undefined

					if (sConfig.sensorType === 'esc')
						valToProcess = dp[`esc_${sConfig.dataKey}` as keyof AggregatedDataPoint] as number | null
					else if (sConfig.sensorType === 'ds')
						valToProcess = dp[`ds_${sConfig.dataKey}` as keyof AggregatedDataPoint] as number | null
					else if (sConfig.sensorType === 'th') valToProcess = dp.th_val

					if (valToProcess !== null && valToProcess !== undefined) {
						dp[key] = valToProcess
						lastValidValues.set(sConfig.internalId, valToProcess)
					} else if (
						lastValidValues.has(sConfig.internalId) &&
						hasValidDataWithin5Seconds(
							tsMillis,
							tempSensorMapsForInterpolation.get(sConfig.internalId)!,
							sortedUniqueTimestampMillis,
							lastValidValues.get(sConfig.internalId)!
						)
					) {
						dp[key] = lastValidValues.get(sConfig.internalId)!
					} else {
						lastValidValues.delete(sConfig.internalId)
						dp[key] = null
					}
				} else if (sConfig.internalId === 'gps_speed') {
					// gps_speed for display is gps_speed_kmh, already handled
					// but we need to ensure dp.gps_speed (knots) is also interpolated if needed by other calcs
					// This specific interpolation logic for raw gps_speed might need refinement if other calcs depend on interpolated knots
				}
			})
		})

		// 4. Calculate Wh/km and W/speed
		for (let i = 0; i < sortedUniqueTimestampMillis.length; i++) {
			const tsMillis = sortedUniqueTimestampMillis[i]
			const currentDp = dataPointsMap.get(tsMillis)

			if (!currentDp) continue

			// Wh/km calculation
			if (i > 0) {
				const prevTsMillis = sortedUniqueTimestampMillis[i - 1]
				const prevDp = dataPointsMap.get(prevTsMillis)

				if (
					prevDp &&
					currentDp.esc_mah !== null &&
					currentDp.esc_mah !== undefined &&
					prevDp.esc_mah !== null &&
					prevDp.esc_mah !== undefined &&
					currentDp.esc_v !== null &&
					currentDp.esc_v !== undefined &&
					prevDp.esc_v !== null &&
					prevDp.esc_v !== undefined &&
					currentDp.gps_lat !== null &&
					currentDp.gps_lat !== undefined &&
					currentDp.gps_lon !== null &&
					currentDp.gps_lon !== undefined &&
					prevDp.gps_lat !== null &&
					prevDp.gps_lat !== undefined &&
					prevDp.gps_lon !== null &&
					prevDp.gps_lon !== undefined
				) {
					const deltaMah = currentDp.esc_mah - prevDp.esc_mah
					if (deltaMah > 0) {
						// Only if mAh increased
						const avgVoltage = (currentDp.esc_v + prevDp.esc_v) / 2
						const energyWh = (avgVoltage * deltaMah) / 1000
						const distanceM = haversineDistance(
							prevDp.gps_lat,
							prevDp.gps_lon,
							currentDp.gps_lat,
							currentDp.gps_lon
						)
						const distanceKm = distanceM / 1000

						if (distanceKm > 0) {
							currentDp.wh_per_km = applyRangeChecks('wh_per_km', energyWh / distanceKm)
						} else {
							currentDp.wh_per_km = null
						}
					} else {
						currentDp.wh_per_km = null
					}
				} else {
					currentDp.wh_per_km = null
				}
			} else {
				currentDp.wh_per_km = null // No previous data point for the first one
			}

			// W/speed calculation
			if (
				currentDp.esc_v !== null &&
				currentDp.esc_v !== undefined &&
				currentDp.esc_i !== null &&
				currentDp.esc_i !== undefined && // Using direct esc_i, assuming it's battery current
				currentDp.gps_speed_kmh !== null &&
				currentDp.gps_speed_kmh !== undefined
			) {
				const powerW = currentDp.esc_v * currentDp.esc_i
				if (currentDp.gps_speed_kmh > 0) {
					currentDp.w_per_speed = applyRangeChecks('w_per_speed', powerW / currentDp.gps_speed_kmh)
				} else {
					currentDp.w_per_speed = null
				}
			} else {
				currentDp.w_per_speed = null
			}
		}

		// 5. Format data for ECharts
		const finalSeries: ChartSeriesData[] = []
		CANONICAL_SERIES_CONFIG.forEach((config) => {
			// Filter out series if their sensorType was not found at all in logEntries (initial filter)
			// For 'calculated' series, they depend on other sensors, so we don't filter them here based on sensorName.
			// They will just have null data if dependencies are missing.
			if (
				config.sensorType !== 'calculated' &&
				!this.logEntries.some((logEntry) => logEntry.n === config.sensorType)
			) {
				return
			}

			const seriesChartData: Array<[Date, number | null]> = []
			sortedUniqueTimestampMillis.forEach((tsMillis) => {
				const dp = dataPointsMap.get(tsMillis)
				let value: number | null | undefined = null

				if (dp) {
					if (config.internalId === 'wh_per_km') value = dp.wh_per_km
					else if (config.internalId === 'w_per_speed') value = dp.w_per_speed
					else if (config.internalId === 'gps_speed')
						value = dp.gps_speed_kmh // Display km/h
					else if (config.internalId === 'mc_i') value = dp.mc_i
					else if (config.sensorType === 'esc')
						value = dp[`esc_${config.dataKey}` as keyof AggregatedDataPoint] as number | null
					else if (config.sensorType === 'ds')
						value = dp[`ds_${config.dataKey}` as keyof AggregatedDataPoint] as number | null
					else if (config.sensorType === 'th') value = dp.th_val
				}
				seriesChartData.push([new Date(tsMillis), typeof value === 'number' ? value : null])
			})

			finalSeries.push({
				name: config.displayName,
				type: 'line',
				data: seriesChartData,
				yAxisIndex: (config as SeriesConfig).yAxisIndex ?? 0, // Default to 0 if not specified
				showSymbol: false,
				connectNulls: false, // Important for calculated data that might have gaps
			})
		})

		console.log('------ Aggregated DataPoints Map:', dataPointsMap)
		console.log('------ Final Series for ECharts:', finalSeries)
		console.timeEnd('getChartFormattedData')
		return { series: finalSeries }
	},
}

// Modified helper function to check if there's valid (non-null) data within the previous 5 seconds
// Now it also considers the last valid value to avoid interpolating from a very old value if current direct value is null
const hasValidDataWithin5Seconds = (
	currentTimestamp: number,
	sensorDataMap: Map<number, number | null>, // This map contains raw values for the specific sensor
	sortedTimestamps: number[],
	lastKnownGoodValue: number | null
): boolean => {
	if (lastKnownGoodValue === null) return false // If there was never a good value, don't interpolate

	const fiveSecondsMs = 5000
	const cutoffTime = currentTimestamp - fiveSecondsMs

	// Check if the last known good value itself was recent enough
	// This requires knowing the timestamp of lastKnownGoodValue, which is complex with current structure.
	// Simpler: check if ANY data point for this sensor was recent.

	for (let i = sortedTimestamps.length - 1; i >= 0; i--) {
		const ts = sortedTimestamps[i]
		if (ts >= currentTimestamp) continue
		if (ts < cutoffTime) break

		const value = sensorDataMap.get(ts) // Check raw data presence
		if (value !== null && value !== undefined) {
			return true // Found a recent raw data point for this sensor
		}
	}
	return false // No recent raw data point found
}
