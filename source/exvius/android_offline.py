"""Apply explicit offline Java changes to apktool's decoded GL9 sources."""
from pathlib import Path
import re
import shutil

PROJECT = Path(__file__).resolve().parents[2]
PACKAGE = Path('com/square_enix/android_googleplay/FFBEWW')

OFFLINE_TEXT = {
    'MAP_TEXT_120064': 'Town of Mitra',
    'GACHA_CONF_HAVE_PAYMENT_LAPIS': 'Lapis held: <param=num>',
    'CONNECT': 'Loading...',
    'CONNECTING': 'Loading',
    'DOWNLOAD': 'Loading...',
    'DOWNLOAD_NOTICE': 'Loading local game data.<br>This may take a few moments.',
    'NETWORK_FAIL': 'Unable to load local game data.',
    'CONNECT_ERROR': 'Unable to load local game data.<br><br>Please try again.',
    'CONNECT_ERROR2': 'Unable to load local game data.<br><br>Please try again.',
    'PURCHASE_ERROR_FIRST_TITLE': 'Unable to load this purchase.',
    'SERVER_MSG_22': 'Unable to load local game data.',
    'SERVER_MSG_34': 'Unable to load local game data.',
    'SERVER_MSG_35': 'Unable to load local game data.',
    'SERVER_MSG_164': 'Unable to load local game data.',
    'SERVER_MSG_922': 'Unable to load local game data.',
    'INITIAL_DOWNLOAD_NOTICE1': 'Loading game data stored on this device.',
    'INITIAL_DOWNLOAD_NOTICE2': 'Please wait while the local files load.',
    'INITIAL_DOWNLOAD_NOTICE3': ' ',
    'BKGD_DL_NOTICE_BODY': 'Loading game data stored on this device.',
    'DLC_BACKGROUND_DOWNLOAD_CONTENT': 'Preparing local game data.',
    'DLC_SCREENSIZE_WIFI': 'Preparing local game data: <param=size>.',
    'DOWNLOAD_CONFIRM_MESSAGE_EXPLAIN_WIFI': 'Loading from this device.',
    'DLC_BACKGROUND_DOWNLOAD_TITLE': 'Loading Local Data',
    'BKGD_DL_NOTICE_HEADER': 'Loading Local Data',
    'TUTORIAL_DOWNLOAD_SIZE': 'Local data size: <param=size>',
    'DOWNLOAD_CONFIRM_MESSAGE_EXPLAIN': 'The necessary data will be loaded from this device.',
    'MST_LOAD_FAILED': 'Unable to load local game data. Returning to the title screen.',
    'INSTALL_ERROR_TITLE_BACK': 'Unable to load a local game file. Returning to the title screen.',
    'ERROR_MAP_BIN_NOT_FOUND': 'Unable to load local map data. Returning to the title screen.',
    'TITLE_DELETE_DATA': 'Reload game data from this device?<br>Your save and installed game files will be kept.',
    'TITLE_REDOWNLOAD': 'Reload Local Data',
    'DATA_REDOWNLOAD_COMPLETE': 'Local game data will be loaded when you begin play.',
}


def write_changed(path, text):
    if not path.exists() or path.read_text(encoding='utf-8') != text:
        path.write_text(text, encoding='utf-8')


def replace_method(text, signature, body):
    pattern = r'(?m)^\.method ' + re.escape(signature) + r'\n.*?^\.end method'
    text, count = re.subn(pattern, '.method ' + signature + '\n' + body + '\n.end method',
                          text, flags=re.S | re.M)
    if count != 1:
        raise ValueError(f'Expected exactly one method: {signature}; found {count}')
    return text


def prepare_offline_code(client):
    original = PROJECT / 'source/build/android/decoded-code/smali'
    if not (original / PACKAGE / 'GooglePlayLapis.smali').exists():
        raise ValueError('Decode the original APK Java sources before building offline.')
    destination = client / 'smali'
    if not destination.exists():
        shutil.copytree(original, destination)
    changes = {
        'GooglePlayLapis': {
            'public onCreate()V': '    .locals 0\n    return-void',
        },
        'PlayGamesLogin': {
            'private static init()V': '    .locals 0\n    return-void',
            'public static init(Lorg/cocos2dx/lib/Cocos2dxActivity;)V': '    .locals 0\n    return-void',
            'private static initPgs()V': '    .locals 0\n    return-void',
            'public static signIn()V': '    .locals 0\n    return-void',
            'private static retrieveAccessToken()V': '    .locals 0\n    return-void',
            'public static isSignedIn()Z': '    .locals 1\n    const/4 v0, 0x0\n    return v0',
            'public static getToken()Ljava/lang/String;': '    .locals 1\n    const-string v0, ""\n    return-object v0',
        },
        'GoogleLogin': {
            'public static init(Lorg/cocos2dx/lib/Cocos2dxActivity;)V': '    .locals 0\n    return-void',
            'public static checkPreviousLogin(Lorg/cocos2dx/lib/Cocos2dxActivity;)Z': '    .locals 1\n    const/4 v0, 0x0\n    return v0',
            'public static login()V': '    .locals 0\n    return-void',
            'public static loginSilently()V': '    .locals 0\n    return-void',
            'public static isServiceAvailable()Z': '    .locals 1\n    const/4 v0, 0x0\n    return v0',
            'public static isLoggedIn()Z': '    .locals 1\n    const/4 v0, 0x0\n    return v0',
        },
        'PlatformUtils': {
            'public getAdvertisingId()V': '    .locals 0\n    return-void',
            'protected initializePlatform()V': '    .locals 0\n    return-void',
            'protected tapjoyConnect()V': '    .locals 0\n    return-void',
            'protected onStart(Lcom/square_enix/android_googleplay/FFBEWW/Lapis;)V': '    .locals 0\n    return-void',
            'protected onStop(Lcom/square_enix/android_googleplay/FFBEWW/Lapis;)V': '    .locals 0\n    return-void',
            'protected setUserId(Ljava/lang/String;)V': '    .locals 0\n    return-void',
        },
        'PlatformUtilsGoogle': {
            'protected onResume()V': '    .locals 0\n    invoke-super {p0}, Lcom/square_enix/android_googleplay/FFBEWW/PlatformUtils;->onResume()V\n    return-void',
            'protected getAdTrackingEnabled()Z': '    .locals 1\n    const/4 v0, 0x0\n    return v0',
            'public getAdvertisingId(Lcom/square_enix/android_googleplay/FFBEWW/PlatformUtils$IAdIdResolverListener;)V': '''    .locals 1
    if-eqz p1, :exvius_no_ad_listener
    const-string v0, ""
    invoke-interface {p1, v0}, Lcom/square_enix/android_googleplay/FFBEWW/PlatformUtils$IAdIdResolverListener;->onAdIdResolved(Ljava/lang/String;)V
    :exvius_no_ad_listener
    return-void''',
        },
        'FbWrap': {
            'public init()V': '    .locals 0\n    return-void',
            'public isLoggedIn()Z': '    .locals 1\n    const/4 v0, 0x0\n    return v0',
        },
    }
    for name in ('getAccessToken', 'getAppId', 'getAppURLSchemeSuffix',
                 'getGraphAPIVersion', 'getSDKVersion', 'getUserID'):
        changes['FbWrap'][f'public {name}()Ljava/lang/String;'] = (
            '    .locals 1\n    const-string v0, ""\n    return-object v0')
    # These bridges contain telemetry only. Native gameplay may call them after
    # startup, so disabling just their init call would leave null SDK clients.
    for name in ('FirebaseWrapper', 'AppsFlyerWrapper', 'SgIronSrcManager', 'sgTapjoyAd'):
        bridge = (original / PACKAGE / (name + '.smali')).read_text(encoding='utf-8')
        methods = re.findall(r'(?m)^\.method (public static [^\n]+)', bridge)
        changes[name] = {}
        for signature in methods:
            if ' native ' not in signature and signature.endswith(')V'):
                changes[name][signature] = '    .locals 0\n    return-void'
    # Later menu actions must not restart account, billing or support SDKs.
    for name in ('GooglePlayLapis', 'GoogleLogin', 'FbWrap', 'HelpshiftBridge'):
        bridge = (original / PACKAGE / (name + '.smali')).read_text(encoding='utf-8')
        for signature in re.findall(r'(?m)^\.method (public [^\n]+)', bridge):
            if ' native ' in signature or '<init>' in signature:
                continue
            if signature.endswith(')V'):
                changes.setdefault(name, {})[signature] = '    .locals 0\n    return-void'
            elif signature.endswith(')Z'):
                changes.setdefault(name, {})[signature] = '    .locals 1\n    const/4 v0, 0x0\n    return v0'
            elif signature.endswith(')Ljava/lang/String;'):
                changes.setdefault(name, {})[signature] = '    .locals 1\n    const-string v0, ""\n    return-object v0'
            elif name == 'FbWrap' and signature.endswith(')Ljava/util/ArrayList;'):
                changes[name][signature] = '''    .locals 1
    new-instance v0, Ljava/util/ArrayList;
    invoke-direct {v0}, Ljava/util/ArrayList;-><init>()V
    return-object v0'''
    changes['sgInputManager'] = {
        'public startInputManager()V': '    .locals 0\n    return-void',
        'public stopInputManager()V': '    .locals 0\n    return-void',
    }
    changes['h'] = {'protected initializePlatform()V': '    .locals 0\n    return-void'}
    for name, methods in {
        'PlayGamesLogin': ('getUserId',),
        'GoogleLogin': ('getToken', 'getRefreshToken', 'getUserID', 'getServiceAvailabilityStatusMessage'),
    }.items():
        for method in methods:
            changes[name][f'public static {method}()Ljava/lang/String;'] = (
                '    .locals 1\n    const-string v0, ""\n    return-object v0')
    for name, methods in changes.items():
        text = (original / PACKAGE / (name + '.smali')).read_text(encoding='utf-8')
        for signature, body in methods.items():
            text = replace_method(text, signature, body)
        write_changed(destination / PACKAGE / (name + '.smali'), text)
    # Keep the game's activity lifecycle, rendering and native calls intact.
    text = (original / PACKAGE / 'Lapis.smali').read_text(encoding='utf-8')
    activity_start = re.search(r'(?ms)^\.method protected onCreate\(Landroid/os/Bundle;\)V\n.*?^\.end method', text)
    if activity_start is None:
        raise ValueError('Original activity startup method is missing.')
    startup = activity_start.group()
    startup, asset_calls = re.subn(r'(?m)^(    \.locals \d+\n)',
        r'\1\n    invoke-static {p0}, Lcom/exvius/local/LocalGameBridge;->installAssets(Landroid/content/Context;)V\n',
        startup, count=1)
    if asset_calls != 1:
        raise ValueError('Original activity register declaration is missing.')
    for target in ('AppsFlyerWrapper;->init(', 'Lapis;->initializeBacktrace(',
                   'HelpshiftBridge;->install(', 'FirebaseWrapper;->init('):
        pattern = r'(?m)^    invoke-static [^\n]*' + re.escape(target) + r'[^\n]*$'
        startup, count = re.subn(pattern, '    nop', startup)
        if count != 1:
            raise ValueError(f'Expected one startup call: {target}; found {count}')
    text = text[:activity_start.start()] + startup + text[activity_start.end():]
    # Every caller, including native logging and later activity events, must
    # remain local instead of lazily restarting the crash reporting SDK.
    for signature in ('private static initializeBacktrace(Z)V',
                      'public static sendBacktrace(Ljava/lang/Exception;)V',
                      'public static sendBacktrace(Ljava/lang/String;)V',
                      'public static logBacktrace(Ljava/lang/String;)V',
                      'public static addBacktraceBreadcrumb(Ljava/lang/String;Ljava/util/Map;)V'):
        text = replace_method(text, signature, '    .locals 0\n    return-void')
    text = replace_method(text, 'private updateNetworkState()V', '''    .locals 1
    invoke-static {}, Lcom/exvius/local/LocalGameBridge;->localDataState()I
    move-result v0
    sput v0, Lcom/square_enix/android_googleplay/FFBEWW/Lapis;->networkState:I
    return-void''')
    text = replace_method(text, 'public static getNetworkState()I', '''    .locals 1
    invoke-static {}, Lcom/exvius/local/LocalGameBridge;->localDataState()I
    move-result v0
    return v0''')
    text = replace_method(text, 'private isConnectAvailable(Landroid/net/NetworkInfo;)Z', '''    .locals 1
    invoke-static {}, Lcom/exvius/local/LocalGameBridge;->localDataState()I
    move-result v0
    return v0''')
    text = replace_method(text, 'protected onNewIntent(Landroid/content/Intent;)V', '''    .locals 0
    invoke-super {p0, p1}, Lorg/cocos2dx/lib/Cocos2dxActivity;->onNewIntent(Landroid/content/Intent;)V
    return-void''')
    write_changed(destination / PACKAGE / 'Lapis.smali', text)

    # The older store controller has its own billing initialization, separate
    # from Play Games and the newer platform wrappers.
    source = original / 'com/soomla/store/StoreController.smali'
    body = source.read_text(encoding='utf-8')
    body = replace_method(body, 'public initialize(Landroid/app/Activity;Landroid/os/Handler;)V',
                          '''    .locals 0
    sput-object p1, Lcom/soomla/store/StoreController;->mActivity:Landroid/app/Activity;
    sput-object p2, Lcom/soomla/store/StoreController;->mHandler:Landroid/os/Handler;
    return-void''')
    body = replace_method(body, 'private startBillingService()Z',
                          '    .locals 1\n    const/4 v0, 0x0\n    return v0')
    for signature in ('private stopBillingService()V', 'public static notifyConsumePurchase(Ljava/lang/String;)V'):
        body = replace_method(body, signature, '    .locals 0\n    return-void')
    body = replace_method(body, 'public _buyGoogleMarketItem(Ljava/lang/String;)V', '''    .locals 2
    const-string v0, ""
    const/4 v1, 0x0
    invoke-static {v0, v0, v1}, Lcom/square_enix/android_googleplay/FFBEWW/LapisJNI;->purchaseStateChangedCallback(Ljava/lang/String;Ljava/lang/String;Z)V
    return-void''')
    for signature in ('public _syncItemPrices([Ljava/lang/String;)V', 'public _syncItemPricesAndPurchases()V'):
        body = replace_method(body, signature, '''    .locals 1
    const/4 v0, 0x0
    invoke-static {v0}, Lcom/square_enix/android_googleplay/FFBEWW/LapisJNI;->onSyncPricesFinished(I)V
    invoke-static {}, Lcom/square_enix/android_googleplay/FFBEWW/LapisJNI;->resetGooglePurchaseFlags()V
    return-void''')
    write_changed(destination / 'com/soomla/store/StoreController.smali', body)

    # Modify the real transport callers in both original DEX source trees.
    # These keep their existing file completion, parsing and UI callbacks.
    original_third = original.parent / 'smali_classes3'
    third = client / 'smali_classes3'
    if not third.exists():
        shutil.copytree(original_third, third)

    # Cocos also ships an Apache asynchronous downloader. It bypasses URL's
    # openConnection, so retain its queue/native callbacks and replace its I/O.
    source = original_third / 'org/cocos2dx/lib/Cocos2dxDownloader.smali'
    body = source.read_text(encoding='utf-8')
    body, count = re.subn(
        r'    new-instance v0, Le/f/a/a/a;\n.*?    iput-object v0, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader;->_httpClient:Le/f/a/a/a;',
        '    nop', body, flags=re.S)
    if count != 1:
        raise ValueError('Expected one original asynchronous HTTP client constructor.')
    body = replace_method(body, 'public static createDownloader(IILjava/lang/String;I)Lorg/cocos2dx/lib/Cocos2dxDownloader;', '''    .locals 1
    new-instance v0, Lorg/cocos2dx/lib/Cocos2dxDownloader;
    invoke-direct {v0}, Lorg/cocos2dx/lib/Cocos2dxDownloader;-><init>()V
    iput p0, v0, Lorg/cocos2dx/lib/Cocos2dxDownloader;->_id:I
    iput-object p2, v0, Lorg/cocos2dx/lib/Cocos2dxDownloader;->_tempFileNameSufix:Ljava/lang/String;
    iput p3, v0, Lorg/cocos2dx/lib/Cocos2dxDownloader;->_countOfMaxProcessingTasks:I
    return-object v0''')
    write_changed(third / source.relative_to(original_third), body)
    source = original_third / 'org/cocos2dx/lib/Cocos2dxDownloader$3.smali'
    body = replace_method(source.read_text(encoding='utf-8'), 'public run()V', '''    .locals 5
    new-instance v0, Lorg/cocos2dx/lib/DownloadTask;
    invoke-direct {v0}, Lorg/cocos2dx/lib/DownloadTask;-><init>()V
    iget-object v1, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$3;->val$downloader:Lorg/cocos2dx/lib/Cocos2dxDownloader;
    invoke-static {v1}, Lorg/cocos2dx/lib/Cocos2dxDownloader;->access$400(Lorg/cocos2dx/lib/Cocos2dxDownloader;)Ljava/util/HashMap;
    move-result-object v2
    iget v3, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$3;->val$id:I
    invoke-static {v3}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;
    move-result-object v4
    invoke-virtual {v2, v4, v0}, Ljava/util/HashMap;->put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;
    iget-object v2, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$3;->val$url:Ljava/lang/String;
    iget-object v4, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$3;->val$path:Ljava/lang/String;
    invoke-static {v1, v3, v2, v4}, Lcom/exvius/local/LocalCocosTasks;->load(Ljava/lang/Object;ILjava/lang/String;Ljava/lang/String;)V
    return-void''')
    write_changed(third / source.relative_to(original_third), body)
    source = original_third / 'org/cocos2dx/lib/Cocos2dxVideoView.smali'
    body, count = re.subn(
        r'invoke-virtual \{([^}]+)\}, Landroid/media/MediaPlayer;->setDataSource\(Landroid/content/Context;Landroid/net/Uri;\)V',
        r'invoke-static {\1}, Lcom/exvius/local/LocalGameBridge;->setLocalMediaSource(Landroid/media/MediaPlayer;Landroid/content/Context;Landroid/net/Uri;)V',
        source.read_text(encoding='utf-8'))
    if count != 1:
        raise ValueError('Expected one original URI video loader.')
    # Keep the existing Android movie player's centered aspect-fit path enabled.
    size_pattern = r'(?ms)^\.method public fixSize\(IIII\)V\n(.*?)^\.end method'
    match = re.search(size_pattern, body)
    if not match:
        raise ValueError('Original Android movie sizing method is missing.')
    sizing = match.group(1)
    sizing, count = re.subn(
        r'    iget-boolean v2, p0, Lorg/cocos2dx/lib/Cocos2dxVideoView;->mKeepRatio:Z',
        '    const/4 v2, 0x1\n    iput-boolean v2, p0, Lorg/cocos2dx/lib/Cocos2dxVideoView;->mKeepRatio:Z', sizing)
    if count != 1:
        raise ValueError('Expected one Android movie aspect-ratio branch.')
    sizing = sizing.replace('if-ge v2, v3, :cond_2', 'if-gt v2, v3, :cond_2')
    body = body[:match.start(1)] + sizing + body[match.end(1):]
    write_changed(third / source.relative_to(original_third), body)
    source = original_third / 'org/cocos2dx/lib/Cocos2dxDownloader$4.smali'
    body = replace_method(source.read_text(encoding='utf-8'), 'public run()V', '''    .locals 1
    iget-object v0, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$4;->val$downloader:Lorg/cocos2dx/lib/Cocos2dxDownloader;
    invoke-static {v0}, Lcom/exvius/local/LocalCocosTasks;->cancel(Ljava/lang/Object;)V
    return-void''')
    write_changed(third / source.relative_to(original_third), body)
    targets = [(original / PACKAGE / 'FileDownloader.smali', destination / PACKAGE / 'FileDownloader.smali'),
               (original / PACKAGE / 'FbWrap$d.smali', destination / PACKAGE / 'FbWrap$d.smali'),
               (original_third / 'org/cocos2dx/lib/Cocos2dxHttpURLConnection.smali',
                third / 'org/cocos2dx/lib/Cocos2dxHttpURLConnection.smali')]
    for source, target in targets:
        body = source.read_text(encoding='utf-8')
        body, count = re.subn(
            r'invoke-virtual \{([^}]+)\}, Ljava/net/URL;->openConnection\(\)Ljava/net/URLConnection;',
            r'invoke-static {\1}, Lcom/exvius/local/LocalGameBridge;->openConnection(Ljava/net/URL;)Ljava/net/HttpURLConnection;', body)
        body, streams = re.subn(
            r'invoke-virtual \{([^}]+)\}, Ljava/net/URL;->openStream\(\)Ljava/io/InputStream;',
            r'invoke-static {\1}, Lcom/exvius/local/LocalGameBridge;->openStream(Ljava/net/URL;)Ljava/io/InputStream;', body)
        if count + streams != 1:
            raise ValueError('Expected one original transport call in ' + source.name)
        if source.name == 'FileDownloader.smali':
            body = body.replace('const-string v0, "Downloading: "', 'const-string v0, "Loading: "')
            body = body.replace('const-string p1, "Downloading: "', 'const-string p1, "Loading: "')
            body = body.replace('const-string p1, "File downloaded"', 'const-string p1, "Local file loaded"')
            body = body.replace('const-string v5, "Error downloading file "', 'const-string v5, "Unable to load local file "')
            marker = '.method protected varargs doInBackground([Ljava/lang/Void;)Ljava/lang/Integer;\n    .locals 11\n'
            if body.count(marker) != 1:
                raise ValueError('Original local file loader register layout changed.')
            body = body.replace(marker, marker + '''
    iget-object v0, p0, Lcom/square_enix/android_googleplay/FFBEWW/FileDownloader;->fileURL:Ljava/lang/String;
    iget-object v1, p0, Lcom/square_enix/android_googleplay/FFBEWW/FileDownloader;->saveFilePath:Ljava/lang/String;
    invoke-static {v0, v1}, Lcom/exvius/local/LocalGameBridge;->existingFile(Ljava/lang/String;Ljava/lang/String;)Z
    move-result v0
    if-eqz v0, :exvius_load_local_file
    iget-wide v0, p0, Lcom/square_enix/android_googleplay/FFBEWW/FileDownloader;->handler:J
    invoke-static {v0, v1}, Lcom/square_enix/android_googleplay/FFBEWW/FileDownloader;->onDownloadComplete(J)V
    const/4 v0, 0x1
    invoke-static {v0}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;
    move-result-object v0
    return-object v0
    :exvius_load_local_file
''')
        write_changed(target, body)

    source = original / PACKAGE / 'webview/LapisWebView$b.smali'
    body = source.read_text(encoding='utf-8')
    body, count = re.subn(
        r'invoke-virtual \{([^}]+)\}, Landroid/webkit/WebView;->postUrl\(Ljava/lang/String;\[B\)V',
        r'invoke-static {\1}, Lcom/exvius/local/LocalGameBridge;->postLocalPage(Landroid/webkit/WebView;Ljava/lang/String;[B)V', body)
    if count != 1:
        raise ValueError('Expected one original game web page submission.')
    write_changed(destination / PACKAGE / 'webview/LapisWebView$b.smali', body)

    for source, target in [
        (original / PACKAGE / 'webview/LapisWebView$a.smali', destination / PACKAGE / 'webview/LapisWebView$a.smali'),
        (original_third / 'org/cocos2dx/lib/Cocos2dxWebView.smali',
         third / 'org/cocos2dx/lib/Cocos2dxWebView.smali')]:
        body = source.read_text(encoding='utf-8')
        pattern = r'(?m)^(    invoke-virtual \{([^,]+), [^}]+\}, Landroid/webkit/WebView;->setWebViewClient\(Landroid/webkit/WebViewClient;\)V)$'
        body, count = re.subn(pattern,
            r'    invoke-static {\2}, Lcom/exvius/local/LocalGameBridge;->configureWebView(Landroid/webkit/WebView;)V\n\1', body)
        if count != 1:
            raise ValueError('Expected one original web view setup in ' + source.name)
        write_changed(target, body)

    for source, target, methods in [
        (original / PACKAGE / 'LapisJNI.smali', destination / PACKAGE / 'LapisJNI.smali', {
            'public static decodeFileForBase64WithNewCrypto(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;':
                '    .locals 1\n    invoke-static {p0, p1, p2}, Lcom/exvius/local/LocalGameBridge;->decodeGameTable(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;\n    move-result-object v0\n    return-object v0',
            'public static SendInvite(Ljava/lang/String;)Z': '    .locals 1\n    const/4 v0, 0x0\n    return v0',
            'public static shareUrl(Ljava/lang/String;Ljava/lang/String;)V': '    .locals 0\n    return-void',
            'public static oneStoreIapRequest(Ljava/lang/String;)V': '    .locals 0\n    return-void',
            'public static oneStoreIapSyncAllPrice()V': '    .locals 0\n    return-void',
        }),
        (original / PACKAGE / 'webview/LapisWebView.smali', destination / PACKAGE / 'webview/LapisWebView.smali', {
            'public static launchNewApplication(Ljava/lang/String;)Z': '    .locals 1\n    const/4 v0, 0x0\n    return v0',
            'public static launchNewBrowser(Ljava/lang/String;Ljava/lang/String;)V': '    .locals 0\n    return-void',
        }),
        (original_third / 'org/cocos2dx/lib/Cocos2dxHelper.smali', third / 'org/cocos2dx/lib/Cocos2dxHelper.smali', {
            'public static openURL(Ljava/lang/String;)Z': '    .locals 1\n    const/4 v0, 0x0\n    return v0',
            'public static getAssetsPath()Ljava/lang/String;':
                '    .locals 1\n    invoke-static {}, Lcom/exvius/local/LocalGameBridge;->gameAssetsPath()Ljava/lang/String;\n    move-result-object v0\n    return-object v0',
        }),
    ]:
        body = source.read_text(encoding='utf-8')
        for signature, replacement in methods.items():
            body = replace_method(body, signature, replacement)
        write_changed(target, body)

    # Retain the game's web view callbacks and custom game navigation. Supply
    # each HTTP resource from the same local resolver before Chromium can fetch.
    for source, target in [
        (original / PACKAGE / 'webview/LapisWebViewClient.smali', destination / PACKAGE / 'webview/LapisWebViewClient.smali'),
        (original_third / 'org/cocos2dx/lib/Cocos2dxWebView$Cocos2dxWebViewClient.smali',
         third / 'org/cocos2dx/lib/Cocos2dxWebView$Cocos2dxWebViewClient.smali')]:
        body = source.read_text(encoding='utf-8')
        if source.name == 'LapisWebViewClient.smali':
            body = replace_method(body,
                'public shouldOverrideUrlLoading(Landroid/webkit/WebView;Ljava/lang/String;)Z', '''    .locals 2
    const-string v0, "ffbecall://"
    invoke-virtual {p2, v0}, Ljava/lang/String;->startsWith(Ljava/lang/String;)Z
    move-result v0
    if-eqz v0, :exvius_local_web_page
    const/16 v0, 0xb
    invoke-virtual {p2, v0}, Ljava/lang/String;->substring(I)Ljava/lang/String;
    move-result-object v0
    invoke-static {v0}, Lcom/square_enix/android_googleplay/FFBEWW/LapisJNI;->webViewOnReceivedParam(Ljava/lang/String;)Z
    goto :exvius_web_handled
    :exvius_local_web_page
    invoke-static {p2}, Lcom/exvius/local/LocalGameBridge;->handles(Ljava/lang/String;)Z
    move-result v0
    if-nez v0, :exvius_open_local_page
    const-string v0, "file:"
    invoke-virtual {p2, v0}, Ljava/lang/String;->startsWith(Ljava/lang/String;)Z
    move-result v0
    if-eqz v0, :exvius_web_handled
    :exvius_open_local_page
    invoke-virtual {p1, p2}, Landroid/webkit/WebView;->loadUrl(Ljava/lang/String;)V
    :exvius_web_handled
    const/4 v0, 0x1
    return v0''')
        if 'shouldInterceptRequest(' in body:
            raise ValueError('Review the existing web resource interception before modifying it.')
        body += '''
.method public shouldInterceptRequest(Landroid/webkit/WebView;Ljava/lang/String;)Landroid/webkit/WebResourceResponse;
    .locals 1
    invoke-static {p2}, Lcom/exvius/local/LocalGameBridge;->webResource(Ljava/lang/String;)Landroid/webkit/WebResourceResponse;
    move-result-object v0
    return-object v0
.end method

.method public shouldInterceptRequest(Landroid/webkit/WebView;Landroid/webkit/WebResourceRequest;)Landroid/webkit/WebResourceResponse;
    .locals 1
    invoke-interface {p2}, Landroid/webkit/WebResourceRequest;->getUrl()Landroid/net/Uri;
    move-result-object v0
    invoke-virtual {v0}, Landroid/net/Uri;->toString()Ljava/lang/String;
    move-result-object v0
    invoke-static {v0}, Lcom/exvius/local/LocalGameBridge;->webResource(Ljava/lang/String;)Landroid/webkit/WebResourceResponse;
    move-result-object v0
    return-object v0
.end method
'''
        write_changed(target, body)
    # Early startup uses the APK's small plain text table before the main
    # encrypted text table is ready. Apply the same offline wording there.
    for path in (client / 'assets/localized_texts').glob('*/0ThfQQWd.csv'):
        lines = []
        for line in path.read_text(encoding='utf-8').splitlines(keepends=True):
            fields = line.rstrip('\r\n').split('^')
            if fields[0] in OFFLINE_TEXT:
                ending = line[len(line.rstrip('\r\n')):]
                line = '^'.join([fields[0]] + [OFFLINE_TEXT[fields[0]]] * (len(fields) - 1)) + ending
            lines.append(line)
        write_changed(path, ''.join(lines))
    # Platform and billing diagnostics can run before Cocos has an Activity.
    # Their native rlog bridge then aborts on a null Java object, notably on
    # the first launch from Android's package installer. Keep these messages
    # in Android's logger without depending on the game's native UI lifecycle.
    report_call = re.compile(
        r'(?m)^(\s*)invoke-static \{([^}]+)\}, '
        r'Lcom/square_enix/android_googleplay/FFBEWW/LapisJNI;->rlogs?'
        r'\(Ljava/lang/String;Ljava/lang/String;Z\)V$')
    for relative in (PACKAGE / 'PlatformUtils.smali', PACKAGE / 'PlatformUtilsGoogle.smali',
                     PACKAGE / 'webview/LapisWebView.smali',
                     Path('com/sg/gumi/GooglePlayBilling.smali'),
                     Path('com/soomla/billing/BillingServiceV3.smali')):
        target = destination / relative
        body = target.read_text(encoding='utf-8')
        def android_log(match):
            message, tag, _ = (part.strip() for part in match[2].split(','))
            return (match[1] + f'invoke-static {{{tag}, {message}}}, '
                    'Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I')
        write_changed(target, report_call.sub(android_log, body))
    # Apktool assembles this source tree instead of copying the original first DEX.
    (client / 'classes.dex').unlink(missing_ok=True)
    (client / 'classes3.dex').unlink(missing_ok=True)
    print('Offline Java: local requests, files, web resources and data-readiness checks; online SDK entry points disabled.')
