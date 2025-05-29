<script setup lang="ts">
import { computed } from 'vue'
import { useSessionDataStore, BATTERY_CURRENT_THRESHOLD_AMPS } from '../stores'
import { NCheckbox } from 'naive-ui'

const store = useSessionDataStore()

const allSeriesNames = computed(() => store.getChartFormattedData.series.map((s) => s.name))
const visibleSeriesSet = computed(() => store.visibleSeries)

const isSeriesVisible = (seriesName: string) => {
	return visibleSeriesSet.value.has(seriesName)
}

const toggleSeriesVisibility = (seriesName: string) => {
	store.toggleSeries(seriesName)
}

// Battery current filtering state

// Group series for display
const groupedSeries = computed(() => {
	const groups: Record<string, string[]> = {
		Custom: [],
		Temperature: [],
		Others: [],
	}

	allSeriesNames.value.forEach((name) => {
		const lowerName = name.toLowerCase()
		if (
			lowerName.includes('tesc') ||
			lowerName.includes('talum') ||
			lowerName.includes('tmosfet') ||
			lowerName.includes('tambient') ||
			name.startsWith('DS Temp')
		) {
			groups['Temperature'].push(name)
		} else {
			groups['Others'].push(name)
		}
	})
	// Filter out empty groups
	return Object.fromEntries(Object.entries(groups).filter(([, series]) => series.length > 0))
})

const getGroupIcon = (groupName: string) => {
	const icons: Record<string, string> = {
		Custom: '⚙️',
		Temperature: '🌡️',
		Others: '📊',
	}
	return icons[groupName] || '📊'
}

const getGroupColor = (groupName: string) => {
	const colors: Record<string, string> = {
		Custom: '#8b5cf6',
		Temperature: '#ef4444',
		Others: '#6b7280',
	}
	return colors[groupName] || '#6b7280'
}
</script>

<template>
	<div v-if="Object.keys(groupedSeries).length > 0" class="series-visibility-container">
		<div class="series-header">
			<h3 class="series-title">
				<span class="series-icon">👁️</span>
				Series Visibility
			</h3>
		</div>

		<div class="groups-container">
			<!-- Custom group with special content -->
			<div class="group-card" :style="{ '--group-color': getGroupColor('Custom') }">...</div>

			<!-- Other groups -->
			<template v-for="(seriesList, groupName) in groupedSeries" :key="String(groupName)">
				<div
					v-if="groupName !== 'Custom'"
					class="group-card"
					:style="{ '--group-color': getGroupColor(String(groupName)) }"
				>
					<div class="group-header">
						<span class="group-icon">{{ getGroupIcon(String(groupName)) }}</span>
						<h4 class="group-title">{{ groupName }}</h4>
					</div>

					<div class="toggles-container">
						<div
							v-for="seriesName in seriesList"
							:key="seriesName"
							class="toggle-item"
							:class="{ 'toggle-active': isSeriesVisible(seriesName) }"
							@click="toggleSeriesVisibility(seriesName)"
						>
							<div class="toggle-switch">
								<div class="toggle-slider" :class="{ 'slider-active': isSeriesVisible(seriesName) }">
									<div class="toggle-knob"></div>
								</div>
							</div>
							<span class="toggle-label">{{ seriesName }}</span>
						</div>
					</div>
				</div>
			</template>
		</div>
	</div>
</template>

<style scoped>
.series-visibility-container {
	background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
	border-radius: 16px;
	padding: 24px;
	box-shadow:
		0 4px 6px -1px rgba(0, 0, 0, 0.1),
		0 2px 4px -1px rgba(0, 0, 0, 0.06);
	border: 1px solid #e2e8f0;
}

.series-header {
	margin-bottom: 20px;
}

.series-title {
	display: flex;
	align-items: center;
	gap: 8px;
	margin: 0;
	font-size: 1.25rem;
	font-weight: 600;
	color: #1e293b;
}

.series-icon {
	font-size: 1.5rem;
}

.groups-container {
	display: grid;
	grid-template-columns: repeat(3, 1fr);
	gap: 20px;
}

.group-card {
	background: white;
	border-radius: 12px;
	padding: 20px;
	box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
	border: 2px solid transparent;
	transition: all 0.3s ease;
	position: relative;
	overflow: hidden;
}

.group-card::before {
	content: '';
	position: absolute;
	top: 0;
	left: 0;
	right: 0;
	height: 4px;
	background: var(--group-color);
}

.group-card:hover {
	transform: translateY(-2px);
	box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
	border-color: var(--group-color);
}

.group-header {
	display: flex;
	align-items: center;
	gap: 10px;
	margin-bottom: 16px;
	padding-bottom: 12px;
	border-bottom: 1px solid #f1f5f9;
}

.group-icon {
	font-size: 1.25rem;
}

.group-title {
	margin: 0;
	font-size: 1.1rem;
	font-weight: 600;
	color: #374151;
}

.toggles-container {
	display: flex;
	flex-direction: column;
	gap: 12px;
}

.toggle-item {
	display: flex;
	align-items: center;
	gap: 12px;
	padding: 8px 12px;
	border-radius: 8px;
	cursor: pointer;
	transition: all 0.2s ease;
	user-select: none;
}

.toggle-item:hover {
	background-color: #f8fafc;
}

.toggle-active {
	background-color: #f0f9ff;
}

.toggle-switch {
	position: relative;
	width: 44px;
	height: 24px;
	flex-shrink: 0;
}

.toggle-slider {
	position: absolute;
	top: 0;
	left: 0;
	right: 0;
	bottom: 0;
	background-color: #cbd5e1;
	border-radius: 12px;
	transition: all 0.3s ease;
	cursor: pointer;
}

.slider-active {
	background-color: var(--group-color, #10b981);
}

.toggle-knob {
	position: absolute;
	top: 2px;
	left: 2px;
	width: 20px;
	height: 20px;
	background-color: white;
	border-radius: 50%;
	transition: all 0.3s ease;
	box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.slider-active .toggle-knob {
	transform: translateX(20px);
}

.toggle-label {
	font-size: 0.9rem;
	font-weight: 500;
	color: #374151;
	transition: color 0.2s ease;
}

.toggle-active .toggle-label {
	color: #1e293b;
	font-weight: 600;
}

.custom-checkbox {
	padding: 12px;
	border-radius: 8px;
	background-color: #f8fafc;
	border: 1px solid #e2e8f0;
	transition: all 0.2s ease;
}

.custom-checkbox:hover {
	background-color: #f1f5f9;
	border-color: #cbd5e1;
}

@media (max-width: 768px) {
	.groups-container {
		grid-template-columns: 1fr;
		gap: 16px;
	}

	.series-visibility-container {
		padding: 16px;
	}

	.group-card {
		padding: 16px;
	}
}
</style>
