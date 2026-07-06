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

/** True for a local/dev image (no published build metadata baked in). */
export const IS_DEV_BUILD = !IS_PUBLISHED_BUILD

/**
 * The version string to SHOW in the UI. Published images show their real
 * version; dev images always read 'dev' so it's unmistakable you're not on a
 * production container (prevents accidental changes against prod).
 */
export const DISPLAY_VERSION = IS_PUBLISHED_BUILD ? BUILD.version : 'dev'

export default BUILD
