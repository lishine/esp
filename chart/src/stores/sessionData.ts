import { defineStore } from 'pinia'
import { ofetch, FetchError } from 'ofetch'

// Centralized Series Configuration
export const CANONICAL_SERIES_CONFIG = [
	{ displayName: 'Bat current', internalId: 'esc_i', sensorType: 'esc', dataKey: 'i', unit: 'A', decimals: 2 },
	{ displayName: 'Motor current', internalId: 'mc_i', sensorType: 'mc', dataKey: 'value', unit: 'A', decimals: 2 }, // Assuming 'mc' data is {"value": X} or just X. If just X, dataKey can be null/undefined and handled in extractor.
	{ displayName: 'TEsc', internalId: 'esc_t', sensorType: 'esc', dataKey: 't', unit: '°C', decimals: 0 },
	{
		displayName: 'TAmbient',
		internalId: 'ds_ambient',
		sensorType: 'ds',
		dataKey: 'ambient',
		unit: '°C',
		decimals: 1,
	},
	{ displayName: 'TAlum', internalId: 'ds_alum', sensorType: 'ds', dataKey: 'alum', unit: '°C', decimals: 1 },
	{ displayName: 'TMosfet', internalId: 'ds_mosfet', sensorType: 'ds', dataKey: 'mosfet', unit: '°C', decimals: 1 },
	{ displayName: 'Speed', internalId: 'gps_speed', sensorType: 'gps', dataKey: 'speed', unit: 'km/h', decimals: 2 },
	{ displayName: 'RPM', internalId: 'esc_rpm', sensorType: 'esc', dataKey: 'rpm', unit: '', decimals: 0 },
	{ displayName: 'Throttle', internalId: 'th_val', sensorType: 'th', dataKey: 'value', unit: '', decimals: 0 }, // Assuming 'th' data is {"value": X} or just X.
	{ displayName: 'V', internalId: 'esc_v', sensorType: 'esc', dataKey: 'v', unit: 'V', decimals: 2 },
] as const // Use 'as const' for stricter typing and readonly properties

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
	restart?: string // Added restart field
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
				// Initialize default visibility based on CANONICAL_SERIES_CONFIG
				// and what's actually available in the processed chart data.
				const availableSeriesNamesInChartData = new Set(this.getChartFormattedData.series.map((s) => s.name))

				CANONICAL_SERIES_CONFIG.forEach((config) => {
					if (availableSeriesNamesInChartData.has(config.displayName)) {
						this.visibleSeries.add(config.displayName)
					}
				})
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
				// metadata = JSON.parse(lines[0]) as SessionMetadata // Old way
				const parsedFirstLine = JSON.parse(lines[0])
				metadata = {
					device_description: parsedFirstLine.device_description,
					fan_enabled: parsedFirstLine.fan_enabled,
					ds_associations: parsedFirstLine.ds_associations,
					date: parsedFirstLine.date,
					restart: parsedFirstLine.restart, // Parse restart
				}
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

		async fetchSessionData(prevOffset?: number) {
			// Added optional prevOffset parameter
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
					`Fetching data from: ${apiUrl} (DEV: ${String(import.meta.env.DEV)}, useUserApiIp: ${String(this.useUserApiIp)}, userApiIp: ${this.userApiIp}, prevOffset: ${prevOffset})`
				)

				const fetchOptions: RequestInit = {
					// Changed to RequestInit for broader compatibility if needed
					method: 'POST',
					// parseResponse: (txt) => txt, // ofetch specific, handle response directly
					// retry: 3, // ofetch specific
					// retryDelay: 500, // ofetch specific
					// timeout: 10000, // ofetch specific
					// onRequestError: ({ error }) => { // ofetch specific
					// 	console.error('Request error:', error)
					// 	throw error
					// },
					// onResponseError: ({ response }) => { // ofetch specific
					// 	console.error('Response error:', response.status, response._data)
					// 	throw new Error(`API error: ${response.status.toString()}`)
					// },
				}

				if (prevOffset && prevOffset > 0) {
					fetchOptions.body = JSON.stringify({ prev: prevOffset })
					fetchOptions.headers = { 'Content-Type': 'application/json' }
				}

				// Using ofetch's direct options for retry and error handling
				const response = await ofetch(apiUrl, {
					...fetchOptions, // Spread our constructed options
					parseResponse: (txt) => txt, // Keep as text since we handle JSONL parsing
					retry: 3, // ofetch specific retry
					retryDelay: 500,
					timeout: 10000, // Set fetch timeout to 10 seconds
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

			// Helper function to apply range checks using internal IDs
			const applyRangeChecks = (internalId: string, value: number | null, entry?: LogEntry): number | null => {
				if (value === null || typeof value !== 'number' || isNaN(value)) return null

				let checkedValue: number | null = value // Allow null
				if (internalId === 'esc_rpm') {
					if (checkedValue < 0 || checkedValue > 30000) checkedValue = null // Adjusted RPM max based on typical values
				} else if (internalId === 'esc_v') {
					if (checkedValue < 30 || checkedValue > 55) checkedValue = null
				} else if (internalId === 'esc_i') {
					if (checkedValue < 0 || checkedValue > 200) checkedValue = null
				} else if (internalId === 'esc_t') {
					if (checkedValue < 10 || checkedValue > 120) checkedValue = null
				} else if (internalId === 'mc_i') {
					// Motor current internal ID
					if (checkedValue < 0 || checkedValue > 200) checkedValue = null
				} else if (internalId === 'th_val') {
					// Throttle internal ID
					if (checkedValue < 990 || checkedValue > 2050) checkedValue = null // Adjusted throttle max
				} else if (internalId.startsWith('ds_')) {
					// DS Temp internal ID prefix
					if (checkedValue < -10 || checkedValue > 60) checkedValue = null // Adjusted DS temp min
				} else if (internalId === 'gps_speed' && entry) {
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

			// 2. Build series configurations from CANONICAL_SERIES_CONFIG
			// This ensures that we only attempt to process series that are defined.
			const activeSeriesConfigs = CANONICAL_SERIES_CONFIG.map((canonConfig) => {
				// For DS sensors, the dataKey might vary (e.g. 'Ambient', 'alum').
				// For other sensors, dataKey is fixed (e.g. 'rpm', 'speed').
				// 'value' is a placeholder for direct numeric values (mc, th).
				let valueExtractorFn: (entry: LogEntry) => number | undefined | null

				if (canonConfig.sensorType === 'esc') {
					valueExtractorFn = (entry: LogEntry) =>
						(entry.v as EscValues)[canonConfig.dataKey as keyof EscValues]
				} else if (canonConfig.sensorType === 'gps') {
					valueExtractorFn = (entry: LogEntry) => {
						const gpsEntry = entry.v as GpsValues
						const val = gpsEntry[canonConfig.dataKey as keyof GpsValues]
						if (canonConfig.internalId === 'gps_speed') {
							if (!gpsEntry.fix || typeof val !== 'number') {
								// Ensure fix is true and val is number
								return null // No valid speed if no fix or val is not a number
							}
							return val * 1.852 // Convert knots to km/h
						}
						// For other GPS properties that might be boolean (like 'fix' itself if charted)
						// or other types, they should be handled or filtered by CANONICAL_SERIES_CONFIG
						// to only include chartable numeric data.
						return typeof val === 'number' ? val : null
					}
				} else if (canonConfig.sensorType === 'ds') {
					valueExtractorFn = (entry: LogEntry) => (entry.v as DsValues)[canonConfig.dataKey]
				} else if (canonConfig.sensorType === 'mc' || canonConfig.sensorType === 'th') {
					// Assuming 'mc' and 'th' log entries have 'v' as the direct numeric value
					valueExtractorFn = (entry: LogEntry) => entry.v as number
				} else {
					valueExtractorFn = () => undefined // Should not happen with valid config
				}

				return {
					seriesName: canonConfig.displayName,
					internalId: canonConfig.internalId,
					sensorName: canonConfig.sensorType, // Renamed from sensorType to sensorName for consistency with LogEntry.n
					valueExtractor: valueExtractorFn,
				}
			}).filter((config) =>
				// Only include configs for which there's any relevant data in logEntries
				state.logEntries.some((logEntry) => logEntry.n === config.sensorName)
			)

			// 3. Process data for each series
			activeSeriesConfigs.forEach((config) => {
				// Create a temporary map for the current sensor's data: timestamp -> value
				const sensorDataMap = new Map<number, number | null>()
				const sensorEntries = new Map<number, LogEntry>() // To store entry for range checks if needed

				state.logEntries.forEach((entry) => {
					if (entry.n === config.sensorName) {
						const value = config.valueExtractor(entry)
						if (typeof value === 'number') {
							sensorDataMap.set(entry.preciseTimestamp.getTime(), value)
							if (config.internalId === 'gps_speed') {
								// Check against internalId
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
					const entryForCheck = config.internalId === 'gps_speed' ? sensorEntries.get(tsMillis) : undefined

					let valueToPushForChart: number | null
					let checkedDirectValue: number | null = null // Declare checkedDirectValue here

					if (directValue !== undefined) {
						// A data point (value or explicit null) exists for this sensor at this tsMillis
						checkedDirectValue = applyRangeChecks(
							config.internalId, // Use internalId for range check logic
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
