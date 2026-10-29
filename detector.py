import csv, json, time
from shared import *

OPEN_RATIO, MIN_ROOM_LUX, MOVE_RMS = 0.3, 5.0, 0.5
NEED_HITS, STALE_S, COOLDOWN_S = 2, 6, 10

state = {"edge1": None, "edge2": None, "armed": True, "hits": 0, "last_alert": 0}
c = make_client("detector")
log = open("log.csv", "a", newline="")
w = csv.writer(log)


def decide():
    a, b, now = state["edge1"], state["edge2"], time.time()
    if not state["armed"]:
        return "DISARMED", "sistem dimatikan pemilik"
    if not a or not b or now - a["rx"] > STALE_S or now - b["rx"] > STALE_S:
        return "WAITING", "menunggu data edge1 dan edge2"
    ratio = a["lux"] / max(b["lux"], 1.0)
    opened = b["lux"] >= MIN_ROOM_LUX and ratio >= OPEN_RATIO
    moving = a["motion_rms"] >= MOVE_RMS
    why = f'rasio={ratio:.2f}, rms={a["motion_rms"]:.2f}'
    if opened and moving:
        return "ALERT", "laci dibuka dan digerakkan, " + why
    if opened:
        return "WARNING", "laci terbuka, " + why
    if moving:
        return "NUDGE", "laci bergerak/ditabrak, " + why
    return "NORMAL", why


def on_connect(cl, u, f, rc, p=None):
    cl.subscribe(topic("edge/+/telemetry"), qos=1)
    cl.subscribe(topic("cmd"), qos=1)


def on_message(cl, u, msg):
    d = json.loads(msg.payload)
    if msg.topic.endswith("/cmd"):
        if d.get("cmd") in ("ARM", "DISARM"):
            state["armed"] = d["cmd"] == "ARM"
            print("[CMD]", d["cmd"])
        return
    d["rx"] = time.time()
    state[d["device_id"]] = d
    if d["device_id"] != "edge1":  # evaluasi tiap window edge1
        return
    status, reason = decide()
    state["hits"] = state["hits"] + 1 if status == "ALERT" else 0
    if state["hits"] >= NEED_HITS:
        final = "ALERT"
    else:
        final = "WARNING" if status == "ALERT" else status
    cl.publish(topic("status"), json.dumps({"status": final, "reason": reason}),
               qos=1, retain=True)
    w.writerow([int(time.time() * 1000), d["motion_rms"], d["lux"],
                state["edge2"]["lux"] if state["edge2"] else "", final])
    log.flush()
    print(f"[DETECTOR] {final}: {reason}")
    if final in ("ALERT", "WARNING") and time.time() - state["last_alert"] > COOLDOWN_S:
        state["last_alert"] = time.time()
        cl.publish(topic("alerts"),
                   json.dumps({"status": final, "reason": reason}), qos=1)


c.on_connect, c.on_message = on_connect, on_message
c.connect(HOST, PORT, 60)
print("LaciGuard detector, PROJECT_ID =", PROJECT_ID)
c.loop_forever()
