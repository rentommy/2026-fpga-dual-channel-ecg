from pathlib import Path
root=Path(__file__).resolve().parent
s=(root.parent/'run_scope_standalone.py').read_text(encoding='utf-8')
assert s.count('0x45434732')==1
s=s.replace('0x45434732','0x45434734')
s=s.replace("choices=['demo','adc-test','adc']", "choices=['demo','adc-test','adc','replay']")
s=s.replace("    args = parser.parse_args()", "    parser.add_argument('--recording', type=Path, help='Two-column int32 raw replay file')\n    args = parser.parse_args()\n    replay = np.load(args.recording,allow_pickle=False) if args.source=='replay' else None\n    if replay is not None and (replay.ndim!=2 or replay.shape[1]!=2 or len(replay)<3000):\n        parser.error('Replay needs at least 3000 samples and two columns')\n    replay_pos=0")
s=s.replace("if args.source!='demo':", "if args.source in ['adc','adc-test']:")
s=s.replace("1 if args.source=='demo' else", "1 if args.source in ['demo','replay'] else")
s=s.replace("            if args.source=='demo':\n", "            if args.source=='replay':\n                if now < next_demo:\n                    time.sleep(min(.002,next_demo-now));continue\n                if replay_pos>=len(replay):\n                    replay_pos=0;warmup_remaining=543;filter_reset=True;history.fill(0)\n                    io.feed_replay(None,True)\n                raw=replay[replay_pos:replay_pos+5].copy();replay_pos+=len(raw)\n                io.feed_replay(raw,False)\n                next_demo=max(next_demo+len(raw)/500,now+.001)\n            elif args.source=='demo':\n")
(root/'scope_runtime.py').write_text(s,encoding='utf-8')
