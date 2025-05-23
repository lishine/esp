import { defineStore } from 'pinia'
import { ofetch, FetchError } from 'ofetch'

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
	date: string // Added date field
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
			let metadata: SessionMetadata | null = null
			try {
				metadata = JSON.parse(lines[0]) as SessionMetadata
				this.sessionMetadata = metadata
			} catch (e) {
				console.error('Failed to parse session metadata:', e)
				this.error = 'Failed to parse session metadata.'
				this.sessionMetadata = null
				// If metadata parsing fails, we cannot proceed with log entries as date is needed
				return
			}

			if (!metadata.date) {
				console.error('Metadata is missing or does not contain date.')
				this.error = 'Metadata is missing or does not contain date.'
				this.sessionMetadata = null
				this.logEntries = []
				return
			}

			const sessionDate = metadata.date // "YYYY-MM-DD"

			// Parse log entries (remaining lines)
			const rawLogEntryArrays: Array<Array<Omit<LogEntry, 'preciseTimestamp'>>> = []
			for (let i = 1; i < lines.length; i++) {
				const line = lines[i].trim()
				if (line === '') continue
				try {
					// Each line is now an array of log entries
					const entriesInLine = JSON.parse(line) as Array<Omit<LogEntry, 'preciseTimestamp'>>
					rawLogEntryArrays.push(entriesInLine)
				} catch (e) {
					console.error('Failed to parse log entry array line:', line, e)
				}
			}

			// Flatten the array of arrays and group entries by their original timestamp string
			const entriesWithPreciseTimestamp: LogEntry[] = []
			const entriesByTimestamp = new Map<string, Array<Omit<LogEntry, 'preciseTimestamp'>>>()

			rawLogEntryArrays.forEach((entryArray) => {
				if (entryArray.length === 0) return

				// The first object in the array contains the timestamp
				const timestampEntry = entryArray[0]
				if (!timestampEntry.t) {
					console.error('Skipping line due to missing timestamp:', entryArray)
					return
				}
				const timestampKey = timestampEntry.t // "HH-MM-SS"

				// The remaining objects are the actual log entries for this timestamp
				const logEntriesForTimestamp = entryArray.slice(1)

				if (!entriesByTimestamp.has(timestampKey)) {
					entriesByTimestamp.set(timestampKey, [])
				}
				const groupForKey = entriesByTimestamp.get(timestampKey)
				if (groupForKey) {
					groupForKey.push(...logEntriesForTimestamp)
				}
			})

			// Process each group to assign preciseTimestamps
			// Iterate over sorted timestamps to maintain order
			const sortedTimestamps = Array.from(entriesByTimestamp.keys()).sort()

			sortedTimestamps.forEach((timestampKey) => {
				const group = entriesByTimestamp.get(timestampKey)
				if (!group) return // Should not happen if key came from map keys

				const countInSecond = group.length
				const msIncrement = countInSecond > 0 ? 1000 / countInSecond : 0

				group.forEach((entry, index) => {
					// Construct Date object using sessionDate and the timestampKey (HH-MM-SS)
					// sessionDate is "YYYY-MM-DD", timestampKey is "HH-MM-SS"
					const formattedTimePart = timestampKey.replace(/-/g, ':') // "HH:MM:SS"
					const isoTimestampStr = `${sessionDate}T${formattedTimePart}`
					const baseDate = new Date(isoTimestampStr + 'Z') // Parse as UTC

					if (isNaN(baseDate.getTime())) {
						console.error(
							'Invalid date parsed for entry:',
							entry,
							'from date:',
							sessionDate,
							'and timestampKey:',
							timestampKey
						)
						// Skip this entry or handle error appropriately
						return
					}

					const ms = Math.floor(index * msIncrement) // Correctly uses index within the group
					baseDate.setUTCMilliseconds(ms)

					entriesWithPreciseTimestamp.push({
						...entry,
						t: timestampKey, // Keep the original timestamp string
						preciseTimestamp: baseDate,
					} as LogEntry) // Cast to LogEntry
				})
			})

			// Sort all entries by their new preciseTimestamp (already mostly sorted by processing sorted timestamps, but a final sort is safer)
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
				const response = await ofetch('http://10.100.102.6/api/data', {
					method: 'POST',
					parseResponse: (txt) => txt, // Keep as text since we handle JSONL parsing
					retry: 3,
					retryDelay: 500,
					timeout: 5000,
					onRequestError: ({ error }) => {
						console.error('Request error:', error)
						throw error
					},
					onResponseError: ({ response }) => {
						console.error('Response error:', response.status, response._data)
						throw new Error(`API error: ${response.status.toString()}`)
					},
				})
				this._parseSessionData(response)
			} catch (err) {
				console.error('Error fetching or parsing session data:', err)
				if (err instanceof FetchError) {
					this.error = `Network error: ${err.message}`
				} else {
					this.error = err instanceof Error ? err.message : 'An unknown error occurred'
				}
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
