# The request path to the home screen

A captured run of the client from launch to a playable home screen, against a local server. This is the
practical companion to the endpoint table in `FFBE_SERVER_CONTRACT.md`: it shows which of the 211
endpoints the client actually touches on the critical path, in order, and which reply answers each one.

The sequence is the union of several runs, so it is the path as exercised rather than a single run's
log. Fifteen request classes appear between launch and the home screen. Two more follow once it is up.

## The sequence

| # | Request class | request-ID | URL token | encode key | answered |
|---|---|---|---|---|---|
| 1 | `GameSettingRequest` | `OTX6Fmvu` | `OTX6Fmvu.php` | `4foXVwWd` | yes |
| 2 | `GetBackgroundDownloadInfoRequest` | `lEHBdOEf` | `action.php` | `Z1krd75o` | yes |
| 3 | `InitializeRequest` | `75fYdNxq` | `fSG1eXI9.php` | `rVG09Xnt` | yes |
| 4 | `CreateUserRequest` | `P6pTz4WA` | `0FK8NJRX.php` | `73BUnZEr` | yes |
| 5 | `UpdateSwitchInfoRequest` | `mRPo5n2j` | `SqoB3a1T.php` | `4Z5UNaIW` | yes |
| 6 | `GetUserInfoRequest` | `X07iYtp5` | `u7sHDCg4.php` | `rcsq2eG7` | yes |
| 7 | `GetUserInfo2Request` | `2eK5Vkr8` | `7KZ4Wvuw.php` | `7VNRi6Dk` | yes |
| 8 | `GetUserInfo3Request` | `4rjw5pnv` | `lZXr14iy.php` | `0Dn4hbWC` | yes |
| 9 | `GetReinforcementInfoRequest` | `AJhnI37s` | `hXMoLwgE.php` | `87khNMou` | yes |
| 10 | `sgHomeMarqueeInfoRequest` | `PBSP9qn5` | `PBSP9qn5.php` | `d3GDS9X8` | yes |
| 11 | `UpdateDeviceIdRequest` | `aQm3zP2c` | `action.php` | `mvRSdn8f` | yes |
| 12 | `RoutineHomeUpdateRequest` | `Daud71Hn` | `1YWTzU9h.php` | `aw0syG7H` | yes |
| 13 | `sgOfferwallInfoRequest` | `uO1w9ggv` | `NmNB96p8.php` | `QgNR0HvE` | yes |
| 14 | `TfaMissionStartRequest` | `BSq28mwY` | `Mn15zmDZ.php` | `d2mqJ6pT` | yes |
| 15 | `DungeonResourceLoadMstListRequest` | `jnw49dUq` | `Sl8UgmP4.php` | `3PVu6ReZ` | yes |
| 16 | `RoutineEventUpdateRequest` | `4kA1Ne05` | `WCK5tvr0.php` | `V0TGwId5` | yes |
| 17 | `NoticeUpdateRequest` | `CQ4jTm2F` | `TqtzK84R.php` | `9t68YyjT` | yes |

The first fifteen are the boot chain. Numbers 16 and 17 are home-screen polls that fire after the home
screen is up.

## What each step is for

**1. `GameSettingRequest`** is the boot packet. It carries the user-info, signal-key and version groups
before any session exists, and its reply configures the client's paths and feature flags, including the
CDN host.

**2. `GetBackgroundDownloadInfoRequest`** decides whether the client needs to download anything. An
empty list is accepted and means "nothing to fetch".

**3. `InitializeRequest`** carries the version manifest. This is where the server tells the client which
MST and resource versions are current, which in turn drives the CDN downloads. Advertise a version the
client has and it will not re-download; advertise a different one and it fetches the table you name.

**4. `CreateUserRequest`** is the account-creation call, used only for a fresh account. Once the server
issues a user id early enough, the client skips the creation screen entirely.

**5. `UpdateSwitchInfoRequest`** handles feature switches. The reply carries switch state keyed by
switch type.

**6. `GetUserInfoRequest`** is the important one for reaching a usable home screen: it carries the
player's roster, party decks and active party id. A reply missing the active party id, when a deck
exists under a different id, crashes the client in the home screen. This was the single field that
stood between the login flow and a working home screen in testing.

**7 and 8. `GetUserInfo2Request` and `GetUserInfo3Request`** are follow-ups for additional account
sections. A minimal user-info echo satisfies them.

**9. `GetReinforcementInfoRequest`** fetches the borrowable-helper list. Its rows ride
`ReinforcementResponse`, which binds two tags — one carries the list and one clears it — and an empty
list is accepted: the home screen renders and a battle simply has no helper to offer. The row rules are
in `support_and_friends_endpoints.md`.

**10. `sgHomeMarqueeInfoRequest`** fetches the scrolling home banners. An empty banner list is safe and
renders as nothing.

**11. `UpdateDeviceIdRequest`** reports the device id.

**12. `RoutineHomeUpdateRequest`** is the home poll. Its reply carries a delta in seconds until the
next poll. Send zero, or omit it, and the client re-polls on the margin interval; send a positive
delta and it stays quiet.

**13. `sgOfferwallInfoRequest`** controls the offerwall. Both flags can be zero, which disables it.

**14. `TfaMissionStartRequest`** starts the opening mission. The same request-ID is shared
with `MissionWaveStartRequest` and `GrandMissionEntryRequest`, and the pairs are identical on the wire,
so one reply serves all three.

**15. `DungeonResourceLoadMstListRequest`** loads a table list. An empty list is permissive.

**16. `RoutineEventUpdateRequest`** is the event-side twin of step 12. It has a single field, a delta
in seconds until the next event poll, landing in the same update-time object. Empty is accepted but
leaves the poll running; a positive delta quiets it.

**17. `NoticeUpdateRequest`** fetches notices. The request carries a kind id, and the reply tag depends
on that kind. The client sends this from banner taps and from the information list. An empty list is
accepted and renders as an empty notice list.

## The other half: resource delivery

Reaching the home screen also requires the resource axis, which is not `actionSymbol` traffic.

The client learns where to download from through the CDN path value in its configuration, pushed by the
server. That value has to be a **bare host** with no scheme, because the client prepends the scheme
itself. Writing `https://host/` into it produces `https://https://host//...` and no fetch ever leaves
the device.

With the host set correctly, the client downloads the versioned tables and their payloads from the
server. A complete run pulls the full resource set with no 404s, and the stored copy matches the
original byte for byte. The same mechanism can serve a patched table: advertise a higher version in the
manifest and the client downloads your copy instead of the one it already has, without touching the
read-only shipped tree.

## Notes from the run

The envelope detail that trips people first is the double padding. The client pads the body manually
and then lets Java pad it again, so a reply with single padding is rejected and shows a connection
error. Once the server double-pads, the boot chain advances.

The client retries an outstanding request about once a second while its connector is in an error state.
A request the server never answers therefore shows up as a burst of identical requests rather than a
single stalled one. Answering it is what stops the burst.

## What comes after

This note stops the moment the home screen is up. The screens beyond it — a mission, a summon, the
recurring polls, the shop and the party edits — are the subject of `validated_endpoints.md`.
