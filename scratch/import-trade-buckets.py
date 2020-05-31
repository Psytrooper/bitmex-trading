import argparse
import bitmex
import configparser
import csv
import iso8601
import json
import logging
import sys
import time
import traceback2

from datetime import datetime
from datetime import timezone as timezone
from MySqlDataStore import get_mysql_connection

# Deal with command-line options.
parser = argparse.ArgumentParser()
parser.add_argument("--fillgaps", help="fill gaps between end of historical trade buckets in CSV and now", action="store_true")
args = parser.parse_args()

# Read configuration.
config = configparser.ConfigParser()
config.read('config/charlie.ini')
defaults = config['DEFAULT']

# Logging.
logger = logging.getLogger("bitmex-trade-buckets-logger")
logger.setLevel(logging.INFO)

# Add file and console handlers.
logger.addHandler(logging.FileHandler(defaults.get('log.buckets.outfile')))
logger.addHandler(logging.StreamHandler())

# Open client-access to bitmex API.
bitmex_client = bitmex.bitmex(
	test=defaults.getboolean('bitmex.api.test'),
	api_key=defaults.get('bitmex.api.key'),
	api_secret=defaults.get('bitmex.api.secret')
)

# Get connection to MySQL.
logger.info('Opening connection with MySQL')
try:
	connection = get_mysql_connection(defaults)
except Exception:
	logger.error(traceback2.format_exc())
	sys.exit(1)

def insert_trade_bucket(trade_bucket):
	timestamp = trade_bucket['timestamp']
	symbol = trade_bucket['symbol']
	open_px = trade_bucket['open'] if 'open' in trade_bucket and len("{}".format(trade_bucket['open'])) > 0 else None
	high_px = trade_bucket['high'] if 'high' in trade_bucket and len("{}".format(trade_bucket['high'])) > 0 else None
	low_px = trade_bucket['low'] if 'low' in trade_bucket and len("{}".format(trade_bucket['low'])) > 0 else None
	close_px = trade_bucket['close'] if 'close' in trade_bucket and len("{}".format(trade_bucket['close'])) > 0 else None
	trades = trade_bucket['trades'] if 'trades' in trade_bucket and len("{}".format(trade_bucket['trades'])) > 0 else None
	volume = trade_bucket['volume'] if 'volume' in trade_bucket and len("{}".format(trade_bucket['volume'])) > 0 else None
	vwap = trade_bucket['vwap'] if 'vwap' in trade_bucket and len("{}".format(trade_bucket['vwap'])) > 0 else None
	lastSize = trade_bucket['lastSize'] if 'lastSize' in trade_bucket and len("{}".format(trade_bucket['lastSize'])) > 0 else None
	turnover = trade_bucket['turnover'] if 'turnover' in trade_bucket and len("{}".format(trade_bucket['turnover'])) > 0 else None
	homeNotional = trade_bucket['homeNotional'] if 'homeNotional' in trade_bucket and len("{}".format(trade_bucket['homeNotional'])) > 0 else None
	foreignNotional = trade_bucket['foreignNotional'] if 'foreignNotional' in trade_bucket and len("{}".format(trade_bucket['foreignNotional'])) > 0 else None

	timestamp_ms = timestamp.timestamp()
	try:
		with connection.cursor() as cursor:
			sql = "INSERT INTO `tradeBin1m` (`timestamp_dt`, `symbol`, `open_px`, `high_px`, `low_px`, `close_px`, `trades`, `volume`, `vwap`, `last_size`, `turnover`, `home_notional`, `foreign_notional`) VALUES (FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
			logger.info(f'timestamp_dt:{timestamp} symbol:{symbol} open_px:{open_px} high_px:{high_px} low_px:{low_px} close_px:{close_px} trades:{trades} volume:{volume} vwap:{vwap} lastSize:{lastSize} turnover:{turnover} homeNotional:{homeNotional} foreignNotional:{foreignNotional}')
			cursor.execute(sql, (timestamp_ms, symbol, open_px, high_px, low_px, close_px, trades, volume, vwap, lastSize, turnover, homeNotional, foreignNotional))
			connection.commit()
	except Exception:
		logger.error(traceback2.format_exc())

def get_max_timestamp_of_trade_buckets():
	logger.info('Reading max timestamp of existing trade buckets')
	max_timestamp_dt = None
	try:
		with connection.cursor() as cursor:
			sql = "SELECT MAX(timestamp_dt) AS max_timestamp_dt FROM tradeBin1m"
			cursor.execute(sql)
			result = cursor.fetchone()
			max_timestamp_dt = None if not result else result['max_timestamp_dt']
	except Exception:
		logger.error(traceback2.format_exc())
	return max_timestamp_dt.timestamp() if max_timestamp_dt else None

if args.fillgaps:
	now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
	logger.info(f'Fill gaps in trade buckets through {now}')

	max_timestamp_dt = get_max_timestamp_of_trade_buckets()
	if max_timestamp_dt == None:
		logger.info('Could not find max(timestamp_dt) for trade buckets. Default to now.')
		max_timestamp_dt = now

	twenty_one_days_ago = now - 21*24*60*60
	start_time = min(twenty_one_days_ago, max_timestamp_dt) + 60

	while start_time <= now:
		# start_time_str should have format "2020-01-02 18:03", understood to be in UTC timezone.
		start_time_dt = datetime.fromtimestamp(start_time, tz=timezone.utc)
		start_time_str = start_time_dt.strftime("%Y-%m-%d %H:%M")

		# Query 2 hours of trades at a time.  That's a 120 samples per API query (hence, count=120).
		trades = bitmex_client.Trade.Trade_getBucketed(symbol="XBTUSD", binSize="1m", partial=False, reverse=False, count=120, filter=json.dumps({"startTime": start_time_str})).result()
		for k in range(0, len(trades[0])):
			insert_trade_bucket(trades[0][k])
		
		# Sleep to avoid API rate limit violations.
		time.sleep(2)

		# Advance 2 hours. Update NOW in order to capture any trade buckets that may have completed since we started filling gaps.
		start_time = start_time + 2*60*60
		now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
else:
	# Read in data from CSV that Tim downloaded from Bitmex. It contains trade buckets through 2020-01-02 18:03:00 (UTC).
	with open('bitmex-btc-ohlcv-1-minute-data.csv') as csvDataFile:
		csvReader = csv.reader(csvDataFile)
		next(csvReader, None)

		for row in csvReader:
			trade_bucket = {
				'close': row[1],
				'foreignNotional': row[2],
				'high': row[3],
				'homeNotional': row[4],
				'lastSize': row[5],
				'low': row[6],
				'open': row[7],
				'symbol': row[8],
				'timestamp': iso8601.parse_date(row[9]),
				'trades': row[10],
				'turnover': row[11],
				'volume': row[12],
				'vwap': row[13]
			}
			insert_trade_bucket(trade_bucket)

# Gracefully shut down database connection on interrupt.
if connection != None:
	connection.close()

sys.exit(0)
