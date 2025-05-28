export const BATTERY_CURRENT_THRESHOLD_AMPS = 3
import { defineStore } from 'pinia'
import type { SessionState, SessionMetadata, LogEntry, EscValues } from './types'
import { visibilityActions } from './visibilityActions'
import { fileActions } from './fileActions'
import { chartFormatters } from './chartFormatters'

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
			sessionMetadata: null,
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
			filterSeriesByBatCurrent: true, // Added for battery current filtering
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

		setFilterSeriesByBatCurrent(value: boolean) {
			this.filterSeriesByBatCurrent = value
		},

		_parseSessionData(fullDataString: string) {
			const lines = fullDataString.trim().split('\n')
			if (lines.length === 0) {
				this.error = 'No data received.'
				this.sessionMetadata = null
				this.logEntries = []
				return
			}

			// Parse metadata (first line)
			let metadata: SessionMetadata | null = null
			try {
				const parsedFirstLine = JSON.parse(lines[0])
				metadata = {
					device_description: parsedFirstLine.device_description,
					fan_enabled: parsedFirstLine.fan_enabled,
					ds_associations: parsedFirstLine.ds_associations,
					date: parsedFirstLine.date,
					restart: parsedFirstLine.restart,
				}
				this.sessionMetadata = metadata
			} catch (e) {
				console.error('Failed to parse session metadata:', e)
				this.error = 'Failed to parse session metadata.'
				this.sessionMetadata = null
				return
			}

			if (!metadata.date) {
				console.error('Metadata is missing or does not contain date.')
				this.error = 'Metadata is missing or does not contain date.'
				this.sessionMetadata = null
				this.logEntries = []
				return
			}

			const sessionDate = metadata.date

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
					const isoTimestampStr = `${sessionDate}T${formattedTimePart}`
					const baseDate = new Date(isoTimestampStr + 'Z')

					if (isNaN(baseDate.getTime())) {
						console.error(
							'Invalid date parsed for entry:',
							entry,
							'from date:',
							sessionDate,
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
		},

		...visibilityActions,
		...fileActions,
	},

	getters: {
		getMetadata: (state): SessionMetadata | null => state.sessionMetadata,
		getLogEntries: (state): LogEntry[] => state.logEntries,
		getVisibleSeries: (state): string[] => Array.from(state.visibleSeries),
		getFilteredLogEntries: (state): LogEntry[] => {
			if (!state.logEntries.length) {
				return []
			}

			const firstLogEntryTimestamp = state.logEntries[0]?.preciseTimestamp.getTime() || -Infinity
			const lastLogEntryTimestamp =
				state.logEntries[state.logEntries.length - 1]?.preciseTimestamp.getTime() || Infinity

			let firstRelevantEntry: LogEntry | null = null
			let lastRelevantEntry: LogEntry | null = null

			// Find the first relevant entry
			for (let i = 0; i < state.logEntries.length; i++) {
				const entry = state.logEntries[i]
				if (entry.n === 'esc' && (entry.v as EscValues).i > BATTERY_CURRENT_THRESHOLD_AMPS) {
					firstRelevantEntry = entry
					break
				}
			}

			// Find the last relevant entry
			for (let i = state.logEntries.length - 1; i >= 0; i--) {
				const entry = state.logEntries[i]
				if (entry.n === 'esc' && (entry.v as EscValues).i > BATTERY_CURRENT_THRESHOLD_AMPS) {
					lastRelevantEntry = entry
					break
				}
			}

			if (!firstRelevantEntry || !lastRelevantEntry) {
				console.warn(
					'Could not determine dynamic time range based on battery current threshold. Displaying full time range.'
				)
				return state.logEntries
			}

			const firstRelevantTimestamp = firstRelevantEntry.preciseTimestamp.getTime()
			const lastRelevantTimestamp = lastRelevantEntry.preciseTimestamp.getTime()

			// Calculate start and end times, ensuring they are within the overall log entry range
			const startTimeMs = Math.max(firstRelevantTimestamp - 30 * 1000, firstLogEntryTimestamp)
			const endTimeMs = Math.min(lastRelevantTimestamp + 30 * 1000, lastLogEntryTimestamp)

			// Filter entries based on the calculated time range
			const filteredResult = state.logEntries.filter(
				(entry) =>
					entry.preciseTimestamp.getTime() >= startTimeMs && entry.preciseTimestamp.getTime() <= endTimeMs
			)

			return filteredResult
		},
		getChartFormattedData(state): ReturnType<typeof chartFormatters.getChartFormattedData> {
			const filteredEntries = this.getFilteredLogEntries // Use the filtered entries
			return chartFormatters.getChartFormattedData.call({
				logEntries: filteredEntries,
				filterSeriesByBatCurrent: state.filterSeriesByBatCurrent as boolean,
			})
		},
	},
})

export type { SessionMetadata, LogEntry } from './types'
export type { LogFileListItem as LogFile } from '../services/githubService'
