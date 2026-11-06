'use strict';

// Autoplay (MissionRepeatUtil) clears the client's result info once per
// sequence, then every reply's echo stays in it, so run N's MissionEnd reports
// its own exp, gil and drops plus the previous reply's. Tell the server which
// run of the sequence it is; server/ffbe_battle.repeat_run_report subtracts.
export const REPEAT_RUN_TOKEN = 'exvRepeatRun';

export function repeatRunMark(active, completedRuns) {
  return active && completedRuns >= 1 ? completedRuns + 1 : 0;
}

export function installMissionRepeat(module, note, retained) {
  const addInt = new NativeFunction(module.getExportByName('_ZN8JsonNode8addParamIiEEvPKcT_'),
    'void', ['pointer', 'pointer', 'int'], {exceptions: 'propagate'});
  const token = Memory.allocUtf8String(REPEAT_RUN_TOKEN);
  retained.push(token);
  let active = false, completed = 0, building = 0;
  const attach = (name, callbacks) => retained.push(Interceptor.attach(module.getExportByName(name), callbacks));
  attach('_ZN23MissionRepeatResultInfo13onRepeatStartEv', {
    onEnter() { active = true; completed = 0; note('MISSION_REPEAT_START'); }
  });
  for (const name of ['_ZN17MissionRepeatUtil11onRepeatEndEv', '_ZN17MissionRepeatUtil17onRepeatInterruptEv',
                      '_ZN17MissionRepeatUtil5resetEv', '_ZN17MissionRepeatUtil10onResetAppEv'])
    attach(name, { onEnter() { if (active) note('MISSION_REPEAT_STOP runs=' + completed); active = false; } });
  // One MissionResultResponse per received battle result; a retried request keeps its run number.
  const responses = new Set(['_ZN21MissionResultResponseC1Ev', '_ZN21MissionResultResponseC2Ev']
    .map(name => module.getExportByName(name).toString()));
  for (const address of responses)
    retained.push(Interceptor.attach(ptr(address), { onEnter() { if (active) completed += 1; } }));
  attach('_ZN17MissionEndRequest10createBodyEv', {
    onEnter() { building += 1; },
    onLeave() { building -= 1; }
  });
  attach('_ZN8JsonNode8addParamIiEEvPKcT_', {
    onEnter(args) {
      this.node = null;
      if (!building || args[1].readCString() !== 'S4U09svH') return;
      const run = repeatRunMark(active, completed);
      if (run) { this.node = args[0]; this.run = run; }
    },
    onLeave() {
      if (!this.node) return;
      addInt(this.node, token, this.run);
      note('MISSION_REPEAT_RUN ' + this.run);
    }
  });
}
