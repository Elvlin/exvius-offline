const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
const source = fs.readFileSync(require('node:path').join(__dirname, 'android_display.js'), 'utf8');
const { chooseResolution, anchorLayout, collapseCampaignBanner, clampMapScroll, cutsceneScrollFloor, clampAnimationFrame } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

assert.equal(clampAnimationFrame(60, 60), 59);
assert.equal(clampAnimationFrame(59, 60), 59);
assert.equal(clampAnimationFrame(0, 60), 0);
assert.equal(clampAnimationFrame(1, 1), 0);
assert.equal(clampAnimationFrame(-1, 60), -1);
assert.equal(clampAnimationFrame(0, 0), 0);

// Old phones, modern tall phones, tablets, landscape and resized windows.
for (const [width, height] of [[640, 960], [720, 1280], [1080, 2400],
                              [1080, 2267], [1536, 2048], [2400, 1080], [800, 800]]) {
  const result = chooseResolution(640, 1136, width, height);
  assert.ok(result);
  assert.ok(result.width >= 640 && result.height >= 1136, 'Preserve all original content');
  assert.ok(Math.abs(result.width * result.scale - width) <= result.scale, 'Fill screen width');
  assert.ok(Math.abs(result.height * result.scale - height) <= result.scale, 'Fill screen height');
  assert.ok([3, 4].includes(result.policy), 'Never stretch or crop');
}
assert.equal(chooseResolution(640, 1136, 1080, 2400).policy, 4);
assert.equal(chooseResolution(640, 1136, 1536, 2048).policy, 3);
for (const invalid of [0, -1, NaN, Infinity])
  assert.equal(chooseResolution(640, 1136, invalid, 2400), null);
console.log('Adaptive display: 7 screen shapes and invalid sizes passed.');
const reference = {width: 640, height: 1136}, canvas = {width: 640, height: 1358};
const button = {x: 20, y: 995, width: 100, height: 100};
assert.deepEqual(anchorLayout('footer_home', button, reference, canvas),
  {x: 20, y: 1244, width: 100, height: 100});
assert.equal(anchorLayout('footer_bg', {x:0,y:1051,width:656,height:58}, reference, canvas).y + 58, canvas.height);
assert.equal(anchorLayout('footer_section_line', {x:640,y:1100,width:640,height:34}, reference, canvas).y, canvas.height);
assert.equal(anchorLayout('home_bottom_parts_offset', {x:0,y:705,width:640,height:268}, reference, canvas).y, 954);
assert.equal(anchorLayout('home_bg_clip_area', {x:1,y:-1,width:640,height:718}, reference, canvas).height, 967);
const background = anchorLayout('unit_bg', {x:0,y:-172,width:640,height:1000}, reference, canvas);
assert.ok(Math.abs(background.width / background.height - 0.64) < 0.00001);
assert.equal(background.height, 1000);
const child = {x:331,y:146,width:166,height:112};
assert.deepEqual(anchorLayout('home_bottom_parts_main_menu_world_button', child, reference, canvas), child);
const header = {x:0,y:108,width:640,height:90};
assert.deepEqual(anchorLayout('home_top_parts_offset', header, reference, canvas), header);
assert.equal(anchorLayout('gacha_scroll_area', {x:0,y:300,width:640,height:700}, reference, canvas).height, 922);
assert.deepEqual(anchorLayout('gacha_item_list', {x:0,y:300,width:640,height:100}, reference, canvas), {x:0,y:300,width:640,height:100});
for (const [name, box] of [
  ['departure_item_scrl_area', {x:330,y:625,width:300,height:245}],
  ['result_scroll_area', {x:20,y:280,width:600,height:580}]
]) assert.deepEqual(anchorLayout(name, box, reference, canvas), box,
  'Embedded lists must not cover Depart or Next');
// A lower-page list must expose the extra rows, not just grow its invisible
// scroll bounds. Both crest tabs use independently named clipping rectangles.
for (const family of ['wkreward', 'mthreward']) {
  for (const name of ['clip_area_', 'scrl_area_', 'scrl_bar_']) {
    const box = {x:0,y:600,width:name === 'scrl_bar_' ? 8 : 620,height:390};
    const fitted = anchorLayout(name + family, box, reference, canvas);
    assert.equal(fitted.y, box.y);
    assert.equal(fitted.height, box.height + canvas.height - reference.height);
  }
}
const note = {x:0,y:990,width:640,height:36};
assert.equal(anchorLayout('er_disclaimer_bg', note, reference, canvas).y,
  note.y + canvas.height - reference.height);
assert.equal(anchorLayout('er_disclaimer_txt', note, reference, canvas).y,
  note.y + canvas.height - reference.height);
for (const name of ['party_register_list_slot_list_frame_bottom',
                    'party_register_list_caution_label', 'party_register_list_bottom_frame'])
  assert.equal(anchorLayout(name, note, reference, canvas).y, note.y + canvas.height - reference.height);
assert.deepEqual(anchorLayout('popup_scroll_area', {x:0,y:600,width:540,height:390}, reference, canvas),
  {x:0,y:600,width:540,height:390});
const emptyBanner = {y:240,height:160};
const crestClip = {x:0,y:600,width:620,height:390};
const crestExpanded = anchorLayout('clip_area_wkreward', crestClip, reference, canvas);
const crestCollapsed = collapseCampaignBanner('clip_area_wkreward', crestExpanded, crestClip, emptyBanner, reference);
assert.equal(crestCollapsed.y, crestClip.y - emptyBanner.height);
assert.equal(crestCollapsed.y + crestCollapsed.height, crestExpanded.y + crestExpanded.height);
assert.deepEqual(collapseCampaignBanner('footer_home', button, button, emptyBanner, reference), button);
assert.deepEqual(collapseCampaignBanner('emblem_header', header, header, emptyBanner, reference), header);
assert.deepEqual(collapseCampaignBanner('clip_area_wkreward', crestExpanded, crestClip, null, reference), crestExpanded);
// Actual Global 9.0 layout_emblemMain_640x1136.csv coordinates.
const originalCrestBanner = {y:250,height:160};
for (const [family,y,h] of [['wkreward',462,449],['mthreward',521,388]]) {
  for (const prefix of ['clip_area_', 'scrl_area_', 'scrl_bar_']) {
    const name = prefix + family, box = {x:0,y,width:640,height:h};
    const fitted = collapseCampaignBanner(name, anchorLayout(name, box, reference, canvas),
      box, originalCrestBanner, reference);
    assert.equal(fitted.y, y - 160);
    assert.equal(fitted.y + fitted.height, y + h + 222);
  }
}
const crestTab = {x:7,y:404,width:306,height:64};
assert.equal(collapseCampaignBanner('emblemtab_wk_on', crestTab, crestTab,
  originalCrestBanner, reference).y, 244);
assert.deepEqual(anchorLayout('clip_area_wkreward_frame', {x:0,y:467,width:624,height:154},
  reference, canvas), {x:0,y:467,width:624,height:154});
console.log('Bottom anchors, touch geometry and proportional background cover passed.');
for (const [frameWidth, frameHeight] of [[640,960],[720,1280],[1080,2400],[1440,3200],[1536,2048]]) {
  const actual = chooseResolution(640, 1136, frameWidth, frameHeight);
  const footer = anchorLayout('footer_home', button, reference, actual);
  assert.equal(actual.height - (footer.y + footer.height), 1109 - (button.y + button.height));
  assert.equal(footer.width, button.width);
  assert.equal(footer.height, button.height);
}
console.log('Bottom menu seated on the screen edge with constant button proportions on all five device shapes.');
assert.deepEqual(clampMapScroll(-20, -40, 14, 14, 640, 1358), {x:0,y:0});
assert.deepEqual(clampMapScroll(9999, 9999, 32, 40, 640, 1358), {x:1216,y:962});
assert.equal(clampMapScroll(0, 0, 0, 40, 640, 1358), null);
assert.equal(cutsceneScrollFloor('Ver36_111010100.cpk', 65, 1136, 1358), 1794);
assert.equal(cutsceneScrollFloor('111010100', 65, 1136, 1136), 0);
assert.equal(cutsceneScrollFloor('111010100', 61, 1136, 1358), 0);
assert.equal(cutsceneScrollFloor('211010100', 65, 1136, 1358), 0);
assert.equal(cutsceneScrollFloor('111010100', 65, NaN, 1358), 0);
console.log('Small-map scroll bounds and the original airship shot upper edge passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
