import numpy as np
import pymysql
import time
import threading
import os


from src.utils.logger import BitmexLogger


# Facilitate implicit casting between numyp.float types and MySQL floats.
pymysql.converters.encoders[np.float64] = pymysql.converters.escape_float
pymysql.converters.conversions = pymysql.converters.encoders.copy()
pymysql.converters.conversions.update(pymysql.converters.decoders)


def get_mysql_connection(config):
    connection = ConnectionWrapper(config)
    return connection


class ConnectionWrapper:

    def __init_logger__(self):
        self.logger = BitmexLogger(label='mysql', log_file=self.config.get('log.mysql.outfile')).logger

    def __init__(self, config):
        self.config = config
        self.retryWaitSec = 2
        self.lock = threading.RLock()
        self.__connect__(config)
        # Logging.
        self.__init_logger__()

    def __connect__(self, config):
        db_user = config.get('db.user')
        db_password = config.get('db.password')
        db_name = config.get('db.name')
        db_host = config.get('db.host')
        db_socket = config.get('db.socket', None)

        self.connection = pymysql.connect(unix_socket=db_socket, host=db_host, user=db_user, password=db_password,
                                          db=db_name, charset='latin1', cursorclass=pymysql.cursors.DictCursor)

    def cursor(self):
        try:
            self.lock.acquire(True)
            cursor = self.connection.cursor()
            if self.connection.open:
                return cursor
            else:
                # print(f'From Else: Retrying Connecting....After {retryWaitSec} Sec')
                self.__connect__(self.config)
                self.retryWaitSec = 2
                cursor = self.cursor()
                return cursor
        except Exception:
            self.retryWaitSec = self.retryWaitSec * 2
            if self.retryWaitSec > 60:
                self.logger.info('exiting system.....')
                pid = os.getpid()
                os.kill(pid, 9)
            self.logger.info(f'MySql Disconnected. Retrying Connecting....After {self.retryWaitSec} Sec')
            time.sleep(self.retryWaitSec)
            cursor = self.cursor()
            return cursor
        finally:
            self.lock.release()

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()

    def rollback(self):
        self.connection.rollback()
