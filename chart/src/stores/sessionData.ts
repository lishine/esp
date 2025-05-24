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
	state: () => {
		let storedUserApiIp = ''
		if (typeof localStorage !== 'undefined') {
			storedUserApiIp = localStorage.getItem('espChartUserApiIp') || ''
		}

		let storedUseUserApiIp = false
		if (typeof localStorage !== 'undefined') {
			const useIpStr = localStorage.getItem('espChartUseUserApiIp')
			storedUseUserApiIp = useIpStr === 'true'
		}

		return {
			sessionMetadata: null as SessionMetadata | null,
			logEntries: [] as LogEntry[],
			isLoading: false,
			error: null as string | null,
			// New state for user-configurable IP, loaded from localStorage
			userApiIp: storedUserApiIp,
			useUserApiIp: storedUseUserApiIp,
			visibleSeries: new Set<string>(), // Initialize with all series visible by default, or load from localStorage
		}
	},

	actions: {
		// Action to load visibility preferences from localStorage
		loadVisibilityPreferences() {
			if (typeof localStorage !== 'undefined') {
				const storedVisibility = localStorage.getItem('espChartVisibleSeries')
				if (storedVisibility) {
					try {
						const visibleArray = JSON.parse(storedVisibility)
						this.visibleSeries = new Set(visibleArray)
					} catch (e) {
						console.error('Failed to parse visible series from localStorage:', e)
						// If parsing fails, visibleSeries remains an empty Set.
						// initializeDefaultVisibility will be called later in _parseSessionData if needed.
						this.visibleSeries = new Set<string>()
					}
				} else {
					// If nothing in localStorage, visibleSeries remains an empty Set.
					// initializeDefaultVisibility will be called later in _parseSessionData if needed.
					this.visibleSeries = new Set<string>()
				}
			} else {
				// If localStorage is not available, visibleSeries remains an empty Set.
				this.visibleSeries = new Set<string>()
			}
		},

		// Action to save visibility preferences to localStorage
		saveVisibilityPreferences() {
			if (typeof localStorage !== 'undefined') {
				localStorage.setItem('espChartVisibleSeries', JSON.stringify(Array.from(this.visibleSeries)))
			}
		},

		initializeDefaultVisibility() {
			// This method should only be called AFTER logEntries are populated.
			// It sets all available series to visible if visibleSeries is currently empty.
			if (this.logEntries.length > 0 && this.visibleSeries.size === 0) {
				console.log('Initializing default visibility: making all series visible.')
				// Logic to get all potential series names directly from logEntries/configs
				// This mirrors the series name generation in getChartFormattedData's seriesConfigs
				const allPotentialSeriesNames = new Set<string>()

				// ESC Metrics
				;(['rpm', 'v', 'i', 't'] as Array<keyof EscValues>).forEach((key) =>
					allPotentialSeriesNames.add(`ESC ${key.toUpperCase()}`)
				)
				// MC (Motor Current)
				if (this.logEntries.some((entry) => entry.n === 'mc')) {
					allPotentialSeriesNames.add('Motor Current')
				}
				// TH (Throttle)
				if (this.logEntries.some((entry) => entry.n === 'th')) {
					allPotentialSeriesNames.add('Throttle')
				}
				// GPS Speed
				if (this.logEntries.some((entry) => entry.n === 'gps')) {
					allPotentialSeriesNames.add('GPS Speed')
				}
				// DS (Temperature Sensors)
				const dsSensorKeys = new Set<string>()
				this.logEntries.forEach((entry) => {
					if (entry.n === 'ds') {
						const dsValue = entry.v as DsValues
						Object.keys(dsValue).forEach((key) => dsSensorKeys.add(key))
					}
				})
				Array.from(dsSensorKeys).forEach((key) => {
					allPotentialSeriesNames.add(`DS Temp ${key}`)
				})

				allPotentialSeriesNames.forEach((name) => this.visibleSeries.add(name))
				this.saveVisibilityPreferences() // Persist this default
			}
		},

		toggleSeries(seriesName: string) {
			const isVisible = this.visibleSeries.has(seriesName)
			this.setSeriesVisibility(seriesName, !isVisible)
		},

		toggleAllSeries(visible: boolean) {
			const allSeriesNames = this.getChartFormattedData.series.map((s) => s.name)
			if (visible) {
				allSeriesNames.forEach((name) => this.visibleSeries.add(name))
			} else {
				this.visibleSeries.clear()
			}
			this.saveVisibilityPreferences()
		},

		setSeriesVisibility(seriesName: string, visible: boolean) {
			if (visible) {
				this.visibleSeries.add(seriesName)
			} else {
				this.visibleSeries.delete(seriesName)
			}
			this.saveVisibilityPreferences()
		},

		setUserApiIp(ip: string) {
			this.userApiIp = ip.trim()
			if (typeof localStorage !== 'undefined') {
				localStorage.setItem('espChartUserApiIp', this.userApiIp)
			}
		},
		setUseUserApiIp(use: boolean) {
			this.useUserApiIp = use
			if (typeof localStorage !== 'undefined') {
				localStorage.setItem('espChartUseUserApiIp', String(use))
			}
		},
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
			// After parsing data, if visibleSeries is still empty (i.e., nothing from localStorage),
			// initialize default visibility based on the now-parsed data.
			if (this.visibleSeries.size === 0 && this.logEntries.length > 0) {
				this.initializeDefaultVisibility()
			}
		},

		async fetchSessionData() {
			this.loadVisibilityPreferences() // Load preferences at the start of fetching data
			this.isLoading = true
			this.error = null
			this.sessionMetadata = null
			this.logEntries = []

			try {
				let protocol = 'https'
				let effectiveIp = '192.168.4.1' // Default for production/remote

				if (import.meta.env.DEV) {
					// Development mode (localhost)
					protocol = 'http'
					// Default IP for dev as per your request, can be overridden by user input
					effectiveIp = '192.168.4.1'
				}

				if (this.useUserApiIp && this.userApiIp) {
					// Validate userApiIp roughly (not a full validation)
					if (this.userApiIp.match(/^(\d{1,3}\.){3}\d{1,3}$/) || this.userApiIp.includes(':')) {
						// Allow host:port
						effectiveIp = this.userApiIp
						// Protocol for user IP might need to be smarter or also user-configurable
						// For now, if user provides IP, assume it matches the dev/prod protocol context
					} else {
						console.warn('Invalid custom IP format, using default:', this.userApiIp)
						// Stick to default effectiveIp based on DEV/PROD
					}
				}

				const apiUrl = `${protocol}://${effectiveIp}/api/data`
				console.log(
					`Fetching data from: ${apiUrl} (DEV: ${String(import.meta.env.DEV)}, useUserApiIp: ${String(this.useUserApiIp)}, userApiIp: ${this.userApiIp})`
				)

				const response = await ofetch(apiUrl, {
					method: 'POST',
					parseResponse: (txt) => txt, // Keep as text since we handle JSONL parsing
					retry: 3,
					retryDelay: 500,
					timeout: 50000,
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
		getVisibleSeries: (state) => Array.from(state.visibleSeries),
		// Other getters like getUniqueSensorNames, getEntriesBySensorName remain.
		// getEscRpmHistory would need an update to use preciseTimestamp if it were actively used for charting.

		getChartFormattedData: (state): FormattedChartData => {
			if (state.logEntries.length === 0) {
				return { series: [] }
			}
			// Removed fallback logic to modify state.visibleSeries from the getter.
			// Visibility should be handled by actions and `loadVisibilityPreferences`.

			console.time('getChartFormattedData')

			// 1. Collect all unique preciseTimestamps and sort them
			const uniqueTimestampMillis = new Set<number>()
			state.logEntries.forEach((entry) => {
				uniqueTimestampMillis.add(entry.preciseTimestamp.getTime())
			})
			const sortedUniqueTimestampMillis = Array.from(uniqueTimestampMillis).sort((a, b) => a - b)

			const finalSeries: ChartSeriesData[] = []

			// Helper function to apply range checks
			const applyRangeChecks = (name: string, value: number | null, entry?: LogEntry): number | null => {
				if (value === null || typeof value !== 'number' || isNaN(value)) return null

				let checkedValue: number | null = value // Allow null
				if (name === 'ESC RPM') {
					if (checkedValue < 0 || checkedValue > 3000) checkedValue = null
				} else if (name === 'ESC Voltage') {
					if (checkedValue < 30 || checkedValue > 55) checkedValue = null
				} else if (name === 'ESC Current') {
					if (checkedValue < 0 || checkedValue > 200) checkedValue = null
				} else if (name === 'ESC Temp') {
					if (checkedValue < 10 || checkedValue > 120) checkedValue = null
				} else if (name === 'Motor Current') {
					if (checkedValue < 0 || checkedValue > 200) checkedValue = null
				} else if (name === 'Throttle') {
					if (checkedValue < 990 || checkedValue > 1500) checkedValue = null
				} else if (name.startsWith('DS Temp ')) {
					if (checkedValue < 10 || checkedValue > 60) checkedValue = null
				} else if (name === 'GPS Speed' && entry) {
					const gpsValues = entry.v as GpsValues
					if (!gpsValues.fix || value === null || typeof value !== 'number' || isNaN(value)) {
						checkedValue = null // No fix or invalid initial value
					} else {
						const speedInKmh = value * 1.852 // Convert knots to km/h
						// Apply range check to km/h value
						if (speedInKmh < 0 || speedInKmh > 35) {
							// Adjusted upper range for km/h if 20 was for kts
							checkedValue = null
						} else {
							checkedValue = speedInKmh
						}
					}
				}
				return checkedValue
			}

			// 2. Define series configurations
			const seriesConfigs = [
				// ESC Metrics
				...(['rpm', 'v', 'i', 't'] as Array<keyof EscValues>).map((key) => ({
					seriesName: `ESC ${key.toUpperCase()}`, // e.g., ESC RPM
					sensorName: 'esc',
					valueExtractor: (entry: LogEntry) => (entry.v as EscValues)[key],
				})),
				// MC (Motor Current)
				{
					seriesName: 'Motor Current',
					sensorName: 'mc',
					valueExtractor: (entry: LogEntry) => entry.v as number,
				},
				// TH (Throttle)
				{
					seriesName: 'Throttle',
					sensorName: 'th',
					valueExtractor: (entry: LogEntry) => entry.v as number,
				},
				// GPS Speed
				{
					seriesName: 'GPS Speed',
					sensorName: 'gps',
					valueExtractor: (entry: LogEntry) => (entry.v as GpsValues).speed,
				},
				// Add other GPS metrics here if needed, similar to ESC metrics
			]

			// DS (Temperature Sensors) - dynamically add them
			const dsSensorKeys = new Set<string>()
			state.logEntries.forEach((entry) => {
				if (entry.n === 'ds') {
					const dsValue = entry.v as DsValues
					Object.keys(dsValue).forEach((key) => dsSensorKeys.add(key))
				}
			})
			Array.from(dsSensorKeys).forEach((key) => {
				seriesConfigs.push({
					seriesName: `DS Temp ${key}`,
					sensorName: 'ds',
					valueExtractor: (entry: LogEntry) => (entry.v as DsValues)[key],
				})
			})

			// 3. Process data for each series
			seriesConfigs.forEach((config) => {
				// Create a temporary map for the current sensor's data: timestamp -> value
				const sensorDataMap = new Map<number, number | null>()
				const sensorEntries = new Map<number, LogEntry>() // To store entry for range checks if needed

				state.logEntries.forEach((entry) => {
					if (entry.n === config.sensorName) {
						const value = config.valueExtractor(entry)
						if (typeof value === 'number') {
							sensorDataMap.set(entry.preciseTimestamp.getTime(), value)
							if (config.seriesName === 'GPS Speed') {
								// Store entry for GPS fix check
								sensorEntries.set(entry.preciseTimestamp.getTime(), entry)
							}
						} else {
							// Catches both null and undefined if not a number
							sensorDataMap.set(entry.preciseTimestamp.getTime(), null)
						}
					}
				})

				const seriesChartData: Array<[Date, number | null]> = []
				let currentSeriesLastValidValue: number | null = null // Initialize last valid value for the series

				sortedUniqueTimestampMillis.forEach((tsMillis) => {
					const directValue = sensorDataMap.get(tsMillis) // Raw value for this sensor at this tsMillis
					const entryForCheck = config.seriesName === 'GPS Speed' ? sensorEntries.get(tsMillis) : undefined

					let valueToPushForChart: number | null

					if (directValue !== undefined) {
						// A data point (value or explicit null) exists for this sensor at this tsMillis
						const checkedDirectValue = applyRangeChecks(
							config.seriesName,
							directValue, // directValue could be a number or an actual null from the source data
							entryForCheck
						)

						if (checkedDirectValue !== null) {
							// If the direct value, after checking, is valid (not null)
							currentSeriesLastValidValue = checkedDirectValue // Update the last known valid value
							valueToPushForChart = checkedDirectValue // Use this valid direct value for the chart
						} else {
							// The direct value was invalid (became null after check) or was originally null.
							// For the chart point, use the previously known valid value.
							valueToPushForChart = currentSeriesLastValidValue
						}
					} else {
						// No data point at all for this sensor at this specific tsMillis
						// Use the last known valid value.
						valueToPushForChart = currentSeriesLastValidValue
					}
					seriesChartData.push([new Date(tsMillis), valueToPushForChart])
				})

				finalSeries.push({
					name: config.seriesName,
					type: 'line',
					data: seriesChartData,
					showSymbol: false,
				})
			})
			console.timeEnd('getChartFormattedData')
			return { series: finalSeries }
		},
	},
})
