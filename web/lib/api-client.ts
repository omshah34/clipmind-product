// Global abort controller registry
const controllers = new Map<string, AbortController>();

/**
 * Enhanced fetch with built-in AbortController management.
 * Automatically cancels any in-flight request with the same key.
 * 
 * Usage:
 *   const { promise, cancel } = fetchWithCancel("user-profile", "/api/v1/me");
 */
export function fetchWithCancel<T>(
  key: string,
  url: string,
  options?: RequestInit
): { promise: Promise<T>; cancel: () => void } {
  // Cancel any in-flight request with the same key
  controllers.get(key)?.abort();

  const controller = new AbortController();
  controllers.set(key, controller);

  const promise = fetch(url, { ...options, signal: controller.signal })
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json() as Promise<T>;
    })
    .finally(() => {
      // Only delete if this is still the active controller for this key
      if (controllers.get(key) === controller) {
        controllers.delete(key);
      }
    });

  return {
    promise,
    cancel: () => controller.abort(),
  };
}
