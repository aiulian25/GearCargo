# Image processing and dependency review (GC-005)

Reviewed 28 October 2026. This covers attachment image parsing and the associated
dependency changes. It does not claim that the complete container is free of
advisories.

## Decoder boundaries

JPEG, PNG, GIF, WebP and HEIF/HEIC are the only image decoders available to the
attachment worker. Uploads are checked before an attachment record is saved.
Non-HEIF originals, including normal animations, retain their bytes. HEIF is
oriented and converted to JPEG as before. Legacy files encounter the same guards
when OCR runs. PDF text extraction now uses the bounded OCR worker described in
[OCR operations](OCR_QUEUE.md). Other document formats retain their behavior.

Each decode runs in a disposable Linux subprocess, as the application user, with:

| Limit | Maximum |
|---|---|
| Input file / generated JPEG | 10 MiB |
| Image dimensions | 20 million pixels; 12,000 pixels on either side |
| Top-level text/binary metadata | 256 KiB |
| Animation | 100 frames; 100 million logical canvas pixels across frames |
| Address space / CPU / wall time | 512 MiB / 8 seconds / 12 seconds |
| Output-file size / core dumps | 64 MiB / disabled |
| OCR pixel buffer | 4 million pixels; 4,096 pixels on either side |

Only bounded RGB pixels return to the application for OCR; original metadata is
not reparsed there. The first frame is used for OCR. Very narrow images cannot
expand into huge buffers when targeting a 1,500-pixel short side. Tesseract has a
5-second orientation timeout and 15 seconds per recognition pass. Rejected
uploads leave no attachment row or image temporary file. A timeout kills and
reaps the decoder process group.

These per-operation limits are now combined with GC-025's two deployment-wide
processing slots, including synchronous upload validation. Process resource limits
do not replace codec security patches. The production runtime is Linux;
the `resource`/process-group controls are not a portable Windows decoder API.

## Reviewed dependency changes

Pillow `~=13.0` was already present in the working tree when GC-005 started, and
the original local runtime already had 13.0.0. That existing fix was preserved.
The upstream [GIF parser](https://github.com/python-pillow/Pillow/security/advisories/GHSA-74r2-7ff9-mjj2)
and [PNG EXIF parser](https://github.com/python-pillow/Pillow/security/advisories/GHSA-g4qv-2jxx-769h)
advisories identify 13.0.0 as patched. Decoder isolation and format/pixel bounds
provide additional protection. No harmful advisory exploit samples were run.

| Frontend package | Original lock | Reviewed lock |
|---|---|---|
| Vite | 7.3.6 | 7.3.7 |
| Vitest and its companion packages | 4.1.11 | 4.1.12 |
| follow-redirects | 1.16.0 | 1.16.2 |
| zod | 4.5.4 | 4.6.7 |
| serialize-javascript | 7.0.5 | 7.1.4 |
| fast-uri | 3.1.8 | 3.1.9 |

The Vite/Vitest owning ranges were raised to their compatible fixes. Transitives
were updated within owner ranges; no forced upgrade, override or audit ignore was
added. npm 10's peer resolver crashed during lockfile generation; a temporary npm
11 client generated it, and the normal npm 10 `npm ci --ignore-scripts`, tests,
lint and build validated it. The Docker build also used its normal `npm ci`.

## Accepted npm exception: deepmerge

The fresh full npm scan changed from 11 affected package nodes (3 high, 3 moderate,
5 low) to **four low-severity nodes**. The remaining nodes are one advisory and
its owner chain:

`vite-plugin-pwa → workbox-build → @rollup/plugin-node-resolve 16.0.3 → deepmerge 4.3.1`.

[GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4)
has no patched release listed. In the installed node-resolve implementation,
`dist/cjs/index.js` imports deepmerge and calls it only as
`deepMerge({}, defaults)` to initialize a constant default-options object. The
ES module build uses the same call. Those defaults are package literals, not uploaded
data. GearCargo's PWA options are repository-controlled in `frontend/vite.config.js`.
This chain runs during the build and is not a Node server shipped in the runtime
image. The production-only npm scan reports zero findings.

This low-severity exception is accepted for that exact call path and dependency
set. Review it when the owner/deepmerge releases a fix, the implementation changes,
or untrusted build configuration is introduced. Do not apply npm's suggested PWA
downgrade to 0.2.1 merely to remove the report. The existing full informational
scan continues to show the finding and the high/critical CI gate remains active.

## Actual image inventory and unresolved OS findings

The locally built `gearcargo:gc005-verified` image is Linux/amd64 with Python
3.12.16. The recorded image digest, 95 Python distributions, native codec versions,
source hashes, OS package inventory and full scan results are under
`/tmp/gearcargo-gc005/`. The task's implementation note records the digest.

Relevant installed components:

| Component | Actual version / linkage |
|---|---|
| Pillow | 13.0.0 |
| pillow-heif | 1.8.1; bundled libheif 1.23.6 |
| NumPy / pytesseract | 2.5.4 / 0.3.13 |
| Pillow TIFF / WebP | bundled libtiff 4.7.2 / WebP 1.6.0 |
| HEIF codecs | bundled libde265 1.1.3; x265 4.3+1 |

Both the resolved Python manifest and installed Python inventory reported no
known advisories. The **Trivy high/critical image gate remains failing**:
119 package/advisory pairs (114 high, 5 critical), representing 58 unique CVEs.
The original `gearcargo:dev` image has the identical set of package/CVE pairs;
none were introduced or removed. All are Debian package findings, with no fixed
Debian version supplied by the scan. The image build ran the existing Debian
update/upgrade steps. These findings are not silently suppressed or accepted as
a group.

Selected reachability evidence:

- `ldd` confirms the HEIF extension loads its wheel's libheif 1.23.6, not Debian's
  separately installed libheif 1.15.1. Debian still marks the latter vulnerable,
  for example [CVE-2026-32740](https://security-tracker.debian.org/tracker/CVE-2026-32740).
  The old OS package's presence must remain visible in the image inventory.
- TIFF is not an accepted upload decoder; Pillow itself links its bundled TIFF
  library. Tesseract receives generated, bounded pixels rather than arbitrary
  original TIFF input.
- The reported Tesseract model-parser issues, including
  [CVE-2026-88047](https://security-tracker.debian.org/tracker/CVE-2026-88047),
  require crafted `.traineddata` files. The application selects installed
  `eng+ron+spa` models; uploads cannot select or replace model files. Keep model
  directories and images trusted and read-only to the application user.
- Other scanner findings concern D-Bus, CLI tools, fonts, SQLite, XML and other
  system APIs. This scoped image-upload review does not establish that every such
  call path is unreachable. It does not grant a blanket risk acceptance for them.

A separate base-image remediation or explicit per-advisory risk decision is
still needed before calling the image-wide security gate green. Changing the
base distribution or compiling a replacement OS stack was not folded into this
parser/toolchain fix. No `--ignore-unfixed`, advisory ignore list or scanner
severity reduction was added.

Use the separate locally retained rollback artifact and matching source/data if
compatibility requires reverting. Rollback restores the older parser/toolchain
behavior and its known findings; it is not a security remediation. No production
deployment, registry push or automatic downgrade is performed by these changes.
