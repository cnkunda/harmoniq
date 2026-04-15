/**
 * Optional dev logging for stem/tab transport (loop wrap, seeks). No-op in production.
 */
export function logListenTransportWrap(prevSec: number, nextSec: number): void {
  if (typeof __DEV__ === 'undefined' || !__DEV__) return
  // eslint-disable-next-line no-console
  console.debug('[ListenTransport] position wrap/jump', {
    prevSec: Math.round(prevSec * 1000) / 1000,
    nextSec: Math.round(nextSec * 1000) / 1000,
  })
}
