<script setup lang="ts">
import { NButton, NCard } from 'naive-ui'
// let a = 'hello' // Commented out to avoid TS6133: 'a' is declared but its value is never read.
// let b = 'hello' // Commented out to avoid TS6133: 'b' is declared but its value is never read.
let c = 'Title from variable C' // Declare 'c' - this will be used for the card title
</script>

<template>
	<div class="flex min-h-screen flex-col items-center justify-center bg-gray-100 p-4">
		<n-card :title="d" class="max-w-md shadow-lg">
			{/* Changed from 'd' to 'c' */} {/* Bind to the declared 'c' */}
			<p class="mb-4 text-gray-700">This card's title is now bound to the variable 'c' from the script.</p>
			<n-button type="primary" class="mt-4"> Primary Button </n-button>
			<n-button type="info" class="mt-4 ml-2"> Info Button </n-button>
		</n-card>
	</div>
</template>

<style>
/* Global styles can go here if needed, or in src/style.css */
/* For this example, we're relying on Tailwind and Naive UI's default styles */
</style>
