import json, math, os, random, re, subprocess, time
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


def _non_wakeup_first(c):
    c.sort(key=lambda n: "wakeup" in n.lower() and "non-wakeup" not in n.lower())
    return c


def find_accel(names):
    env = os.getenv("ACCEL_SENSOR")
    if env:
        return env
    bad = ("linear", "uncali", "gravity", "temp")
    c = [n for n in names
         if ("accelerometer" in n.lower() or re.search(r"(^|[^a-z])acc([^a-z]|$)", n.lower()))
         and not any(b in n.lower() for b in bad)]
    if not c:
        raise RuntimeError("Sensor accelerometer tidak ditemukan. Isi ACCEL_SENSOR di .env")
    return _non_wakeup_first(c)[0]


def find_light(names):
    env = os.getenv("LIGHT_SENSOR")
    if env:
        return env
    bad = ("uncali", "factory", "flicker", "smd", "raw", "str", "back", "algo")
    c = [n for n in names
         if ("light" in n.lower() or re.search(r"(^|[^a-z])als([^a-z]|$)", n.lower()))
         and not any(b in n.lower() for b in bad)]
    if not c:
        raise RuntimeError("Sensor cahaya tidak ditemukan. Isi LIGHT_SENSOR di .env")
    return _non_wakeup_first(c)[0]


def _values(d, name):
    if name not in d or not d[name].get("values"):
        raise RuntimeError(f"Sensor '{name}' tidak mengirim data. Coba ganti sensor di .env")
    return d[name]["values"]


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
                self.n_acc = find_accel(names)
            if light:
                self.n_lux = find_light(names)
            print(f"[SENSOR] accel={self.n_acc} light={self.n_lux}")

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
        try:
            d = json.loads(out)
        except ValueError:
            raise RuntimeError("termux-sensor tidak mengirim data. Cek Termux:API dan izin")
        r = {"accel": None, "lux": None}
        if self.n_acc:
            r["accel"] = tuple(float(v) for v in _values(d, self.n_acc)[:3])
        if self.n_lux:
            r["lux"] = float(_values(d, self.n_lux)[0])
        return r


def motion_rms(accels):  # processing A: RMS getaran
    errs = [math.sqrt(x * x + y * y + z * z) - GRAVITY for x, y, z in accels]
    return math.sqrt(sum(e * e for e in errs) / len(errs))


def lux_median(values):  # processing B: filter median cahaya
    return median(values)
