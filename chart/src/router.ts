import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import DataDisplayView from './views/DataDisplayView.vue' // Adjusted path

const routes: Array<RouteRecordRaw> = [
	{
		path: '/',
		name: 'DataDisplay',
		component: DataDisplayView,
		// Children routes can be used if you want to share the same component
		// but change parts of it or handle different paths.
		// For this case, a separate top-level route or a more specific child is fine.
	},
	{
		path: '/github/:filename', // New route for GitHub files
		name: 'GitHubFileDisplay',
		component: DataDisplayView, // Still uses DataDisplayView
		props: true, // This allows the :filename param to be passed as a prop if needed,
		// or we can access it via useRoute().params.filename
	},
]

export const router = createRouter({
	history: createWebHistory(import.meta.env.BASE_URL),
	routes,
})
