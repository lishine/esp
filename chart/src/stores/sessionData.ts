import { defineStore } from 'pinia'
// The import for mock data remains, but its content will change
import mockFullSessionDataRaw from './mockSessionData.jsonl?raw'

// Value types for different sensors
export interface EscValues {
	rpm: number
	mah: number
	t: number // Temperature
	i: number // Current
	v: number // Voltage
}

export interface GpsValues {
	seen: number
	active: number
	fix: boolean
	lon?: number
	speed?: number
	lat?: number
	alt?: number
	hdg?: number
}

// For DS sensors, 'v' is an object with dynamic keys (aq, bq, etc.)
export interface DsValues {
	[key: string]: number
}

// Union type for the 'v' field in a log entry
export type LogEntryValue = EscValues | GpsValues | DsValues | number

// Structure for a single log entry
export interface LogEntry {
	r: string // run id or similar
	t: string // timestamp part (original string form)
	n: string // sensor name
	v: LogEntryValue // sensor value(s)
	preciseTimestamp: Date // New precise timestamp
}

// Structure for ECharts data
export interface ChartSeriesData {
	name: string // e.g., "ESC RPM", "DS Temp AQ"
	type: 'line'
	data: Array<[Date, number | null]> // Array of [Date_object, value]
	yAxisIndex?: number // Optional: if using multiple y-axes
	showSymbol?: boolean // Optional: for line charts
}

export interface FormattedChartData {
	series: ChartSeriesData[]
}

// Structure for DS18B20 sensor associations in metadata
export interface DsAssociation {
	name: string // e.g., "aq"
	address: string // sensor's unique address
}

// Structure for the session metadata (first line of data)
export interface SessionMetadata {
	device_description: string
	fan_enabled: boolean
	ds_associations: DsAssociation[]
}

export const useSessionDataStore = defineStore('sessionData', {
	state: () => ({
		sessionMetadata: null as SessionMetadata | null,
		logEntries: [] as LogEntry[],
		isLoading: false,
		error: null as string | null,
	}),

	actions: {
		_parseSessionData(fullDataString: string) {
			const lines = fullDataString.trim().split('\n')
			if (lines.length === 0) {
				this.error = 'No data received.'
				this.sessionMetadata = null
				this.logEntries = []
				return
			}

			// Parse metadata (first line)
			try {
				this.sessionMetadata = JSON.parse(lines[0]) as SessionMetadata
			} catch (e) {
				console.error('Failed to parse session metadata:', e)
				this.error = 'Failed to parse session metadata.'
				this.sessionMetadata = null
			}

			// Parse log entries (remaining lines)
			// Use Omit to initially parse without preciseTimestamp, as it's derived
			const rawLogEntries: Array<Omit<LogEntry, 'preciseTimestamp'>> = []
			for (let i = 1; i < lines.length; i++) {
				const line = lines[i].trim()
				if (line === '') continue
				try {
					rawLogEntries.push(JSON.parse(line) as Omit<LogEntry, 'preciseTimestamp'>)
				} catch (e) {
					console.error('Failed to parse log entry line:', line, e)
				}
			}

			const entriesWithPreciseTimestamp: LogEntry[] = []
			const groups = new Map<string, Array<Omit<LogEntry, 'preciseTimestamp'>>>()

			// Group entries by their original r and t key
			for (const entry of rawLogEntries) {
				const key = `${entry.r}_${entry.t}` // Group by run and original timestamp string
				if (!groups.has(key)) {
					groups.set(key, [])
				}
				const groupForKey = groups.get(key)
				if (groupForKey) {
					groupForKey.push(entry)
				}
			}

			// Process each group to assign preciseTimestamps
			for (const group of groups.values()) {
				// Iterate over groups
				const countInSecond = group.length
				// Ensure msIncrement is well-defined even for empty group (though shouldn't happen if group was added)
				const msIncrement = countInSecond > 0 ? 1000 / countInSecond : 0

				group.forEach((entry, index) => {
					// Construct Date object from entry.t
					// "YYYY-MM-DD_HH-MM-SS" -> "YYYY-MM-DDTHH:MM:SSZ" for UTC parsing
					// entry.t is "YYYY-MM-DD_HH-MM-SS"
					// We need "YYYY-MM-DDTHH:MM:SS" for Date parsing
					const parts = entry.t.split('_')
					const datePart = parts[0]
					const timePart = parts[1] // "HH-MM-SS"
					const formattedTimePart = timePart.replace(/-/g, ':') // "HH:MM:SS"
					const isoTimestampStr = `${datePart}T${formattedTimePart}`
					const baseDate = new Date(isoTimestampStr + 'Z') // Parse as UTC

					if (isNaN(baseDate.getTime())) {
						console.error('Invalid date parsed for entry:', entry, 'from t:', entry.t)
						// Skip this entry or handle error appropriately
						return
					}

					const ms = Math.floor(index * msIncrement) // Correctly uses index within the group
					baseDate.setUTCMilliseconds(ms)

					entriesWithPreciseTimestamp.push({
						...entry,
						preciseTimestamp: baseDate,
					} as LogEntry) // Cast to LogEntry
				})
			}

			// Sort all entries by their new preciseTimestamp
			entriesWithPreciseTimestamp.sort((a, b) => a.preciseTimestamp.getTime() - b.preciseTimestamp.getTime())

			console.log(
				'Sorted preciseTimestamps (first 5):',
				entriesWithPreciseTimestamp.slice(0, 5).map((e) => e.preciseTimestamp.toISOString())
			)
			console.log(
				'Sorted preciseTimestamps (last 5):',
				entriesWithPreciseTimestamp.slice(-5).map((e) => e.preciseTimestamp.toISOString())
			)
			console.log('Total entries: ' + entriesWithPreciseTimestamp.length.toString())

			this.logEntries = entriesWithPreciseTimestamp
		},

		async fetchSessionData() {
			this.isLoading = true
			this.error = null
			this.sessionMetadata = null
			this.logEntries = []

			try {
				await new Promise((resolve) => setTimeout(resolve, 100)) // Simulate network delay (reduced for testing)
				this._parseSessionData(mockFullSessionDataRaw)
			} catch (err) {
				console.error('Error fetching or parsing session data:', err)
				this.error = err instanceof Error ? err.message : 'An unknown error occurred during fetch/parse'
			} finally {
				this.isLoading = false
			}
		},
	},

	getters: {
		getMetadata: (state) => state.sessionMetadata,
		getLogEntries: (state) => state.logEntries,
		// Other getters like getUniqueSensorNames, getEntriesBySensorName remain.
		// getEscRpmHistory would need an update to use preciseTimestamp if it were actively used for charting.

		getChartFormattedData: (state): FormattedChartData => {
			// The `|| state.logEntries.length === 0` is redundant if `!state.logEntries` is true.
			// However, state.logEntries is initialized as `[] as LogEntry[]`, so it's never null/undefined.
			// The correct check is just for length.
			if (state.logEntries.length === 0) {
				return { series: [] }
			}

			// Collect all unique preciseTimestamps (as Date objects) and sort them
			const uniqueTimestampValues = new Set<number>() // Store time as number for uniqueness
			state.logEntries.forEach((entry) => {
				// entry.preciseTimestamp is guaranteed to exist here due to the parsing logic
				// and the LogEntry interface.
				uniqueTimestampValues.add(entry.preciseTimestamp.getTime())
			})

			const sortedUniqueTimestamps: Date[] = Array.from(uniqueTimestampValues)
				.sort((a, b) => a - b) // Sort numbers (timestamps)
				.map((time) => new Date(time)) // Convert back to Date objects

			const series: ChartSeriesData[] = []

			// Helper function to create a series
			const createSeries = (
				name: string,
				sensorName: string,
				valueExtractor: (entry: LogEntry) => number | null | undefined
			): ChartSeriesData => {
				const data: Array<[Date, number | null]> = []
				for (const tsDate of sortedUniqueTimestamps) {
					// Find the first entry for this sensor at this precise timestamp.
					const entry = state.logEntries.find(
						(e) =>
							// e.preciseTimestamp is guaranteed by LogEntry type
							e.preciseTimestamp.getTime() === tsDate.getTime() && e.n === sensorName
					)

					let value: number | null = null
					if (entry) {
						const rawValueFromExtractor = valueExtractor(entry)

						if (typeof rawValueFromExtractor === 'number' && !isNaN(rawValueFromExtractor)) {
							let processedValue: number | null = rawValueFromExtractor

							// Apply range checks based on the series 'name'
							if (name === 'ESC RPM') {
								if (processedValue < 0 || processedValue > 3000) processedValue = null
							} else if (name === 'ESC Voltage') {
								if (processedValue < 30 || processedValue > 55) processedValue = null
							} else if (name === 'ESC Current') {
								if (processedValue < 0 || processedValue > 200) processedValue = null
							} else if (name === 'ESC Temp') {
								if (processedValue < 10 || processedValue > 120) processedValue = null
							} else if (name === 'Motor Current') {
								if (processedValue < 0 || processedValue > 200) processedValue = null
							} else if (name === 'Throttle') {
								if (processedValue < 990 || processedValue > 1500) processedValue = null
							} else if (name.startsWith('DS Temp ')) {
								// e.g., "DS Temp aq"
								if (processedValue < 10 || processedValue > 60) processedValue = null
							} else if (name === 'GPS Speed') {
								const gpsValues = entry.v as GpsValues // Assuming entry.v is GpsValues if name is 'GPS Speed'
								if (!gpsValues.fix) {
									processedValue = null // No fix, speed is invalid
								} else {
									// Fix is true, check range for the extracted speed (which is rawValueFromExtractor)
									if (rawValueFromExtractor < 0 || rawValueFromExtractor > 20) {
										processedValue = null
									}
									// else processedValue remains rawValueFromExtractor (valid and in range or already nulled by extractor)
								}
							}
							// Note: ESC mAh range is 0-15000, not currently charted as a separate series.
							// else if (name === 'ESC mAh') {
							//   if (processedValue < 0 || processedValue > 15000) processedValue = null;
							// }
							value = processedValue
						} else {
							// rawValueFromExtractor is not a valid number (e.g. undefined, null from extractor, or NaN)
							// Ensure GPS Speed is null if !fix, even if rawValueFromExtractor was not a number.
							if (name === 'GPS Speed' && entry.n === 'gps') {
								const gpsValues = entry.v as GpsValues
								if (!gpsValues.fix) {
									value = null
								} else {
									// Fix is true, but speed value itself was not a number (e.g. undefined from extractor)
									value = null
								}
							} else {
								value = null // Default to null for other non-numeric extracted values
							}
						}
					} else {
						// No entry for this sensor at this timestamp
						value = null
					}
					data.push([tsDate, value])
				}
				return { name, type: 'line', data, showSymbol: false }
			}

			// ESC Metrics
			const escMetrics: Array<{ key: keyof EscValues; name: string }> = [
				{ key: 'rpm', name: 'ESC RPM' },
				{ key: 'v', name: 'ESC Voltage' },
				{ key: 'i', name: 'ESC Current' },
				{ key: 't', name: 'ESC Temp' },
			]
			escMetrics.forEach((metric) => {
				series.push(createSeries(metric.name, 'esc', (entry) => (entry.v as EscValues)[metric.key]))
			})

			// MC (Motor Current)
			series.push(createSeries('Motor Current', 'mc', (entry) => entry.v as number))

			// TH (Throttle)
			series.push(createSeries('Throttle', 'th', (entry) => entry.v as number))

			// DS (Temperature Sensors)
			const dsSensorKeys = new Set<string>()
			state.logEntries.forEach((entry) => {
				// entry.v can be EscValues, GpsValues, DsValues, or number.
				// We are interested in DsValues, which is an object.
				// `typeof entry.v === 'object'` is a good check.
				// `entry.v !== null` is also good practice.
				// The linter might be overly aggressive here or there's a subtle type inference.
				// For safety and clarity, keeping the check. If entry.n is 'ds', entry.v should be DsValues.
				if (entry.n === 'ds') {
					// If entry.n is 'ds', TypeScript should infer entry.v as DsValues based on LogEntryValue.
					// DsValues is defined as { [key: string]: number }, so it's an object and not null.
					const dsValue = entry.v as DsValues
					Object.keys(dsValue).forEach((key) => dsSensorKeys.add(key))
				}
			})
			Array.from(dsSensorKeys).forEach((key) => {
				series.push(createSeries(`DS Temp ${key}`, 'ds', (entry) => (entry.v as DsValues)[key]))
			})

			// GPS Metrics
			// GPS Speed is handled first due to its special defaulting logic
			series.push(
				createSeries('GPS Speed', 'gps', (entry) => {
					// The core logic for GPS speed (defaulting to 0) is inside createSeries.
					// This extractor just provides the raw speed if available.
					return (entry.v as GpsValues).speed
				})
			)

			// const otherGpsMetrics: Array<{
			// 	key: keyof GpsValues
			// 	name: string
			// 	condition?: (v: GpsValues) => boolean
			// }> = [
			// 	{ key: 'alt', name: 'GPS Altitude', condition: (v) => v.fix },
			// 	{ key: 'seen', name: 'GPS Satellites Seen' },
			// 	{ key: 'active', name: 'GPS Satellites Active' },
			// 	// hdg could be added if needed
			// ]

			// otherGpsMetrics.forEach((metric) => {
			// 	series.push(
			// 		createSeries(metric.name, 'gps', (entry) => {
			// 			const gpsValues = entry.v as GpsValues
			// 			if (metric.condition && !metric.condition(gpsValues)) {
			// 				return null // Condition not met (e.g., no fix for alt)
			// 			}
			// 			const val = gpsValues[metric.key]
			// 			return typeof val === 'number' ? val : null
			// 		})
			// 	)
			// })
			return { series }
		},
	},
})
