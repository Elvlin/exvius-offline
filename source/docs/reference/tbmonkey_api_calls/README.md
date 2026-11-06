# FFBE API notes

Notes on the server-facing surface of the v9.0.0 *FINAL FANTASY BRAVE EXVIUS* Android client, for
anyone who wants to point the game at a server of their own.

- **`FFBE_SERVER_CONTRACT.md`**: the server contract. Transport, route, the request/response
  envelope, the eleven areas a server has to answer, and the full endpoint table (211 URLs).
- **`boot_to_home_endpoints.md`**: the practical companion. The 15 endpoints the client actually
  touches between launch and a playable home screen, in order, with what each reply has to satisfy.
- **`validated_endpoints.md`**: the next step past the home screen — the mission, summon, home-poll
  and shop paths that have been driven against a live client, what each reply has to carry, and the four
  things a battle reply gets wrong by omission (monster parts, skills, the break groups, and the fact
  that the enemy's behaviour is not yours to send).
- **`arena_and_colosseum_endpoints.md`**: the two competitive modes — their request families, the orb bar
  and where its rates come from, and the cap-a-layout-can't-draw trap that crashes the arena's ranking
  screen.
- **`support_and_friends_endpoints.md`**: the borrowed-helper list and the friends area — how the rows
  ride the reinforcement reply, what has been proven to render, and why a row built from another
  class's field names faults the support screen.
- **`events_and_unlocks_endpoints.md`**: the event gate list, the emblem screens and the crest campaign,
  and the story switches that open feature tiles — what derives, what has to be authored, and what is
  still unproven.
- **`gacha_endpoints.md`**: the summon system in depth — how a banner actually reaches the client,
  the response groups behind it, and what a server has to author because it never shipped.
- **`towns_and_maps_endpoints.md`**: the town transition requests and the per-location pack delivery
  behind a town or a field — what the replies have to satisfy, how the client decides which packs to
  fetch, and how a missing pack fails.
- **`missing_cdn_packs.md`**: the packs the client asks for that no build we can compare against
  contains, with exact CDN paths, what the JP dump did and did not close, and what a useful copy of the
  game would look like.
- **`finding_the_endpoints.md`**: the method. How the endpoint table is recovered from the client
  binary, and how to watch a running client and pin a failure back to the call that caused it.
- **`response_tag_map.json`**: 8-character response tag to response class, for making sense of the
  tags the client sends and expects.

## The endpoints to address

To get the client to a running home screen, these are the requests to answer, in the order it sends
them:

```
GameSettingRequest
GetBackgroundDownloadInfoRequest
InitializeRequest
CreateUserRequest
UpdateSwitchInfoRequest
GetUserInfoRequest
GetUserInfo2Request
GetUserInfo3Request
GetReinforcementInfoRequest
sgHomeMarqueeInfoRequest
UpdateDeviceIdRequest
RoutineHomeUpdateRequest
sgOfferwallInfoRequest
TfaMissionStartRequest
DungeonResourceLoadMstListRequest
```

On the home screen two more follow: `RoutineEventUpdateRequest` and `NoticeUpdateRequest`.

Once the game is actually being played, the client reaches a further set of endpoints — mission
start and end, the summon flow, the other routine polls, party edits, the shop, and the arena,
Colosseum, support-list and emblem paths. The driven ones are walked through in
`validated_endpoints.md`; the deeper modes have their own notes
(`arena_and_colosseum_endpoints.md`, `support_and_friends_endpoints.md`,
`events_and_unlocks_endpoints.md`).

`boot_to_home_endpoints.md` lists the request-ID, encode key and URL for each of these, and what the
reply has to contain. The other ~195 endpoints in the contract table are reached later, from
individual screens and actions (battle, gacha, shop, friends), not on the boot path.

Beyond the `actionSymbol` calls there is a second axis: the client downloads versioned master-data
tables and resource packs from a host the server configures. A server has to serve those too, or the
client will not finish loading. Map and town content is fetched **per location**, on demand; the packs
with no known source are listed in `missing_cdn_packs.md`.

## Four things that will bite you

**The body is padded twice.** The client pads manually with PKCS7 and then lets Java pad again, so its
ciphertext carries 16 more bytes than a single-padded implementation produces. A single-padded reply is
rejected and the client shows a connection error. Double-pad.

**The CDN host is a bare host.** The value the server pushes for the resource host must have no scheme.
The client prepends `https://` itself, so `https://host/` becomes `https://https://host//...` and
nothing downloads.

**The user id is yours to issue, and it has to arrive early.** Once the client has a user id it skips
account creation. More importantly, the `GetUserInfoRequest` reply must carry the active party id
alongside the party decks. If a deck exists under one id and the active party id is left at its
default of zero, the client crashes inside the home screen. It is a single field, but it is the
difference between the login flow and a working home screen.

**A server number that indexes the client's UI has to fit it.** The arena's ranking screen draws one
orb button per orb up to the cap it is served, and its layout ships ten of them. A larger cap makes the
eleventh lookup return null and the client crashes while building the screen — a SIGSEGV for a value
that looked harmless in the reply. Keep server-supplied counts within the client's own layout.
