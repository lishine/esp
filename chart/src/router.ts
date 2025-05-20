import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import DataDisplayView from './views/DataDisplayView.vue' // Adjusted path

const routes: Array<RouteRecordRaw> = [
	{
		path: '/',
		name: 'DataDisplay',
		component: DataDisplayView,
	},
]

export const router = createRouter({
	history: createWebHistory(import.meta.env.BASE_URL),
	routes,
})
