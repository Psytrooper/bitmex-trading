from time import strftime, gmtime
import time
import datetime
import requests, json
import cryptography
from bitmex_websocket import BitMEXWebsocket
import pymysql

db_user = 'dbmasteruser'
db_password = 'replace'
db='bitmex'
db_host='localhost'
symbol="XBTUSD"

movement_start_price_delta = 25
movement_end_price_delta = 5
movement_time_delta = 5
is_in_movement = False
movement_id = 0

api_key = 'replace'
api_secret='replace'

ws = BitMEXWebsocket(endpoint='https://testnet.bitmex.com/api/v1', symbol=symbol, api_key=None, api_secret=None)
print("Instrument: %s" % ws.get_instrument())

connection = pymysql.connect(unix_socket='/opt/local/var/run/mysql57/mysqld.sock',
                             host=db_host,
                             user=db_user,
                             password=db_password,
                             db=db,
                             charset='latin1',
                             cursorclass=pymysql.cursors.DictCursor)

current_minute = time.gmtime()[4]

while current_minute != 0:

    ticker = ws.get_ticker()
    print(strftime("%Y-%m-%d %H:%M:%S", gmtime()),':::', ticker)

    l = ticker['last']
    b = ticker['buy']
    s = ticker['sell']
    m = ticker['mid']

    cnt = 0
    with connection.cursor() as cursor:
        # Create a new record                                                                                                                  
        # sql = "INSERT INTO `ticker` (`symbol`, `dt`, `l`, `b`, `s`, `m`) VALUES (%s, now(), %s, %s, %s, %s)"
        # cursor.execute(sql, (symbol,l,b,s,m))

        # connection is not autocommit by default. So you must commit to save your changes.                                                                                                                        
        # connection.commit()
        cnt += 1

    time.sleep(3)

    current_minute = time.gmtime()[4]
