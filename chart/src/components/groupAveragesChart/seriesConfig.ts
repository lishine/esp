export const GROUP_AVERAGE_SERIES_CONFIG = [
	{
		displayName: 'Avg Bat Current',
		internalId: 'avg_current', // Match dataKey
		dataKey: 'avg_current',
		unit: 'A',
		decimals: 2,
		color: '#FF5733',
		yAxisIndex: 0,
	},
	{
		displayName: 'Avg Motor Current',
		internalId: 'avg_motor_current', // Match dataKey
		dataKey: 'avg_motor_current',
		unit: 'A',
		decimals: 2,
		color: '#33FF57',
		yAxisIndex: 0,
	},
	{
		displayName: 'Avg RPM',
		internalId: 'avg_rpm', // Match dataKey
		dataKey: 'avg_rpm',
		unit: 'RPM', // Added unit
		decimals: 0,
		color: '#3357FF',
		yAxisIndex: 1,
	},
	{
		displayName: 'Avg Speed',
		internalId: 'avg_speed_kmh', // Match dataKey
		dataKey: 'avg_speed_kmh',
		unit: 'km/h',
		decimals: 2,
		color: '#FF33A1',
		yAxisIndex: 2,
	},
	{
		displayName: 'Avg Voltage',
		internalId: 'avg_volt',
		dataKey: 'avg_volt',
		unit: 'V',
		decimals: 2,
		color: '#C70039',
		yAxisIndex: 3,
	},
	{
		displayName: 'Avg Throttle',
		internalId: 'avg_throttle',
		dataKey: 'avg_throttle',
		unit: '',
		decimals: 1,
		color: '#FFC300',
		yAxisIndex: 4,
	},
	{
		displayName: 'Motor/Bat Current Efficiency',
		internalId: 'motor_battery_current_efficiency',
		dataKey: 'motor_battery_current_efficiency',
		unit: '',
		decimals: 1,
		color: '#581845',
		yAxisIndex: 6,
	},
	{
		displayName: 'Wh/km',
		internalId: 'watt-hour_per_km',
		dataKey: 'watt-hour_per_km',
		unit: '',
		decimals: 1,
		color: '#DAF7A6',
		yAxisIndex: 7,
	},
	{
		displayName: 'Watt/Speed',
		internalId: 'watt_per_speed',
		dataKey: 'watt_per_speed',
		unit: '',
		decimals: 1,
		color: '#A6F7DA',
		yAxisIndex: 8,
	},
	{
		displayName: 'Distance',
		internalId: 'distance_km',
		dataKey: 'distance_km',
		unit: 'km',
		decimals: 2,
		color: '#33FFBD',
		yAxisIndex: 9,
	},
	{
		displayName: 'Duration',
		internalId: 'duration_s',
		dataKey: 'duration_s',
		unit: 's',
		decimals: 0,
		color: '#33D4FF',
		yAxisIndex: 10,
	},
] as const

export type GroupAverageSeriesConfig = (typeof GROUP_AVERAGE_SERIES_CONFIG)[number]
