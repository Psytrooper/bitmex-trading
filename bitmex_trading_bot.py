import argparse
import asyncio
import bitmex
import boto3
import bravado
import configparser
import json
import logging
import numpy as np
import pandas as pd
import pymysql
import sys
import time, threading
import traceback2
import websockets
import signal

from datetime import datetime
from datetime import timezone as timezone
from time import sleep
from MySqlDataStore import get_mysql_connection
from BitmexBotUtils import StatusCode
from BitmexBotUtils import ShouldPlaceOrderCode
from BitmexBotUtils import get_next_delay_period

######################################################################################################
# Parse command line and configuration. Set up logger.
######################################################################################################

# Deal with command-line options.
args_parser = argparse.ArgumentParser()
args_parser.add_argument('--instance', type=int, required=True, choices=range(0,5), help='non-negative integer that specifies production instance of trading bot')
args = args_parser.parse_args()

# Read configuration.
config = configparser.ConfigParser()
config.read(f'config/bitmex_bot_{args.instance}.ini')
defaults = config['DEFAULT']

# Logging.
logger = logging.getLogger("bitmex-trading-bot-logger")
logger.setLevel(logging.INFO)

# Add file and console handlers.
logger.addHandler(logging.FileHandler(defaults.get('log.trading.outfile')))
logger.addHandler(logging.StreamHandler())

######################################################################################################
# Methods for vetting configuration parameters.
######################################################################################################

def is_delta_ok(delta, use_absolute):
	if use_absolute and delta < 0.0:
		logger.error(f'for absolute differences, the value of delta:{delta} should be >= 0')
		return False
	if not use_absolute and (delta < 0.0 or delta > 1.0):
		logger.error(f'for relative differences, the value of delta:{delta} should be in the interval [0,1]')
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

if not is_configuration_ok(defaults):
	logger.error('Bad configuration. Check your INI configuration setup.')
	sys.exit(1)

######################################################################################################
# Open handlers for Bitmex API, MySQL queries, and SNS messaging.
######################################################################################################

# Open client-access to bitmex API.
bitmex_client = bitmex.bitmex(
	test=defaults.getboolean('bitmex.api.test'),
	api_key=defaults.get('bitmex.api.key'),
	api_secret=defaults.get('bitmex.api.secret')
)

logger.info('Opening connection with MySQL')
try:
	connection = get_mysql_connection(defaults)
except Exception:
	logger.error(traceback2.format_exc())
	sys.exit(1)

logger.info('Instance SNS handler (AWS SDK)')
try:
	sns = boto3.session.Session(profile_name='bitmex-sns').client('sns')
except Exception:
	logger.error(traceback2.format_exc())
	sys.exit(1)

######################################################################################################
# Database utilities.
######################################################################################################

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
			sql = "INSERT INTO `fills` (`transaction_dt`, `exec_id`, `order_id`, `symbol`, `side`, `price`, `stop_px`, `order_qty`, `order_type`, `order_status`, `last_px`, `last_qty`, `leaves_qty`, `cum_qty`, `avg_px`, `created_dt`) VALUES (FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())"
			cursor.execute(sql, (tx_time, trade['execID'], trade['orderID'], trade['symbol'], trade['side'], trade['price'], trade['stopPx'], trade['orderQty'], trade['ordType'], trade['ordStatus'], trade['lastPx'], trade['lastQty'], trade['leavesQty'], trade['cumQty'], trade['avgPx']))
			connection.commit()
	except Exception:
		logger.error(traceback2.format_exc())
		return

def insert_position(position):
	# Avoid the timestamp in position['currentTimestamp'], as it in fact does not reflect the current time.
	now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
	logger.info(f"Inserting position: symbol:{position['symbol']} currentQty:{position['currentQty']} avgCostPrice:{position['avgCostPrice']} unrealisedPnl:{position['unrealisedPnl']} currentTimestamp:{now}")
	try:
		with connection.cursor() as cursor:
			sql = "INSERT INTO `positions` (`symbol`, `current_qty`, `avg_cost_price`, `unrealised_pnl`, `current_timestamp_dt`) VALUES (%s, %s, %s, %s, FROM_UNIXTIME(%s))"
			cursor.execute(sql, (position['symbol'], position['currentQty'], position['avgCostPrice'], position['unrealisedPnl'], now))
			connection.commit()
	except Exception:
		logger.error(traceback2.format_exc())

def insert_order(order_id, symbol, price, side, quantity, order_type, created_dt, decision_px, stop_px=None):
	logger.info(f'Inserting order: order_id:{order_id} symbol:{symbol} price:{price} decision_px:{decision_px} stop_px:{stop_px} side:{side} quantity:{quantity} order_type:{order_type} created_dt:{created_dt}')
	try:
		with connection.cursor() as cursor:
			sql = "INSERT INTO `orders` (`order_id`, `symbol`, `price`, `decision_px`, `stop_px`, `side`, `quantity`, `order_type`, `created_dt`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FROM_UNIXTIME(%s))"
			cursor.execute(sql, (order_id, symbol, price, decision_px, stop_px, side, quantity, order_type, created_dt))
			connection.commit()
	except Exception:
		logger.error(traceback2.format_exc())

# Read the last N days of 1m trade buckets into a panda dataframe.
def read_trade_buckets_into_dataframe(symbol, ndays):
	logger.info(f'Reading 1m trade buckets for symbol:{symbol}')
	df = pd.DataFrame()
	now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
	try:
		# XXX should use prepared statement, but params argument to pd.read() did not work.
		sql = f"SELECT timestamp_dt, close_px, high_px, low_px, home_notional FROM tradeBin1m WHERE symbol = '{symbol}' AND timestamp_dt >= (FROM_UNIXTIME({now}) - interval {ndays} day) ORDER BY timestamp_dt ASC"
		df = pd.read_sql(sql, connection)
	except Exception:
		logger.error(traceback2.format_exc())
	return df

def read_decisions(symbol, side, num_minutes):
	logger.info(f'Reading decisions; symbol:{symbol} side:{side} num_minutes:{num_minutes}')
	decisions = []
	try:
		with connection.cursor() as cursor:
			# Add 30s grace period at the front of the bucket samples so as to accomodate jitter in the timer trigger.
			num_seconds = 60*num_minutes + 30
			sql = "SELECT * FROM decisions WHERE symbol = %s AND side = %s AND timestamp_dt >= (NOW() - interval %s second) ORDER BY timestamp_dt ASC"
			cursor.execute(sql, (symbol, side, num_seconds))
			decisions = cursor.fetchall()
			# Cap the size of decisions just in case our query returns # records in excess of num_minutes.
			decisions = decisions[-num_minutes:]
	except Exception:
		logger.error(traceback2.format_exc())
	return decisions

def read_last_decision(symbol, side):
	logger.info(f'Reading last decision for symbol:{symbol} side:{side}')
	decision = None
	try:
		with connection.cursor() as cursor:
			sql = "SELECT * FROM decisions WHERE symbol = %s AND side = %s ORDER BY timestamp_dt DESC LIMIT 1"
			cursor.execute(sql, (symbol, side))
			decision = cursor.fetchone()
	except Exception:
		logger.error(traceback2.format_exc())
	return decision

def write_decision(symbol, side, position, price, mkt_price=None, active=False, synthetic=False):
	logger.info(f'Writing decisions; symbol:{symbol} side:{side} position:{position} price:{price}')
	now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
	try:
		with connection.cursor() as cursor:
			sql = "INSERT INTO `decisions` (`timestamp_dt`, `symbol`, `side`, `position`, `price`, `mkt_price`, `synthetic`, `active`) VALUES (FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s, %s)"
			cursor.execute(sql, (now, symbol, side, position, price, mkt_price, synthetic, active))
			connection.commit()
	except Exception:
		logger.error(traceback2.format_exc())

######################################################################################################
# Trading utilities.
######################################################################################################

def read_market_price():
	mkt_price = None
	try:
		quotes = bitmex_client.OrderBook.OrderBook_getL2(symbol='XBTUSD', depth=1).result()
		if len(quotes[0]) < 2: return None
		mkt_price = (quotes[0][0]['price'] + quotes[0][1]['price']) / 2.0
	except Exception:
		logger.error(traceback2.format_exc())
	return mkt_price

def should_place_order(mkt_price, decisions):
	# Find the mkt_price from decision 5m ago, skipping over synthetic decisions.
	# Look back at most 10 records, as that represents the greatest number of decision records (including synthetic decisons) spanning 5m.
	active_count, five_minute_index = 0, -1
	for k in range(1,11):
		if k > len(decisions): break
		if decisions[-k]['synthetic'] == True: continue
		if decisions[-k]['active'] == False: break
		active_count += 1
		if active_count >= 5:
			five_minute_index = k
			break

	# Too soon if active samples span less than 5m.
	if active_count < 5: return ShouldPlaceOrderCode.TOO_SOON

	# Make sure the timestamp between now and decisions[-five_minute_index] is not in excess of 5m.
	now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
	then = decisions[-five_minute_index]['timestamp_dt'].replace(tzinfo=timezone.utc).timestamp()
	if (now - then) >= 360: return ShouldPlaceOrderCode.NO

	delta = mkt_price - float(decisions[-five_minute_index]['mkt_price'])
	return ShouldPlaceOrderCode.YES if delta >= 10 else ShouldPlaceOrderCode.NO

def broadcast_order_failure(symbol, quantity, decision_px, stop_px=None, position=None, failure_message=None):
	where_from = defaults.get('db.name')
	notification = 'Order failed ' if not stop_px else 'Stop order failed '
	if failure_message: notification += failure_message + ' '
	notification += f'on [{where_from}]: symbol:{symbol} quantity:{quantity} decision_px:{decision_px}'
	if stop_px: notification += f' stop_px:{stop_px}'
	if position: notification += f', while liquidating position'
	try:
		sns.publish(TopicArn=defaults.get('sns.topic.arn'), Message=notification, Subject='Bitmex order failed')
	except Exception:
		# Capture stack trace if we cannot send out messages, but do not interrupt trading.
		logger.error(traceback2.format_exc())

def broadcast_message(symbol, quantity, avg_px, decision_px=None, realized_pnl=None, stop_px=None, ord_status=None):
	ord_status = ord_status.lower() if isinstance(ord_status, str) else 'placed'
	where_from = defaults.get('db.name')
	if not stop_px:
		notification = f'Order {ord_status} [{where_from}]: symbol:{symbol} quantity:{quantity}'
	else:
		notification = f'Stop order {ord_status} [{where_from}]: symbol:{symbol} quantity:{quantity} stop_px:{stop_px}'
	if decision_px: notification += f' decision_px:{decision_px}'
	if avg_px: notification += f' average_price:{avg_px}'
	if realized_pnl: notification += f' realized_pnl:{realized_pnl:.16f}'
	try:
		sns.publish(TopicArn=defaults.get('sns.topic.arn'), Message=notification, Subject='Bitmex trade')
	except Exception:
		# Capture stack trace if we cannot send out messages, but do not interrupt trading.
		logger.error(traceback2.format_exc())

def place_stop_order(symbol, quantity, entry_px, decision_px):
	# Use the long-stop price if selling; otherwise, use the short-stop price.
	# XXX Pad reference price by 10 to avert unwanted executions of Stop orders at market. This should be configurable.
	if quantity < 0:
		side, reference_px = 'long', min(decision_px, entry_px) - 10
	else:
		side, reference_px = 'short', max(decision_px, entry_px) + 10
	stop_px = get_stop_threshold(reference_px, side)

	# Set trigger and limit price equal; as these are away from the market, we should be paid maker fees.
	logger.info(f'Placing stop order: symbol:{symbol} quantity:{quantity} entry_px:{entry_px} decision_px:{decision_px} stop_px:{stop_px}')

	# Support up to 5 retries in case Bitmex rejects our order due to load-shedding policy.
	attempts, new_stop_order = 0, None
	while attempts < 5 and not new_stop_order:
		logger.info(f'Attempt to place order on attempt:{attempts}')
		try:
			new_stop_order = bitmex_client.Order.Order_new(symbol=symbol, orderQty=quantity, ordType='Stop', stopPx=stop_px).result()
			# Retry if order Canceled; otherwise, break.
			if new_stop_order[0]['ordStatus'] != 'Canceled': break
			else:
				stop_px += np.sign(quantity)*10
				logger.info(f'Stop order canceled; move stop_px further from market to {stop_px}')
				new_stop_order = None
		except bravado.exception.HTTPServiceUnavailable:
			# XXX we should check the error message to be sure the "overloaded" condition happened.
			logger.error(traceback2.format_exc())
		except Exception:
			logger.error(traceback2.format_exc())
			break
		# Bitmex has rejected order due to load-shedding policy. Per docs, wait 500 ms, then retry. Note: this is a blocking sleep().
		sleep(0.5)
		attempts += 1
	if not new_stop_order:
		failure_message = 'from overload condition and/or cancellation' if attempts >= 1 else None
		broadcast_order_failure(symbol, quantity, decision_px, stop_px=stop_px, failure_message=failure_message)
		return StatusCode.ERROR

	# For stop orders, there is no price, just a stop-price.
	create_timestamp = new_stop_order[0]['timestamp'].timestamp()
	insert_order(new_stop_order[0]['orderID'], new_stop_order[0]['symbol'], new_stop_order[0]['price'], new_stop_order[0]['side'], new_stop_order[0]['orderQty'], 'Stop', create_timestamp, decision_px, stop_px=new_stop_order[0]['stopPx'])
	broadcast_message(symbol, quantity, new_stop_order[0]['avgPx'], decision_px=decision_px, stop_px=stop_px, ord_status=new_stop_order[0]['ordStatus'])

	return StatusCode.OK

# position parameter is non-null when we are placing an order to close said position.
def place_order(symbol, quantity, decision_px, position=None):
	logger.info(f'Place order: symbol:{symbol} quantity:{quantity}')

	# DO NOT use API method Order.Order_newBulk() to post both the new order and the new stop-limit order.
	# Oddly, the API for bulk orders fails when the ordType differs between orders.

	# Support up to 5 retries in case Bitmex rejects our order due to load-shedding policy.
	attempts, new_order = 0, None
	while attempts < 5 and not new_order:
		logger.info(f'Attempt to place order on attempt:{attempts}')
		try:
			new_order = bitmex_client.Order.Order_new(symbol=symbol, orderQty=quantity, ordType='Market').result()
			break
		except bravado.exception.HTTPServiceUnavailable:
			# XXX we should check the error message to be sure the "overloaded" condition happened.
			logger.error(traceback2.format_exc())
		except Exception:
			logger.error(traceback2.format_exc())
			break
		# Bitmex has rejected order due to load-shedding policy. Per docs, wait 500 ms, then retry. Note: this is a blocking sleep().
		sleep(0.5)
		attempts += 1
	if not new_order:
		failure_message = 'from overload condition' if attempts >= 1 else None
		broadcast_order_failure(symbol, quantity, decision_px, position=position, failure_message=failure_message)
		return StatusCode.ERROR

	# Persist new order to data store.
	create_timestamp = new_order[0]['timestamp'].timestamp()
	insert_order(new_order[0]['orderID'], new_order[0]['symbol'], new_order[0]['price'], new_order[0]['side'], new_order[0]['orderQty'], 'Market', create_timestamp, decision_px)

	# Register realized P&L only when a position is closed.
	realized_pnl = None
	if position:
		realized_pnl = (1.0 / position['avgEntryPrice'] - 1.0 / new_order[0]['avgPx']) * abs(quantity)
		realized_pnl *= (1.0 - position['commission'])

	# Message interested parties about trade. Include trade-price if order filled.
	broadcast_message(symbol, quantity, new_order[0]['avgPx'], decision_px=decision_px, realized_pnl=realized_pnl, ord_status=new_order[0]['ordStatus'])

	# Initiate stop order if we are not closing a position.
	if not position:
		entry_px = float(new_order[0]['avgPx'])
		place_stop_order(symbol, -quantity, entry_px, decision_px)

	return StatusCode.OK

# Cancel open orders and unwind any open positions. If side is specified, then only unwind
# positions on the specified side.
def resolve_positions(symbol, decision_px, side=None):
	logger.info('Resolve positions')

	# Cancel open orders.
	logger.info('Cancel all orders')
	try:
		bitmex_client.Order.Order_cancelAll(symbol=symbol).result()
	except Exception:
		logger.error(traceback2.format_exc())
		return StatusCode.ERROR

	# Close open positions.
	logger.info('Query positions to close')
	try:
		positions = bitmex_client.Position.Position_get(filter=json.dumps({"symbol": "XBTUSD"})).result()
	except Exception:
		logger.error(traceback2.format_exc())
		return StatusCode.ERROR

	was_error = False
	for pos in positions[0]:
		# Skip over flat positions.
		if pos['currentQty'] == 0: continue

		# Make sure we are on the right side.  Note: short positions are negative.
		if side == 'short' and pos['currentQty'] > 0: continue
		if side == 'long' and pos['currentQty'] < 0: continue

		# Unwind position by multiplying currentQty by -1.
		symbol = pos['symbol']
		order_qty = -1 * pos['currentQty']
		code = place_order(symbol, order_qty, decision_px, position=pos)
		was_error |= code == StatusCode.ERROR

	return StatusCode.OK if not was_error else StatusCode.ERROR

def reconcile_positions_with_decision_logs():
	logger.info('Reconciling positions with decision logs')
	try:
		positions = bitmex_client.Position.Position_get(filter=json.dumps({'symbol': 'XBTUSD'})).result()
	except Exception:
		logger.error(traceback2.format_exc())
		return

	# Immediately return if there are no position listings.
	if len(positions[0]) <= 0: return

	# Calculate net of short and long decision positions.
	short_decision = read_last_decision('XBTUSD', 'short')
	long_decision = read_last_decision('XBTUSD', 'long')
	if short_decision and long_decision:
		net_position = long_decision['position'] - short_decision['position']
	elif short_decision:
		net_position = -short_decision['position']
	elif long_decision:
		net_position = long_decision['position']
	else:
		net_position = 0

	# When our net position does not equal Bitmex's notion of our position, then we reconcile the two
	# by writing a pair of synthetic decisions to our decision logs. Note that Bitmex may show a flat
	# position, in which case, we would flatten both of our short/long positions in decision logs.

	logger.info(f"net_position:{net_position} positions[0][0]['currentQty']:{positions[0][0]['currentQty']}")
	if net_position != positions[0][0]['currentQty']:
		side = 'short' if positions[0][0]['currentQty'] < 0 else 'long'
		decision_position = abs(positions[0][0]['currentQty'])
		decision_px = positions[0][0]['avgEntryPrice']
		write_decision('XBTUSD', side, decision_position, decision_px, active=False, synthetic=True)
		# Maintain flat decision for other side.
		other_side = 'short' if side == 'long' else 'short'
		write_decision('XBTUSD', other_side, 0, 0, active=False, synthetic=True)

def reconcile_fills_and_positions():
	logger.info('Reconciling fills and positions')

	# Scan trade history up to 1 minute ago, as we should call this method each minute.
	now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
	start_time = now - 60
	start_time_dt = datetime.fromtimestamp(start_time, tz=timezone.utc)
	start_time_str = start_time_dt.strftime("%Y-%m-%d %H:%M")

	# Look back 1 minute. The pitfalls here are (a) that there is network outage longer than that,
	# or (b) that a trade executes during the small window between 1 minute ago and when the
	# trade-history query was last done (which might well be more than 1 minute ago).
	# The count of 64 for results is arbitrary and conceivably could miss some fills.

	logger.info('Query trade history')
	try:
		trade_history = bitmex_client.Execution.Execution_getTradeHistory(symbol='XBTUSD', count=64, reverse=True, filter=json.dumps({"execType": "Trade", "startTime": start_time_str})).result()
	except Exception:
		logger.error(traceback2.format_exc())
		return

	for trade in trade_history[0]:
		insert_fill_conditionally(trade)
		# Broadcast status of Stop orders if (i) order was completely filled or (ii) order was cancelled.
		case1 = trade['ordStatus'] == 'Filled' and trade['cumQty'] == trade['orderQty']
		case2 = trade['ordStatus'] == 'Canceled'
		if trade['ordType'] == 'Stop' and (case1 or case2):
			# Use negative quantity for sell-side trades.
			quantity = trade['cumQty'] if trade['side'] == 'Buy' else -trade['cumQty']
			broadcast_message(trade['symbol'], quantity, trade['avgPx'], stop_px=trade['stopPx'], ord_status=trade['ordStatus'])

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

def get_stop_threshold(px, side):
	if side == 'long':
		use_absolute = defaults.getboolean('bitmex.tradebot.decision.long.stop.delta.absolute')
		delta = defaults.getfloat('bitmex.tradebot.decision.long.stop.delta', 0)
	else:
		use_absolute = defaults.getboolean('bitmex.tradebot.decision.short.stop.delta.absolute')
		# Negate delta for shorts as stop-price for shorts opposes direction of the stop-price for longs.
		delta = -defaults.getfloat('bitmex.tradebot.decision.short.stop.delta', 400)
	if use_absolute:
		stop_threshold = px - delta
	else:
		stop_threshold = (1.0 - delta) * px
	return stop_threshold

def exceeds_stop_threshold(last_px, decisions, side):
	# No stop-condition triggers if we do not hold any open position.
	if len(decisions) <= 0 or abs(decisions[-1]['position']) <= 0: return False

	# Time-stop triggers when the current position has been held 3 or more hours.
	if sum([np.sign(d['position']) for d in decisions[0:]]) >= 180: return True

	# A more restricted version of the time-stop triggers if there are gaps in the decision log.
	# We assume gaps if the time elapsed between the first and last decision is 3 or more hours,
	# which equates to 10740 seconds (actually 60 seconds less than 3 hours, as we assume the first
	# minute-sample is recorded after the initial 60 seconds of the 3-hour time-swath has expired).

	if len(decisions) >= 2 \
		and (decisions[-1]['timestamp_dt'].timestamp() - decisions[0]['timestamp_dt'].timestamp()) >= 10740 \
		and sum([np.sign(d['position']) for d in decisions[0:]]) >= len(decisions):
		return True

	stop_threshold = get_stop_threshold(float(decisions[-1]['price']), side)
	logger.info(f'Check whether stop-price reached for last_px:{last_px} side:{side} stop_threshold:{stop_threshold}')

	if side == 'long' and last_px < stop_threshold:
		logger.info('Stop threshold exceeded (long decision)')
		return True

	if side == 'short' and last_px > stop_threshold:
		logger.info('Stop threshold exceeded (short decision)')
		return True

	return False

def make_long_trading_decision(df):
	logger.info('Make long trading decision.')

	# Get current position, 1+ for long/short, 0 for flat.
	decisions = read_decisions('XBTUSD', 'long', 180)
	cur_position = decisions[-1]['position'] if len(decisions) else 0
	threshold = defaults.getfloat('bitmex.tradebot.decision.long.threshold', 4)
	ma_multiplier = defaults.getfloat('bitmex.tradebot.decision.long.ma20.multiplier', 1.5)
	last_idx = len(df.index) - 1
	mkt_price = read_market_price()
	logger.info(f'df.z_480.iloc[last_idx]:{df.z_480.iloc[last_idx]} df.close_px.iloc[last_idx]:{df.close_px.iloc[last_idx]} df.ma_20_days.iloc[last_idx]:{df.ma_20_days.iloc[last_idx]} threshold:{threshold} ma_multiplier:{ma_multiplier} mkt_price:{mkt_price}')

	# Default decision position/px in case no trade takes place below.
	last_px = decisions[-1]['price'] if len(decisions) else 0
	last_active = decisions[-1]['active'] if len(decisions) else False
	decision_position, decision_px, active = cur_position, last_px, last_active

	if active and cur_position <= 0:
		disposition = should_place_order(mkt_price, decisions)
		if disposition == ShouldPlaceOrderCode.YES:
			logger.info(f'Open new position only if it implies a change in our current position of {cur_position}.')
			long_size = defaults.getint('bitmex.tradebot.decision.long.size')
			code = place_order('XBTUSD', long_size, df.close_px.iloc[last_idx])
			if code == StatusCode.OK:
				decision_position, decision_px, active = long_size, last_px, False
		elif disposition == ShouldPlaceOrderCode.NO:
			decision_position, decision_px, active = 0, 0, False
	elif not active and cur_position <= 0 \
		and df.z_480.iloc[last_idx] > threshold \
		and df.close_px.iloc[last_idx] < df.ma_20_days.iloc[last_idx] * ma_multiplier:
		logger.info('Start waiting period before initiating long position')
		decision_position, decision_px, active = 0, df.close_px.iloc[last_idx], True
	elif exceeds_stop_threshold(df.close_px.iloc[last_idx], decisions, 'long'):
		logger.info(f'Close position after 3 hours, but only if it implies a change in our current position of {cur_position}.')
		code = resolve_positions('XBTUSD', df.close_px.iloc[last_idx], 'long') if cur_position > 0 else StatusCode.OK
		if code == StatusCode.OK:
			decision_position, decision_px, active = 0, 0, False
	else:
		logger.info('Hold onto current position.')

	# Each time the trading trigger fires, we write this decision for our long strategy.
	write_decision('XBTUSD', 'long', decision_position, decision_px, mkt_price=mkt_price, active=active)

def make_short_trading_decision(df):
	logger.info('Make short trading decision.')

	# Get current position, 1+ for long/short, 0 for flat.
	decisions = read_decisions('XBTUSD', 'short', 180)
	cur_position = decisions[-1]['position'] if len(decisions) else 0
	threshold = defaults.getfloat('bitmex.tradebot.decision.short.threshold', 3)
	last_idx = len(df.index) - 1
	logger.info(f'df.ma_comps.iloc[last_idx]:{df.ma_comps.iloc[last_idx]} df.close_px.iloc[last_idx]:{df.close_px.iloc[last_idx]} df.close_px.iloc[last_idx-1]:{df.close_px.iloc[last_idx-1]} df.ma_20_days.iloc[last_idx]:{df.ma_20_days.iloc[last_idx]} threshold:{threshold}')

	# Default decision position/px in case no trade takes place below.
	last_px = decisions[-1]['price'] if len(decisions) else 0
	decision_position, decision_px = cur_position, last_px

	if cur_position <= 0 \
		and df.ma_comps.iloc[last_idx] >= threshold \
		and df.close_px.iloc[last_idx] < df.close_px.iloc[last_idx-1]*0.99 \
		and df.close_px.iloc[last_idx] > df.ma_20_days.iloc[last_idx]:
		logger.info(f'Open new position only if it implies a change in our current position of {cur_position}.')
		short_size = defaults.getint('bitmex.tradebot.decision.short.size')
		# negative quantity means short the contract
		code = place_order('XBTUSD', -short_size, df.close_px.iloc[last_idx])
		if code == StatusCode.OK:
			decision_position, decision_px = short_size, df.close_px.iloc[last_idx]
	elif exceeds_stop_threshold(df.close_px.iloc[last_idx], decisions, 'short'):
		logger.info(f'Close position after 3 hours, but only if it implies a change in our current position of {cur_position}.')
		code = resolve_positions('XBTUSD', df.close_px.iloc[last_idx], 'short') if cur_position > 0 else StatusCode.OK
		if code == StatusCode.OK:
			decision_position, decision_px = 0, 0
	else:
		logger.info('Hold onto current position.')

	# Each time the trading trigger fires, we write this decision for our short strategy.
	write_decision('XBTUSD', 'short', decision_position, decision_px)

def setup_timer_for_trading(delay_period):
	delay_period = get_next_delay_period(delay_period)
	t = threading.Timer(delay_period, conditionally_trade)
	try:
		t.start()
	except Exception:
		t.cancel()

def conditionally_trade():
	now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
	logger.info(f'Trading trigger fired at {now}')

	# Fire up the timer for next interval
	setup_timer_for_trading(60)

	# Incorporate any external position-changes into our decision logs.
	reconcile_positions_with_decision_logs()

	# Read the last 21 days of 1m trade-buckets into Panda dataframe.
	df = read_trade_buckets_into_dataframe('XBTUSD', 21)
	if df.empty: return

	# Resample data, eliminating unused columns.
	df['time'] = pd.to_datetime(df.timestamp_dt)
	df['my_date'] = df.time.dt.date
	df['hour'] = df.time.dt.hour

	df.index = pd.DatetimeIndex(df.time)
	five_min = pd.DataFrame()
	five_min['close_px'] = df.close_px.resample('5min').last()
	five_min['high_px'] = df.high_px.resample('5min').max()
	five_min['low_px'] = df.low_px.resample('5min').min()
	five_min['volume'] = df.home_notional.resample('5min').sum()
	five_min['my_date'] = df.my_date.resample('5min').last()
	five_min['hour'] = df.hour.resample('5min').last()
	five_min['time'] = df.time.resample('5min').last()

	five_min['ma_5'] = five_min['close_px'].rolling(5).mean()
	five_min['ma_10'] = five_min['close_px'].rolling(10).mean()
	five_min['ma_20'] = five_min['close_px'].rolling(20).mean()
	five_min['ma_50'] = five_min['close_px'].rolling(50).mean()
	five_min['ma_200'] = five_min['close_px'].rolling(200).mean()
	five_min['ma_20_days'] = five_min['close_px'].rolling(5760).mean()
	five_min['pct_chg'] = five_min['close_px'] / five_min['close_px'].shift(1) - 1
	five_min['volatility_480'] = five_min.pct_chg.rolling(96).std()
	five_min['z_480'] = five_min.pct_chg / five_min.volatility_480

	# Just include trailing 20 days of data.
	five_min = five_min[-5760:]
	df = five_min

	df['ma_5_10'] = np.where(df.ma_5 > df.ma_10,1,0)
	df['ma_10_20'] = np.where(df.ma_10 > df.ma_20,1,0)
	df['ma_20_50'] = np.where(df.ma_20 > df.ma_50,1,0)
	df['ma_50_200'] = np.where(df.ma_50 > df.ma_200,1,0)
	df['ma_comps'] = df[['ma_5_10', 'ma_10_20', 'ma_20_50', 'ma_50_200']].sum(axis=1)

	# Consider long trade.
	make_long_trading_decision(df)

	# Consider short trade.
	make_short_trading_decision(df)

	# Update any new fills and positions.
	reconcile_fills_and_positions_after_delay(3)

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
