import type { SessionState } from './types'
import type { ChartSeriesData } from './types'
import { CANONICAL_SERIES_CONFIG } from './seriesConfig'

export interface VisibilityActionContext {
	visibleSeries: Set<string>
	logEntries: SessionState['logEntries']
	getChartFormattedData: { series: ChartSeriesData[] }
	loadVisibilityPreferences: () => void
	saveVisibilityPreferences: () => void
	initializeDefaultVisibility: () => void
	toggleSeries: (seriesName: string) => void
	toggleAllSeries: (visible: boolean) => void
	setSeriesVisibility: (seriesName: string, visible: boolean) => void
}

type MethodSignatures = {
	loadVisibilityPreferences: () => void
	saveVisibilityPreferences: () => void
	initializeDefaultVisibility: () => void
	toggleSeries: (seriesName: string) => void
	toggleAllSeries: (visible: boolean) => void
	setSeriesVisibility: (seriesName: string, visible: boolean) => void
}

type VisibilityActions = {
	[K in keyof MethodSignatures]: (
		this: VisibilityActionContext,
		...args: Parameters<MethodSignatures[K]>
	) => ReturnType<MethodSignatures[K]>
}

export const visibilityActions: VisibilityActions = {
	loadVisibilityPreferences(this: VisibilityActionContext) {
		if (typeof localStorage !== 'undefined') {
			const storedVisibility = localStorage.getItem('espChartVisibleSeries')
			if (storedVisibility) {
				try {
					const visibleArray = JSON.parse(storedVisibility)
					this.visibleSeries = new Set(visibleArray)
					console.log(
						'[visibilityActions] Loaded from localStorage:',
						visibleArray,
						'Current visibleSeries:',
						Array.from(this.visibleSeries)
					)
				} catch (e) {
					console.error('Failed to parse visible series from localStorage:', e)
					this.visibleSeries = new Set<string>()
					console.log(
						'[visibilityActions] Failed to parse localStorage, set to empty. Current visibleSeries:',
						Array.from(this.visibleSeries)
					)
				}
			} else {
				this.visibleSeries = new Set<string>()
				console.log(
					'[visibilityActions] No "espChartVisibleSeries" in localStorage, set to empty. Current visibleSeries:',
					Array.from(this.visibleSeries)
				)
			}
		} else {
			this.visibleSeries = new Set<string>()
			console.log(
				'[visibilityActions] localStorage not available, set to empty. Current visibleSeries:',
				Array.from(this.visibleSeries)
			)
		}
	},

	saveVisibilityPreferences(this: VisibilityActionContext) {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('espChartVisibleSeries', JSON.stringify(Array.from(this.visibleSeries)))
		}
	},

	initializeDefaultVisibility(this: VisibilityActionContext) {
		console.log(
			'[visibilityActions] Attempting initializeDefaultVisibility. Current visibleSeries (start):',
			Array.from(this.visibleSeries),
			'logEntries count:',
			this.logEntries.length
		)
		if (this.logEntries.length > 0 && this.visibleSeries.size === 0) {
			console.log('[visibilityActions] Condition met: Initializing default visibility (visibleSeries.size is 0).')
			const availableSeriesNamesInChartData = new Set(
				this.getChartFormattedData.series.map((s: ChartSeriesData) => s.name)
			)
			console.log(
				'[visibilityActions] Available series names in chart data for default init:',
				Array.from(availableSeriesNamesInChartData)
			)

			CANONICAL_SERIES_CONFIG.forEach((config) => {
				if (availableSeriesNamesInChartData.has(config.displayName)) {
					this.visibleSeries.add(config.displayName)
					console.log(`[visibilityActions] Default init: Added "${config.displayName}" to visibleSeries.`)
				} else {
					console.log(
						`[visibilityActions] Default init: Did NOT add "${config.displayName}" as it's not in availableSeriesNamesInChartData.`
					)
				}
			})
			this.saveVisibilityPreferences()
			console.log(
				'[visibilityActions] Default visibility initialized. Current visibleSeries (end):',
				Array.from(this.visibleSeries)
			)
		} else {
			console.log(
				'[visibilityActions] Condition NOT met for default init. Either no log entries or visibleSeries.size is not 0. Current visibleSeries.size:',
				this.visibleSeries.size
			)
		}
	},

	toggleSeries(this: VisibilityActionContext, seriesName: string) {
		const isVisible = this.visibleSeries.has(seriesName)
		this.setSeriesVisibility(seriesName, !isVisible)
	},

	toggleAllSeries(this: VisibilityActionContext, visible: boolean) {
		const allSeriesNames = this.getChartFormattedData.series.map((s: ChartSeriesData) => s.name)
		if (visible) {
			allSeriesNames.forEach((name: string) => this.visibleSeries.add(name))
		} else {
			this.visibleSeries.clear()
		}
		this.saveVisibilityPreferences()
	},

	setSeriesVisibility(this: VisibilityActionContext, seriesName: string, visible: boolean) {
		if (visible) {
			this.visibleSeries.add(seriesName)
		} else {
			this.visibleSeries.delete(seriesName)
		}
		this.saveVisibilityPreferences()
	},
}
