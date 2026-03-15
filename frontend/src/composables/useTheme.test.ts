import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const STORAGE_KEY = 'clue-theme'

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    vi.resetModules()
  })

  it('defaults to dark when localStorage is empty', async () => {
    const { useTheme } = await import('./useTheme')
    const { theme } = useTheme()
    expect(theme.value).toBe('dark')
  })

  it('loads saved theme from localStorage', async () => {
    localStorage.setItem(STORAGE_KEY, 'light')
    const { useTheme } = await import('./useTheme')
    const { theme } = useTheme()
    expect(theme.value).toBe('light')
  })

  it('applies data-theme attribute immediately on import', async () => {
    localStorage.setItem(STORAGE_KEY, 'vintage')
    await import('./useTheme')
    expect(document.documentElement.getAttribute('data-theme')).toBe('vintage')
  })

  it('returns all themes', async () => {
    const { useTheme } = await import('./useTheme')
    const { themes } = useTheme()
    expect(themes).toEqual(['dark', 'light', 'vintage'])
  })

  it('setTheme changes the active theme', async () => {
    const { useTheme } = await import('./useTheme')
    const { theme, setTheme } = useTheme()
    setTheme('light')
    expect(theme.value).toBe('light')
  })

  it('setTheme updates the data-theme attribute', async () => {
    const { useTheme } = await import('./useTheme')
    const { setTheme } = useTheme()
    setTheme('vintage')
    await nextTick()
    expect(document.documentElement.getAttribute('data-theme')).toBe('vintage')
  })

  it('setTheme persists the selection to localStorage', async () => {
    const { useTheme } = await import('./useTheme')
    const { setTheme } = useTheme()
    setTheme('light')
    await nextTick()
    expect(localStorage.getItem(STORAGE_KEY)).toBe('light')
  })

  it('setTheme ignores unknown theme names', async () => {
    const { useTheme } = await import('./useTheme')
    const { theme, setTheme } = useTheme()
    const before = theme.value
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    setTheme('neon' as any)
    expect(theme.value).toBe(before)
  })

  it('cycleTheme advances to the next theme', async () => {
    const { useTheme } = await import('./useTheme')
    const { theme, cycleTheme } = useTheme()
    // default is 'dark' → cycle to 'light'
    expect(theme.value).toBe('dark')
    cycleTheme()
    expect(theme.value).toBe('light')
  })

  it('cycleTheme wraps around from the last theme to the first', async () => {
    localStorage.setItem(STORAGE_KEY, 'vintage')
    const { useTheme } = await import('./useTheme')
    const { theme, cycleTheme } = useTheme()
    expect(theme.value).toBe('vintage')
    cycleTheme()
    expect(theme.value).toBe('dark')
  })

  it('cycleTheme covers all themes in order', async () => {
    const { useTheme } = await import('./useTheme')
    const { theme, themes, cycleTheme } = useTheme()
    const visited: string[] = [theme.value]
    for (let i = 0; i < themes.length - 1; i++) {
      cycleTheme()
      visited.push(theme.value)
    }
    expect(visited).toEqual(themes)
  })
})
