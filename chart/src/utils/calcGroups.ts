import type { LogEntry, EscValues, GpsValues } from '../stores/types'
import { haversineDistance } from './gpsDistance'

// --- Filtering and Formatting Function ---
const MIN_DURATION_S = 15
const MIN_MAH_DELTA = 100

export interface GroupAggregate {
	mah_delta: number | null // Rounded integer
	km_delta: string | null // Formatted string "Xkm Ym"
	avg_speed_kmh: number | null // 1 decimal place
	avg_v: number | null // 1 decimal place
	avg_i: number | null // Rounded integer
	calculated_wh_per_km: number | null // Rounded integer
	calculated_w_per_speed: number | null // Rounded integer
	duration_s: string | null // Formatted string "mm:ss"
	start_time_str: string | null
	end_time_str: string | null
	entry_count: number
}

// Internal type for raw calculations before formatting and filtering
interface InternalGroupAggregateValues {
	mah_delta: number | null
	km_delta: number | null
	avg_speed_kmh: number | null
	avg_v: number | null
	avg_i: number | null
	calculated_wh_per_km: number | null
	calculated_w_per_speed: number | null
	duration_s: number | null
	start_time_str: string | null
	end_time_str: string | null
	entry_count: number
}

function processGroupToAggregate(group: LogEntry[]): InternalGroupAggregateValues | null {
	if (group.length < 2) {
		return null
	}

	const escEntriesInGroup = group.filter((e) => e.n === 'esc' && e.v) as LogEntry[]
	const gpsEntriesInGroup = group.filter(
		(e) => e.n === 'gps' && e.v && (e.v as GpsValues).lat !== null && (e.v as GpsValues).lon !== null
	) as LogEntry[]

	let firstMah: number | null = null
	for (const entry of escEntriesInGroup) {
		const escV = entry.v as EscValues
		if (escV.mah !== null && escV.mah !== undefined) {
			firstMah = escV.mah
			break
		}
	}

	let lastMah: number | null = null
	for (let i = escEntriesInGroup.length - 1; i >= 0; i--) {
		const entry = escEntriesInGroup[i]
		const escV = entry.v as EscValues
		if (escV.mah !== null && escV.mah !== undefined) {
			lastMah = escV.mah
			break
		}
	}

	const mah_delta = firstMah !== null && lastMah !== null ? lastMah - firstMah : null

	let km_delta: number | null = 0
	if (gpsEntriesInGroup.length < 2) {
		km_delta = null
	} else {
		for (let j = 1; j < gpsEntriesInGroup.length; j++) {
			const p1 = gpsEntriesInGroup[j - 1].v as GpsValues
			const p2 = gpsEntriesInGroup[j].v as GpsValues
			if (p1.lat != null && p1.lon != null && p2.lat != null && p2.lon != null) {
				km_delta += haversineDistance(p1.lat, p1.lon, p2.lat, p2.lon) / 1000
			}
		}
	}

	const speedsKmhRaw = gpsEntriesInGroup
		.map((e) => (e.v as GpsValues).speed)
		.filter((s) => s !== null && s !== undefined) as number[]
	const avg_speed_kmh =
		speedsKmhRaw.length > 0 ? (speedsKmhRaw.reduce((a, b) => a + b, 0) / speedsKmhRaw.length) * 1.852 : null // Assuming speed is in knots

	const voltages = escEntriesInGroup
		.map((e) => (e.v as EscValues).v)
		.filter((v) => v !== null && v !== undefined) as number[]
	const avg_v = voltages.length > 0 ? voltages.reduce((a, b) => a + b, 0) / voltages.length : null

	const currents = escEntriesInGroup
		.map((e) => (e.v as EscValues).i)
		.filter((iVal) => iVal !== null && iVal !== undefined) as number[]
	const avg_i = currents.length > 0 ? currents.reduce((a, b) => a + b, 0) / currents.length : null

	const total_energy_Wh_group = avg_v !== null && mah_delta !== null ? (avg_v * mah_delta) / 1000 : null
	const calculated_wh_per_km =
		km_delta !== null && km_delta > 0 && total_energy_Wh_group !== null && (mah_delta === null || mah_delta > 0)
			? total_energy_Wh_group / km_delta
			: null

	const avg_power_W_group = avg_v !== null && avg_i !== null ? avg_v * avg_i : null
	const calculated_w_per_speed =
		avg_speed_kmh !== null && avg_speed_kmh > 0 && avg_power_W_group !== null
			? avg_power_W_group / avg_speed_kmh
			: null

	const duration_s = (group[group.length - 1].preciseTimestamp.getTime() - group[0].preciseTimestamp.getTime()) / 1000
	const formatTime = (date: Date) =>
		date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
	const start_time_str = formatTime(group[0].preciseTimestamp)
	const end_time_str = formatTime(group[group.length - 1].preciseTimestamp)
	const entry_count = group.length

	return {
		mah_delta,
		km_delta,
		avg_speed_kmh,
		avg_v,
		avg_i,
		calculated_wh_per_km,
		calculated_w_per_speed,
		duration_s,
		start_time_str,
		end_time_str,
		entry_count,
	}
}

// --- Formatting Helper Functions ---
function formatDurationMMSS(totalSeconds: number | null): string | null {
	if (totalSeconds === null || totalSeconds < 0) return null
	const minutes = Math.floor(totalSeconds / 60)
	const seconds = Math.floor(totalSeconds % 60)
	return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function formatKmDeltaString(km: number | null): string | null {
	if (km === null || km < 0) return null
	const kilometers = Math.floor(km)
	const meters = Math.round((km - kilometers) * 1000)
	if (kilometers > 0) {
		return `${kilometers}km ${meters}m`
	}
	return `${meters}m`
}

function filterAndFormatAggregates(rawAggregates: InternalGroupAggregateValues[]): GroupAggregate[] {
	const filtered = rawAggregates.filter((agg) => {
		return (
			agg.duration_s !== null &&
			agg.duration_s >= MIN_DURATION_S &&
			agg.mah_delta !== null &&
			agg.mah_delta >= MIN_MAH_DELTA
		)
	})

	return filtered.map((raw): GroupAggregate => {
		return {
			mah_delta: raw.mah_delta !== null ? Math.round(raw.mah_delta) : null,
			km_delta: formatKmDeltaString(raw.km_delta),
			avg_speed_kmh: raw.avg_speed_kmh !== null ? parseFloat(raw.avg_speed_kmh.toFixed(1)) : null,
			avg_v: raw.avg_v !== null ? parseFloat(raw.avg_v.toFixed(1)) : null,
			avg_i: raw.avg_i !== null ? Math.round(raw.avg_i) : null,
			calculated_wh_per_km: raw.calculated_wh_per_km !== null ? Math.round(raw.calculated_wh_per_km) : null,
			calculated_w_per_speed: raw.calculated_w_per_speed !== null ? Math.round(raw.calculated_w_per_speed) : null,
			duration_s: formatDurationMMSS(raw.duration_s),
			start_time_str: raw.start_time_str,
			end_time_str: raw.end_time_str,
			entry_count: raw.entry_count,
		}
	})
}

export function calculateGroupAggregates(entriesToGroup: LogEntry[]): GroupAggregate[] {
	const groups: LogEntry[][] = []
	if (entriesToGroup.length === 0) {
		return []
	}

	let currentGroupStartIndex = 0
	let lastNonNullEscCurrentEntryIndex = -1

	for (let i = 0; i < entriesToGroup.length; i++) {
		const entry = entriesToGroup[i]
		if (
			entry.n === 'esc' &&
			entry.v &&
			(entry.v as EscValues).i !== null &&
			(entry.v as EscValues).i !== undefined
		) {
			if (lastNonNullEscCurrentEntryIndex !== -1) {
				const prevNonNullEscEntry = entriesToGroup[lastNonNullEscCurrentEntryIndex]
				const timeDiffSeconds =
					(entry.preciseTimestamp.getTime() - prevNonNullEscEntry.preciseTimestamp.getTime()) / 1000

				if (timeDiffSeconds >= 5) {
					let allIntermediateEscCurrentsNull = true
					for (let k = lastNonNullEscCurrentEntryIndex + 1; k < i; k++) {
						const intermediateEntry = entriesToGroup[k]
						if (
							intermediateEntry.n === 'esc' &&
							intermediateEntry.v &&
							(intermediateEntry.v as EscValues).i !== null &&
							(intermediateEntry.v as EscValues).i !== undefined
						) {
							allIntermediateEscCurrentsNull = false
							break
						}
					}
					if (allIntermediateEscCurrentsNull) {
						const group = entriesToGroup.slice(currentGroupStartIndex, lastNonNullEscCurrentEntryIndex + 1)
						if (group.length > 0) {
							groups.push(group)
						}
						currentGroupStartIndex = i
					}
				}
			}
			lastNonNullEscCurrentEntryIndex = i
		}
	}

	if (currentGroupStartIndex < entriesToGroup.length) {
		const lastGroup = entriesToGroup.slice(currentGroupStartIndex)
		if (lastGroup.length > 0) {
			groups.push(lastGroup)
		}
	}

	const rawAggregatedResults: InternalGroupAggregateValues[] = []
	for (const group of groups) {
		const aggregate = processGroupToAggregate(group)
		if (aggregate !== null) {
			rawAggregatedResults.push(aggregate)
		}
	}
	return filterAndFormatAggregates(rawAggregatedResults)
}
