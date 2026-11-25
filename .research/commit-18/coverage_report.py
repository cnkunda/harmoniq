import json
import os

p = 'coverage/coverage-final.json'
if not os.path.exists(p):
    print('missing', p, os.listdir('coverage')[:10])
    raise SystemExit
data = json.load(open(p, encoding='utf-8'))
targets = [
    'src/config.ts',
    'src/audio/GlobalAudioManager.ts',
    'src/audio/recordSession.native.ts',
    'src/audio/recordSession.web.ts',
    'src/db/client.native.ts',
    'src/db/client.web.ts',
]
for key, entry in data.items():
    norm = key.replace(os.sep, '/')
    for t in targets:
        if norm.endswith(t):
            s = entry['s']
            sm = entry['statementMap']
            stmt_hit = sum(1 for v in s.values() if v > 0)
            lines_hit = set()
            lines_total = set()
            for sid, ct in s.items():
                ln = sm[sid]['start']['line']
                lines_total.add(ln)
                if ct > 0:
                    lines_hit.add(ln)
            b = entry.get('b', {})
            b_hit = sum(1 for arr in b.values() for c in arr if c > 0)
            b_tot = sum(len(arr) for arr in b.values())
            f = entry.get('f', {})
            f_hit = sum(1 for v in f.values() if v > 0)
            print(
                f"{t}: stmts {stmt_hit}/{len(s)} = {100 * stmt_hit / len(s):.2f}%"
                f" | lines {len(lines_hit)}/{len(lines_total)} = {100 * len(lines_hit) / max(1, len(lines_total)):.2f}%"
                f" | branches {b_hit}/{b_tot} = {100 * b_hit / max(1, b_tot):.2f}%"
                f" | funcs {f_hit}/{len(f)}"
            )
