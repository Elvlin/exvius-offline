# Android to iOS compatibility matrix

All iOS replacements below are proposed, not implemented. Preserve Android paths.

| Android component | Reuse | Proposed iOS replacement / validation |
| --- | --- | --- |
| server gameplay modules and ffbe_pipeline | High | Embed unchanged first; preserve transform order |
| LocalGame in-process adapter | High | Native bridge to existing method/status/headers/bytes contract |
| Global endpoints.json and responses.json | Conditional | Compare with Memorial protocol; translate only measured differences |
| PlayerState JSON saves | High | Durable sandbox path; verify failed writes, migration, and restart |
| ffbe_crypto | Interface and behavior | Build iOS cryptography dependency or validate equivalent vectors; no CLI fallback |
| PyYAML friend definitions | High | Package compatible dependency; pure-Python loading is an option |
| Chaquopy / Gradle runtime | None | Embedded CPython and signed iOS runtime dependencies |
| android_game.py | Partial | Extract equivalent path binding and archive actions into an iOS host adapter |
| LocalGameBridge.java / native_bridge.js JNI | Behavior only | Objective-C++/C bridge with GIL ownership and serialized calls |
| LocalGameConnection.java | Contract only | Verified client transport boundary; do not assume URLProtocol covers all traffic |
| LocalCocosTasks.java | Lifecycle only | iOS callbacks, progress, cancellation, and correct dispatch threads |
| android_offline.py smali patching | Intent only | Version-pinned Mach-O/platform adapters; retain prepatch validation |
| Android Frida hooks and offsets | Intent/helpers | Rediscover iOS targets, layouts and ABI; pre-graft necessary targets if using Gadget |
| Title, summon, event, raid menus | Logic partially | Port UI bindings; verify scenes exist in Memorial |
| Google billing/login/telemetry stubs | Intent only | Inventory iOS SDKs; disable platform calls without breaking client callbacks |
| GameAssets APK resource mounting | None | iOS bundle/search-root adapter and native resource lookup |
| CRI installer hooks | Intent only | Verify iOS CRI local loading and completion; avoid retired CDN fallback |
| DataPack/DataUpdates/DownloadActivity | Manifest/integrity rules | iOS downloader/importer, staging, checksums, interrupted-install recovery |
| gamedata.xml / shared_prefs registry | Logical versions | iOS preference mapping or backend-compatible generated registry |
| WebView page handling | HTML/behavior partly | Separate iOS web-content adapter; preserve POST semantics and local links |
| MediaPlayer movie paths | Assets conditional | iOS media adapter; validate containers/codecs and local paths |
| Android sound directories | None | Platform-aware resource mapping; verify actual iOS directory names |
| Decoded tables, art, maps, events | Conditional | Check schemas, IDs, loaders, codecs and resource completeness |
| android_display.js | Pure layout helpers partly | iPhone/iPad safe-area, touch, orientation and native Cocos bindings |
| apktool/zipalign/apksigner | None | Reproducible iOS build, packaging and signing workflow |
| Desktop Rust launcher | Optional research use | Not required or relied upon during on-device gameplay |

The desktop smoke uses synthetic content. It does not certify compatibility for
any proprietary client, asset pack, summon animation, battle, or iOS runtime.
