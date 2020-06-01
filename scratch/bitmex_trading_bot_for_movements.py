import asyncio
import bitmex
import configparser
import json
import logging
import sys
import threading
import traceback2

from datetime import datetime
from numpy import sign
from src.MySqlDataStore import get_mysql_connection

# Read configuration.
config = configparser.ConfigParser()
config.read('config/bitmex_bot.ini')
defaults = config['DEFAULT']

# Logging.
logger = logging.getLogger("bitmex-trading-bot-logger")
logger.setLevel(logging.INFO)

# Add file and console handlers.
logger.addHandler(logging.FileHandler(defaults.get('log.trading.outfile')))
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

# Only insert the trade if it has not already been recorded.
def insert_fill_conditionally(trade):
	logger.info(f"Determine if trade already exists: execID:{trade['execID']}")
	already_exists = False
	try:
		with connection.cursor() as cursor:
			sql = "SELECT exec_id FROM fills WHERE exec_id = %s"
			cursor.execute(sql, (trade['execID']))
			exec_id = cursor.fetchone()
			already_exists = not exec_id == None
	except Exception:
		logger.error(traceback2.format_exc())
		return

	if already_exists: return

	logger.info(f"Inserting fill: execID:{trade['execID']} orderID:{trade['orderID']} symbol:{trade['symbol']} side:{trade['side']} price:{trade['price']} orderQty:{trade['orderQty']} ordType:{trade['ordType']} ordStatus:{trade['ordStatus']} lastPx:{trade['lastPx']} lastQty:{trade['lastQty']} leavesQty:{trade['leavesQty']} cumQty:{trade['cumQty']} avgPx:{trade['avgPx']}")
	tx_time = trade['transactTime'].timestamp()
	try:
		with connection.cursor() as cursor:
			sql = "INSERT INTO `fills` (`transaction_dt`, `exec_id`, `order_id`, `symbol`, `side`, `price`, `order_qty`, `order_type`, `order_status`, `last_px`, `last_qty`, `leaves_qty`, `cum_qty`, `avg_px`, `created_dt`) VALUES (FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())"
			cursor.execute(sql, (tx_time, trade['execID'], trade['orderID'], trade['symbol'], trade['side'], trade['price'], trade['orderQty'], trade['ordType'], trade['ordStatus'], trade['lastPx'], trade['lastQty'], trade['leavesQty'], trade['cumQty'], trade['avgPx']))
			connection.commit()
	except Exception:
		logger.error(traceback2.format_exc())
		return

def insert_position(position):
	logger.info(f"Inserting position: symbol:{position['symbol']} currentQty:{position['currentQty']} avgCostPrice:{position['avgCostPrice']} unrealisedPnl:{position['unrealisedPnl']} currentTimestamp:{position['currentTimestamp']}")
	current_timestamp = position['currentTimestamp'].timestamp()
	try:
		with connection.cursor() as cursor:
			sql = "INSERT INTO `positions` (`symbol`, `current_qty`, `avg_cost_price`, `unrealised_pnl`, `current_timestamp_dt`) VALUES (%s, %s, %s, %s, FROM_UNIXTIME(%s))"
			cursor.execute(sql, (position['symbol'], position['currentQty'], position['avgCostPrice'], position['unrealisedPnl'], current_timestamp))
			connection.commit()
	except Exception:
		logger.error(traceback2.format_exc())

def insert_order(order_id, symbol, price, side, quantity, created_dt):
	logger.info(f'Inserting order: order_id:{order_id} symbol:{symbol} price:{price} side:{side} quantity:{quantity} created_dt:{created_dt}')
	try:
		with connection.cursor() as cursor:
			sql = "INSERT INTO `orders` (`order_id`, `symbol`, `price`, `side`, `quantity`, `created_dt`) VALUES (%s, %s, %s, %s, %s, FROM_UNIXTIME(%s))"
			cursor.execute(sql, (order_id, symbol, price, side, quantity, created_dt))
			connection.commit()
	except Exception:
		logger.error(traceback2.format_exc())

def read_historical_price(symbol, minutes_ago):
	logger.info(f'Reading historical price: symbol:{symbol} minutes_ago:{minutes_ago}')
	price = None
	try:
		with connection.cursor() as cursor:
			sql = "SELECT symbol, l, b, m, s, quote_dt FROM ticker WHERE symbol = %s AND quote_dt < NOW() - INTERVAL %s MINUTE ORDER BY quote_dt DESC LIMIT 1"
			cursor.execute(sql, (symbol, minutes_ago))
			quote = cursor.fetchone()
			price = None if not quote else quote['m']
	except Exception:
		logger.error(traceback2.format_exc())
		return None
	return price

def read_movement(symbol):
	logger.info(f'Reading movement: symbol:{symbol}')
	movement = {}
	try:
		with connection.cursor() as cursor:
			sql = "SELECT price, m_status, direction FROM movements WHERE symbol = %s"
			cursor.execute(sql, (symbol))
			movement = cursor.fetchone()
	except Exception:
		logger.error(traceback2.format_exc())
		return {}
	return movement

def inside_movement(movement):
	return False if not movement else movement['m_status'] == 'start'

def write_movement(symbol, price, new_status, direction, last_movement):
	logger.info('Write movement')
	try:
		with connection.cursor() as cursor:
			if not last_movement:
				logger.info(f'Inserting movement: symbol:{symbol} price:{price} new_status:{new_status} direction:{direction}')
				sql = "INSERT INTO movements (symbol, price, m_status, direction, last_modified_dt) VALUES (%s, %s, %s, %s, NOW())"
				cursor.execute(sql, (symbol, price, new_status, direction))
			else:
				logger.info(f'Updating movement: symbol:{symbol} price:{price} new_status:{new_status} direction:{direction}')
				sql = "UPDATE movements SET price = %s, m_status = %s, direction = %s, last_modified_dt = NOW() WHERE symbol = %s"
				cursor.execute(sql, (price, new_status, direction, symbol))
			connection.commit()
	except Exception:
		logger.error(traceback2.format_exc())

def place_order(symbol, quantity):
	logger.info(f'Place order: symbol:{symbol} quantity:{quantity}')
	try:
		new_order = bitmex_client.Order.Order_new(symbol=symbol, orderQty=quantity, ordType='Market').result()
	except Exception:
		logger.error(traceback2.format_exc())
		return

	# Persist new order to data store.
	create_timestamp = new_order[0]['timestamp'].timestamp()
	insert_order(new_order[0]['orderID'], new_order[0]['symbol'], new_order[0]['price'], new_order[0]['side'], new_order[0]['orderQty'], create_timestamp)

# Cancel open orders and unwind any open positions.
def resolve_positions(symbol):
	logger.info('Resolve positions')

	# Cancel open orders.
	logger.info('Cancel all orders')
	try:
		bitmex_client.Order.Order_cancelAll(symbol=symbol)
	except Exception:
		logger.error(traceback2.format_exc())
		return

	# Close open positions.
	logger.info('Query positions to close')
	try:
		positions = bitmex_client.Position.Position_get(filter=json.dumps({"symbol": "XBTUSD"})).result()
	except Exception:
		logger.error(traceback2.format_exc())
		return

	for pos in positions[0]:
		# Skip over flat positions.
		if pos['currentQty'] == 0: continue

		# Unwind position by multiplying currentQty by -1.
		symbol = pos['symbol']
		order_qty = -1 * pos['currentQty']
		place_order(symbol, order_qty)

def reconcile_fills_and_positions():
	logger.info('Reconciling fills and positions')

	now = datetime.utcnow().timestamp()
	start_time = now - 60*60 # one hour ago
	start_time_dt = datetime.fromtimestamp(start_time)
	start_time_str = start_time_dt.strftime("%Y-%m-%d %H:%M")

	# Look back 1 hour. The pitfall here is that there is network outage longer than that.
	# The count of 64 for results should capture all trades, most of which usually will have
	# already been persisted to our backend.

	logger.info('Query trade history')
	try:
		trade_history = bitmex_client.Execution.Execution_getTradeHistory(symbol='XBTUSD', count=64, reverse=True, filter=json.dumps({"execType": "Trade", "startTime": start_time_str})).result()
	except Exception:
		logger.error(traceback2.format_exc())
		return

	for trade in trade_history[0]:
		insert_fill_conditionally(trade)

	logger.info('Query positions to persist')
	try:
		positions = bitmex_client.Position.Position_get(filter=json.dumps({'symbol': 'XBTUSD'})).result()
	except Exception:
		logger.error(traceback2.format_exc())
		return
		
	for pos in positions[0]:
		insert_position(pos)

# Reconcile broker-side notion of trades / positions with our backend.
def reconcile_fills_and_positions_after_delay(delay):
	t = threading.Timer(delay, reconcile_fills_and_positions)
	try:
		t.start()
	except Exception:
		t.cancel()

def setup_timer_for_trading(delay):
	t = threading.Timer(delay, conditionally_trade)
	try:
		t.start()
	except Exception:
		t.cancel()

def conditionally_trade():
	logger.info('Trading trigger fired')

	# Fire up the timer for next interval
	setup_timer_for_trading(60)

	# Determine historical quote.
	oldPx = read_historical_price('XBTUSD', defaults.getint('movement.start.xbtusd.intervalMinutes'))
	if oldPx == None: return

	# Get current bid/sell prices from top-of-book, and average them to get current price.
	logger.info('Query top of book')
	try:
		top_of_book = bitmex_client.OrderBook.OrderBook_getL2(symbol='XBTUSD', depth=1).result()
	except Exception:
		logger.error(traceback2.format_exc())
		return

	curPx = (top_of_book[0][0]['price'] + top_of_book[0][1]['price']) / 2.0

	# Determine type of price difference to consider, either absolute or relative.
	change = None
	if defaults.get('movement.start.xbtusd.deltaType') == 'absolute':
		change = abs(curPx - oldPx)
	elif defaults.get('movement.start.xbtusd.deltaType') == 'relative':
		change = abs(curPx - oldPx) / oldPx

	# Return if the deltaType was not specified in the configuration.
	if change == None: return

	# Determine current movement status.
	last_movement = read_movement('XBTUSD')

	# Create new order if the price has moved sufficiently far AND we are not already in a movement.
	if change >= defaults.getfloat('movement.start.xbtusd.change') and not inside_movement(last_movement):
		logger.info('Movement started')

		# Negative order quantity implies short/sell order; positive order quantity implies long/buy order.
		side = sign(curPx - oldPx)
		order_qty = side * defaults.getint('movement.start.xbtusd.orderQty')
		place_order('XBTUSD', order_qty)

		# Indicate that movement has started.
		direction = 'down' if side == -1 else 'up'
		write_movement('XBTUSD', curPx, 'start', direction, last_movement)

	elif inside_movement(last_movement):
		# Already in movement. Figure out if movement has ended.
		is_price_reversal = (last_movement['direction'] == 'up' and curPx < last_movement['price']) \
						 or (last_movement['direction'] == 'down' and curPx > last_movement['price'])

		lastPx = read_historical_price('XBTUSD', defaults.getint('movement.end.xbtusd.intervalMinutes'))
		is_price_stabilized = False if not lastPx else abs(curPx - lastPx) <= defaults.getfloat('movement.end.xbtusd.change')
		if is_price_reversal or is_price_stabilized:
			logger.info('Movement ended')
			resolve_positions('XBTUSD')

		# Mark end of movement if price reversed or settled down.
		direction = None
		if is_price_reversal:
			write_movement('XBTUSD', curPx, 'end_price_reversal', direction, last_movement)
		elif is_price_stabilized:
			write_movement('XBTUSD', curPx, 'end_price_stabilized', direction, last_movement)

	# Update any new fills and positions.
	reconcile_fills_and_positions_after_delay(5)

async def run_trading_bot():
	# Every minute wake up and conditionally trade.
	setup_timer_for_trading(60)

	while True:
		await asyncio.sleep(1)

async def gracefully_finish(loop):
    # Gracefully shut down database connection on interrupt.
    if connection != None:
        connection.close()

    # Gracefully terminate ongoing tasks.
    tasks = [task for task in asyncio.Task.all_tasks()]
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.error("Task cancelled: %s" % task)   
    loop.stop()

event_loop = asyncio.get_event_loop()
try:
    event_loop.run_until_complete(run_trading_bot())
except Exception:
    logger.error(traceback2.format_exc())
finally:
    event_loop.run_until_complete(gracefully_finish(event_loop))
    event_loop.close()
