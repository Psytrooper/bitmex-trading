import argparse
import configparser
import sys
import time
import threading
import traceback2
import signal
import queue


from src.MySqlDataStore import get_mysql_connection
from src.bitmex_trade_scraper import BitmexTradeScraper
from src.bitmex_trading_bot import BitmexTradingBot


def is_delta_ok(delta, use_absolute):
    if use_absolute and delta < 0.0:
        print(f'for absolute differences, the value of delta:{delta} should be >= 0')
        return False
    if not use_absolute and (delta < 0.0 or delta > 1.0):
        print(f'for relative differences, the value of delta:{delta} should be in the interval [0,1]')
        return False
    return True


def is_configuration_ok(config):
    # Vet long parameters.
    use_absolute = config.getboolean('bitmex.tradebot.decision.long.stop.delta.absolute')
    delta = config.getfloat('bitmex.tradebot.decision.long.stop.delta', 0)
    if not is_delta_ok(delta, use_absolute):
        return False

    # Vet short parameters.
    use_absolute = config.getboolean('bitmex.tradebot.decision.short.stop.delta.absolute')
    delta = config.getfloat('bitmex.tradebot.decision.short.stop.delta', 400)
    if not is_delta_ok(delta, use_absolute):
        return False

    return True


def init_mysql_connection(defaults):
    try:
        print("Connecting to MySql....")
        return get_mysql_connection(defaults)
    except Exception as ex:
        print(ex)
        print(traceback2.format_exc())
        sys.exit(1)


def interrupt_handler(sif, frame):
    tradeSignal.put(None)
    time.sleep(1)
    bitmex_scraper.gracefully_finish()
    # bitmex_bot.gracefully_finish()
    connection.close()
    sys.exit(0)


# Deal with command-line options.
args_parser = argparse.ArgumentParser()
args_parser.add_argument('--instance', type=int, default=0, choices=range(0, 6), help='non-negative integer that specifies production instance of trading bot')
args = args_parser.parse_args()

# Read configuration.
_config = configparser.ConfigParser()
_config.read(f'config/bitmex_bot_{args.instance}.ini')
_defaults = _config['TEST']

if not is_configuration_ok(_defaults):
    print('Bad configuration. Check your INI configuration setup.')
    sys.exit(1)

tradeSignal = queue.Queue(2)
connection = init_mysql_connection(_defaults)

bitmex_scraper = BitmexTradeScraper(_defaults, tradeSignal, connection)
# bitmex_bot = BitmexTradingBot(_defaults, tradeSignal, connection)

signal.signal(signal.SIGINT, interrupt_handler)
signal.signal(signal.SIGTERM, interrupt_handler)
signal.signal(signal.SIGHUP, interrupt_handler)

try:
    producer = threading.Thread(target=bitmex_scraper.start_scrapping)
    producer.start()
    # consumer = threading.Thread(target=bitmex_bot.start_trading)
    # consumer.start()
except KeyboardInterrupt as e:
    # tradeSignal.put(None)
    bitmex_scraper.gracefully_finish()
    # bitmex_bot.gracefully_finish()
