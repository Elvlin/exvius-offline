# Exvius Debug

Isolated loader test build for Android 8+ ARM64. This is a test build, not a validated public release.

- App label: Exvius Debug
- Package: `com.exvius.offline.debug`
- Version: `9.0.0-debug.loader1` (9022001)
- Normal 1x speed; installs separately from the public Exvius app.
- Public-app installation and update checks are disabled in this Debug app.
- Initial setup downloads game data into this Debug app's own directory. It does not copy the public app's save.

This build uses a retained Debug-only signing identity so future Debug APKs signed with the same key and a higher version code can update it. It cannot update an earlier one-time-signed Debug installation. Export any old Debug save before replacing that old test installation. Do not uninstall the public Exvius app.

APK: `Exvius-Debug-loader1-reusable.apk`

SHA256: `36cde40bbbaa2e6f0e950316dbc3647a7c2f0ba51b7bdba165af9b3c66a776ba`

Signer certificate SHA256: `6d23c3e6a8f842a6eee14946387c98ac62c1db61812cb64ed47258791a2e70d2`

APK v2/v3 signatures and ZIP integrity were verified. The signed app payload matches the loader1 candidate. A physical-phone test has not been performed in the build environment, so successful startup and gameplay remain to be confirmed on device.

The signing key and password are not included in this repository.
