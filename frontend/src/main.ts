import '@mcp-b/global'
import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { router } from './router'

const app = createApp(App)
app.use(router)

app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue Error]', err, '\nComponent:', instance?.$options?.name || 'unknown', '\nInfo:', info);
};

app.mount('#app')
