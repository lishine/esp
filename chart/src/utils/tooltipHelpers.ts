import type { MetadataGroup } from '@/stores/types'

/**
 * Parses a "HH:MM:SS" time string into total seconds from midnight.
 * @param timeStr The time string.
 * @returns Total seconds, or -1 if format is invalid.
 */
export function parseTimeToSeconds(timeStr: string): number {
	if (!timeStr || !/^\d{2}:\d{2}:\d{2}$/.test(timeStr)) {
		// console.warn(`Invalid time string format: ${timeStr}`);
		return -1
	}
	const parts = timeStr.split(':').map(Number)
	return parts[0] * 3600 + parts[1] * 60 + parts[2]
}

/**
 * Finds the active group name ('n') based on the chart's current time.
 * @param chartCurrentTimeInSeconds The current time on the chart, in seconds from midnight.
 * @param groups The array of metadata groups.
 * @returns The name 'n' of the active group, or an empty string if not found.
 */
export function findActiveGroupName(chartCurrentTimeInSeconds: number, groups?: MetadataGroup[]): string {
	if (!groups || groups.length === 0 || chartCurrentTimeInSeconds < 0) {
		return ''
	}

	// Ensure groups are sorted by time 't' if not already guaranteed by data source
	// Create a shallow copy before sorting to avoid mutating the original store data
	const sortedGroups = [...groups].sort((a, b) => parseTimeToSeconds(a.t) - parseTimeToSeconds(b.t))

	for (let i = 0; i < sortedGroups.length; i++) {
		const groupStartTimeSeconds = parseTimeToSeconds(sortedGroups[i].t)
		if (groupStartTimeSeconds < 0) continue // Skip malformed group times

		const nextGroupStartTimeSeconds =
			i + 1 < sortedGroups.length ? parseTimeToSeconds(sortedGroups[i + 1].t) : Infinity

		// If next group's time is malformed (and not Infinity), treat current group as the last effectively
		if (nextGroupStartTimeSeconds < 0 && nextGroupStartTimeSeconds !== Infinity) {
			if (chartCurrentTimeInSeconds >= groupStartTimeSeconds) {
				return sortedGroups[i].n
			}
			continue
		}

		if (
			chartCurrentTimeInSeconds >= groupStartTimeSeconds &&
			chartCurrentTimeInSeconds < nextGroupStartTimeSeconds
		) {
			return sortedGroups[i].n
		}
	}
	return '' // No matching group found
}
