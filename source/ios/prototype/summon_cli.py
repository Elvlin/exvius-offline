"""Local terminal UI and JSON entry point; no network server or game client."""
import argparse
import contextlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from summon_service import SummonError, SummonService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--demo', action='store_true')
    mode.add_argument('--data', type=Path, help='Existing preserved backend data root')
    parser.add_argument('--workspace', type=Path,
                        default=Path(__file__).resolve().parents[1] / '.local/summon-demo')
    parser.add_argument('--save', type=Path, help='Separate prototype save (not an Android campaign)')
    parser.add_argument('--initial-lapis', type=int, help='Seed only a new campaign; default demo 10000, real data 0')
    parser.add_argument('--json', choices=('banners', 'state', 'details', 'summon'))
    parser.add_argument('--banner', default='9100203')
    parser.add_argument('--offer', choices=('primary', 'secondary'), default='primary')
    args = parser.parse_args()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            if args.demo:
                from demo_data import prepare
                data = prepare(args.workspace / 'data')
            else:
                data = args.data
            save = args.save or (args.workspace / ('campaign.json' if args.demo else 'preserved-campaign.json'))
            service = SummonService(data, save, demo=args.demo,
                initial_lapis=args.initial_lapis if args.initial_lapis is not None else (10000 if args.demo else 0))
        if args.json:
            with contextlib.redirect_stdout(sys.stderr):
                result = (service.banners() if args.json == 'banners' else service.state() if args.json == 'state'
                          else service.details(args.banner, args.offer) if args.json == 'details'
                          else service.summon(args.banner, args.offer))
            print(json.dumps(result, ensure_ascii=True))
            return 0
        print('FFBE local summon prototype. ' + ('PLACEHOLDER UNIT METADATA; real banner definitions/rates.' if args.demo else 'Preserved data mode.'))
        print('Commands: banners | details ID [primary/secondary] | summon ID [primary/secondary] | state | quit')
        print('Save:', save)
        while True:
            try:
                words = input('summon> ').split()
                if not words:
                    continue
                if words[0] == 'quit':
                    return 0
                if words[0] == 'banners' and len(words) == 1:
                    result = service.banners()
                elif words[0] == 'state' and len(words) == 1:
                    result = service.state()
                elif words[0] in ('details', 'summon') and 2 <= len(words) <= 3:
                    result = getattr(service, words[0])(words[1], words[2] if len(words) == 3 else 'primary')
                else:
                    print('Unknown command or missing arguments')
                    continue
                print(json.dumps(result, indent=2, ensure_ascii=True))
            except SummonError as error:
                print(error.code + ': ' + str(error))
            except (EOFError, KeyboardInterrupt):
                return 0
    except (SummonError, ValueError, OSError) as error:
        print(json.dumps({'error': getattr(error, 'code', 'configuration_error'), 'message': str(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
