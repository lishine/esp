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
				} catch (e) {
					console.error('Failed to parse visible series from localStorage:', e)
					this.visibleSeries = new Set<string>()
				}
			} else {
				this.visibleSeries = new Set<string>()
			}
		} else {
			this.visibleSeries = new Set<string>()
		}
	},

	saveVisibilityPreferences(this: VisibilityActionContext) {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('espChartVisibleSeries', JSON.stringify(Array.from(this.visibleSeries)))
		}
	},

	initializeDefaultVisibility(this: VisibilityActionContext) {
		if (this.logEntries.length > 0 && this.visibleSeries.size === 0) {
			console.log('Initializing default visibility: making all series visible.')
			const availableSeriesNamesInChartData = new Set(
				this.getChartFormattedData.series.map((s: ChartSeriesData) => s.name)
			)

			CANONICAL_SERIES_CONFIG.forEach((config) => {
				if (availableSeriesNamesInChartData.has(config.displayName)) {
					this.visibleSeries.add(config.displayName)
				}
			})
			this.saveVisibilityPreferences()
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
