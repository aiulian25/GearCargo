/**
 * Build metadata baked in at image-build time (Dockerfile → Vite `VITE_*` env).
 * The backend exposes the SAME values at /api/app-version; comparing the two
 * lets the app detect a newer published build and tell a feature update
 * (git_sha changed) apart from a weekly OS-security rebuild (git_sha unchanged,
 * newer build_date). In local dev these are unset → treated as 'dev' (no update
 * prompts).
 */
export const BUILD = {
  version: import.meta.env.VITE_APP_VERSION || '0.0.0',
  gitSha: import.meta.env.VITE_GIT_SHA || 'dev',
  buildDate: import.meta.env.VITE_BUILD_DATE || '',
}

/** True when running a real published image (not a local dev build). */
export const IS_PUBLISHED_BUILD = BUILD.gitSha !== 'dev' && BUILD.gitSha !== ''

export default BUILD
