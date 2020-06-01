import os
import logging
from logging.handlers import RotatingFileHandler

from src.settings import WORK_DIR


class BitmexLogger:

    def __init__(self, label, log_file):
        logger = logging.getLogger(label)
        logger.setLevel(logging.DEBUG)
        # create file handler which logs even debug messages
        fh = RotatingFileHandler(os.path.join(WORK_DIR, log_file), maxBytes=5 * 1024 * 1024, backupCount=4)
        fh.setLevel(logging.INFO)
        # create console handler with a higher log level
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        # create formatter and add it to the handlers
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        fh.setFormatter(formatter)
        # add the handlers to logger
        logger.addHandler(ch)
        logger.addHandler(fh)

        self.logger = logger
