// Centralized Series Configuration
export const CANONICAL_SERIES_CONFIG = [
	{ displayName: 'Bat current', internalId: 'esc_i', sensorType: 'esc', dataKey: 'i', unit: 'A', decimals: 2 },
	{ displayName: 'Motor current', internalId: 'mc_i', sensorType: 'mc', dataKey: 'value', unit: 'A', decimals: 2 },
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
	{ displayName: 'Throttle', internalId: 'th_val', sensorType: 'th', dataKey: 'value', unit: '', decimals: 0 },
	{ displayName: 'V', internalId: 'esc_v', sensorType: 'esc', dataKey: 'v', unit: 'V', decimals: 2 },
	{ displayName: 'mAh', internalId: 'esc_mah', sensorType: 'esc', dataKey: 'mah', unit: 'mAh', decimals: 0 },
	{
		displayName: 'Heading',
		internalId: 'gps_hdg',
		sensorType: 'gps',
		dataKey: 'hdg',
		unit: '°',
		decimals: 0,
		color: '#20B2AA' /* LightSeaGreen */,
	},
] as const

export interface SeriesConfig {
	displayName: string
	internalId: string
	sensorType: string
	dataKey: string
	unit: string
	decimals: number
	yAxisIndex?: number
	color?: string
}

export type CanonicalSeriesConfig = (typeof CANONICAL_SERIES_CONFIG)[number]
