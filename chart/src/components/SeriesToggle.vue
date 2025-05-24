<script setup lang="ts">
import { computed } from 'vue'
import { useSessionDataStore } from '../stores/sessionData'
import { NCard, NSpace, NSwitch } from 'naive-ui'

const store = useSessionDataStore()

const allSeriesNames = computed(() => store.getChartFormattedData.series.map((s) => s.name))
const visibleSeriesSet = computed(() => store.visibleSeries)

const isSeriesVisible = (seriesName: string) => {
	return visibleSeriesSet.value.has(seriesName)
}

const toggleSeriesVisibility = (seriesName: string) => {
	store.toggleSeries(seriesName)
}

// Group series for display
const groupedSeries = computed(() => {
	const groups: Record<string, string[]> = {
		ESC: [],
		Motor: [],
		Throttle: [],
		GPS: [],
		'DS Temperature': [],
		Other: [],
	}

	allSeriesNames.value.forEach((name) => {
		if (name.startsWith('ESC')) {
			groups['ESC'].push(name)
		} else if (name.startsWith('Motor')) {
			groups['Motor'].push(name)
		} else if (name.startsWith('Throttle')) {
			groups['Throttle'].push(name)
		} else if (name.startsWith('GPS')) {
			groups['GPS'].push(name)
		} else if (name.startsWith('DS Temp')) {
			groups['DS Temperature'].push(name)
		} else {
			groups['Other'].push(name)
		}
	})
	// Filter out empty groups
	return Object.fromEntries(Object.entries(groups).filter(([, series]) => series.length > 0))
})

// Ensure preferences are loaded when the component is mounted or store is initialized
// This might be better placed in App.vue or when the store is first initialized.
// store.loadVisibilityPreferences() // Already called in fetchSessionData
</script>

<template>
	<n-card title="Series Visibility" size="small">
		<!-- This n-space will lay out the collapse items (groups) horizontally and wrap them -->
		<n-space wrap justify="space-around" :item-style="{ 'flex-grow': 1, 'min-width': '180px' }">
			<!-- Each n-collapse here will act as a group container. We iterate over groups to create multiple n-collapse instances or one n-collapse with multiple items -->
			<!-- For simplicity, let's make each group its own mini-collapse or just a section -->
			<!-- Removing accordion from n-collapse to allow multiple items to be open if we keep a single n-collapse -->
			<!-- The user's screenshot doesn't show accordion behavior, multiple sections are open. -->

			<!-- Option 1: Iterate and create a small card/section for each group -->
			<template v-for="(seriesList, groupName) in groupedSeries" :key="String(groupName)">
				<n-card :title="String(groupName)" size="small" style="margin-bottom: 10px">
					<n-space vertical>
						<n-switch
							v-for="seriesName in seriesList"
							:key="seriesName"
							:value="isSeriesVisible(seriesName)"
							@update:value="toggleSeriesVisibility(seriesName)"
						>
							<template #checked>
								{{ seriesName }}
							</template>
							<template #unchecked>
								{{ seriesName }}
							</template>
						</n-switch>
					</n-space>
				</n-card>
			</template>
		</n-space>
	</n-card>
</template>

<style scoped>
.n-card {
	margin-top: 16px;
}
</style>
