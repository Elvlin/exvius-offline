# FFBE Server Contract (v9.0.0)

What the *FINAL FANTASY BRAVE EXVIUS* Android client expects from a server, recovered from the
shipped build. The game reached end of service, so this is a reference for anyone who wants to run the
client against a server of their own.

## About this document

The client is a stock cocos2d-x app with one game host, a per-request obfuscated endpoint table, and
per-request AES keys compiled into the binary. Everything below was read out of `libgame.so` (the ARM64
game library) and the APK itself. Where a claim is an inference rather than something read from the
binary, it says so.

Two numbers frame the problem. There are **211 distinct `/actionSymbol/<token>.php` paths** in the
binary, and **222 request classes** resolve to them, so ten paths are shared by more than one class.
Every request class exposes three tiny accessors that name its request-ID token, its encode key and its
URL. Disassembling those three stubs recovers the whole endpoint table, which is in section 4.

The payload contract is only partly recovered. The JSON field names are themselves 8-character
obfuscated tokens, so a server can be routed to before it can be answered correctly. A handful of
payloads have since been mapped end to end, but that map is not published here; the method for
recovering the rest is in section 6. Section 3 lists what each area needs; section 5 lists what is
still open.

This has not stayed a reading exercise. The client has been run in an emulator against a local
server and driven well past static analysis: the boot chain completes, the opening mission plays, a
summon pulls and awards units, and the home screen's polls are answered. For the endpoints that path
actually touches, and what each reply has to satisfy, see `boot_to_home_endpoints.md` for the run
from launch to the home screen and `validated_endpoints.md` for the screens beyond it.

## 1. Transport and route

### 1.1 Where requests go

The client makes HTTPS requests to a single host under one base path.

| Part | Value |
|---|---|
| Host | `v900-lapis.gumi.sg` |
| Base path | `/lapisProd/app` |
| Path segment | `php/gme` |
| Endpoint | `/actionSymbol/<8-char token>.php` |
| Scheme | `https://` |

So a full request URL has the shape:

```
https://v900-lapis.gumi.sg/lapisProd/app/php/gme/actionSymbol/<token>.php
```

The host and base path are separate literals that the client joins at runtime, and the asset host is
configurable by the server (see 2.2 and 2.8). Older community notes for this game use a
version-specific host name such as `lapisv230.gumi.sg`; the *path* is stable across versions while the
host is not.

Bodies are JSON. The HTTP work is ordinary `HttpURLConnection` under cocos2d-x's network layer, not a
custom socket stack.

### 1.2 The request and response envelope

Both directions use the same scheme. The body is JSON, encrypted with AES-128-CBC, then base64 encoded.

| Item | Value |
|---|---|
| Cipher | AES-128-CBC |
| Base64 | outside the ciphertext |
| Padding | PKCS7, applied twice |
| Key | the request's 8-character encode key, UTF-8, zero-padded to 16 bytes |
| IV | the fixed 16-byte ASCII string `dZMjkk8gFDzKHlsx` |

Three details are easy to get wrong.

**The body is padded twice.** The client pads manually with PKCS7 to a 16-byte boundary and then lets
Java's `PKCS5Padding` pad again. The result carries 16 more bytes than a single-padded implementation
produces. A single-padded reply is rejected: the client's parse returns 0 and it shows a connection
error. If you are writing a server, double-pad.

**The key is per request, and the same key covers the reply.** The 8-character `EncodeKey` from the
endpoint table is the key material, zero-padded to 16 bytes. There is no separate reply key.

**The cipher lives in Java, not in the native library.** The native side calls into
`LapisJNI.encodeCStringForBase64WithNewCrypto` through JNI. The statically linked OpenSSL AES code in
`libgame.so` is not on this path at all, which is why searching the native library for the crypto
routine finds nothing useful.

### 1.3 TLS trust

The client does not pin certificates. It uses the platform default verifier, which means a CA in the
Android **system** trust store is accepted, and with a modern `targetSdkVersion` a CA in the *user*
store is not. No certificate has to be baked into the APK and no pin has to be defeated.

The socket is opened by Java's `HttpsURLConnection` (the cocos2d-x wrapper), not by native code.
Verification is on, at the platform default. Searches for the usual pinning markers come up empty:
no `SSL_CTX_set_cert_verify_callback` calls, no pinned certificate literals, and a network security
config that allows cleartext to `127.0.0.1` only. A copy of libcurl (7.52.1) is linked into the
library, but it is off the request path; its `SSL_CTX_set_verify` call site is unreachable from the
game's own network code.

For a local server this means the two standard steps: install your CA in the system store of a rooted
image, and redirect the game host to your machine.

## 2. What every request carries

Above any action-specific fields, `BaseRequest` attaches a common set of groups. A server that accepts
one request has to tolerate all of them: a login group or a guest checksum, a user-info tag, a
signal-key tag, an app-version tag, an MST-version tag and a resource-version tag. The user-info group
is the one most other replies reuse, so after the first login the client generally echoes back the
record the server issued.

Two tokens are server-owned. The user id inside the user-info group is issued by the server and is not
present in any shipped file. The signal key is also server-issued; what the client does with it beyond
storing it is not established (section 5).

## 3. Areas

The client's server-facing behaviour groups into eleven areas. For each one: what the client does, and
what a server has to supply. A subset of these has been driven against a live client and is walked
request by request in `validated_endpoints.md`.

### 3.1 Auth, login and session

The client presents a login service (guest, Google Play Games, Facebook, Apple or Google), obtains or
refreshes a token, connects, then fetches an existing account or creates one. Account transfer by code
is also handled here, and a feature-switch request runs at login.

A server needs a connect endpoint set that accepts the login group or guest checksum, returns a user
record and a signal key, and answers the account calls (`CreateUserRequest`, `GetUserInfoRequest` and
its second and third variants, `UpdateSwitchInfoRequest`, `UpdateDeviceIdRequest`,
`InitializeRequest`). The user record's fields include the account and user ids, handle name, friend
id, the account type, action and other point balances, gil, experience, level, gift id, the various
capacity adders, and the purchase fields. The wire encoding of those fields is not recovered here.

Notable classes: `LoginService`, `LoginServiceManager`, `LoginScene`, `ConnectScene`,
`ConnectRequestList`, `UserInfo`, `ModelChangeUserInfo`, `SignalKeyResponse`.

### 3.2 Resource delivery (CDN)

The client downloads master-data tables (called MST), resource CPK packs and localized-text tables,
then keeps them on disk. It decides what to fetch by comparing the versions it holds against version
tables the server supplies.

The on-disk naming convention is `Ver<N>_<token>.dat`, where `<N>` is a per-table data version and
`<token>` is the table's compiled-in identifier. A complete shipped install holds 219 MST `.dat` files
plus 47 index files, and 145 localized-text tables for one language.

A server needs to supply the version tables, a CDN base URL, and the `.dat` payloads. The CDN host is
pushed at runtime, not hard-coded, so a reconstruction can point the client at any host it likes.

The table format is base64 over AES-128, with the key being the table's 8-character constant
zero-padded to 16 bytes. The client tries CBC first (using the same fixed IV as the network envelope)
and falls back to ECB if that fails, silently. Both encodings occur in the shipped data.

One observed detail: the shipped client's own asset cache records remote banner files as
`id,version,url,localpath`, and the URLs point at a CloudFront distribution
(`d3syu63yncawjw.cloudfront.net`) with the path prefix `lapis-static-prod/dlc_assets_prod/`. That is
the shape a server-listed asset follows when the client caches it.

Notable classes: `DownloadSequencePopup`, `InitialDownloadScene`, `AllResourceVersionMstResponse`,
`ResourceVersionMstLocalize*`, `sgSplitLocalizedTextMstList`, `EnvUrlMst`.

### 3.3 Player save and instance state

The client keeps the player's authoritative state in memory and fills it from server responses. The
model is the `User*Info` family: units, parties, inventory, equipment, materia, vision cards, items,
gifts and account. There is no local serialization of that roster. Some *in-progress* state is kept
locally (battle save slots, tutorial progress, suspended missions, saved fixed-party decks), but the
roster itself is server data.

A server has to send the whole state on connect and then a delta after every mutating action. Two
response parsers carry most of the per-account fields (team info, diamond balance); the individual
8-character wire keys are not published here.

Notable classes: `UserInfo`, `UserTeamInfo`, `UserDiamondInfo`, `UserUnitInfo`, `UserParty`,
`UserPartyDeckList`, and the matching `*Response` classes. There are 496 `readParam` symbols in total,
one per response parser.

### 3.4 Party, roster and unit management

The client edits party decks, equips items, materia and vision cards, fuses, awakens and mixes units,
marks favourites, and registers party slots that friends can borrow.

A server needs to accept those actions and return the updated unit and party records. Party ordering
is server-side: the client renders the order it is given rather than computing one.

Notable classes: `PartyDeckEditRequest`, `UnitEquipRequest`, `UnitMixRequest`, `UnitClassUpRequest`,
`VisionCardMixRequest`, `ReinforcementSettingRequest`.

### 3.5 Battle

The client requests mission admission, submits a turn and result payload at mission end (including a
per-unit stat, equipment and resistance history and the continue count), and can resume, retire or
restart. During a battle it fires separate requests for continues, boss-death, the Libra scan, party
changes and a forced terminate.

A server needs to admit missions, accept the end payload and return rewards and drops, provide resume
info, and answer the continue, retire and restart calls. Whether the server validates or recomputes
the uploaded stats, or just accepts them, is not established.

Two competitive families hang off the same machinery. The arena (`Rb*`) has its own entry, matching,
start, end, restart, ranking and trade-board requests; the Colosseum (`Clsm*`) has entry, start, end and
lottery. Both are reached by a door request answered with an acknowledgement and then build their
screens from state delivered earlier. Their orbs — four point/maximum/countdown triples, one per mode —
ride the team-info reply, and the arena's ranking screen builds one orb button per orb up to the cap it
is served, so a cap larger than the ten the client's layout ships faults the scene. The Colosseum's
entry is an acknowledgement, but the screen it hands off to reads a battle-info class that has to ride
the same reply. `arena_and_colosseum_endpoints.md` has both failure modes.

Notable classes: `MissionStartRequest`, `MissionEndRequest`, `MissionResultResponse`,
`MissionResumeInfoResponse`, `BattleScene`, `BattleManager`, plus the survival, colosseum and
TFA mission variants.

### 3.6 Gacha

The client reads banner and cost master data, requests a pull or an entry, and receives the results
from the server. The client never rolls. Boxes, panels, select tickets, rerolls, prism exchange and
ad-gacha milestones all follow the same pattern.

The pool and the rates were both server-side. The client's banner table has no rate or weight member,
and neither table shipped in the APK, so the rates shown in game were rendering server data. A server
is therefore the RNG of record for this area.

A server needs to supply banner, step and box state, and for each pull the drawn unit ids plus the
resulting unit records. The banner layer reaches the client in reply bodies rather than as a downloaded
table, and most of its content has to be authored; `gacha_endpoints.md` covers that channel and the
object graph the client expects.

### 3.7 Shop, IAP and premium currency

The client runs a purchase state machine over Google Play or MyCard, keeps a local purchase list, then
reports purchase start, settlement, hold, failure, give-up and cancel to the game server. Premium
currency is spent in shops, bundles and exchanges.

A server needs receipt settlement, a currency ledger, shop stock and exchange answers, bundle state,
and the MyCard path for the region that uses it. Server-side receipt verification is implied by the
purchase flags but not proven.

Notable classes: `PurchaseStartRequest`, `PurchaseSettlementRequest`, `ShopUseRequest`,
`ShopExchangeItem*`, `BundlePurchaseRequest`, `MyCardInitializeRequest`, `UserDiamondInfoResponse`.

### 3.8 Friends, missions, events and news

The client lists, searches, agrees, refuses, deletes and favourites friends, fetches a friend's leader
unit and vision card as a borrowable helper, sets its own reinforcement, and polls routine updates
for the home, event, world and raid menus, plus notices and the home marquee.

A server needs friend lists and leader snapshots, reinforcement responses, the routine deltas, notice
lists and read state, and home-marquee banner URLs. It also needs to answer the URL dictionary
(`F_URL_MST` / `EnvUrlMst`): the server pushes `P_GS_*` overrides that steer the CDN, notice and banner
hosts. This is the intended hook for repointing a reconstruction at your own infrastructure.

The reinforcement list is the battle-helper list. Its rows ride `ReinforcementResponse`, which binds a
carrying tag and a clearing tag, and an empty list is accepted; a populated row has to be built from
that class's own field names, or the support-select layout faults on the fields it never received. The
friends list (`FriendUnitInfoResponse`) is optional display data whose populated shape is unverified —
an empty list renders. `support_and_friends_endpoints.md` covers both, the vision-card class the support
row resolves through, and the espers that ride any player-state reply.

Events are opened through a gate list delivered in reply bodies (`SpDungeonCondMstResponse`, tag
`0xkoNP8U`), which is replace-on-read: the area, its dungeon and its first mission can be derived from
the shipped mission tables, while the window, the tab and the art are authored. A tile's art and an
event's maps arrive as per-location packs, not in replies, fetched by name from the client's own
resource tables. Of the 913 event areas with at least three missions, 707 have fully battle-derivable
content from the client-side JP corpus. The crest screens, the emblem campaign and the story switches
that open feature tiles are the rest of this area; `events_and_unlocks_endpoints.md` has all three.

Notable classes: `FriendListRequest`, `FriendDetailRequest`, `GetReinforcementInfoRequest`,
`RoutineHomeUpdateRequest`, `RoutineEventUpdateRequest`, `NoticeUpdateRequest`, `NoticeMstResponse`,
`sgHomeMarqueeInfoRequest`.

### 3.9 Localized text and MST updates

Localized text is downloaded as a separate MST set per language, using the same `Ver<N>_<token>.dat`
envelope as the main tables. A server needs to supply current versions and the payloads for the
client's language.

Notable classes: `sgSplitLocalizedTextMstList`, `sgSplitLocalizedTextMstResponse`,
`DownloadSequencePopup::requestLocalizedTextMstDownload`.

### 3.10 Telemetry and third-party SDKs

The client spools an encrypted report stream and uploads it to `/actionSymbol/RntCZywQ.php`, so client
reports do traverse the game server rather than only third parties. It also fires analytics and ad
events to a set of SDKs, each on its own host. A server has to answer the report endpoint (accepting
and ignoring is probably enough, though this is not verified) and can ignore the SDK backends, since
they are distinct hosts.

### 3.11 Towns, maps and exploration

The client enters a town, moves through it and leaves it with three small requests — `TownInRequest`,
`TownOutRequest` and `TownUpdateRequest` — plus a map-side update, `MissionUpdateRequest`, fired by the
map scripts. None of them is answered with content: there is no town-state response class, so the reply
only has to be a valid one. The scene's connect check consumes it, and without any reply the client
shows its generic connection error. The ordinary account record satisfies all four.

What fills a map or a town is downloaded, not served in a reply. The client fetches a CPK pack per
location on demand from the CDN host the boot reply configures, by a name it builds from its own
resource tables; the pack carries the map's script and dialogue. A requested pack that is missing is
fatal to the location — the client raises the same generic connection error and the scene does not load
— so a server has to return valid bytes for every path the client asks for, or hold the story switches
that make the request. The packs did not ship with the APK, and the live-service families are absent
from the offline builds we can compare against: `missing_cdn_packs.md` lists them.

`towns_and_maps_endpoints.md` has the request table, the reply requirements, the URL shape, the
download/ignore gate and the pack contents. Event areas are delivered the same way; the gate list they
appear in is covered in `events_and_unlocks_endpoints.md`.

Notable classes: `TownInRequest`, `TownOutRequest`, `TownUpdateRequest`, `MissionUpdateRequest`,
`EnterTownScene`, `ExitTownScene`, `TownSystemScene`, `MapScene`, `MapDrawManager`,
`DownloadSequencePopup`, `ResourceVersionMstResponse`, `MapResourceVersionResponse`.

## 4. Endpoint appendix

Every request class in the shipped binary, with the request-ID token, the encode key and the URL it
resolves to. The three values are the return values of each class's `getRequestID()`,
`getEncodeKey()` and `getUrl()` accessors, each a three-instruction stub whose string target was read
directly.

Coverage: 222 request classes, 211 distinct URLs. Ten URLs are shared by more than one class, and one
URL is the literal `/actionSymbol/action.php`.

| Request class | request-ID key | encode key | URL path |
|---|---|---|---|
| `AllianceDeckEditRequest` | `P76LYXow` | `2E3UinsJ` | `/actionSymbol/7gAGFC4I.php` |
| `AllianceEntryRequest` | `HtR8XF4e` | `zS4tPgi7` | `/actionSymbol/EzfT0wX6.php` |
| `AllianceUndercoverStrengthenRequest` | `qj63QmHE` | `75pZA8tv` | `/actionSymbol/UR1OtKJS.php` |
| `ArchiveUpdateRequest` | `cVTxW0K3` | `IFLW9H4M` | `/actionSymbol/2bCcKx0D.php` |
| `BeastBoardPieceOpenRequest` | `0gk3Tfbz` | `7uxYTm3k` | `/actionSymbol/Y2Zvnad9.php` |
| `BeastMixRequest` | `C8X1KUpV` | `WfNSmy98` | `/actionSymbol/7vHqNPF0.php` |
| `BundlePurchaseRequest` | `w6Z9a6tD` | `NE3Pp4K8` | `/actionSymbol/tPc64qmn.php` |
| `BundleStatusRequest` | `uLXAMvCT` | `PrSPuc8c` | `/actionSymbol/tPc64qmn.php` |
| `CampaignTieupRequest` | `mI0Q2YhW` | `72d5UTNC` | `/actionSymbol/2u30vqfY.php` |
| `ChallengeClearRequest` | `D9xphQ8X` | `UD5QCa2s` | `/actionSymbol/dEvLKchl.php` |
| `ClientReportRequest` | `Uq4gcH1s` | `jw84xYPr` | `/actionSymbol/RntCZywQ.php` |
| `ClsmEndRequest` | `3zgbapQ7` | `6aBHXGv4` | `/actionSymbol/7vHqNPF0.php` |
| `ClsmEntryRequest` | `5g0vWZFq` | `8bmHF3Cz` | `/actionSymbol/UmLwv56W.php` |
| `ClsmLotteryRequest` | `Un16HuNI` | `pU62SkhJ` | `/actionSymbol/4uj3NhUQ.php` |
| `ClsmStartRequest` | `4uCSA3ko` | `wdSs23yW` | `/actionSymbol/rncR9js8.php` |
| `CraftAddRequest` | `QkN1Sp64` | `qz0SG1Ay` | `/actionSymbol/iQ7R4CFB.php` |
| `CraftCancelRequest` | `79xDN1Mw` | `68zcUF3E` | `/actionSymbol/7WdDLIE4.php` |
| `CraftEndRequest` | `WIuvh09n` | `yD97t8kB` | `/actionSymbol/9G7Vc8Ny.php` |
| `CraftExeRequest` | `PKDhIN34` | `ZbHEB15J` | `/actionSymbol/UyHLjV60.php` |
| `CraftStartRequest` | `Gr9zxXk5` | `K92H8wkY` | `/actionSymbol/w71MZ0Gg.php` |
| `CreateUserRequest` | `P6pTz4WA` | `73BUnZEr` | `/actionSymbol/0FK8NJRX.php` |
| `DailyDungeonSelectRequest` | `JyfxY2e0` | `ioC6zqG1` | `/actionSymbol/9LgmdR0v.php` |
| `DailyQuestClaimAllRewardRequest` | `DCmya9WD` | `KHx6JdrT` | `/actionSymbol/Br9PwJ6A.php` |
| `DailyQuestClaimRewardRequest` | `Zy8fYJ5e` | `jwYGF3sY` | `/actionSymbol/Br9PwJ6A.php` |
| `DailyQuestShareRequest` | `3sTwRcpq` | `PMyGMdUa` | `/actionSymbol/3sTwRcpq.php` |
| `DailyQuestUpdateRequest` | `6QYd5Hym` | `9QtGVCWg` | `/actionSymbol/QWDn5epF.php` |
| `DmgRankEndRequest` | `s98cw1WA` | `7pGj8hSW` | `/actionSymbol/zd5KJ3jn.php` |
| `DmgRankRetireRequest` | `W3Z4VF1X` | `5fkWyeE6` | `/actionSymbol/8wdmR9yG.php` |
| `DmgRankStartRequest` | `5P6ULvjg` | `1d5AP9p6` | `/actionSymbol/j37Vk5xe.php` |
| `DungeonLiberationRequest` | `nQMb2L4h` | `0xDA4Cr9` | `/actionSymbol/0vc6irBY.php` |
| `DungeonResourceLoadMstListRequest` | `jnw49dUq` | `3PVu6ReZ` | `/actionSymbol/Sl8UgmP4.php` |
| `EquipGrowAbilityFixRequest` | `k8ew94DN` | `58dS0DZN` | `/actionSymbol/CnPyXkUV.php` |
| `EquipGrowAbilitySelectResumeRequest` | `80R6BXUw` | `7YxgkK1V` | `/actionSymbol/Ke7YG3xW.php` |
| `EquipGrowEntryRequest` | `U8F0Q25i` | `6fTy3HRM` | `/actionSymbol/UiSOVXT2.php` |
| `EquipItemFavoriteRequest` | `cVRHU84e` | `dRBYF8Q0` | `/actionSymbol/fZ4jONfh.php` |
| `ExbonusExeRequest` | `68RQ9GwN` | `FvL0AP1U` | `/actionSymbol/u843ypX2.php` |
| `ExbonusUpdateRequest` | `HaJp14F6` | `a3BP2MRo` | `/actionSymbol/lNJqXG3D.php` |
| `ExchangeShopRequest` | `I7fmVX3R` | `qoRP87Fw` | `/actionSymbol/1bf0HF4w.php` |
| `FacebookAddFriendRequest` | `NAW9vJnm` | `532vAYUy` | `/actionSymbol/NAW9vJnm.php` |
| `FacebookLogoutRequest` | `xHTo4BZp` | `wwHxtAy6` | `/actionSymbol/xHTo4BZp.php` |
| `FacebookRewardClaimRequest` | `47R9pLGq` | `Rja82ZUK` | `/actionSymbol/47R9pLGq.php` |
| `FacebookRewardListRequest` | `8YZsGLED` | `85YBRzZg` | `/actionSymbol/8YZsGLED.php` |
| `FriendAgreeRequest` | `kx13SLUY` | `9FjK0zM3` | `/actionSymbol/1DYp5Nqm.php` |
| `FriendDeleteRequest` | `a2d6omAy` | `d0VP5ia6` | `/actionSymbol/8R4fQbYh.php` |
| `FriendDetailRequest` | `7kG0JAvE` | `aKvkU6Y4` | `/actionSymbol/QBiJEyUt.php` |
| `FriendFavoriteRequest` | `1oE3Fwn4` | `3EBXbj1d` | `/actionSymbol/8IYSJ5H1.php` |
| `FriendListRequest` | `u7Id4bMg` | `1iV2oN9r` | `/actionSymbol/p3hwqW5U.php` |
| `FriendRefuseRequest` | `1nbWRV9w` | `RYdX9h2A` | `/actionSymbol/Vw0a4I3i.php` |
| `FriendRequest` | `j0A5vQd8` | `6WAkj0IH` | `/actionSymbol/8drhF2mG.php` |
| `FriendSearchRequest` | `3siZRSU4` | `VCL5oj6u` | `/actionSymbol/6Y1jM3Wp.php` |
| `FriendSuggestRequest` | `iAs67PhJ` | `j2P3uqRC` | `/actionSymbol/6TCn0BFh.php` |
| `GachaBoxNextRequest` | `xa9uR3pI` | `U2Lm8vcS` | `/actionSymbol/tULiKh5j.php` |
| `GachaEntryRequest` | `rj6dxU9w` | `39cFjtId` | `/actionSymbol/tUJxSQz7.php` |
| `GachaExeRequest` | `9fVIioy1` | `oaEJ9y1Z` | `/actionSymbol/oC30VTFp.php` |
| `GachaInfoRequest` | `UNP1GR5n` | `VA8QR57X` | `/actionSymbol/3nhWq25K.php` |
| `GachaPanelNextRequest` | `32YLaEmn` | `qbHn0E2L` | `/actionSymbol/7WGJtJwo.php` |
| `GachaSelectEntryRequest` | `6nTcSp4R` | `uG1jRky6` | `/actionSymbol/6RI813OP.php` |
| `GachaSelectExchangeExeRequest` | `W58vo4Hp` | `98yAYp5c` | `/actionSymbol/ROLuCfi2.php` |
| `GachaSelectExeRequest` | `xio14KrL` | `BuJqHc41` | `/actionSymbol/eB0VYGMt.php` |
| `GameSettingRequest` | `OTX6Fmvu` | `4foXVwWd` | `/actionSymbol/OTX6Fmvu.php` |
| `GetBackgroundDownloadInfoRequest` | `lEHBdOEf` | `Z1krd75o` | `/actionSymbol/action.php` |
| `GetReinforcementInfoRequest` | `AJhnI37s` | `87khNMou` | `/actionSymbol/hXMoLwgE.php` |
| `GetTitleInfoRequest` | `ocP3A1FI` | `Mw56RNZ2` | `/actionSymbol/BbIeq31M.php` |
| `GetUserInfo2Request` | `2eK5Vkr8` | `7VNRi6Dk` | `/actionSymbol/7KZ4Wvuw.php` |
| `GetUserInfo3Request` | `4rjw5pnv` | `0Dn4hbWC` | `/actionSymbol/lZXr14iy.php` |
| `GetUserInfoRequest` | `X07iYtp5` | `rcsq2eG7` | `/actionSymbol/u7sHDCg4.php` |
| `GiftUpdateRequest` | `9KN5rcwj` | `xLEtf78b` | `/actionSymbol/noN8I0UK.php` |
| `GloryConfirmedGimmickRequest` | `7Bt6HTw0` | `4nik5jwd` | `/actionSymbol/F86LHcMO.php` |
| `GloryEntryRequest` | `UDb5Je1j` | `FtD9IGj7` | `/actionSymbol/nEZ9twZH.php` |
| `GloryMissionEndRequest` | `BQG1rm3y` | `5xvUq9Gm` | `/actionSymbol/F86LHcMO.php` |
| `GloryMissionReStartRequest` | `YAF1wt9J` | `fxCuP4k3` | `/actionSymbol/DHpM2abg.php` |
| `GloryMissionStartRequest` | `oj76TPS2` | `5hqtxF36` | `/actionSymbol/hZ4GFCAH.php` |
| `GooglePromotionRewardRequest` | `6PDhpa5T` | `F7AMb1u2` | `/actionSymbol/jSxaKcr0.php` |
| `GrandMissionEntryRequest` | `MTf2j9aK` | `Uey5jW2G` | `/actionSymbol/8DermCsY.php` |
| `InitializeRequest` | `75fYdNxq` | `rVG09Xnt` | `/actionSymbol/fSG1eXI9.php` |
| `IsNeedValidateRequest` | `er5xMIj6` | `djhiU6x8` | `/actionSymbol/gk3Wtr8A.php` |
| `ItemBuyRequest` | `sxK2HG6T` | `InN5PUR0` | `/actionSymbol/oQrAys71.php` |
| `ItemCarryEditRequest` | `UM7hA0Zd` | `04opy1kf` | `/actionSymbol/8BE6tJbf.php` |
| `ItemSellRequest` | `d9Si7TYm` | `E8H3UerF` | `/actionSymbol/hQRf8D6r.php` |
| `LibraryVisionCardEntryRequest` | `Lx8F2iU0` | `63ucryZ7` | `/actionSymbol/lIUfgWYj.php` |
| `LoginBonusRequest` | `vw9RP3i4` | `Vi6vd9zG` | `/actionSymbol/iP9ogKy6.php` |
| `MailListRequest` | `KQHpi0D7` | `7kgsrGQ1` | `/actionSymbol/u3E8hpad.php` |
| `MailReceiptRequest` | `XK7efER9` | `P2YFr7N9` | `/actionSymbol/M2fHBe9d.php` |
| `MasterCardReleaseRequest` | `23fbcXt4` | `7JE6MzkC` | `/actionSymbol/sC1oeYeD.php` |
| `MateriaFavoriteRequest` | `k5v0hMd8` | `La3si8kz` | `/actionSymbol/lW4xfpvS.php` |
| `MedalExchangeRequest` | `LiM9Had2` | `dCja1E54` | `/actionSymbol/0X8Fpjhb.php` |
| `MissionBreakRequest` | `17LFJD0b` | `Z2oPiE6p` | `/actionSymbol/P4oIeVf0.php` |
| `MissionContinueRequest` | `LuCN4tU5` | `34n2iv7z` | `/actionSymbol/ZzCXI6E7.php` |
| `MissionContinueRetireRequest` | `V3CiWT0r` | `F1QRxT5m` | `/actionSymbol/cQU1D9Nx.php` |
| `MissionEndRequest` | `x5Unqg2d` | `1tg0Lsqj` | `/actionSymbol/0ydjM5sU.php` |
| `MissionReStartRequest` | `GfI4LaU3` | `Vw6bP0rN` | `/actionSymbol/r5vfM1Y3.php` |
| `MissionRetireRequest` | `v51PM7wj` | `oUh1grm8` | `/actionSymbol/gbZ64SQ2.php` |
| `MissionStartRequest` | `29JRaDbd` | `i48eAVL6` | `/actionSymbol/63VqtzbQ.php` |
| `MissionSwitchUpdateRequest` | `Tvq54dx6` | `bZezA63a` | `/actionSymbol/1Xz8kJLr.php` |
| `MissionUpdateRequest` | `j5JHKq6S` | `Nq9uKGP7` | `/actionSymbol/fRDUy3E2.php` |
| `MissionWaveReStartRequest` | `e9RP8Cto` | `M3bYZoU5` | `/actionSymbol/8m7KNezI.php` |
| `MissionWaveStartRequest` | `BSq28mwY` | `d2mqJ6pT` | `/actionSymbol/Mn15zmDZ.php` |
| `MyCardInitializeRequest` | `BruItbuW` | `q54ajlRb` | `/actionSymbol/d6f9LSI7.php` |
| `NoticeReadUpdateRequest` | `pC3a2JWU` | `iLdaq6j2` | `/actionSymbol/j6kSWR3q.php` |
| `NoticeUpdateRequest` | `CQ4jTm2F` | `9t68YyjT` | `/actionSymbol/TqtzK84R.php` |
| `NvSacrificeRequest` | `x94MnujU` | `KXcC8A1o` | `/actionSymbol/VliYfNhr.php` |
| `OptionUpdateRequest` | `otgXV79T` | `B9mAa7rp` | `/actionSymbol/0Xh2ri5E.php` |
| `ParadeEntryRequest` | `Q46YTgWo` | `kF7Z5vCK` | `/actionSymbol/9i4b61rU.php` |
| `ParadeMissionEndRequest` | `4cACW7y3` | `Pv08w12y` | `/actionSymbol/hC8r9p81.php` |
| `PartyDeckEditRequest` | `TS5Dx9aZ` | `34qFNPf7` | `/actionSymbol/6xkK4eDG.php` |
| `PartyRegisterSlotLoadRequest` | `Q7jV6pno` | `7zcaE16T` | `/actionSymbol/2y4BVhyj.php` |
| `PartyRegisterSlotSaveRequest` | `CE98eghN` | `0S9Uzr42` | `/actionSymbol/QjDQEMYc.php` |
| `PartyRegisterSlotUpdateRequest` | `RQ5BjDE0` | `CpZH8rY0` | `/actionSymbol/HgSTAzd2.php` |
| `PlaybackMissionStartRequest` | `1YnQM4iB` | `YC20v1Uj` | `/actionSymbol/zm2ip59f.php` |
| `PlaybackMissionWaveStartRequest` | `1BpXP3Fs` | `NdkX15vE` | `/actionSymbol/scyPYa81.php` |
| `PlayerEmblemEntryRequest` | `Z7J9H6TK` | `F7A2MJoE` | `/actionSymbol/huKNdci6.php` |
| `PlayerEmblemSettingRequest` | `19YwqU2T` | `76kGLIgN` | `/actionSymbol/cswGxj8F.php` |
| `PurchaseCancelRequest` | `L7K0ezU2` | `Z1mojg9a` | `/actionSymbol/y71uBCER.php` |
| `PurchaseCurrentStateRequest` | `9mM3eXgi` | `X9k5vFdu` | `/actionSymbol/bAR4k7Qd.php` |
| `PurchaseFailedRequest` | `jSe80Gx7` | `sW0vf3ZM` | `/actionSymbol/2TCis0R6.php` |
| `PurchaseGiveUpRequest` | `BFf1nwh6` | `xoZ62QWy` | `/actionSymbol/C2w0f3go.php` |
| `PurchaseHoldRequest` | `79EVRjeM` | `5Mwfq90Z` | `/actionSymbol/dCxtMZ27.php` |
| `PurchaseListRequest` | `BT28S96F` | `X3Csghu0` | `/actionSymbol/YqZ6Qc1z.php` |
| `PurchaseSettingRequest` | `QkwU4aD9` | `ePFcMX53` | `/actionSymbol/9hUtW0F8.php` |
| `PurchaseSettlementRequest` | `JsFd4b7j` | `jmh7xID8` | `/actionSymbol/yt82BRwk.php` |
| `PurchaseStartRequest` | `qAUzP3R6` | `9Kf4gYvm` | `/actionSymbol/tPc64qmn.php` |
| `RateAppRewardRequest` | `L0OsxMaT` | `m1pPBwC3` | `/actionSymbol/L0OsxMaT.php` |
| `RbBoardPieceOpenRequest` | `hqzU9Qc5` | `g68FW4k1` | `/actionSymbol/iXKfI4v1.php` |
| `RbEndRequest` | `os4k7C0b` | `MVA3Te2i` | `/actionSymbol/e8AHNiT7.php` |
| `RbEntryRequest` | `f8kXGWy0` | `EA5amS29` | `/actionSymbol/30inL7I6.php` |
| `RbMatchingRequest` | `DgG4Cy0F` | `4GSMn0qb` | `/actionSymbol/mn5cHaJ0.php` |
| `RbRankingRequest` | `kcW85SfU` | `SR6PoLM3` | `/actionSymbol/3fd8y7W1.php` |
| `RbReStartRequest` | `6ZNY3zAm` | `PRzAL3V2` | `/actionSymbol/DQ49vsGL.php` |
| `RbStartRequest` | `eHY7X8Nn` | `P1w8BKLI` | `/actionSymbol/dR20sWwE.php` |
| `ReinforcementSettingRequest` | `ZSq2y7EX` | `jUreV31B` | `/actionSymbol/I1g4ezbP.php` |
| `ResourceAllDownloadRequest` | `i0d5n1Dp` | `fL07ojUc` | `/actionSymbol/Vtx9kFg0.php` |
| `RmDungeonEndRequest` | `WaPC2T6i` | `dEnsQ75t` | `/actionSymbol/CH9fWn8K.php` |
| `RmDungeonStartRequest` | `R5mWbQ3M` | `A7V1zkyc` | `/actionSymbol/NC8Ie07P.php` |
| `RmEndRequest` | `fyp10Rrc` | `FX5L3Sfv` | `/actionSymbol/I9p3n48A.php` |
| `RmEntryRequest` | `wx5sg9ye` | `p2tqP7Ng` | `/actionSymbol/fBn58ApV.php` |
| `RmRestartRequest` | `yh21MTaG` | `R1VjnNx0` | `/actionSymbol/NC8Ie07P.php` |
| `RmRetireRequest` | `e0R3iDm1` | `T4Undsr6` | `/actionSymbol/fBn58ApV.php` |
| `RmStartRequest` | `7FyJS3Zn` | `iu67waph` | `/actionSymbol/8BJSL7g0.php` |
| `RoutineEventUpdateRequest` | `4kA1Ne05` | `V0TGwId5` | `/actionSymbol/WCK5tvr0.php` |
| `RoutineGachaUpdateRequest` | `t60dQP49` | `Q6ZGJj0h` | `/actionSymbol/qS0YW57G.php` |
| `RoutineHomeUpdateRequest` | `Daud71Hn` | `aw0syG7H` | `/actionSymbol/1YWTzU9h.php` |
| `RoutineRaidMenuUpdateRequest` | `g0BjrU5D` | `z80swWd9` | `/actionSymbol/Sv85kcPQ.php` |
| `RoutineWorldUpdateRequest` | `6H1R9WID` | `XDIL4E7j` | `/actionSymbol/oR1psQ5B.php` |
| `SacrificeRequest` | `7tWdn9zH` | `U80FYThX` | `/actionSymbol/QBiJEyUt.php` |
| `SearchGetItemInfoRequest` | `0D9mpGUR` | `vK2V8mZM` | `/actionSymbol/e4Gjkf0x.php` |
| `ShopExchangeItemListRequest` | `syKz34cE` | `h69WSu02` | `/actionSymbol/7KJjJiIh.php` |
| `ShopExchangeItemRequest` | `xD5b6PqQ` | `vaDW85R2` | `/actionSymbol/qhP5wSXV.php` |
| `ShopExchangeUnitRequest` | `Vgi7j68T` | `x6rSuK0J` | `/actionSymbol/lnXYChmF.php` |
| `ShopUseRequest` | `73SD2aMR` | `ZT0Ua4wL` | `/actionSymbol/w76ThDMm.php` |
| `SignInCheckRequest` | `ufKRrNc7` | `F83wNKFt` | `/actionSymbol/Qfpa24mZ.php` |
| `SignInRequest` | `FckReppg` | `g8iv4P8I` | `/actionSymbol/8DRAiBXE.php` |
| `SignOutRequest` | `o96pHAp3` | `UtE1qMv3` | `/actionSymbol/KwChAfkX.php` |
| `SpChallengeEntryRequest` | `MTf2j9aK` | `Uey5jW2G` | `/actionSymbol/8DermCsY.php` |
| `SpChallengeRewardGetRequest` | `2G7ZVs4A` | `mG25PIUn` | `/actionSymbol/9inGHyqC.php` |
| `StrongBoxOpenRequest` | `PIv7u8jU` | `sgc30nRh` | `/actionSymbol/48ktHf13.php` |
| `SublimationSkillRequest` | `s48Qzvhd` | `97Uvrdz3` | `/actionSymbol/xG3jBbw5.php` |
| `SurvivalMissionEndRequest` | `3cuPF20R` | `VNj9J3Bg` | `/actionSymbol/HBIJ1BxB.php` |
| `SurvivalMissionEntryRequest` | `cH9DnW03` | `nUfp8v2y` | `/actionSymbol/iAL25ka3.php` |
| `SurvivalMissionRestartRequest` | `p02YN1JA` | `70HoeuUR` | `/actionSymbol/9R2VNtZV.php` |
| `SurvivalMissionRetireRequest` | `yW35iC40` | `YKfeAw01` | `/actionSymbol/T1MnS9pf.php` |
| `SurvivalMissionReturnRequest` | `Ge2ZLDC1` | `0X67saPi` | `/actionSymbol/cGQ3zDn8.php` |
| `SurvivalMissionStartRequest` | `67tFRKyo` | `DT3UHBu1` | `/actionSymbol/RXwRAXmX.php` |
| `TfaBonusRewardInfoRequest` | `fcPxKx8M` | `fga9Awck` | `/actionSymbol/fcPxKx8M.php` |
| `TfaEntryRequest` | `C0Lne0I7` | `OVmfEPwl` | `/actionSymbol/C0Lne0I7.php` |
| `TfaMissionEndRequest` | `JiglLZx6` | `c4d1b068` | `/actionSymbol/JiglLZx6.php` |
| `TfaMissionStartRequest` | `BSq28mwY` | `d2mqJ6pT` | `/actionSymbol/Mn15zmDZ.php` |
| `TfaRankingDetailRequest` | `Bg1cbQV7` | `apV7aUzj` | `/actionSymbol/Bg1cbQV7.php` |
| `TfaResultRewardFixRequest` | `JO2zA1Jy` | `bv2RPd1G` | `/actionSymbol/JO2zA1Jy.php` |
| `TfaResultRewardSelectResumeRequest` | `4qVA8LFK` | `hqwHhgPE` | `/actionSymbol/4qVA8LFK.php` |
| `TowerEndRequest` | `fBN47X2b` | `kzFy73L9` | `/actionSymbol/TZXbYd9b.php` |
| `TowerEntryRequest` | `VfEh2wD0` | `L9d1gYAm` | `/actionSymbol/scI7HnwD.php` |
| `TowerRestartRequest` | `9Z3jCWfF` | `04HMuYV1` | `/actionSymbol/iqxK7alu.php` |
| `TowerRetireRequest` | `MTuX7ai2` | `5dqrT8Mi` | `/actionSymbol/sn4mo4gN.php` |
| `TowerStartRequest` | `dZA90j5s` | `M3dCmDW8` | `/actionSymbol/1ch0bfGj.php` |
| `TownInRequest` | `8EYGrg76` | `JI8zU5rC` | `/actionSymbol/isHfQm09.php` |
| `TownOutRequest` | `sJcMPy04` | `Kc2PXd9D` | `/actionSymbol/0EF3JPjL.php` |
| `TownUpdateRequest` | `G1hQM8Dr` | `37nH21zE` | `/actionSymbol/0ZJzH2qY.php` |
| `TransferCodeCheckRequest` | `CY89mIdz` | `c5aNjK9J` | `/actionSymbol/C9LoeYJ8.php` |
| `TransferCodeIssueRequest` | `crzI2bA5` | `T0y6ij47` | `/actionSymbol/hF0yCKc1.php` |
| `TransferRequest` | `oE5fmZN9` | `C6eHo3wU` | `/actionSymbol/v6Jba7pX.php` |
| `TrophyRewardRequest` | `wukWY4t2` | `2o7kErn1` | `/actionSymbol/05vJDxg9.php` |
| `UnitClassUpRequest` | `zf49XKg8` | `L2sTK0GM` | `/actionSymbol/8z4Z0DUY.php` |
| `UnitEquipRequest` | `pB3st6Tg` | `45VZgFYv` | `/actionSymbol/nIk9z5pT.php` |
| `UnitExClassUpRequest` | `k6NI9Tm1` | `3xNEuAJ0` | `/actionSymbol/P19pJnPf.php` |
| `UnitExchangeRequest` | `3ekgi8bh` | `up94SLAv` | `/actionSymbol/YVZlW2gN.php` |
| `UnitFavoriteRequest` | `tBDi10Ay` | `w9mWkGX0` | `/actionSymbol/sqeRg12M.php` |
| `UnitMixRequest` | `UiSC9y8R` | `4zCuj2hK` | `/actionSymbol/6aLHwhJ8.php` |
| `UnitNvClassUpRequest` | `Pf5C8xjJ` | `2tJE0Ijo` | `/actionSymbol/ukNsKIEo.php` |
| `UnitNvpClassUpRequest` | `V8GtMQ2q` | `m23Etnuz` | `/actionSymbol/5kOVOj0a.php` |
| `UnitSellRequest` | `9itzg1jc` | `DJ43wmds` | `/actionSymbol/0qmzs2gA.php` |
| `UnitStorageUpdateRequest` | `5ik69cuw` | `3HDUxoG5` | `/actionSymbol/HkfCn09z.php` |
| `UnitSublimationRequest` | `a54L9CKY` | `B7iQjmz5` | `/actionSymbol/PiQObNT2.php` |
| `UnitUsePointRequest` | `nsxUW3Y7` | `1iPZp3kJ` | `/actionSymbol/Why4WO1r.php` |
| `UpdateDeviceIdRequest` | `aQm3zP2c` | `mvRSdn8f` | `/actionSymbol/action.php` |
| `UpdateSwitchInfoRequest` | `mRPo5n2j` | `4Z5UNaIW` | `/actionSymbol/SqoB3a1T.php` |
| `UpdateUserInfoRequest` | `ey8mupb4` | `6v5ykfpr` | `/actionSymbol/v3RD1CUB.php` |
| `VariableStoreCheckRequest` | `i0woEP4B` | `Hi0FJU3c` | `/actionSymbol/Nhn93ukW.php` |
| `VisionCardDisplayRequest` | `TmS3EjZ8` | `e3LTk8ti` | `/actionSymbol/mCy1T1hc.php` |
| `VisionCardFavoriteRequest` | `VTbX14dD` | `YkRC3A9U` | `/actionSymbol/PEIMihWu.php` |
| `VisionCardMixRequest` | `5J14x3Qz` | `NVMk7Qr1` | `/actionSymbol/aeBv64rU.php` |
| `sgAdsGachaMilestoneRequest` | `PkSzb2TM` | `Jp4Fz3qb` | `/actionSymbol/PkSzb2TM.php` |
| `sgComebackQuestClaimRewardRequest` | `1IOdaWOW` | `4NO3PIyU` | `/actionSymbol/I7RzrQ3J.php` |
| `sgEmblemEventRequest` | `wMWvnYDR` | `U9QMZrFq` | `/actionSymbol/wMWvnYDR.php` |
| `sgExpdAccelerateRequest` | `Ik142Ff6` | `d3D4l8b4` | `/actionSymbol/Ik142Ff6.php` |
| `sgExpdEndRequest` | `2pe3Xa8b` | `cjHumZ2J` | `/actionSymbol/2pe3Xa8b.php` |
| `sgExpdMileStoneClaimRequest` | `r4A791RF` | `t04N07LQ` | `/actionSymbol/r4A791RF.php` |
| `sgExpdQuestInfoRequest` | `hW0804Q9` | `4Bn7d973` | `/actionSymbol/hW0804Q9.php` |
| `sgExpdQuestRefreshRequest` | `vTgYyHM6` | `vceNlSf3` | `/actionSymbol/vTgYyHM6.php` |
| `sgExpdQuestStartRequest` | `I8uq68c3` | `60Os29Mg` | `/actionSymbol/I8uq68c3.php` |
| `sgExpdRecallRequest` | `0Fb87D0F` | `9J02K0lX` | `/actionSymbol/0Fb87D0F.php` |
| `sgGachaRerollExeRequest` | `Dll4rncD` | `KJ13DlZz` | `/actionSymbol/QQVXslxB.php` |
| `sgGachaSelectPrismExeRequest` | `bgast6dR` | `7mDIdVEI` | `/actionSymbol/pXAIaMKW.php` |
| `sgHiddenSkillUpgrade` | `qxUUaS8s` | `rXDvnsv8` | `/actionSymbol/qxUUaS8s.php` |
| `sgHomeMarqueeInfoRequest` | `PBSP9qn5` | `d3GDS9X8` | `/actionSymbol/PBSP9qn5.php` |
| `sgMissionUnlockRequest` | `LJhqu0x6` | `ZcBV06K4` | `/actionSymbol/LJhqu0x6.php` |
| `sgOfferwallInfoRequest` | `uO1w9ggv` | `QgNR0HvE` | `/actionSymbol/NmNB96p8.php` |
| `sgPanelQuestEntryRequest` | `GVyjSq16` | `T3g6EPOp` | `/actionSymbol/GVyjSq16.php` |
| `sgPanelQuestExtraRewardRequest` | `AOY6npa3` | `vZWKUHhY` | `/actionSymbol/AOY6npa3.php` |
| `sgPanelQuestRewardRequest` | `6uue8aKx` | `bjtzvZ5X` | `/actionSymbol/6uue8aKx.php` |
| `sgPanelQuestStatusGetRequest` | `egJpaGtk` | `uzEklRfc` | `/actionSymbol/egJpaGtk.php` |
| `sgStoreLogReportRequest` | `6611dc2f` | `af7a56a0` | `/actionSymbol/6611dc2f.php` |
| `sgUserExtraChallengeInfoRequest` | `dzU2t3HA` | `Qu6RHqbb` | `/actionSymbol/zgry2aNV.php` |


## 5. What is not established

These are the open questions, stated so nobody mistakes them for settled facts.

**No complete JSON schema.** Response field names are 8-character obfuscated tokens compared with
`strcmp` inside each `*Response::readParam`. There are 496 of those parsers in the binary. A handful of
payloads have been mapped end to end; the rest are recoverable by the same method but are not
published. A server can be routed to before it can be answered correctly.

**Signal key lifecycle.** The client receives a signal key from the server and stores it. When it is
refreshed, whether every request needs it, and what relation it has to the encode key are all unknown.

**Request-ID versus encode key.** The encode key is settled: it is the AES key for both directions,
confirmed against a live client. The request-ID is a separate token carried in the request envelope,
and its role beyond identifying the action is not established.

**Endpoint list completeness.** The 211 paths are the ones compiled as literals. A route could still be
assembled at runtime from the URL dictionary or by string concatenation, so the list is not provably
exhaustive.

**Server authority.** This is now settled for two areas and open for the rest. Gacha is entirely
server-authoritative: the client holds no rate or weight table, so the draw can only come from the
server. Battle drops are the same shape — the client displays a candidate pool and discards the rate,
so the roll has to happen server-side. Whether the original server audited the battle stat history the
client uploads, or merely accepted it, is still unknown. Feature switches are a third: several tiles
are gated by the function table and no shipped row grants the bits, so the server is the only source of
that progression.

**The modes past the home screen.** The arena, Colosseum, support and emblem paths are routed and their
entry replies are understood, but the screens behind them have not been driven end to end: whether the
emblem campaign's three groups are consumed on their own request, and whether zero-valued Colosseum
battle info is safe, are both open.

**Version negotiation.** The manifest row is understood: the server supplies a table name and a
version, and the client builds the `Ver<N>_<token>` filename itself. The rule that assigns `<N>`, and
the set of tables mandatory at first boot, are not decoded.

**Login state machine.** The guest versus platform login paths and the two-factor flow were not traced.

**One TLS residual, not reached in practice.** An SDK helper that would install a global default socket
factory exists but was not seen to be called anywhere reachable. Static reading cannot rule it out, but
repeated live runs in a rooted emulator verify successfully against a CA in the system store, so no
runtime path has reached it.

## 6. How the map was recovered

For anyone extending this, the method matters more than the results.

The endpoint table came from three accessors per request class. `getRequestID()`, `getEncodeKey()` and
`getUrl()` each compile to a three-instruction stub that loads a string and returns it, so resolving
the address of the loaded string recovers all three values for all 222 classes mechanically.

The route and host came from the URL builder: separate literals for the host, the base path, the
`php/gme` segment and the `/actionSymbol/` prefix, joined by small functions. Following the join
reconstructs the full URL.

The envelope could not be read from the native library, because the cipher is not there. The native
`encodeCStringForBase64WithNewCrypto` is a JNI bridge, so the algorithm lives in the APK's `classes.dex`
and the decompiled Java gives the mode, the padding and the key derivation directly. This is also why
a native-code search for the AES routine comes up empty, which is a useful negative to know before
spending time on it.

TLS trust came from call sites rather than from strings. Verification is on unless something calls the
setter that turns it off; that setter has no call sites, and the pinning APIs have none either. A
negative like this is only as good as the call-site search behind it, which is why the search is
described rather than just the conclusion.

Finally, the envelope was validated against a live client: requests decrypted, replies re-encrypted
with the per-request key, and the double padding confirmed by the client accepting a double-padded
reply and rejecting a single-padded one.

The payload maps come from the same tooling, one parser at a time. A response class reads its body in
`*Response::readParam`, which compares the incoming field name against its 8-character token and then
branches to the store for that field. Reading the comparison and its branch target gives the token and
the field offset; the sibling `*Mst` struct's own `set*` accessors give the human name for that
offset. Join the two and a token map falls out. Which fields actually matter on a given screen is then
a question for a live run, because most reply handlers clear their target object before reading.

`finding_the_endpoints.md` is the platform-neutral write-up of both halves: reading this table out of
a client build, and watching a running client so a screen that will not advance can be pinned to the
call that caused it.
