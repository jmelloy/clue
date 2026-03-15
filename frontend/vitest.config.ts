/// <reference types="vitest/config" />
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, defineProject } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { storybookTest } from '@storybook/addon-vitest/vitest-plugin'
import { playwright } from '@vitest/browser-playwright'

const dirname = typeof __dirname !== 'undefined' ? __dirname : path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  test: {
    projects: [
      defineProject({
        plugins: [
          vue(),
          storybookTest({
            configDir: path.join(dirname, '.storybook')
          })
        ],
        test: {
          name: 'storybook',
          browser: {
            enabled: true,
            headless: true,
            provider: playwright({}),
            instances: [{ browser: 'chromium' }]
          },
          setupFiles: ['.storybook/vitest.setup.ts']
        }
      }),
      defineProject({
        plugins: [vue()],
        test: {
          name: 'unit',
          environment: 'happy-dom',
          include: ['src/**/*.test.ts']
        }
      })
    ]
  }
})

