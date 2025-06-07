export const GROUP_AVERAGE_SERIES_CONFIG = [
	{
		displayName: 'Avg Bat Current',
		internalId: 'avg_esc_i', // Keep internalId for consistency if used elsewhere
		dataKey: 'avg_current', // Align with metrics key
		unit: 'A',
		decimals: 2,
		color: '#FF5733',
		yAxisIndex: 0,
	},
	{
		displayName: 'Avg Motor Current',
		internalId: 'avg_mc_i', // Keep internalId
		dataKey: 'avg_motor_current', // Align with metrics key
		unit: 'A',
		decimals: 2,
		color: '#33FF57',
		yAxisIndex: 0,
	},
	{
		displayName: 'Avg RPM',
		internalId: 'avg_esc_rpm', // Keep internalId
		dataKey: 'avg_rpm', // Align with metrics key
		unit: '',
		decimals: 0,
		color: '#3357FF',
		yAxisIndex: 1,
	},
	{
		displayName: 'Avg Speed',
		internalId: 'avg_gps_speed', // Keep internalId
		dataKey: 'avg_speed_kmh', // Align with metrics key
		unit: 'km/h',
		decimals: 2,
		color: '#FF33A1',
		yAxisIndex: 2,
	},
] as const

export type GroupAverageSeriesConfig = (typeof GROUP_AVERAGE_SERIES_CONFIG)[number]
