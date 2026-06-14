import '@testing-library/jest-dom/vitest'

class IO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// eslint-disable-next-line no-undef
globalThis.IntersectionObserver = IO
// eslint-disable-next-line no-undef
if (!globalThis.matchMedia) {
  globalThis.matchMedia = (q) => ({
    matches: false,
    media: q,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })
}
