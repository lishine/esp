import type { LogEntry, EscValues, GpsValues, GroupAggregate, MetadataGroup } from '../stores/types' // Import correct GroupAggregate and MetadataGroup
import { haversineDistance } from './gpsDistance'

// --- Filtering and Formatting Function ---
const MIN_DURATION_S = 25
const MIN_MAH_DELTA = 100

// Internal type for raw calculations before formatting and filtering
interface InternalGroupAggregateValues {
	consumption: number | null
	distance: number | null
	avg_speed_kmh: number | null
	avg_volt: number | null
	avg_current: number | null
	'watt-hour_per_km': number | null
	watt_per_speed: number | null
	duration: number | null
	rawStartTime: Date | null // Added for precise start time
	rawEndTime: Date | null // Added for precise end time
	entry_count: number
	avg_rpm: number | null
	avg_throttle: number | null
	avg_motor_current: number | null
	motor_battery_current_efficiency: number | null
}

function processGroupToAggregate(group: LogEntry[]): InternalGroupAggregateValues | null {
	if (group.length < 2) {
		return null
	}

	const escEntriesInGroup = group.filter((e) => e.n === 'esc' && e.v) as LogEntry[]
	const gpsEntriesInGroup = group.filter(
		(e) => e.n === 'gps' && e.v && (e.v as GpsValues).lat !== null && (e.v as GpsValues).lon !== null
	) as LogEntry[]
	const thEntriesInGroup = group.filter((e) => e.n === 'th' && e.v !== null && e.v !== undefined) as LogEntry[]
	const mcEntriesInGroup = group.filter((e) => e.n === 'mc' && e.v !== null && e.v !== undefined) as LogEntry[]

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

	const mah_delta_val = firstMah !== null && lastMah !== null ? lastMah - firstMah : null

	let km_delta_val: number | null = 0
	if (gpsEntriesInGroup.length < 2) {
		km_delta_val = null
	} else {
		for (let j = 1; j < gpsEntriesInGroup.length; j++) {
			const p1 = gpsEntriesInGroup[j - 1].v as GpsValues
			const p2 = gpsEntriesInGroup[j].v as GpsValues
			if (p1.lat != null && p1.lon != null && p2.lat != null && p2.lon != null) {
				km_delta_val += haversineDistance(p1.lat, p1.lon, p2.lat, p2.lon) / 1000
			}
		}
	}

	const speedsKmhRaw = gpsEntriesInGroup
		.map((e) => (e.v as GpsValues).speed)
		.filter((s) => s !== null && s !== undefined) as number[]
	const avg_speed_kmh =
		speedsKmhRaw.length > 0 ? (speedsKmhRaw.reduce((a, b) => a + b, 0) / speedsKmhRaw.length) * 1.852 : null

	const voltages = escEntriesInGroup
		.map((e) => (e.v as EscValues).v)
		.filter((v) => v !== null && v !== undefined) as number[]
	const avg_v_val = voltages.length > 0 ? voltages.reduce((a, b) => a + b, 0) / voltages.length : null

	const currents = escEntriesInGroup
		.map((e) => (e.v as EscValues).i)
		.filter((iVal) => iVal !== null && iVal !== undefined) as number[]
	const avg_i_val = currents.length > 0 ? currents.reduce((a, b) => a + b, 0) / currents.length : null

	const total_energy_Wh_group =
		avg_v_val !== null && mah_delta_val !== null ? (avg_v_val * mah_delta_val) / 1000 : null
	const calculated_wh_per_km_val =
		km_delta_val !== null &&
		km_delta_val > 0 &&
		total_energy_Wh_group !== null &&
		(mah_delta_val === null || mah_delta_val > 0)
			? total_energy_Wh_group / km_delta_val
			: null

	const avg_power_W_group = avg_v_val !== null && avg_i_val !== null ? avg_v_val * avg_i_val : null
	const calculated_w_per_speed_val =
		avg_speed_kmh !== null && avg_speed_kmh > 0 && avg_power_W_group !== null
			? avg_power_W_group / avg_speed_kmh
			: null

	const duration_s_val =
		(group[group.length - 1].preciseTimestamp.getTime() - group[0].preciseTimestamp.getTime()) / 1000
	const rawStartTime_val = group[0].preciseTimestamp
	const rawEndTime_val = group[group.length - 1].preciseTimestamp
	const entry_count = group.length

	const rpms = escEntriesInGroup
		.map((e) => (e.v as EscValues).rpm)
		.filter((rpm) => rpm !== null && rpm !== undefined) as number[]
	const avg_rpm = rpms.length > 0 ? rpms.reduce((a, b) => a + b, 0) / rpms.length : null

	const throttles = thEntriesInGroup
		.map((e) => e.v as number)
		.filter((th) => th !== null && th !== undefined) as number[]
	const avg_throttle = throttles.length > 0 ? throttles.reduce((a, b) => a + b, 0) / throttles.length : null

	const motorCurrents = mcEntriesInGroup
		.map((e) => e.v as number)
		.filter((mc) => mc !== null && mc !== undefined) as number[]
	let avg_motor_current =
		motorCurrents.length > 0 ? motorCurrents.reduce((a, b) => a + b, 0) / motorCurrents.length : null

	if (avg_motor_current !== null) {
		avg_motor_current = avg_motor_current * 1.732
	}

	const motor_battery_current_efficiency =
		avg_motor_current !== null && avg_i_val !== null && avg_i_val !== 0 ? avg_motor_current / avg_i_val : null

	return {
		consumption: mah_delta_val,
		distance: km_delta_val,
		avg_speed_kmh,
		avg_volt: avg_v_val,
		avg_current: avg_i_val,
		'watt-hour_per_km': calculated_wh_per_km_val,
		watt_per_speed: calculated_w_per_speed_val,
		duration: duration_s_val,
		rawStartTime: rawStartTime_val,
		rawEndTime: rawEndTime_val,
		entry_count,
		avg_rpm,
		avg_throttle,
		avg_motor_current,
		motor_battery_current_efficiency,
	}
}

function filterAndFormatAggregates(
	rawAggregates: InternalGroupAggregateValues[],
	metadataGroups?: ReadonlyArray<MetadataGroup>
): GroupAggregate[] {
	if (rawAggregates.length === 0) {
		return []
	}

	const aggregatesToFormat: InternalGroupAggregateValues[] = []

	if (rawAggregates.length > 0) {
		const otherRawAggregates = rawAggregates.slice(0, -1)
		const filteredOthers = otherRawAggregates.filter((agg) => {
			return (
				agg.duration !== null &&
				agg.duration >= MIN_DURATION_S &&
				agg.consumption !== null &&
				agg.consumption >= MIN_MAH_DELTA
			)
		})
		aggregatesToFormat.push(...filteredOthers)
		aggregatesToFormat.push(rawAggregates[rawAggregates.length - 1])
	}

	return aggregatesToFormat.map((raw, index): GroupAggregate => {
		let groupName = `Segment ${index + 1}` // Default name

		if (metadataGroups && metadataGroups.length > 0 && raw.rawStartTime && raw.rawEndTime) {
			const aggStartTimeMs = raw.rawStartTime.getTime()
			const aggEndTimeMs = raw.rawEndTime.getTime()

			for (const metaGroup of metadataGroups) {
				if (metaGroup.t) {
					const [h, m, s] = metaGroup.t.split(':').map(Number)
					// Get local date components from raw.rawStartTime
					const year = raw.rawStartTime.getFullYear()
					const month = raw.rawStartTime.getMonth() // 0-indexed
					const day = raw.rawStartTime.getDate()

					// Construct new Date object using local components from raw.rawStartTime for date
					// and h, m, s from metaGroup.t for time. This creates a local Date object.
					const metaGroupPointDate = new Date(year, month, day, h, m, s)
					const metaGroupPointInTimeMs = metaGroupPointDate.getTime() // Get its UTC ms equivalent for comparison

					if (metaGroupPointInTimeMs >= aggStartTimeMs && metaGroupPointInTimeMs < aggEndTimeMs) {
						groupName = metaGroup.n
						break
					}
				}
			}
		}

		return {
			groupName,
			startTime: raw.rawStartTime || undefined,
			endTime: raw.rawEndTime || undefined,
			metrics: {
				consumption: raw.consumption !== null ? Math.round(raw.consumption) : null,
				avg_speed_kmh: raw.avg_speed_kmh !== null ? parseFloat(raw.avg_speed_kmh.toFixed(1)) : null,
				avg_volt: raw.avg_volt !== null ? parseFloat(raw.avg_volt.toFixed(1)) : null,
				avg_current: raw.avg_current !== null ? Math.round(raw.avg_current) : null,
				'watt-hour_per_km': raw['watt-hour_per_km'] !== null ? Math.round(raw['watt-hour_per_km']) : null,
				watt_per_speed: raw.watt_per_speed !== null ? Math.round(raw.watt_per_speed) : null,
				entry_count: raw.entry_count,
				avg_rpm: raw.avg_rpm !== null ? Math.round(raw.avg_rpm) : null,
				avg_throttle: raw.avg_throttle !== null ? parseFloat(raw.avg_throttle.toFixed(1)) : null,
				avg_motor_current: raw.avg_motor_current !== null ? parseFloat(raw.avg_motor_current.toFixed(1)) : null,
				motor_battery_current_efficiency:
					raw.motor_battery_current_efficiency !== null
						? parseFloat(raw.motor_battery_current_efficiency.toFixed(2))
						: null,
				distance_km: raw.distance,
				duration_s: raw.duration,
			},
		}
	})
}

export function calculateGroupAggregates(
	entriesToGroup: LogEntry[],
	metadataGroups?: ReadonlyArray<MetadataGroup>
): GroupAggregate[] {
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
	return filterAndFormatAggregates(rawAggregatedResults, metadataGroups)
}
