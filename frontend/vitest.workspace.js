/// <reference types="vitest/config" />
// NOTE: This file is kept for reference only. The active test configuration is
// vitest.config.ts, which uses test.projects (Vitest 4 API) for both the
// storybook browser project and the unit-test project.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { storybookTest } from '@storybook/addon-vitest/vitest-plugin';
import { playwright } from '@vitest/browser-playwright';

const dirname = typeof __dirname !== 'undefined' ? __dirname : path.dirname(fileURLToPath(import.meta.url));

export default [
  {
    extends: 'vite.config.js',
    plugins: [
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
        instances: [{
          browser: 'chromium'
        }]
      },
      setupFiles: ['.storybook/vitest.setup.ts']
    }
  },
  {
    extends: 'vite.config.js',
    test: {
      name: 'unit',
      environment: 'happy-dom',
      include: ['src/**/*.test.ts']
    }
  }
];
