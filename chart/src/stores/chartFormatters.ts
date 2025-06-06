import type { LogEntry, ChartSeriesData, FormattedChartData, GpsValues, EscValues, DsValues } from './types'
import { CANONICAL_SERIES_CONFIG } from './seriesConfig'
import type { SeriesConfig } from './seriesConfig' // Import SeriesConfig for casting
// import { haversineDistance } from '../utils/gpsDistance' // Removed as it's no longer used
import { applyRangeChecks } from './rangeChecks'
// import { calculateEfficiencySeries } from '../utils/calcSeries' // Removed import

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
	gps_speed?: number | null // Speed in km/h (value from log, converted and interpolated)
	gps_hdg?: number | null // GPS heading
	// Raw DS values
	ds_ambient?: number | null
	ds_alum?: number | null
	ds_mosfet?: number | null
	// Raw MC value
	mc_i_raw?: number | null // Raw motor current before multiplication
	mc_i?: number | null // Motor current after multiplication
	// Raw Throttle value
	th_val?: number | null
	// Calculated values (wh_per_km and w_per_speed removed)
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
					if (gpsVals.speed !== undefined && gpsVals.speed !== null) {
						dp.gps_speed = gpsVals.speed * 1.852 // Convert to km/h immediately
					} else if (gpsVals.speed === null) {
						dp.gps_speed = null // Explicitly set to null if source is null
					}
					if (gpsVals.hdg !== undefined) dp.gps_hdg = gpsVals.hdg
					// console.log(`After initial set, ts: ${tsMillis}, dp.gps_speed: ${dp.gps_speed}`);
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

		// 3a. Perform initial direct calculations (e.g., mc_i from mc_i_raw)
		// This ensures that values are prepared before attempting linear interpolation.
		sortedUniqueTimestampMillis.forEach((tsMillis) => {
			const dp = getOrCreateDataPoint(dataPointsMap, tsMillis)

			// Calculate mc_i from mc_i_raw if available
			if (dp.mc_i_raw !== null && dp.mc_i_raw !== undefined) {
				dp.mc_i = dp.mc_i_raw * 1.732
			} else {
				// If mc_i_raw is not available, ensure dp.mc_i is null to be a candidate for interpolation.
				// This handles cases where mc_i might have been set by some other means or is undefined.
				if (dp.mc_i === undefined || (dp.mc_i !== null && dp.mc_i_raw === undefined)) {
					dp.mc_i = null
				}
			}
			// gps_speed is already converted to km/h during initial aggregation (lines 80-84).
			// Other direct, non-interpolating calculations would go here.
			// Ensure all other potentially interpolated fields are null if not set by raw data
			CANONICAL_SERIES_CONFIG.forEach((sConfig) => {
				const key = sConfig.internalId as keyof AggregatedDataPoint
				if (dp[key] === undefined) {
					dp[key] = null
				}
			})
		})

		// 3b. Apply Linear Interpolation
		const MAX_INTERPOLATION_WINDOW_MS = 5000

		CANONICAL_SERIES_CONFIG.forEach((sConfig) => {
			const key = sConfig.internalId as keyof AggregatedDataPoint

			// Collect all existing actual (non-null) data points for the current series
			// from the dataPointsMap after initial aggregation and pre-calculations.
			const existingData: { ts: number; val: number }[] = []
			sortedUniqueTimestampMillis.forEach((ts) => {
				const dp = dataPointsMap.get(ts)
				if (dp) {
					const val = dp[key] as number | null | undefined // Value could be from raw data or mc_i calculation
					if (val !== null && val !== undefined) {
						existingData.push({ ts, val })
					}
				}
			})

			// If not enough data points for interpolation for this series,
			// ensure all points for this series in dataPointsMap are null unless they have raw data.
			if (existingData.length < 2) {
				// Handles 0 or 1 existing data points
				const singlePointTs = existingData.length === 1 ? existingData[0].ts : null
				// const singlePointVal = existingData.length === 1 ? existingData[0].val : null; // Value is already in dp if ts matches

				sortedUniqueTimestampMillis.forEach((tsMillis) => {
					const dp = getOrCreateDataPoint(dataPointsMap, tsMillis)
					if (singlePointTs === tsMillis) {
						// If there's one existing point and this is its timestamp,
						// dp[key] should already hold existingData[0].val.
						// If it was somehow undefined, it should take that value.
						// If it was null (e.g. from pre-calc), it should take that value.
						// This ensures the single point is preserved.
						if (dp[key] === null || dp[key] === undefined) {
							// Should ideally not be needed if existingData was built correctly
							dp[key] = existingData.length === 1 ? existingData[0].val : null
						}
					} else {
						// For all other timestamps, or if no existing data points, set to null.
						dp[key] = null
					}
				})
				return // Move to the next series config
			}

			let prevPointSearchIdx = 0 // Tracks the index in existingData for the previous known point

			sortedUniqueTimestampMillis.forEach((tsMillis) => {
				const dp = getOrCreateDataPoint(dataPointsMap, tsMillis)
				const currentValue = dp[key]

				// Advance prevPointSearchIdx to the latest point in existingData whose timestamp is <= tsMillis
				// but only if it's not the last point in existingData.
				while (
					prevPointSearchIdx < existingData.length - 1 &&
					existingData[prevPointSearchIdx + 1].ts <= tsMillis
				) {
					prevPointSearchIdx++
				}

				if (currentValue !== null && currentValue !== undefined) {
					// Value already exists (from raw data or pre-calculation like mc_i),
					// no interpolation needed for this specific point.
					return // to next tsMillis for this series
				}

				// Current value is null or undefined, attempt to interpolate.
				let t_prev: number | null = null
				let v_prev: number | null = null
				let t_next: number | null = null
				let v_next: number | null = null

				// prevPointSearchIdx is the index of the latest entry in existingData
				// such that existingData[prevPointSearchIdx].ts <= tsMillis.

				// Determine t_prev: the actual data point strictly before tsMillis
				if (existingData[prevPointSearchIdx].ts < tsMillis) {
					t_prev = existingData[prevPointSearchIdx].ts
					v_prev = existingData[prevPointSearchIdx].val
				} else {
					// existingData[prevPointSearchIdx].ts === tsMillis (or tsMillis could be before the first point if prevPointSearchIdx is 0)
					// We need the point strictly before tsMillis.
					if (prevPointSearchIdx > 0) {
						// If there's a point before existingData[prevPointSearchIdx]
						// This point existingData[prevPointSearchIdx - 1] is guaranteed to be < existingData[prevPointSearchIdx].ts
						// If existingData[prevPointSearchIdx].ts == tsMillis, then existingData[prevPointSearchIdx-1].ts < tsMillis
						// If existingData[prevPointSearchIdx].ts > tsMillis (i.e. tsMillis is before first point), then this condition is still fine.
						if (existingData[prevPointSearchIdx - 1].ts < tsMillis) {
							// Double check it's strictly less
							t_prev = existingData[prevPointSearchIdx - 1].ts
							v_prev = existingData[prevPointSearchIdx - 1].val
						}
					}
					// If prevPointSearchIdx is 0 and existingData[0].ts >= tsMillis, no t_prev exists.
				}

				// Determine t_next: the actual data point strictly after tsMillis
				// existingData[prevPointSearchIdx].ts <= tsMillis
				if (existingData[prevPointSearchIdx].ts === tsMillis) {
					// If the floor point IS tsMillis, t_next is the one after it (if it exists)
					if (prevPointSearchIdx + 1 < existingData.length) {
						t_next = existingData[prevPointSearchIdx + 1].ts
						v_next = existingData[prevPointSearchIdx + 1].val
					}
				} else {
					// existingData[prevPointSearchIdx].ts < tsMillis
					// t_next is also existingData[prevPointSearchIdx + 1] (if it exists),
					// as it's the first point after existingData[prevPointSearchIdx]
					if (prevPointSearchIdx + 1 < existingData.length) {
						t_next = existingData[prevPointSearchIdx + 1].ts
						v_next = existingData[prevPointSearchIdx + 1].val
					}
				}
				// The above t_next logic can be simplified:
				// The candidate for t_next is always existingData[prevPointSearchIdx + 1] if it exists
				// OR existingData[prevPointSearchIdx] if tsMillis is before the first point and prevPointSearchIdx is 0.

				// Refined t_next logic:
				if (prevPointSearchIdx + 1 < existingData.length) {
					// Standard case: point after floor
					t_next = existingData[prevPointSearchIdx + 1].ts
					v_next = existingData[prevPointSearchIdx + 1].val
					// Ensure this t_next is strictly greater than tsMillis
					if (t_next !== null && t_next <= tsMillis) {
						// Should not happen if while loop for prevPointSearchIdx is correct
						t_next = null
						v_next = null
					}
				} else if (existingData[prevPointSearchIdx].ts > tsMillis) {
					// Case: tsMillis is before the very first point in existingData.
					// prevPointSearchIdx is 0. existingData[0].ts > tsMillis.
					// So, existingData[0] is t_next.
					t_next = existingData[prevPointSearchIdx].ts
					v_next = existingData[prevPointSearchIdx].val
				}
				// Otherwise, no t_next (e.g., tsMillis is after the last point).

				if (t_prev !== null && v_prev !== null && t_next !== null && v_next !== null) {
					// Ensure t_prev < tsMillis < t_next for valid interpolation range.
					if (
						tsMillis > t_prev &&
						tsMillis < t_next &&
						t_next - t_prev > 0 &&
						t_next - t_prev <= MAX_INTERPOLATION_WINDOW_MS
					) {
						const interpolatedValue = v_prev + (v_next - v_prev) * ((tsMillis - t_prev) / (t_next - t_prev))
						dp[key] = interpolatedValue
					} else {
						dp[key] = null
					}
				} else {
					dp[key] = null
				}
			})
		})

		// 4. Prepare data maps for calculateEfficiencySeries - REMOVED
		// const escVMap = new Map<number, number | null>()
		// const escIMap = new Map<number, number | null>()
		// const escMahMap = new Map<number, number | null>()
		// const gpsLatMap = new Map<number, number | null>()
		// const gpsLonMap = new Map<number, number | null>()
		// const gpsSpeedMap = new Map<number, number | null>() // This will be in km/h, interpolated

		// sortedUniqueTimestampMillis.forEach((tsMillis) => {
		// 	const dp = dataPointsMap.get(tsMillis)
		// 	if (dp) {
		// 		escVMap.set(tsMillis, dp.esc_v ?? null)
		// 		escIMap.set(tsMillis, dp.esc_i ?? null) // Assuming esc_i is battery current after any processing
		// 		escMahMap.set(tsMillis, dp.esc_mah ?? null)
		// 		gpsLatMap.set(tsMillis, dp.gps_lat ?? null)
		// 		gpsLonMap.set(tsMillis, dp.gps_lon ?? null)
		// 		gpsSpeedMap.set(tsMillis, dp.gps_speed ?? null)
		// 	} else {
		// 		escVMap.set(tsMillis, null)
		// 		escIMap.set(tsMillis, null)
		// 		escMahMap.set(tsMillis, null)
		// 		gpsLatMap.set(tsMillis, null)
		// 		gpsLonMap.set(tsMillis, null)
		// 		gpsSpeedMap.set(tsMillis, null)
		// 	}
		// })

		// Call the new calculation function - REMOVED
		// const { whPerKmMap, wPerSpeedMap } = calculateEfficiencySeries(
		// 	{ escVMap, escIMap, escMahMap, gpsLatMap, gpsLonMap, gpsSpeedMap },
		// 	sortedUniqueTimestampMillis,
		// 	haversineDistance
		// )

		// 5. Format data for ECharts
		const finalSeries: ChartSeriesData[] = []
		CANONICAL_SERIES_CONFIG.forEach((config) => {
			// Filter out series if their sensorType was not found at all in logEntries (initial filter)
			// For 'calculated' series, they depend on other sensors, so we don't filter them here based on sensorName.
			// They will just have null data if dependencies are missing. - 'calculated' type removed
			if (
				// config.sensorType !== 'calculated' && // 'calculated' type removed from config
				!this.logEntries.some((logEntry) => logEntry.n === config.sensorType)
			) {
				return
			}

			const seriesChartData: Array<[Date, number | null]> = []
			sortedUniqueTimestampMillis.forEach((tsMillis) => {
				const dp = dataPointsMap.get(tsMillis)
				let value: number | null | undefined = null

				if (dp) {
					// dp might still be useful for other non-calculated series
					// Removed wh_per_km and w_per_speed
					if (config.internalId === 'gps_speed') {
						value = dp.gps_speed // Display km/h, already calculated and interpolated
					} else if (config.internalId === 'gps_hdg') {
						// Apply range check for heading here, after interpolation
						value =
							dp.gps_hdg !== null && dp.gps_hdg !== undefined
								? applyRangeChecks('gps_hdg', dp.gps_hdg)
								: null
					} else if (config.internalId === 'mc_i') value = dp.mc_i
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
				...((config as SeriesConfig).color && { color: (config as SeriesConfig).color }), // Add color if defined in config
			})
		})

		console.log('------ Final Series for ECharts:', finalSeries)
		console.timeEnd('getChartFormattedData')
		return { series: finalSeries }
	},
}

// Removed hasValidDataWithin5Seconds helper function as it's no longer used with linear interpolation.
