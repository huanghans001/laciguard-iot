import argparse, json, subprocess, time
from shared import *

ap = argparse.ArgumentParser()
ap.add_argument("--source", choices=["auto", "simulator"], default="auto")
sim = ap.parse_args().source == "simulator"

sensors = PhoneSensors(accel=True, light=True, simulator=sim)
c = make_client("edge1")


def on_connect(cl, u, f, rc, p=None):
    cl.subscribe(topic("cmd"), qos=1)


def on_message(cl, u, msg):
    cmd = json.loads(msg.payload).get("cmd")
    if cmd == "FIND":  # perintah dari HP B: bunyikan HP A
        print("[EDGE1] FIND diterima, bergetar")
        if not sim:
            subprocess.run(["termux-vibrate", "-d", "1500"])
        cl.publish(topic("edge/edge1/ack"),
                   json.dumps({"ack": "FIND", "at_ms": int(time.time() * 1000)}),
                   qos=1)


c.on_connect, c.on_message = on_connect, on_message
c.connect(HOST, PORT, 60)
c.loop_start()
print("[EDGE1] Publish ke:", topic("edge/edge1/telemetry"))

seq = 0
while True:
    win = [sensors.read() for _ in range(WINDOW)]
    seq += 1
    payload = {"device_id": "edge1", "sequence": seq,
               "motion_rms": round(motion_rms([w["accel"] for w in win]), 3),
               "lux": round(lux_median([w["lux"] for w in win]), 1),
               "sent_at_ms": int(time.time() * 1000)}
    c.publish(topic("edge/edge1/telemetry"), json.dumps(payload), qos=1)
    print("[EDGE1]", payload)
