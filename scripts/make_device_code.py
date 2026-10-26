"""Make a new device code:  python scripts/make_device_code.py"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from core.devices import new_code, decode_code, topic_for
code = new_code()
print("Device code:", code)
print("ntfy channel to subscribe to on the phone:", topic_for(decode_code(code)))
