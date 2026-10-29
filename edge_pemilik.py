import argparse, json, subprocess, threading, time
from shared import *

ap = argparse.ArgumentParser()
ap.add_argument("--source", choices=["auto", "simulator"], default="auto")
sim = ap.parse_args().source == "simulator"

sensors = PhoneSensors(accel=False, light=True, simulator=sim, room=True)
c = make_client("edge2")


def alarm(text):
    print("[ALARM]", text)
    if not sim:
        subprocess.run(["termux-vibrate", "-d", "1500"])
        subprocess.run(["termux-notification", "--title", "LaciGuard",
                        "--content", text])


def on_connect(cl, u, f, rc, p=None):
    cl.subscribe(topic("alerts"), qos=1)


def on_message(cl, u, msg):
    a = json.loads(msg.payload)
    alarm(f'{a["status"]}: {a["reason"]}')


c.on_connect, c.on_message = on_connect, on_message
c.connect(HOST, PORT, 60)
c.loop_start()


def keyboard():  # a = ARM, d = DISARM, f = FIND (bunyikan HP A)
    keys = {"a": "ARM", "d": "DISARM", "f": "FIND"}
    while True:
        k = input("[a]rm  [d]isarm  [f]ind > ").strip().lower()
        if k in keys:
            c.publish(topic("cmd"), json.dumps({"cmd": keys[k]}), qos=1)


threading.Thread(target=keyboard, daemon=True).start()

seq = 0
while True:
    win = [sensors.read() for _ in range(WINDOW)]
    seq += 1
    payload = {"device_id": "edge2", "sequence": seq,
               "lux": round(lux_median([w["lux"] for w in win]), 1),
               "sent_at_ms": int(time.time() * 1000)}
    c.publish(topic("edge/edge2/telemetry"), json.dumps(payload), qos=1)
