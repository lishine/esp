export function calculateMovingAverageForSeries(
	points: Array<[Date, number | null]>,
	windowMs: number
): Array<[Date, number | null]> {
	if (!points || points.length === 0 || windowMs <= 0) {
		return points
	}

	const averagedPoints: Array<[Date, number | null]> = []

	for (let i = 0; i < points.length; i++) {
		const currentPoint = points[i]
		const currentTime = currentPoint[0].getTime()
		let sum = 0
		let count = 0
		const windowStartTime = currentTime - windowMs

		// Iterate backwards from the current point to include points within the window
		for (let j = i; j >= 0; j--) {
			const historicalPoint = points[j]
			const historicalTime = historicalPoint[0].getTime()

			if (historicalTime >= windowStartTime) {
				if (historicalPoint[1] !== null) {
					sum += historicalPoint[1]
					count++
				}
			} else {
				// Past the window, stop for this currentPoint
				break
			}
		}

		if (count > 0) {
			averagedPoints.push([currentPoint[0], sum / count])
		} else {
			// If no valid points in window (e.g. all null, or window too small at start)
			averagedPoints.push([currentPoint[0], null])
		}
	}
	return averagedPoints
}
