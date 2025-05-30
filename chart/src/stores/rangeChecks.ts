export const applyRangeChecks = (internalId: string, value: number | null): number | null => {
	if (value === null || typeof value !== 'number' || isNaN(value)) return null

	let checkedValue: number | null = value
	if (internalId === 'esc_rpm') {
		if (checkedValue < 0 || checkedValue > 5000) checkedValue = null
	} else if (internalId === 'esc_v') {
		if (checkedValue < 30 || checkedValue > 55) checkedValue = null
	} else if (internalId === 'esc_i') {
		if (checkedValue < 0 || checkedValue > 200) checkedValue = null
	} else if (internalId === 'esc_t') {
		if (checkedValue < 10 || checkedValue > 140) checkedValue = null
	} else if (internalId === 'mc_i') {
		if (checkedValue < 0 || checkedValue > 200) checkedValue = null
	} else if (internalId === 'th_val') {
		if (checkedValue < 990 || checkedValue > 1900) checkedValue = null
	} else if (internalId.startsWith('ds_')) {
		if (checkedValue < 10 || checkedValue > 120) checkedValue = null
	} else if (internalId === 'gps_speed') {
		if (value === null || typeof value !== 'number' || isNaN(value)) {
			checkedValue = null
		} else if (value < 0 || value > 20) {
			checkedValue = null
		} else {
			checkedValue = value
		}
	}
	return checkedValue
}
