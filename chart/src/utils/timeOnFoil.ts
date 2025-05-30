import type { LogEntry, GpsValues } from '../stores/types'

export function calculateTimeOnFoil(logEntries: LogEntry[], minSpeedKmh: number): number {
	if (logEntries.length === 0) {
		return 0
	}

	let totalTimeOnFoil = 0
	let previousGpsEntry: LogEntry | null = null

	for (const currentEntry of logEntries) {
		if (currentEntry.n === 'gps') {
			const currentGps = currentEntry.v as GpsValues

			if (currentGps.speed !== null && currentGps.speed !== undefined) {
				if (previousGpsEntry) {
					const previousGps = previousGpsEntry.v as GpsValues

					if (previousGps.speed !== null && previousGps.speed !== undefined) {
						const timeDiffMs =
							currentEntry.preciseTimestamp.getTime() - previousGpsEntry.preciseTimestamp.getTime()
						const timeDiffSeconds = timeDiffMs / 1000

						if (previousGps.speed >= minSpeedKmh) {
							totalTimeOnFoil += timeDiffSeconds
						}
					}
				}

				previousGpsEntry = currentEntry
			}
		}
	}

	return totalTimeOnFoil
}
