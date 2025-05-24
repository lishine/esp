# Chart Axis Modification Plan

## Current State

- Current (I) axis shows values and labels on the left side of the chart
- Temperature (T) axis shows values and labels on the right side of the chart
- Each axis has its own vertical line

## Desired State

- Both axes should share the same vertical line on the right side of the chart
- Current (I) values and labels should appear on the left side of this vertical line
- Temperature (T) values and labels should appear on the right side of this vertical line

## Implementation Strategy

We need to modify the axis configuration to achieve this layout. In ECharts, we can control the position of axis labels relative to their axis line using the `axisLabel.inside` property:

1. Move the Current (I) axis to the right side but configure its labels to appear inside:

   ```typescript
   {
     id: 'yCurrent',
     name: 'I',
     position: 'right',
     axisLabel: {
       inside: true,  // This places labels inside (left of) the axis line
       align: 'right' // This aligns the text to the right
     }
   }
   ```

2. Keep Temperature (T) axis configuration similar but ensure labels are outside:

   ```typescript
   {
     id: 'yTemperature',
     name: 'T',
     position: 'right',
     axisLabel: {
       inside: false  // This keeps labels outside (right of) the axis line
     }
   }
   ```

3. Adjust grid margins to accommodate the new layout:
   ```typescript
   grid: {
     right: '8%',  // May need adjustment based on actual label widths
     // ... other grid properties
   }
   ```

## Technical Notes

- The `axisLabel.inside` property determines whether labels appear inside or outside of the axis line
- Both axes will share the same vertical line on the right side
- The order of axes in yAxesConfig array determines their z-index
- May need to adjust label padding and alignment for optimal spacing

## Testing Plan

1. Verify both sets of labels are clearly visible
2. Confirm Current (I) labels appear on the left side of the vertical line
3. Confirm Temperature (T) labels appear on the right side of the vertical line
4. Check for any label overlapping issues
5. Test with different data ranges to ensure proper scaling and label placement

## Next Steps

Switch to Code mode to implement these changes in `chart/src/views/DataDisplayView.vue`
