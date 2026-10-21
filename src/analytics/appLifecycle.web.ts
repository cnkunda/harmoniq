/** Flush analytics when the browser tab is hidden or unloaded. */
export function subscribeAnalyticsBackground(onBackground: () => void): () => void {
  if (typeof document === 'undefined' || typeof window === 'undefined') {
    return () => {}
  }

  const onVisibilityChange = () => {
    if (document.visibilityState === 'hidden') onBackground()
  }
  const onPageHide = () => onBackground()

  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('pagehide', onPageHide)
  return () => {
    document.removeEventListener('visibilitychange', onVisibilityChange)
    window.removeEventListener('pagehide', onPageHide)
  }
}
