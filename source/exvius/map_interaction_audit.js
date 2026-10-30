// Read-only diagnostics for the pinned Global v9 map interaction path.
export function installMapInteractionAudit(module, note, retained) {
  const stacks = new Map();
  let touches = 0, loadedTreasures = 0;
  const active = id => stacks.get(id)?.at(-1);
  const typeName = object => {
    if (object.isNull()) return 'none';
    try {
      return object.readPointer().sub(Process.pointerSize).readPointer()
        .add(Process.pointerSize).readPointer().readUtf8String();
    } catch (_) { return 'unknown'; }
  };
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN10MapManager10touchEndedEPN7cocos2d5TouchE'), {
    onEnter() { this.sequence = ++touches; note('MAP_TOUCH_BEGIN sequence=' + this.sequence); },
    onLeave() { note('MAP_TOUCH_END sequence=' + this.sequence); }
  }));
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN12MapEventData11touchActionEPN7cocos2d5TouchE'), {
    onEnter(args) {
      this.thread = this.threadId;
      const stack = stacks.get(this.thread) || [];
      this.row = {sequence: touches, event: args[0], callback: 'none'};
      try { this.row.callback = typeName(args[0].add(0x180).readPointer()); }
      catch (_) { this.row.callback = 'unreadable'; }
      stack.push(this.row);
      stacks.set(this.thread, stack);
    },
    onLeave() {
      try {
        const row = this.row;
        row.hit = row.event.add(0x1ad).readU8();
        row.event = row.event.toString();
        if (row.sequence <= 100) note('MAP_TOUCH_TARGET ' + JSON.stringify(row));
      } catch (error) { note('MAP_TOUCH_AUDIT_ERROR ' + error); }
      stacks.get(this.thread)?.pop();
    }
  }));
  for (const [symbol, key, count] of [
    ['_ZN12MapEventData12getTouchRectEv', 'rect', 4],
    ['_ZNK7cocos2d5Touch17getLocationInViewEv', 'touch', 2]
  ]) retained.push(Interceptor.attach(module.getExportByName(symbol), {
    onEnter() { this.row = active(this.threadId); this.output = this.context.x8; },
    onLeave() {
      if (!this.row) return;
      try { this.row[key] = Array.from({length: count}, (_, i) => this.output.add(i * 4).readFloat()); }
      catch (error) { note('MAP_TOUCH_AUDIT_ERROR ' + error); }
    }
  }));
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN24FieldTreasureMstResponse9readParamEiiPKcS1_b'), {
    onEnter() { note('MAP_TREASURE_ROW_RECEIVED count=' + ++loadedTreasures); }
  }));
  note('MAP_INTERACTION_AUDIT_READY');
}
