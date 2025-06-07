import type { SessionState } from './types'
import type { ChartSeriesData } from './types'
import { CANONICAL_SERIES_CONFIG } from './seriesConfig'

export interface VisibilityActionContext {
	hiddenSeries: Set<string> // Renamed from visibleSeries
	logEntries: SessionState['logEntries']
	getChartFormattedData: { series: ChartSeriesData[] }
	// Action methods will be bound with this context
	loadVisibilityPreferences: () => void
	saveVisibilityPreferences: () => void
	initializeDefaultVisibility: () => void
	toggleSeries: (seriesName: string) => void
	toggleAllSeries: (visible: boolean) => void
	setSeriesVisibility: (seriesName: string, visible: boolean) => void
}

// Define the shape of the methods for strong typing
type MethodSignatures = {
	loadVisibilityPreferences: () => void
	saveVisibilityPreferences: () => void
	initializeDefaultVisibility: () => void
	toggleSeries: (seriesName: string) => void
	toggleAllSeries: (visible: boolean) => void
	setSeriesVisibility: (seriesName: string, visible: boolean) => void
}

// Ensures that 'this' context within actions matches VisibilityActionContext
type VisibilityActions = {
	[K in keyof MethodSignatures]: (
		this: VisibilityActionContext,
		...args: Parameters<MethodSignatures[K]>
	) => ReturnType<MethodSignatures[K]>
}

const OLD_LS_KEY_VISIBLE = 'espChartVisibleSeries'
const NEW_LS_KEY_HIDDEN = 'espChartHiddenSeries'

export const visibilityActions: VisibilityActions = {
	loadVisibilityPreferences(this: VisibilityActionContext) {
		if (typeof localStorage === 'undefined') {
			this.hiddenSeries = new Set<string>()
			return
		}

		const storedOldVisible = localStorage.getItem(OLD_LS_KEY_VISIBLE)

		if (storedOldVisible) {
			try {
				const previouslyVisibleArray = JSON.parse(storedOldVisible) as string[]
				const previouslyVisibleSet = new Set(previouslyVisibleArray)

				let allAvailableSeriesNames: string[]
				if (this.getChartFormattedData && this.getChartFormattedData.series.length > 0) {
					allAvailableSeriesNames = this.getChartFormattedData.series.map((s) => s.name)
				} else {
					allAvailableSeriesNames = CANONICAL_SERIES_CONFIG.map((c) => c.displayName)
				}

				this.hiddenSeries = new Set<string>()
				allAvailableSeriesNames.forEach((name) => {
					if (!previouslyVisibleSet.has(name)) {
						this.hiddenSeries.add(name)
					}
				})

				this.saveVisibilityPreferences() // Save under new key
				localStorage.removeItem(OLD_LS_KEY_VISIBLE)
			} catch {
				this.hiddenSeries = new Set<string>() // Default to all visible on error
			}
		} else {
			const storedNewHidden = localStorage.getItem(NEW_LS_KEY_HIDDEN)
			if (storedNewHidden) {
				try {
					const hiddenArray = JSON.parse(storedNewHidden) as string[]
					this.hiddenSeries = new Set(hiddenArray)
				} catch (e) {
					console.error('Failed to parse hidden series from new key:', e)
					this.hiddenSeries = new Set<string>()
				}
			} else {
				this.hiddenSeries = new Set<string>()
			}
		}
	},

	saveVisibilityPreferences(this: VisibilityActionContext) {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(NEW_LS_KEY_HIDDEN, JSON.stringify(Array.from(this.hiddenSeries)))
		}
	},

	initializeDefaultVisibility(this: VisibilityActionContext) {
		// This function's original purpose was to set a default *visible* set.
		// With the new logic, an empty hiddenSeries means all are visible by default.
		// loadVisibilityPreferences handles the initial setup (including migration or empty set).
		// This function can now ensure that if it's called, it explicitly sets to "all visible".
		this.hiddenSeries.clear() // Ensure all series are visible
		this.saveVisibilityPreferences()
	},

	toggleSeries(this: VisibilityActionContext, seriesName: string) {
		const isCurrentlyHidden = this.hiddenSeries.has(seriesName)
		// If it's hidden, we want to make it visible (isCurrentlyHidden = true -> visible = true)
		// If it's visible (not hidden), we want to make it hidden (isCurrentlyHidden = false -> visible = false)
		this.setSeriesVisibility(seriesName, isCurrentlyHidden)
	},

	toggleAllSeries(this: VisibilityActionContext, visible: boolean) {
		if (visible) {
			// Make all series visible means clearing the hidden set
			this.hiddenSeries.clear()
		} else {
			// Make all series hidden means adding all available series to the hidden set
			const allSeriesNames =
				this.getChartFormattedData && this.getChartFormattedData.series.length > 0
					? this.getChartFormattedData.series.map((s: ChartSeriesData) => s.name)
					: CANONICAL_SERIES_CONFIG.map((c) => c.displayName)
			allSeriesNames.forEach((name: string) => this.hiddenSeries.add(name))
		}
		this.saveVisibilityPreferences()
	},

	setSeriesVisibility(this: VisibilityActionContext, seriesName: string, visible: boolean) {
		if (visible) {
			this.hiddenSeries.delete(seriesName) // To make it visible, remove from hidden
		} else {
			this.hiddenSeries.add(seriesName) // To make it hidden, add to hidden
		}
		this.saveVisibilityPreferences()
	},
}
