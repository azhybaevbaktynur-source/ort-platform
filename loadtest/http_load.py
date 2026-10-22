"""Async HTTP load generator (Locust could not be installed in this environment; same closed-loop user model).

Env: LT_STATE (seed state json), LT_BASE (default http://127.0.0.1:8000), run from <worktree>/backend so that
app.core.security can mint tokens with the same SECRET_KEY as the server (no .env is involved).
Usage: python http_load.py <scenario> <users> <duration_s>
Scenarios: login | join | mix   (mix = /me/lms, course list, question page, media, think time 1-3 s)
"""
import asyncio, json, os, random, sys, time
sys.path.insert(0, os.getcwd())
import httpx
from app.core.security import create_access_token

ST = json.load(open(os.environ["LT_STATE"]))
BASE = os.environ.get("LT_BASE", "http://127.0.0.1:8000") + "/api/v1"
scn, USERS, DUR = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
stats = {}  # name -> [latencies], errors


def rec(name, dt, ok):
    s = stats.setdefault(name, {"lat": [], "err": 0, "codes": {}})
    s["lat"].append(dt)
    if not ok:
        s["err"] += 1


async def call(cl, name, method, url, **kw):
    t = time.perf_counter()
    try:
        r = await cl.request(method, url, **kw)
        dt = time.perf_counter() - t
        ok = r.status_code < 400 or (name == "media_304" and r.status_code == 304)
        rec(name, dt, ok)
        if not ok:
            c = stats[name]["codes"]; c[r.status_code] = c.get(r.status_code, 0) + 1
        return r
    except Exception as e:
        rec(name, time.perf_counter() - t, False)
        c = stats[name]["codes"]; k = type(e).__name__; c[k] = c.get(k, 0) + 1


async def user(i, stu, t_end, start_delay):
    await asyncio.sleep(start_delay)
    teacher = scn == "mix" and i % 20 == 0  # 5 % of users are the teacher token (question list page)
    hdr = {"Authorization": f"Bearer {create_access_token({'sub': ST['teacher_id'] if teacher else stu['id']})}"}
    async with httpx.AsyncClient(base_url=BASE, headers=hdr, timeout=60,
                                 limits=httpx.Limits(max_connections=4)) as cl:
        if scn == "login":
            while time.time() < t_end:
                r = await call(cl, "login", "POST", "/auth/login", json={"email": stu["email"], "password": ST["password"]}, headers={})
                await asyncio.sleep(0.5)
            return
        if scn == "join":
            await call(cl, "join", "POST", "/courses/join", json={"code": ST["join_code"]})
            await call(cl, "me_lms", "GET", "/me/lms")
            return
        # mix
        cid, bid = ST["course_id"], ST["bank_id"]
        if not teacher:
            await call(cl, "join", "POST", "/courses/join", json={"code": ST["join_code"]})
        await call(cl, "me_lms", "GET", "/me/lms")
        while time.time() < t_end:
            if teacher:
                await call(cl, "question_list", "GET", f"/courses/{cid}/banks/{bid}/questions?limit=25")
                await asyncio.sleep(random.uniform(1, 3))
                continue
            await call(cl, "course_list", "GET", "/courses?limit=25")
            await call(cl, "course_get", "GET", f"/courses/{cid}")
            await call(cl, "me_lms", "GET", "/me/lms")
            await asyncio.sleep(random.uniform(1, 3))
            await call(cl, "media", "GET", f"/media/{random.choice(ST['media_shas'])}.webp", headers={})


async def main():
    t0 = time.time()
    t_end = t0 + DUR
    ramp = float(os.environ.get("LT_RAMP", min(20.0, DUR / 3)))
    studs = ST["students"]
    tasks = [asyncio.create_task(user(i, studs[i % len(studs)], t_end, ramp * i / USERS)) for i in range(USERS)]
    await asyncio.gather(*tasks)
    wall = time.time() - t0
    out = {"scenario": scn, "users": USERS, "wall_s": round(wall, 1), "endpoints": {}}
    tot = tot_err = 0
    for n, s in stats.items():
        l = sorted(s["lat"]); k = len(l)
        out["endpoints"][n] = {"n": k, "rps": round(k / wall, 1), "p50_ms": round(l[k // 2] * 1000, 1),
                               "p95_ms": round(l[int(k * .95)] * 1000, 1), "p99_ms": round(l[int(k * .99)] * 1000, 1),
                               "err_pct": round(100 * s["err"] / k, 2), "codes": s["codes"]}
        tot += k; tot_err += s["err"]
    out["total_rps"] = round(tot / wall, 1); out["total_err_pct"] = round(100 * tot_err / max(tot, 1), 2)
    print(json.dumps(out, indent=1))
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
              f"http_{scn}_{USERS}.json"), "w"), indent=1)

asyncio.run(main())
