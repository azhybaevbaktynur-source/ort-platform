#!/bin/bash
# usage: run_http.sh <scenario> <users> <duration>   (env: LT_STATE; run from <worktree>/backend; server PID found by port 8000)
PID=$(lsof -ti tcp:8000 -sTCP:LISTEN | head -1)
cpu() { ps -o time= -p "$PID" | awk -F'[:.]' '{ if (NF==3) print $1*60+$2+$3/100; else print $1*3600+$2*60+$3+$4/100 }'; }
C0=$(cpu); T0=$(date +%s.%N 2>/dev/null || python3 -c 'import time;print(time.time())')
"$(dirname "$0")/../backend/venv/bin/python" "$(dirname "$0")/http_load.py" "$@" | python3 -c "
import sys,json; d=json.load(sys.stdin)
n=sum(e['n'] for e in d['endpoints'].values())
print(json.dumps({k:d[k] for k in ('scenario','users','wall_s','total_rps','total_err_pct')}))
for k,e in d['endpoints'].items(): print(' ',k,e)
open('/tmp/lt_nreq','w').write(str(n))"
C1=$(cpu)
python3 -c "
n=int(open('/tmp/lt_nreq').read()); c=$C1-$C0
print('server_cpu_s',round(c,2),'requests',n,'cpu_ms_per_req',round(1000*c/n,2),'est_render_free_rps(0.1cpu)',round(0.1/(c/n),1))"
