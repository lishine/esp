import type { LogFileListItem } from '../services/githubService'

// Value types for different sensors
export interface EscValues {
	rpm: number | null
	mah: number | null
	t: number | null // Temperature
	i: number | null // Current
	v: number | null // Voltage
}

export interface GpsValues {
	seen: number | null
	active: number | null
	fix: boolean | null
	lon?: number | null
	speed?: number | null
	lat?: number | null
	alt?: number | null
	hdg?: number | null
}

// For DS sensors, 'v' is an object with dynamic keys (aq, bq, etc.)
export interface DsValues {
	[key: string]: number | null
}

// Union type for the 'v' field in a log entry
export type LogEntryValue = EscValues | GpsValues | DsValues | (number | null)

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
	connectNulls?: boolean // Optional: to connect null data points
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
	restart: string // Added restart field
}

export interface SessionState {
	sessionMetadata: SessionMetadata
	logEntries: LogEntry[]
	activeEntries: LogEntry[]
	isLoading: boolean
	error: string | null
	userApiIp: string
	useUserApiIp: boolean
	visibleSeries: Set<string>
	gitHubFiles: LogFileListItem[]
	isGitHubListLoading: boolean
	gitHubListError: string | null
	isGitHubFileLoading: boolean
	gitHubFileError: string | null
	currentFileSource: 'local' | 'github' | null
	currentGitHubFileName: string | null
	totalGpsDistance: number
}
