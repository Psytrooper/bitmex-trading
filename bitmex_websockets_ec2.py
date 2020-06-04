import asyncio
import configparser
import iso8601
import json
import sys
import threading
import traceback2
import websockets
from src.utils.MySqlDataStore import get_mysql_connection

from src.utils.logger import BitmexLogger

# Read configuration.
config = configparser.ConfigParser()
config.read('config/bitmex_bot.ini')
defaults = config['DEFAULT']

# True if we are using testnet, False otherwise.
use_test_env = defaults.getboolean('bitmex.api.test')

# Logging.
logger = BitmexLogger(label="bitmex-websockets-ec2-logger", log_file=defaults.get('log.quotes.outfile')).logger


# Get connection to MySQL.
logger.info('Opening connection with MySQL')
try:
    connection = get_mysql_connection(defaults)
except Exception:
    logger.error(traceback2.format_exc())
    sys.exit(1)


def insert_ticker(symbol, trade_px, bid_px, ask_px, quote_dt, trade_dt):
    # Midpoint of bid/sell prices.
    mid_px = (bid_px + ask_px) / 2.0

    # Convert ISO 8601 times for quote/trade to POSIX timestamps (ie, milliseconds since the epoch).
    # Eg: 1577656569.149 (where 149 is fractional second in units of milliseconds)
    quote_ms = iso8601.parse_date(quote_dt).timestamp()
    trade_ms = iso8601.parse_date(quote_dt).timestamp()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO `ticker` (`symbol`, `l`, `b`, `s`, `m`, `trade_dt`, `quote_dt`) VALUES (%s, %s, %s, %s, %s, FROM_UNIXTIME(%s), FROM_UNIXTIME(%s))"
            logger.info(f'quote_dt:{quote_dt} trade_dt:{trade_dt} symbol:{symbol} trade_px:{trade_px} bid_px:{bid_px} ask_px:{ask_px} mid_px:{mid_px}')
            cursor.execute(sql, (symbol, trade_px, bid_px, ask_px, mid_px, trade_ms, quote_ms))
            connection.commit()
    except Exception:
        logger.error(traceback2.format_exc())


def setup_timer_for_purge(delay):
    t = threading.Timer(delay, purge_stale_tickers)
    try:
        t.start()
    except Exception:
        t.cancel()


# Every hour, remove tickers that are older than 1 day.
def purge_stale_tickers():
    setup_timer_for_purge(3600)
    try:
        with connection.cursor() as cursor:
            sql = "delete from ticker where trade_dt < now() - interval 1 day"
            cursor.execute(sql)
            connection.commit()
    except Exception:
        logger.error(traceback2.format_exc())


async def capture_data():
    # Periodically purge stale tickers.
    setup_timer_for_purge(3600)

    rcvd_trade_partial = False
    rcvd_quote_partial = False

    # Timestamps for when quote / trade record created on server.
    quote_dt = None
    trade_dt = None

    subdomain = "testnet" if use_test_env else "www"
    uri = "wss://{}.bitmex.com/realtime?subscribe=quote:XBTUSD,trade:XBTUSD".format(subdomain)
    async with websockets.connect(uri) as websocket:
        while True:
            # Reconnect if not open.
            if not websocket.open:
                websocket = await websockets.connect(uri)

            data = await websocket.recv()
            data = json.loads(data)

            # Skip over "info" and "success" acknowledgments received after subscription.
            if 'table' not in data or 'action' not in data:
                continue

            if data['table'] == 'quote' and data['action'] == 'partial':
                rcvd_quote_partial = True
                continue

            if data['table'] == 'trade' and data['action'] == 'partial':
                rcvd_trade_partial = True
                continue

            # Subscription specs say that we should skip over any messages before both partials for trade/quote are received.
            if not rcvd_trade_partial or not rcvd_quote_partial:
                continue

            # Sanity-check presence of "data" attribute, which houses the trade/quote payload.
            if 'data' not in data or len(data['data']) <= 0:
                continue

            # Use last quote/trade in insert. Below we save its timestamp.
            last_insert = data['data'][-1]

            # Sanity-check presence of the right symbol we are subscribed to.
            if 'symbol' not in last_insert or last_insert['symbol'] != 'XBTUSD':
                continue

            # Sanity-check presence of timestamp.
            if 'timestamp' not in last_insert:
                continue

            if data['table'] == 'quote' and data['action'] == 'insert' and 'bidPrice' in last_insert and 'askPrice' in last_insert:
                quote_dt = last_insert['timestamp']
                bid_px = last_insert['bidPrice']
                ask_px = last_insert['askPrice']

            if data['table'] == 'trade' and data['action'] == 'insert' and 'price' in last_insert:
                trade_dt = last_insert['timestamp']
                trade_px = last_insert['price']

            if quote_dt is not None and trade_dt is not None:
                insert_ticker(last_insert['symbol'], trade_px, bid_px, ask_px, quote_dt, trade_dt)
                quote_dt = None
                trade_dt = None


async def gracefully_finish(loop):
    # Gracefully shut down database connection on interrupt.
    if connection is not None:
        connection.close()

    # Gracefully terminate ongoing tasks.
    tasks = [task for task in asyncio.Task.all_tasks()]
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("Task cancelled: %s" % task)   
    loop.stop()


event_loop = asyncio.get_event_loop()
try:
    event_loop.run_until_complete(capture_data())
except Exception:
    logger.error(traceback2.format_exc())
finally:
    event_loop.run_until_complete(gracefully_finish(event_loop))
    event_loop.close()
