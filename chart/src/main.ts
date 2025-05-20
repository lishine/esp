import { createApp } from 'vue'
import App from './App.vue'
import { createPinia } from 'pinia'
import { router } from './router' // Use named import from ./router (router.ts)
import naive from 'naive-ui'
import './style.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(naive)

app.mount('#app')
