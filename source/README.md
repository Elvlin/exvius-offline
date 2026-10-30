# Source code

This folder contains the offline adaptation, local game logic and Android integration.

| Folder | Purpose |
| --- | --- |
| `server/` | Local game logic, campaign persistence and request handlers. |
| `exvius/` | Original-client integration, content preparation and release tools. |
| `memorial/android/` | Android download/bootstrap integration and embedded local runtime. |
| `harness/` | Protocol and content inspection utilities. |
| `docs/` | Supporting format and implementation documentation. |

## Building

The current release script runs on Windows.

The build uses Java 11, Python 3.10, Node.js, Android SDK platform 33 with build-tools 36.0.0, Gradle 7.6.4, Chaquopy 16.1.0, apktool 3.0.3 and Frida Gadget 17.24.3 for arm64.

Set `JAVA_HOME` and `ANDROID_HOME` for your machine. The integration expects the verified original Global v9.0.0 APK at `repository snapshots/FFBE-Global-v9.0.0-original.apk` and the external tools under `tools/vendor/`. Original client binaries and signing keys are not part of the source repository.

The original APK SHA-256 is `955deacfbe4b3d0cd04e2947eb005e310915ba98132d71216626bfb3554ad246`.

The Android runtime is built from `memorial/android/`. Then `exvius/android_build.py --local-engine --speed 1 --release-version 9.0.0-offline.1 --release-code 9001` prepares the integrated client. Package it with apktool, align it with zipalign, and sign it with your own private signing key. Keep the same key for future updates to your installation.

`exvius/build_distribution.ps1` runs these steps with `JAVA_HOME`, `ANDROID_HOME` and `EXVIUS_KEYSTORE_PASSWORD` set. Its `KeyStore` and `KeyAlias` parameters select your private signing key. Distribution builds disable Android debugging.

`exvius/build_release_data.py` packages the complete accepted game data from the established `data/` trees. It uses the same original/recovered/overlay precedence as `exvius/push_client_cache.py`, excludes campaign saves, and generates the release data manifest.

For a new release, upload the generated data parts and APK as release assets, then update `data/latest.json` with their exact URLs, sizes, checksums and increasing version numbers. The app only checks this static manifest; gameplay does not require a hosted game server.
