import type { LogEntry, GpsValues } from '../stores/types'

/**
 * Calculates the distance between two geographical points using the Haversine formula.
 * @param lat1 Latitude of the first point in degrees.
 * @param lon1 Longitude of the first point in degrees.
 * @param lat2 Latitude of the second point in degrees.
 * @param lon2 Longitude of the second point in degrees.
 * @returns Distance in meters.
 */
function haversineDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
	const R = 6371e3 // Earth's radius in meters
	const φ1 = (lat1 * Math.PI) / 180 // φ, λ in radians
	const φ2 = (lat2 * Math.PI) / 180
	const Δφ = ((lat2 - lat1) * Math.PI) / 180
	const Δλ = ((lon2 - lon1) * Math.PI) / 180

	const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2)
	const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))

	const d = R * c // Distance in meters
	return d
}

/**
 * Calculates the total GPS distance covered during a session based on log entries.
 * Distance is only calculated between consecutive entries that have a valid GPS fix (lat and lon defined).
 * @param logEntries An array of log entries.
 * @returns The total distance in meters.
 */
export function calculateSessionDistance(logEntries: LogEntry[]): number {
	let totalDistance = 0
	let previousEntry: LogEntry | null = null

	console.log(`[GPS Debug] Total log entries: ${logEntries.length}`)

	for (const currentEntry of logEntries) {
		if (currentEntry.n === 'gps') {
			if (currentEntry.v && typeof currentEntry.v === 'object' && 'fix' in currentEntry.v && currentEntry.v.fix) {
				const currentGps = currentEntry.v as GpsValues
				if (
					currentGps.lat !== null &&
					currentGps.lat !== undefined &&
					currentGps.lon !== null &&
					currentGps.lon !== undefined
				) {
					if (previousEntry) {
						const previousGps = previousEntry.v as GpsValues // previousEntry is guaranteed to be a valid GPS point by now
						if (
							previousGps.lat !== null &&
							previousGps.lat !== undefined &&
							previousGps.lon !== null &&
							previousGps.lon !== undefined
						) {
							const segmentDistance = haversineDistance(
								previousGps.lat,
								previousGps.lon,
								currentGps.lat,
								currentGps.lon
							)
							totalDistance += segmentDistance
						} else {
						}
					} else {
					}
					previousEntry = currentEntry // Set current as previous if it's a valid point for the next iteration
				} else {
					previousEntry = null // Reset if current point with fix has no lat/lon
				}
			} else {
				previousEntry = null // Reset if GPS entry has no fix
			}
		} else {
		}
	}

	return totalDistance
}

export function extractActiveGpsEntries(logEntries: LogEntry[], activeTimestamps: number[]): LogEntry[] {
	if (activeTimestamps.length === 0) {
		return []
	}

	const activeTimestampSet = new Set(activeTimestamps)

	return logEntries.filter((entry) => {
		return entry.n === 'gps' && activeTimestampSet.has(entry.preciseTimestamp.getTime())
	})
}
