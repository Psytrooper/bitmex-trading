import os

__cur_dir = os.path.realpath(os.path.join(__file__, os.pardir, os.pardir))

WORK_DIR = __cur_dir
LOG_DIR = os.path.join(WORK_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

CONF_DIR = os.path.join(WORK_DIR, "config")

MODEL_DIR = os.path.join(WORK_DIR, "models")
