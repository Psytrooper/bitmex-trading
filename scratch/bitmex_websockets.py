import asyncio
import json
import pymysql
import websockets
from datetime import datetime

db_user = 'dbmasteruser'
db_password = 'replace'
db = 'bitmex'
db_host = 'localhost'

connection = pymysql.connect(unix_socket='/opt/local/var/run/mysql57/mysqld.sock',
                             host=db_host,
                             user=db_user,
                             password=db_password,
                             db=db,
                             charset='latin1',
                             cursorclass=pymysql.cursors.DictCursor)

def insert_ticker(symbol, trade_px, bid_px, ask_px, quote_dt, trade_dt):
    # Midpoint of bid/sell prices.
    mid_px = (bid_px + ask_px) / 2.0

    # Convert zulu times for quote/trade to POSIX timestamps (ie, milliseconds since the epoch).
    # Eg: 1577656569.149 (where 149 is fractional second in units of milliseconds)
    quote_ms = datetime.strptime(quote_dt, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
    trade_ms = datetime.strptime(quote_dt, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()

    with connection.cursor() as cursor:
        sql = "INSERT INTO `ticker` (`symbol`, `l`, `b`, `s`, `m`, `trade_dt`, `quote_dt`) VALUES (%s, %s, %s, %s, %s, FROM_UNIXTIME(%s), FROM_UNIXTIME(%s))"
        print(sql)
        cursor.execute(sql, (symbol, trade_px, bid_px, ask_px, mid_px, trade_ms, quote_ms))
        connection.commit()

async def capture_data():
    rcvd_trade_partial = False
    rcvd_quote_partial = False

    # Timestamps for when quote / trade record created on server.
    quote_dt = None
    trade_dt = None

    uri = "wss://www.bitmex.com/realtime?subscribe=quote:XBTUSD,trade:XBTUSD"
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

            if quote_dt != None and trade_dt != None:
                insert_ticker(last_insert['symbol'], trade_px, bid_px, ask_px, quote_dt, trade_dt)
                quote_dt = None
                trade_dt = None

try:
    asyncio.get_event_loop().run_until_complete(capture_data())
finally:
    # Gracefully shut down database connection on interrupt.
    if connection != None:
        connection.close()
    asyncio.get_event_loop().close()
