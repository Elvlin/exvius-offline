# The summon (gacha) system

The summons screen is where this client stops looking like a game and starts looking like a terminal. It
knows how to lay out a banner, draw its buttons and play a summon animation. It does not know what a pull
costs, what is in it, or what it should return. The client never rolls. None of that was in the APK — the
banner definitions, the pools and the rates were all transmitted by the server, so a reconstruction has to
author them.

This note is the companion to the gacha paragraph in `FFBE_SERVER_CONTRACT.md` and the summon entries in
`validated_endpoints.md`. It covers the part those two leave out: how a banner actually reaches the
client, the object graph the client expects, and which pieces exist to be reused versus invented.

## The banner layer is delivered in reply bodies, not from the CDN

The natural assumption — the one we started with — is that banners arrive as downloaded master data
(`Ver<N>_<token>.dat`) like almost everything else. They do not. The classes that hold the banner layer
have no table name and no loader, so they cannot register with the client's version manifest, and no
`F_GACHA_MST`, `F_GACHA_DETAIL_MST` or `F_GACHA_SCHEDULE_MST` key exists in the binary or in the shipped
tables. What does exist is a response
factory that recognises the gacha reply tags and constructs the response groups that fill those lists.

The client is tag-driven here, not request-driven. It dispatches whatever tags a reply carries, and no
request class is bound to them, so **which reply carries the banner groups is the server's choice**. In our
runs they ride the replies to `GachaEntryRequest` and `GachaInfoRequest`. What matters is that they arrive
in a reply body at all: put banners in the CDN and the summons screen is empty rather than broken.

The same is true of a re-fetch. The list-containing replies clear their target list before reading, so each
reply replaces the catalogue it carries rather than merging into it.

## The requests

The endpoint table is in the contract's appendix; what each request is for is the part worth saying.

| Request class | What it is |
|---|---|
| `GachaEntryRequest` | entering the summons screen. Its body is the ordinary account envelope and it carries no banner id — the banner catalogue rides the reply. |
| `GachaInfoRequest` | opening one banner's detail. This one names the banner. |
| `GachaExeRequest` | confirming a pull. The body is small: the banner id, the detail id, the repeat count, and the ticket id if the player chose a ticket. |
| `GachaBoxNextRequest` · `GachaPanelNextRequest` | advancing a box or a panel. |
| `GachaSelectEntryRequest` · `GachaSelectExeRequest` · `GachaSelectExchangeExeRequest` | the select-ticket families. |
| `sgGachaRerollExeRequest` · `sgGachaSelectPrismExeRequest` · `sgAdsGachaMilestoneRequest` | reroll, prism exchange and ad-gacha milestones. |

`RoutineGachaUpdateRequest` appears in the endpoint table with the routine polls, but it is dead in this
build: nothing constructs it, so there is no periodic banner refresh. The catalogue is re-fetched when a
gacha screen asks for it.

## What comes back

The pull's reply is one result object, not a list of draws. Awards arrive as `type:id` entries, where type
10 is a unit, alongside the refreshed currency balances. The client clears its result object before reading
the group, so one reply is one pull's worth of results — a ten-pull is still a single group carrying ten
awards.

One trap to know before writing a server: the repeat-count and ticket-id fields **swap names between the
request class and the reply class**. Reading the request's fields with the reply's meanings miscounts every
pull, and it only shows up when you pull.

## The object graph of one banner

A banner is built from a handful of response groups linked by shared ids. The names are the client's own:

| Group | What it carries |
|---|---|
| `GachaMstResponse` | the banner definition: id, tab type, layout, button art, summon-anime names. |
| `GachaScheduleMstResponse` | the schedule: display order, campaign window, and the list/detail banner art. |
| `GachaDetailMstResponse` | one row per offer, not per banner: a detail id, the cost, which button it drives, a ticket group, art. |
| `GachaPanelMstResponse` · `GachaPanelGroupMstResponse` | the panel link and one row per pool entry. |
| `UserGachaInfoResponse` | the player's per-banner state: term window and how many times it has been pulled. |

Serving the first three is enough for a plain banner. The panel groups are what a "show the rates" panel
reads; box gachas substitute a box-detail group. `UserGachaStepInfoResponse` carries the step number for a
step-up.

### Tabs come from one field

The client sorts a banner into its tab from a single `GachaMst` field, tested in this order: free first,
then exchange, then limited, and anything left over is the paid tab. The recovered values are **0, 6 and
900** for free; **8** for exchange (6 also matches exchange, but free is tested first); **50 and 7** for
limited. The same values filter the list, so a banner sent with the wrong type is not merely misplaced —
it is hidden. The full value set was lost with the rows; only the values the client tests are recovered.

### Buttons come from detail rows, not the cost

A banner's buttons are not derived from its cost string. One detail row with execution type 1 draws the
single button; a second row with execution type 2 draws the multi button; a ticket group that resolves
against the shipped ticket table adds the ticket button. One multi button, at most.

And a cost string with more than one entry **aborts the client** on the summons screen with a
`std::out_of_range` abort. Serve exactly one cost entry per banner.

### Cost, and who checks it

The cost is a small grammar — `kind:itemId:amount:count`. Kind 50 is lapis and 51 is friend points; an
empty cost is free; a ticket-only banner uses an empty cost plus a ticket group instead. The client
displays whether the player can afford the pull but does not disable the button and does not re-check
at tap time. Spending the currency, and refusing an unaffordable pull, belong to the server — as does
the draw itself.

### What the client paints, and from where

- **Titles and descriptions** are local text keyed by the banner id (`MST_GACHA_NAME_<id>` and its
  explanation siblings), not the name field in the detail row. An id with no shipped or patched text row
  renders the raw key.
- **List and detail art** is downloaded as loose files, not from an MST, after the schedule arrives. A
  missing file surfaces as the client's generic connection error rather than a missing image. Filenames
  arrive percent-encoded and must be decoded server-side; a name containing a space 404s otherwise.
- **The summon animation** comes from the banner row's anime file/name pair. An effect-pattern id that does
  not resolve in the shipped effect table makes the client skip the animation with its own "Failed to
  display summon animation" notice. The tutorial's forced pull is the exception to all of this — its
  request carries no banner at all, so its award is entirely the server's.

## What ships, and what has to be authored

The banner row itself never shipped, but a surprising amount around it did. This is the split we work
against.

| Piece | Shipped? |
|---|---|
| Banner definitions, schedules, detail rows, panel/pool rows (the reply groups) | **No — authored.** |
| The player's per-banner state, and the draw itself | **No — server state and server logic.** |
| Banner identity: the id ↔ detail-id pairs | Yes — 606 rows over 275 banner ids in `F_GACHA_DETAIL_EXTRA_MST`. |
| Titles and descriptions | Yes — 2,207 English `MST_GACHA_NAME_*` rows in the localized text tables. |
| Store/exchange rows and artwork names | Yes — 706 rows in `F_GACHA_STORE_MST`. |
| A ready-made select pool | Yes — 234 rows in `F_GACHA_SELECT_UNIT_MST`, every one base rarity 5, uniform weight. |
| Ticket groups | Yes — 17 rows in `F_TICKET_MST`. |
| Summon animation and effect tables | Yes — the `F_GACHA_EFFECT_*` and wheel tables. |
| Banner artwork files | Yes — the files are on disk; which banner each belongs to was in the rows that did not ship. |

So the identity layer can largely be reused: banner ids, detail ids, titles, and even a select-summon pool
are recoverable from the shipped data. What has to be authored is the composition — which banner exists,
when it runs, which tab it belongs to, what it costs, what is in it, and how likely each unit is.

**Rates.** The pool never existed client-side, so nothing in the APK can tell you what the displayed rates
were: the numbers on the in-game rate disclosure came from the server. A reconstruction's rates are
authored. The community sources are calculator-era models rather than tables — a pre-2019 model around 1%
rainbow / 19% gold / 80% blue, a 2019–2021 model around 3% rainbow — and the NV era has no separate
disclosure at all. Treat them as era-specific hints and label whatever you serve as authored, never
recovered. The Fandom wiki's per-year summon calendar carries real banner names, dates, featured units and
artwork back to 2016 — but its titles are not the shipped titles, so serving them means adding them to
the text table, and it is a community source rather than an official one.

**Schedule.** The campaign window lives on the schedule row, and no banner-schedule table shipped at all.
The only shipped time signals are an evergreen window in the select tables and a few banner names with
dates in them, so limited-time banners mean authoring the windows (or importing the community calendar's
dates).

## What is not established

- **Which reply should carry the banner groups.** The client accepts them on any reply that reaches it;
  our runs use the entry and info replies. Treat the choice as yours to make and settle it with a run.
- **The full value sets** for the type, appearance, display, execution-type and banner-type fields. Real
  banner rows were never shipped, so only the values the client tests (the tab classifier above) are
  recovered.
- **The rate field's integer scale** in a pool row. The field is a plain integer; its unit is not
  recovered. It does not matter while the server rolls — it matters only if a rate panel is served.
- **How a limited-count banner declares its pull limit.** The accessor exists, but the field it reads is in
  dispute with the recovered layout, so a limited banner can be listed but its limit is not authorable
  with confidence.
- **The step-up display's base.** The confirm screen renders the step number plus two, and whether the
  server should send 0- or 1-based numbers is unresolved. The state mechanism itself — a per-banner step
  number served in its own group — is recovered.
- **The rest of the per-player state.** Rows for box, panel, select and discount state exist as classes but
  are not mapped. A plain banner and a step-up need less state than the variants do.
- **Several pull-reply fields the client reads** are not modelled: a new-unit badge list, guaranteed
  slots, the NV result and the vision-card effect pattern.
- **The original server's validation.** Nothing in the client enforces the pull: it sends the request and
  renders whatever comes back. Whether the original server audited anything cannot be known from the
  client alone — the honest assumption is that the client trusts the reply.

## Where to look next

`FFBE_SERVER_CONTRACT.md` holds the endpoints and the `sg` variants; `validated_endpoints.md` walks the
pull sequence as driven against a live client; `response_tag_map.json` maps the response classes named
above to the tags the client dispatches on. The payload fields behind those tags are the part left to you —
the method for recovering them is in the contract's last section.
