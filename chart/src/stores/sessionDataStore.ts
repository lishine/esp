export const BATTERY_CURRENT_THRESHOLD_AMPS = 3
export const MIN_SPEED_ON_FOIL = 8 // km/h

import { defineStore } from 'pinia'
import type {
	SessionState,
	SessionMetadata,
	LogEntry,
	EscValues,
	GpsValues,
	DsValues,
	FormattedChartData,
} from './types'
import { visibilityActions } from './visibilityActions'
import { fileActions } from './fileActions'
import { chartFormatters } from './chartFormatters'
import { applyRangeChecks } from './rangeChecks'
import { calculateSessionDistance } from '../utils/gpsDistance'
import { calculateTimeOnFoil } from '../utils/timeOnFoil'

export const useSessionDataStore = defineStore('sessionData', {
	state: (): SessionState => {
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
			sessionMetadata: {
				device_description: '',
				fan_enabled: false,
				ds_associations: [],
				date: '',
				restart: '',
			},
			logEntries: [],
			isLoading: false,
			error: null,
			userApiIp: storedUserApiIp,
			useUserApiIp: storedUseUserApiIp,
			visibleSeries: new Set<string>(),
			gitHubFiles: [],
			isGitHubListLoading: false,
			gitHubListError: null,
			isGitHubFileLoading: false,
			gitHubFileError: null,
			currentFileSource: null,
			currentGitHubFileName: null,
			totalGpsDistance: 0,
			totalTimeOnFoil: 0,
		}
	},

	actions: {
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
				return
			}

			// Parse metadata (first line)
			try {
				const parsedFirstLine = JSON.parse(lines[0])
				this.sessionMetadata = {
					device_description: parsedFirstLine.device_description,
					fan_enabled: parsedFirstLine.fan_enabled,
					ds_associations: parsedFirstLine.ds_associations,
					date: parsedFirstLine.date,
					restart: parsedFirstLine.restart,
				}
			} catch (e) {
				console.error('Failed to parse session metadata:', e)
				this.error = 'Failed to parse session metadata.'
				return
			}

			// Parse log entries (remaining lines)
			const rawLogEntryArrays: Array<Array<Omit<LogEntry, 'preciseTimestamp'>>> = []
			for (let i = 1; i < lines.length; i++) {
				const line = lines[i].trim()
				if (line === '') continue
				try {
					const entriesInLine = JSON.parse(line) as Array<Omit<LogEntry, 'preciseTimestamp'>>
					rawLogEntryArrays.push(entriesInLine)
				} catch (e) {
					console.error('Failed to parse log entry array line:', line, e)
				}
			}

			// Flatten and group entries by timestamp
			const entriesWithPreciseTimestamp: LogEntry[] = []
			const entriesByTimestamp = new Map<string, Array<Omit<LogEntry, 'preciseTimestamp'>>>()

			rawLogEntryArrays.forEach((entryArray) => {
				if (entryArray.length === 0) return

				const timestampEntry = entryArray[0]
				if (!timestampEntry.t) {
					console.error('Skipping line due to missing timestamp:', entryArray)
					return
				}
				const timestampKey = timestampEntry.t

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
			const sortedTimestamps = Array.from(entriesByTimestamp.keys()).sort()

			sortedTimestamps.forEach((timestampKey) => {
				const group = entriesByTimestamp.get(timestampKey)
				if (!group) return

				const countInSecond = group.length
				const msIncrement = countInSecond > 0 ? 1000 / countInSecond : 0

				group.forEach((entry, index) => {
					const formattedTimePart = timestampKey.replace(/-/g, ':')
					const isoTimestampStr = `${this.sessionMetadata.date}T${formattedTimePart}`
					const baseDate = new Date(isoTimestampStr + 'Z')

					if (isNaN(baseDate.getTime())) {
						console.error(
							'Invalid date parsed for entry:',
							entry,
							'from date:',
							'and timestampKey:',
							timestampKey
						)
						return
					}

					const ms = Math.floor(index * msIncrement)
					baseDate.setUTCMilliseconds(ms)

					entriesWithPreciseTimestamp.push({
						...entry,
						t: timestampKey,
						preciseTimestamp: baseDate,
					} as LogEntry)
				})
			})

			// Sort all entries by preciseTimestamp
			entriesWithPreciseTimestamp.sort((a, b) => a.preciseTimestamp.getTime() - b.preciseTimestamp.getTime())

			console.log('Total entries: ' + entriesWithPreciseTimestamp.length.toString())

			this.logEntries = entriesWithPreciseTimestamp
			if (this.visibleSeries.size === 0 && this.logEntries.length > 0) {
				this.initializeDefaultVisibility()
			}

			// GPS distance and time on foil will be calculated in getChartFormattedData getter based on active periods
			this.totalGpsDistance = 0
			this.totalTimeOnFoil = 0
		},

		...visibilityActions,
		...fileActions,
	},

	getters: {
		getMetadata: (state): SessionMetadata | null => state.sessionMetadata,
		getLogEntries: (state): LogEntry[] => state.logEntries,
		getVisibleSeries: (state): string[] => Array.from(state.visibleSeries),
		getTotalGpsDistance: (state): number => state.totalGpsDistance,
		getTotalTimeOnFoil: (state): number => state.totalTimeOnFoil,
		getFilteredLogEntries: (state): LogEntry[] => {
			return state.logEntries // Simply return all log entries
		},
		getChartFormattedData(state): FormattedChartData {
			if (!state.logEntries.length) {
				return { series: [] }
			}

			// Apply range validation to all log entries first
			const rangeValidatedEntries: LogEntry[] = state.logEntries.map((entry) => {
				const validatedEntry = { ...entry }
				if (validatedEntry.n === 'esc') {
					const escValues = validatedEntry.v as EscValues
					validatedEntry.v = {
						...escValues,
						rpm: applyRangeChecks('esc_rpm', escValues.rpm),
						v: applyRangeChecks('esc_v', escValues.v),
						i: applyRangeChecks('esc_i', escValues.i),
						t: applyRangeChecks('esc_t', escValues.t),
					}
				} else if (validatedEntry.n === 'gps') {
					const gpsValues = validatedEntry.v as GpsValues
					const originalSpeed = gpsValues.speed !== undefined ? gpsValues.speed : null
					const checkedSpeed = applyRangeChecks('gps_speed', originalSpeed)
					// console.log(`[SessionDataStore] GPS Speed Check: original=${originalSpeed}, checked=${checkedSpeed}, ts=${validatedEntry.preciseTimestamp.toISOString()}`);
					validatedEntry.v = {
						...gpsValues,
						speed: checkedSpeed,
					}
				} else if (validatedEntry.n === 'ds') {
					const dsValues = validatedEntry.v as DsValues
					const validatedDsValues: DsValues = {}
					for (const key in dsValues) {
						if (Object.prototype.hasOwnProperty.call(dsValues, key)) {
							validatedDsValues[key] = applyRangeChecks(`ds_${key}`, dsValues[key])
						}
					}
					validatedEntry.v = validatedDsValues
				} else if (validatedEntry.n === 'mc') {
					validatedEntry.v = applyRangeChecks('mc_i', validatedEntry.v as number | null)
				} else if (validatedEntry.n === 'th') {
					validatedEntry.v = applyRangeChecks('th_val', validatedEntry.v as number | null)
				}
				return validatedEntry
			})

			// Now apply the filtering logic to rangeValidatedEntries
			const firstLogEntryTimestamp = rangeValidatedEntries[0]?.preciseTimestamp.getTime() || -Infinity
			const lastLogEntryTimestamp =
				rangeValidatedEntries[rangeValidatedEntries.length - 1]?.preciseTimestamp.getTime() || Infinity

			let firstRelevantEntry: LogEntry | null = null
			let lastRelevantEntry: LogEntry | null = null

			// Helper function to check if entry has valid ESC current above threshold
			const isEscEntryAboveThreshold = (entry: LogEntry): boolean => {
				if (entry.n !== 'esc' || !entry.v || typeof entry.v !== 'object') {
					return false
				}
				const escValues = entry.v as EscValues
				return typeof escValues.i === 'number' && escValues.i > BATTERY_CURRENT_THRESHOLD_AMPS
			}

			// Find the first relevant entry in rangeValidatedEntries
			for (const entry of rangeValidatedEntries) {
				if (isEscEntryAboveThreshold(entry)) {
					firstRelevantEntry = entry
					break
				}
			}

			// Find the last relevant entry in rangeValidatedEntries
			for (let i = rangeValidatedEntries.length - 1; i >= 0; i--) {
				const entry = rangeValidatedEntries[i]
				if (isEscEntryAboveThreshold(entry)) {
					lastRelevantEntry = entry
					break
				}
			}

			let finalFilteredAndValidatedEntries: LogEntry[]

			if (!firstRelevantEntry || !lastRelevantEntry) {
				console.warn(
					'Could not determine dynamic time range based on battery current threshold after range validation. Displaying full time range.'
				)
				finalFilteredAndValidatedEntries = rangeValidatedEntries // Use rangeValidatedEntries if filtering fails
			} else {
				const firstRelevantTimestamp = firstRelevantEntry.preciseTimestamp.getTime()
				const lastRelevantTimestamp = lastRelevantEntry.preciseTimestamp.getTime()

				// Calculate start and end times, ensuring they are within the overall log entry range
				const startTimeMs = Math.max(firstRelevantTimestamp - 30 * 1000, firstLogEntryTimestamp)
				const endTimeMs = Math.min(lastRelevantTimestamp + 30 * 1000, lastLogEntryTimestamp)

				// Filter entries based on the calculated time range
				finalFilteredAndValidatedEntries = rangeValidatedEntries.filter(
					// Filter rangeValidatedEntries
					(entry) =>
						entry.preciseTimestamp.getTime() >= startTimeMs && entry.preciseTimestamp.getTime() <= endTimeMs
				)
			}
			console.log(
				`[SessionDataStore] Initial logEntries: ${state.logEntries.length}, RangeValidated: ${rangeValidatedEntries.length}, FilteredByTime: ${finalFilteredAndValidatedEntries.length}`
			)

			// Apply data nullification based on battery current threshold
			const applyDataNullification = (entries: LogEntry[]): LogEntry[] => {
				if (entries.length === 0) return entries

				let shouldNullify = false
				let nullificationChanges = 0
				const mappedEntries = entries.map((entry) => {
					const originalShouldNullify = shouldNullify
					// Update nullification state based on ESC current
					if (entry.n === 'esc') {
						const escValues = entry.v as EscValues
						const escIValue = escValues.i
						if (escIValue !== null && escIValue !== undefined) {
							if (escIValue < BATTERY_CURRENT_THRESHOLD_AMPS) {
								shouldNullify = true
							} else if (escIValue > BATTERY_CURRENT_THRESHOLD_AMPS) {
								shouldNullify = false
							}
							// console.log(`[SessionDataStore] Nullification: ts=${entry.preciseTimestamp.toISOString()}, esc.i=${escIValue}, threshold=${BATTERY_CURRENT_THRESHOLD_AMPS}, prevShouldNullify=${originalShouldNullify}, newShouldNullify=${shouldNullify}`);
						}
						// If escIValue is null/undefined, shouldNullify remains unchanged
					}

					// Return nullified or original entry
					if (!shouldNullify) {
						if (originalShouldNullify !== shouldNullify) nullificationChanges++
						return entry
					}

					// Create nullified copy of the entry
					const nullifiedEntry: LogEntry = { ...entry }
					if (originalShouldNullify !== shouldNullify) nullificationChanges++

					if (entry.n === 'esc') {
						const escValues = entry.v as EscValues
						nullifiedEntry.v = {
							...escValues,
							rpm: null,
							mah: null,
							t: null,
							i: null,
							v: null,
						}
					} else if (entry.n === 'gps') {
						const gpsValues = entry.v as GpsValues
						nullifiedEntry.v = {
							...gpsValues,
							speed: null,
							lon: null,
							lat: null,
							alt: null,
							hdg: null,
						}
					} else if (entry.n === 'ds') {
						const dsValues = entry.v as DsValues
						const nullifiedDsValues: DsValues = {}
						for (const key in dsValues) {
							if (Object.prototype.hasOwnProperty.call(dsValues, key)) {
								nullifiedDsValues[key] = null
							}
						}
						nullifiedEntry.v = nullifiedDsValues
					} else if (entry.n === 'mc' || entry.n === 'th') {
						nullifiedEntry.v = null
					}

					return nullifiedEntry
				})
				console.log(
					`[SessionDataStore] Nullification: Applied to ${entries.length} entries. Nullify state changed ${nullificationChanges} times.`
				)
				return mappedEntries
			}

			// Apply speed-based nullification function
			const applySpeedNullification = (entries: LogEntry[]): LogEntry[] => {
				if (entries.length === 0) return entries

				const speedThreshold = MIN_SPEED_ON_FOIL / 1.852 // Convert km/h to knots
				let shouldCurrentlyNullify = false
				let nullificationChanges = 0

				const mappedEntries = entries.map((entry) => {
					const originalShouldNullify = shouldCurrentlyNullify

					// Update nullification state based on GPS speed
					if (entry.n === 'gps') {
						const gpsValues = entry.v as GpsValues
						const gpsSpeed = gpsValues.speed
						if (gpsSpeed !== null && gpsSpeed !== undefined) {
							if (gpsSpeed < speedThreshold) {
								shouldCurrentlyNullify = true
							} else if (gpsSpeed > speedThreshold) {
								shouldCurrentlyNullify = false
							}
							// If gpsSpeed equals threshold, maintain current state
						}
						// If gpsSpeed is null/undefined, shouldCurrentlyNullify remains unchanged
					}

					// Return original entry if not nullifying
					if (!shouldCurrentlyNullify) {
						if (originalShouldNullify !== shouldCurrentlyNullify) nullificationChanges++
						return entry
					}

					// Create nullified copy of the entry
					const nullifiedEntry: LogEntry = { ...entry }
					if (originalShouldNullify !== shouldCurrentlyNullify) nullificationChanges++

					if (entry.n === 'esc') {
						const escValues = entry.v as EscValues
						nullifiedEntry.v = {
							...escValues,
							rpm: null,
							mah: null,
							t: null,
							i: null,
							v: null,
						}
					} else if (entry.n === 'gps') {
						const gpsValues = entry.v as GpsValues
						nullifiedEntry.v = {
							...gpsValues,
							speed: null,
							lon: null,
							lat: null,
							alt: null,
							hdg: null,
						}
					} else if (entry.n === 'ds') {
						const dsValues = entry.v as DsValues
						const nullifiedDsValues: DsValues = {}
						for (const key in dsValues) {
							if (Object.prototype.hasOwnProperty.call(dsValues, key)) {
								nullifiedDsValues[key] = null
							}
						}
						nullifiedEntry.v = nullifiedDsValues
					} else if (entry.n === 'mc' || entry.n === 'th') {
						nullifiedEntry.v = null
					}

					return nullifiedEntry
				})

				console.log(
					`[SessionDataStore] Speed Nullification: Applied to ${entries.length} entries with threshold ${speedThreshold.toFixed(2)} knots. Nullify state changed ${nullificationChanges} times.`
				)
				return mappedEntries
			}

			const nullifiedEntries = applyDataNullification(finalFilteredAndValidatedEntries)
			const speedNullifiedEntries = applySpeedNullification(nullifiedEntries)

			const chartData = chartFormatters.getChartFormattedData.call({
				logEntries: speedNullifiedEntries,
			})

			this.totalGpsDistance = calculateSessionDistance(speedNullifiedEntries)

			this.totalTimeOnFoil = calculateTimeOnFoil(speedNullifiedEntries, MIN_SPEED_ON_FOIL / 1.852)

			return chartData
		},
	},
})

export type { SessionMetadata, LogEntry } from './types'
export type { LogFileListItem as LogFile } from '../services/githubService'
