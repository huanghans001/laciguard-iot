import json, math, os, random, subprocess, time
from statistics import median
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()
PROJECT_ID = os.getenv("PROJECT_ID", "laciguard_kelompok_XX")
HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
PORT = int(os.getenv("MQTT_PORT", "8883"))
GRAVITY, WINDOW = 9.81, 5


def topic(suffix):
    return f"laciguard/{PROJECT_ID}/{suffix}"


def make_client(name):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                    client_id=f"{name}-{random.randint(1000, 9999)}")
    c.tls_set()  # MQTT over TLS
    return c


def _find(names, key):
    c = [n for n in names if key in n.lower() and "uncalibrated" not in n.lower()]
    c.sort(key=lambda n: "non-wakeup" not in n.lower())
    if not c:
        raise RuntimeError(f"Sensor '{key}' tidak ditemukan di HP ini")
    return c[0]


class PhoneSensors:
    """Baca sensor HP lewat Termux:API, atau simulasi kalau di laptop."""

    def __init__(self, accel=True, light=True, simulator=False, room=False):
        self.sim, self.room = simulator, room
        self.n_acc = self.n_lux = None
        if not simulator:
            names = json.loads(subprocess.run(
                ["termux-sensor", "-l"], capture_output=True, text=True,
                timeout=12, check=True).stdout)["sensors"]
            if accel:
                self.n_acc = _find(names, "accelerometer")
            if light:
                self.n_lux = _find(names, "light")

    def read(self):
        if self.sim:
            scen = os.getenv("SIM_SCENARIO", "still")  # still|open|nudge|breach
            moving = scen in ("nudge", "breach")
            opened = scen in ("open", "breach")
            s = 5.0 if moving else 0.02
            lux = 120 if (self.room or opened) else 2
            return {"accel": (random.gauss(0, s), random.gauss(0, s),
                              9.81 + random.gauss(0, s)),
                    "lux": max(0.0, random.gauss(lux, lux * 0.03 + 0.3))}
        wanted = [n for n in (self.n_acc, self.n_lux) if n]
        out = subprocess.run(["termux-sensor", "-s", ",".join(wanted), "-n", "1"],
                             capture_output=True, text=True, timeout=12,
                             check=True).stdout
        d = json.loads(out)
        r = {"accel": None, "lux": None}
        if self.n_acc:
            r["accel"] = tuple(float(v) for v in d[self.n_acc]["values"][:3])
        if self.n_lux:
            r["lux"] = float(d[self.n_lux]["values"][0])
        return r


def motion_rms(accels):  # processing A: RMS getaran
    errs = [math.sqrt(x * x + y * y + z * z) - GRAVITY for x, y, z in accels]
    return math.sqrt(sum(e * e for e in errs) / len(errs))


def lux_median(values):  # processing B: filter median cahaya
    return median(values)
