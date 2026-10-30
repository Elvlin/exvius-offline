param(
    [string]$Version = '0.1.0',
    [string]$ClientVersion = '9.0.0-offline.1',
    [int]$VersionCode = 9001,
    [string]$KeyStore = 'tools/vendor/exvius-test.jks',
    [string]$KeyAlias = 'exvius-test'
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $taskRoot
if (-not $env:JAVA_HOME -or -not $env:ANDROID_HOME) { throw 'Set JAVA_HOME and ANDROID_HOME first.' }
if (-not $env:EXVIUS_KEYSTORE_PASSWORD) { throw 'Set EXVIUS_KEYSTORE_PASSWORD to the private signing-key password.' }
New-Item -ItemType Directory -Path logs, source/build/distribution/assets -Force | Out-Null
Start-Transcript -Path logs/distribution-app-build-20261030.log -Append | Out-Null
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:FFBE_DATA = Join-Path $taskRoot 'data'
$env:PYTHONPATH = (Join-Path $taskRoot 'tools/vendor/python') + ';' + (Join-Path $taskRoot 'source/exvius') + ';' + (Join-Path $taskRoot 'source/server')
$env:Path = (Join-Path $env:JAVA_HOME 'bin') + ';' + $env:Path
$taskBuildTools = Join-Path $env:ANDROID_HOME 'build-tools/36.0.0'
node source/exvius/test_android_display.js
if ($LASTEXITCODE -ne 0) { throw 'Display checks failed' }
node source/exvius/test_home_carousel.js
if ($LASTEXITCODE -ne 0) { throw 'Home checks failed' }
python source/exvius/test_release_data.py
if ($LASTEXITCODE -ne 0) { throw 'Data package checks failed' }
java -cp source/memorial/android/gradle/wrapper/gradle-wrapper.jar org.gradle.wrapper.GradleWrapperMain -p source/memorial/android --no-daemon assembleDebug
if ($LASTEXITCODE -ne 0) { throw 'Android runtime build failed' }
python source/exvius/android_build.py --local-engine --speed 1 --release-version $ClientVersion --release-code $VersionCode
if ($LASTEXITCODE -ne 0) { throw 'Original client integration failed' }
node tools/vendor/android-agent/node_modules/frida-compile/dist/cli.js source/exvius/android_test.js -o source/build/android/android_test.bundle.js -S -c -T none
if ($LASTEXITCODE -ne 0) { throw 'Native integration compilation failed' }
Copy-Item -LiteralPath source/build/android/android_test.bundle.js -Destination source/build/android/client/lib/arm64-v8a/libexviustest.js.so
$taskUnsigned = 'source/build/android/distribution-unsigned.apk'
$taskAligned = 'source/build/android/distribution-aligned.apk'
$taskFinal = "source/build/distribution/assets/exvius-offline-v$Version.apk"
java -jar tools/vendor/apktool_3.0.3.jar b source/build/android/client -p tools/vendor/apktool-framework -o $taskUnsigned
if ($LASTEXITCODE -ne 0) { throw 'APK packaging failed' }
& "$taskBuildTools/zipalign.exe" -P 16 -f 4 $taskUnsigned $taskAligned
if ($LASTEXITCODE -ne 0) { throw 'APK alignment failed' }
& "$taskBuildTools/apksigner.bat" sign --ks $KeyStore --ks-key-alias $KeyAlias --ks-pass env:EXVIUS_KEYSTORE_PASSWORD --out $taskFinal $taskAligned
if ($LASTEXITCODE -ne 0) { throw 'APK signing failed' }
& "$taskBuildTools/apksigner.bat" verify $taskFinal
if ($LASTEXITCODE -ne 0) { throw 'APK signature check failed' }
python source/exvius/finalize_distribution.py --version $Version --client-version $ClientVersion --version-code $VersionCode
if ($LASTEXITCODE -ne 0) { throw 'Release verification failed' }
Stop-Transcript | Out-Null
