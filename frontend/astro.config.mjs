import { defineConfig } from 'astro/config';
import node from '@astrojs/node';

// https://astro.build/config
export default defineConfig({
    output: 'server',
    adapter: node({
        mode: 'standalone',
    }),
    vite: {
        server: {
            host: true, // Listen on all local IPs (0.0.0.0)
        }
    }
});
