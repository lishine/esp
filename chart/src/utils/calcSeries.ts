export const CALC_WHKM_WV_SERIES_WINDOW_LEN = 5
export const CALC_WHKM_WV_SERIES_WINDOW_SHIFT = 3

export function calculateMovingAverage(data: (number | null)[], windowSize: number): (number | null)[] {
	if (windowSize <= 0 || data.length === 0) {
		return Array(data.length).fill(null)
	}

	const smoothedData: (number | null)[] = []
	const halfWindow = Math.floor(windowSize / 2)

	for (let i = 0; i < data.length; i++) {
		if (i < halfWindow || i >= data.length - halfWindow) {
			smoothedData.push(null)
			continue
		}

		let sum = 0
		let count = 0
		// let nullCount = 0; // Removed as it was unused
		for (let j = i - halfWindow; j <= i + halfWindow; j++) {
			if (data[j] !== null && data[j] !== undefined) {
				sum += data[j] as number
				count++
			} //else {
			// nullCount++;
			//}
		}

		// If more than half the window is null, or if window is too small and contains nulls, result is null
		// A more robust check might be needed depending on desired behavior for sparse data.
		// For now, if count is less than half window size, consider it too sparse.
		if (count < Math.ceil(windowSize / 2)) {
			smoothedData.push(null)
		} else {
			smoothedData.push(sum / count)
		}
	}
	return smoothedData
}

export function calculateEfficiencySeries(
	dataMaps: {
		escVMap: Map<number, number | null>
		escIMap: Map<number, number | null>
		escMahMap: Map<number, number | null>
		gpsLatMap: Map<number, number | null>
		gpsLonMap: Map<number, number | null>
		gpsSpeedMap: Map<number, number | null>
	},
	sortedTimestamps: number[],
	haversineDistance: (lat1: number, lon1: number, lat2: number, lon2: number) => number
): { whPerKmMap: Map<number, number | null>; wPerSpeedMap: Map<number, number | null> } {
	const voltageArray: (number | null)[] = sortedTimestamps.map((ts) => dataMaps.escVMap.get(ts) ?? null)
	const currentArray: (number | null)[] = sortedTimestamps.map((ts) => dataMaps.escIMap.get(ts) ?? null)
	const mahArray: (number | null)[] = sortedTimestamps.map((ts) => dataMaps.escMahMap.get(ts) ?? null)
	const gpsLatArray: (number | null)[] = sortedTimestamps.map((ts) => dataMaps.gpsLatMap.get(ts) ?? null)
	const gpsLonArray: (number | null)[] = sortedTimestamps.map((ts) => dataMaps.gpsLonMap.get(ts) ?? null)
	// gpsSpeedMap now provides speed in km/h, interpolated
	const gpsSpeedArray: (number | null)[] = sortedTimestamps.map((ts) => dataMaps.gpsSpeedMap.get(ts) ?? null)
	// console.log({ gpsSpeedArray: gpsSpeedArray }) // Keep for debugging if needed

	const smoothedVoltageArray = calculateMovingAverage(voltageArray, CALC_WHKM_WV_SERIES_WINDOW_LEN)
	const smoothedCurrentArray = calculateMovingAverage(currentArray, CALC_WHKM_WV_SERIES_WINDOW_LEN)
	const smoothedMahArray = calculateMovingAverage(mahArray, CALC_WHKM_WV_SERIES_WINDOW_LEN)
	// console.log('GPS Speed Array (km/h):', gpsSpeedArray.slice(0, 50))
	// console.log('Number of non-null GPS speeds:', gpsSpeedArray.filter((v) => v !== null).length)
	const smoothedGpsSpeedArray = calculateMovingAverage(gpsSpeedArray, CALC_WHKM_WV_SERIES_WINDOW_LEN)
	// console.log('Smoothed GPS Speed Array non-null count:', smoothedGpsSpeedArray.filter((v) => v !== null).length)

	const whPerKmMap = new Map<number, number | null>()
	const wPerSpeedMap = new Map<number, number | null>()

	for (let i = 0; i < sortedTimestamps.length; i++) {
		const t_center = sortedTimestamps[i]

		const windowStartIdx = Math.max(0, i - Math.floor(CALC_WHKM_WV_SERIES_WINDOW_LEN / 2))
		const windowEndIdx = Math.min(sortedTimestamps.length - 1, i + Math.floor(CALC_WHKM_WV_SERIES_WINDOW_LEN / 2))

		if (windowEndIdx - windowStartIdx + 1 < CALC_WHKM_WV_SERIES_WINDOW_LEN) {
			whPerKmMap.set(t_center, null)
			wPerSpeedMap.set(t_center, null)
			continue
		}

		const shiftedWindowStartIdx = windowStartIdx + CALC_WHKM_WV_SERIES_WINDOW_SHIFT
		const shiftedWindowEndIdx = windowEndIdx + CALC_WHKM_WV_SERIES_WINDOW_SHIFT

		if (shiftedWindowStartIdx < 0 || shiftedWindowEndIdx >= sortedTimestamps.length) {
			whPerKmMap.set(t_center, null)
			wPerSpeedMap.set(t_center, null)
			continue
		}

		// Calculate "Wh/km"
		let whPerKmVal: number | null = null
		const gpsLatStart = gpsLatArray[windowStartIdx]
		const gpsLonStart = gpsLonArray[windowStartIdx]
		const gpsLatEnd = gpsLatArray[windowEndIdx]
		const gpsLonEnd = gpsLonArray[windowEndIdx]

		if (gpsLatStart != null && gpsLonStart != null && gpsLatEnd != null && gpsLonEnd != null) {
			const distanceMetersWindow = haversineDistance(gpsLatStart, gpsLonStart, gpsLatEnd, gpsLonEnd)
			const distanceKmWindow = distanceMetersWindow / 1000

			const mahStartShifted = smoothedMahArray[shiftedWindowStartIdx]
			const mahEndShifted = smoothedMahArray[shiftedWindowEndIdx]

			if (mahStartShifted != null && mahEndShifted != null) {
				const deltaMahShiftedWindow = mahEndShifted - mahStartShifted
				let sumVoltageShiftedWindow = 0
				let countVoltageShiftedWindow = 0
				for (let j = shiftedWindowStartIdx; j <= shiftedWindowEndIdx; j++) {
					if (smoothedVoltageArray[j] != null) {
						sumVoltageShiftedWindow += smoothedVoltageArray[j] as number
						countVoltageShiftedWindow++
					}
				}

				if (countVoltageShiftedWindow > 0) {
					// Ensure some data points for average
					const avgVoltageShiftedWindow = sumVoltageShiftedWindow / countVoltageShiftedWindow
					const energyWhWindow = (avgVoltageShiftedWindow * deltaMahShiftedWindow) / 1000
					if (distanceKmWindow > 0 && deltaMahShiftedWindow > 0 && energyWhWindow != null) {
						whPerKmVal = energyWhWindow / distanceKmWindow
					}
				}
			}
		}
		whPerKmMap.set(t_center, whPerKmVal)

		// Calculate "W/speed"
		let wPerSpeedVal: number | null = null
		let sumPowerWShiftedWindow = 0
		let countPowerWShiftedWindow = 0
		for (let j = shiftedWindowStartIdx; j <= shiftedWindowEndIdx; j++) {
			if (smoothedVoltageArray[j] != null && smoothedCurrentArray[j] != null) {
				sumPowerWShiftedWindow += (smoothedVoltageArray[j] as number) * (smoothedCurrentArray[j] as number)
				countPowerWShiftedWindow++
			}
		}

		if (countPowerWShiftedWindow > 0) {
			// Ensure some data points for average
			const avgPowerWShiftedWindow = sumPowerWShiftedWindow / countPowerWShiftedWindow
			const avgSpeedKmhWindow = smoothedGpsSpeedArray[i] // This is now already in km/h

			if (avgSpeedKmhWindow != null && avgSpeedKmhWindow > 0 && avgPowerWShiftedWindow != null) {
				wPerSpeedVal = avgPowerWShiftedWindow / avgSpeedKmhWindow
			}
		}
		wPerSpeedMap.set(t_center, wPerSpeedVal)
	}

	return { whPerKmMap, wPerSpeedMap }
}
