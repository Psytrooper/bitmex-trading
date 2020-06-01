import bitmex
import boto3
import bravado
import json
import numpy as np
import pandas as pd
import sys
import threading
import traceback2
from datetime import datetime, timezone
from time import sleep


from src.utils.BitmexBotUtils import StatusCode, ShouldPlaceOrderCode
from src.utils.logger import BitmexLogger


class BitmexTradingBot:

    def __init_logger__(self, debug=True):
        self.debug = debug

        self.logger = BitmexLogger(label='bot', log_file=self.defaults.get('log.trading.outfile')).logger

    def __init_boto3(self):
        self.logger.info('Instance SNS handler (AWS SDK)')
        try:
            self.sns = boto3.session.Session(profile_name='bitmex-sns').client('sns')
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
            sys.exit(1)

    def __init__(self, config, signal_queue, connection):
        self.defaults = config  # default: holds the configurations object.
        self.signal_queue = signal_queue
        # logger configuration.
        self.__init_logger__()
        self.logger.info("Bot: Connecting to Bitmex....")
        self.bitmex_client = bitmex.bitmex(
            test=self.defaults.getboolean('bitmex.tradebuckets.api.test'),
            api_key=self.defaults.get('bitmex.tradebuckets.api.key'),
            api_secret=self.defaults.get('bitmex.tradebuckets.api.secret')
        )
        self.connection = connection

        self.__init_boto3()
        self.notify("Trading Bot Started.")
        self.logger.info("################## Bot Statred ##################")

    def notify(self, notification):
        try:
            self.sns.publish(TopicArn=self.defaults.get('sns.topic.arn'), Message=notification, Subject='Bitmex trade')
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())

    def start_trading(self):
        while True:
            if self.signal_queue.get() is not None:
                self.logger.info("Got trade bucket from signal_queue.")
                try:
                    self.conditionally_trade()
                except Exception as e:
                    self.logger.error(f'Got Exception. {e}')
                    self.logger.exception(e)
            else:
                self.logger.info("Got Kill Signal. Stopping Trading Thread.")
                break

    ######################################################################################################
    # Database utilities.
    ######################################################################################################

    # Only insert the trade if it has not already been recorded.
    def insert_fill_conditionally(self, trade):
        self.logger.info(f"Determine if trade already exists: execID:{trade['execID']}")
        already_exists = False
        try:
            with self.connection.cursor() as cursor:
                sql = "SELECT exec_id FROM fills WHERE exec_id = %s"
                cursor.execute(sql, (trade['execID']))
                exec_id = cursor.fetchone()
                already_exists = not (exec_id is not None)
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
            return

        if already_exists:
            return

        self.logger.info(
            f"Inserting fill: execID:{trade['execID']} orderID:{trade['orderID']} symbol:{trade['symbol']} side:{trade['side']} price:{trade['price']} orderQty:{trade['orderQty']} ordType:{trade['ordType']} ordStatus:{trade['ordStatus']} lastPx:{trade['lastPx']} lastQty:{trade['lastQty']} leavesQty:{trade['leavesQty']} cumQty:{trade['cumQty']} avgPx:{trade['avgPx']}")
        tx_time = trade['transactTime'].timestamp()
        try:
            with self.connection.cursor() as cursor:
                sql = "INSERT INTO `fills` (`transaction_dt`, `exec_id`, `order_id`, `symbol`, `side`, `price`, `stop_px`, `order_qty`, `order_type`, `order_status`, `last_px`, `last_qty`, `leaves_qty`, `cum_qty`, `avg_px`, `created_dt`) VALUES (FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())"
                cursor.execute(sql, (
                    tx_time, trade['execID'], trade['orderID'], trade['symbol'], trade['side'], trade['price'],
                    trade['stopPx'], trade['orderQty'], trade['ordType'], trade['ordStatus'], trade['lastPx'],
                    trade['lastQty'], trade['leavesQty'], trade['cumQty'], trade['avgPx']))
                self.connection.commit()
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
            return

    def insert_position(self, position):
        # Avoid the timestamp in position['currentTimestamp'], as it in fact does not reflect the current time.
        now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
        self.logger.info(
            f"Inserting position: symbol:{position['symbol']} currentQty:{position['currentQty']} avgCostPrice:{position['avgCostPrice']} unrealisedPnl:{position['unrealisedPnl']} currentTimestamp:{now}")
        try:
            with self.connection.cursor() as cursor:
                sql = "INSERT INTO `positions` (`symbol`, `current_qty`, `avg_cost_price`, `unrealised_pnl`, `current_timestamp_dt`) VALUES (%s, %s, %s, %s, FROM_UNIXTIME(%s))"
                cursor.execute(sql, (
                    position['symbol'], position['currentQty'], position['avgCostPrice'], position['unrealisedPnl'],
                    now))
                self.connection.commit()
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())

    def insert_order(self, order_id, symbol, price, side, quantity, order_type, created_dt, decision_px, stop_px=None):
        self.logger.info(
            f'Inserting order: order_id:{order_id} symbol:{symbol} price:{price} decision_px:{decision_px} stop_px:{stop_px} side:{side} quantity:{quantity} order_type:{order_type} created_dt:{created_dt}')
        try:
            with self.connection.cursor() as cursor:
                sql = "INSERT INTO `orders` (`order_id`, `symbol`, `price`, `decision_px`, `stop_px`, `side`, `quantity`, `order_type`, `created_dt`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FROM_UNIXTIME(%s))"
                cursor.execute(sql,
                               (order_id, symbol, price, decision_px, stop_px, side, quantity, order_type, created_dt))
                self.connection.commit()
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())

    # Read the last N days of 1m trade buckets into a panda dataframe.
    def read_trade_buckets_into_dataframe(self, symbol, ndays):
        self.logger.info(f'Reading 1m trade buckets for symbol:{symbol}')
        df = pd.DataFrame()
        now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
        try:
            # XXX should use prepared statement, but params argument to pd.read() did not work.
            sql = f"SELECT timestamp_dt, close_px, high_px, low_px, home_notional FROM tradeBin1m WHERE symbol = '{symbol}' AND timestamp_dt >= (FROM_UNIXTIME({now}) - interval {ndays} day) ORDER BY timestamp_dt ASC"
            df = pd.read_sql(sql, self.connection)
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
        return df

    def read_decisions(self, symbol, side, num_minutes):
        self.logger.info(f'Reading decisions; symbol:{symbol} side:{side} num_minutes:{num_minutes}')
        decisions = []
        try:
            with self.connection.cursor() as cursor:
                # Add 30s grace period at the front of the bucket samples so as to accomodate jitter in the timer trigger.
                num_seconds = 60 * num_minutes + 30
                sql = "SELECT * FROM decisions WHERE symbol = %s AND side = %s AND timestamp_dt >= (NOW() - interval %s second) ORDER BY timestamp_dt ASC"
                cursor.execute(sql, (symbol, side, num_seconds))
                decisions = cursor.fetchall()
                # Cap the size of decisions just in case our query returns # records in excess of num_minutes.
                decisions = decisions[-num_minutes:]
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
        return decisions

    def read_last_decision(self, symbol, side):
        self.logger.info(f'Reading last decision for symbol:{symbol} side:{side}')
        decision = None
        try:
            with self.connection.cursor() as cursor:
                sql = "SELECT * FROM decisions WHERE symbol = %s AND side = %s ORDER BY timestamp_dt DESC LIMIT 1"
                cursor.execute(sql, (symbol, side))
                decision = cursor.fetchone()
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
        return decision

    def read_last_fill(self, symbol, side):
        self.logger.info(f'Reading last fill for symbol:{symbol} side:{side}')
        fill = None
        try:
            with self.connection.cursor() as cursor:
                sql = "SELECT * FROM fills WHERE symbol = %s AND side = %s ORDER BY transaction_dt DESC LIMIT 1"
                cursor.execute(sql, (symbol, side))
                fill = cursor.fetchone()
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
        return fill

    def write_decision(self, symbol, side, position, price, mkt_price=None, active=False, synthetic=False):
        self.logger.info(f'Writing decisions; symbol:{symbol} side:{side} position:{position} price:{price}')
        now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
        try:
            with self.connection.cursor() as cursor:
                sql = "INSERT INTO `decisions` (`timestamp_dt`, `symbol`, `side`, `position`, `price`, `mkt_price`, `synthetic`, `active`) VALUES (FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s, %s)"
                cursor.execute(sql, (now, symbol, side, position, price, mkt_price, synthetic, active))
                self.connection.commit()
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())

    ######################################################################################################
    # Trading utilities.
    ######################################################################################################

    def read_market_price(self):
        mkt_price = None
        try:
            quotes = self.bitmex_client.OrderBook.OrderBook_getL2(symbol='XBTUSD', depth=1).result()
            if len(quotes[0]) < 2:
                return None
            mkt_price = (quotes[0][0]['price'] + quotes[0][1]['price']) / 2.0
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
        return mkt_price

    def should_place_order(self, mkt_price, decisions):
        # Find the mkt_price from decision 5m ago, skipping over synthetic decisions.
        # Look back at most 10 records, as that represents the greatest number of decision records (including synthetic decisons) spanning 5m.
        active_count, five_minute_index = 0, -1
        for k in range(1, 11):
            if k > len(decisions):
                break
            if decisions[-k]['synthetic'] == True:
                continue
            if decisions[-k]['active'] == False:
                break
            active_count += 1
            if active_count >= 5:
                five_minute_index = k
                break

        # Too soon if active samples span less than 5m.
        if active_count < 5:
            return ShouldPlaceOrderCode.TOO_SOON

        # Make sure the timestamp between now and decisions[-five_minute_index] is not in excess of 5m.
        now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
        then = decisions[-five_minute_index]['timestamp_dt'].replace(tzinfo=timezone.utc).timestamp()
        if (now - then) >= 360:
            return ShouldPlaceOrderCode.NO

        delta = mkt_price - float(decisions[-five_minute_index]['mkt_price'])
        if delta >= 10:
            return ShouldPlaceOrderCode.YES
        else:
            return ShouldPlaceOrderCode.NO

    def broadcast_order_failure(self, symbol, quantity, decision_px, stop_px=None, position=None, failure_message=None):
        where_from = self.defaults.get('db.name')
        notification = 'Order failed ' if not stop_px else 'Stop order failed '
        if failure_message:
            notification += failure_message + ' '
        notification += f'on [{where_from}]: symbol:{symbol} quantity:{quantity} decision_px:{decision_px}'
        if stop_px:
            notification += f' stop_px:{stop_px}'
        if position:
            notification += f', while liquidating position'
        try:
            self.sns.publish(TopicArn=self.defaults.get('sns.topic.arn'), Message=notification,
                             Subject='Bitmex order failed')
        except Exception as e:
            self.logger.warning(e)
            # Capture stack trace if we cannot send out messages, but do not interrupt trading.
            self.logger.error(traceback2.format_exc())

    def broadcast_message(self, symbol, quantity, avg_px, decision_px=None, realized_pnl=None, stop_px=None,
                          ord_status=None):
        ord_status = ord_status.lower() if isinstance(ord_status, str) else 'placed'
        where_from = self.defaults.get('db.name')
        if not stop_px:
            notification = f'Order {ord_status} [{where_from}]: symbol:{symbol} quantity:{quantity}'
        else:
            notification = f'Stop order {ord_status} [{where_from}]: symbol:{symbol} quantity:{quantity} stop_px:{stop_px}'
        if decision_px:
            notification += f' decision_px:{decision_px}'
        if avg_px:
            notification += f' average_price:{avg_px}'
        if realized_pnl:
            notification += f' realized_pnl:{realized_pnl:.16f}'
        try:
            self.sns.publish(TopicArn=self.defaults.get('sns.topic.arn'), Message=notification, Subject='Bitmex trade')
        except Exception as e:
            self.logger.warning(e)
            # Capture stack trace if we cannot send out messages, but do not interrupt trading.
            self.logger.error(traceback2.format_exc())

    def broadcast_waiting(self):
        mkt_price = self.read_market_price()
        notification = f'Wait time began. Market Price: {mkt_price}'
        try:
            self.sns.publish(TopicArn=self.defaults.get('sns.topic.arn'), Message=notification, Subject='Bitmex trade')
        except Exception as e:
            self.logger.warning(e)
            # Capture stack trace if we cannot send out messages, but do not interrupt trading.
            self.logger.error(traceback2.format_exc())

    def broadcast_notrade(self):
        mkt_price = self.read_market_price()
        notification = f'No trade. Market Price: {mkt_price}'
        try:
            self.sns.publish(TopicArn=self.defaults.get('sns.topic.arn'), Message=notification, Subject='Bitmex trade')
        except Exception as e:
            self.logger.warning(e)
            # Capture stack trace if we cannot send out messages, but do not interrupt trading.
            self.logger.error(traceback2.format_exc())

    def place_stop_order(self, symbol, quantity, entry_px, decision_px):
        # Use the long-stop price if selling; otherwise, use the short-stop price.
        # XXX Pad reference price by 10 to avert unwanted executions of Stop orders at market. This should be configurable.
        if quantity < 0:
            side, reference_px = 'long', min(decision_px, entry_px) - 10
        else:
            side, reference_px = 'short', max(decision_px, entry_px) + 10
        stop_px = self.get_stop_threshold(reference_px, side)

        # Set trigger and limit price equal; as these are away from the market, we should be paid maker fees.
        self.logger.info(
            f'Placing stop order: symbol:{symbol} quantity:{quantity} entry_px:{entry_px} decision_px:{decision_px} stop_px:{stop_px}')

        # Support up to 5 retries in case Bitmex rejects our order due to load-shedding policy.
        attempts, new_stop_order = 0, None
        while attempts < 5 and not new_stop_order:
            self.logger.info(f'Attempt to place order on attempt:{attempts}')
            try:
                new_stop_order = self.bitmex_client.Order.Order_new(symbol=symbol, orderQty=quantity, ordType='Stop',
                                                                    stopPx=stop_px).result()
                # Retry if order Canceled; otherwise, break.
                if new_stop_order[0]['ordStatus'] != 'Canceled':
                    break
                else:
                    stop_px += np.sign(quantity) * 10
                    self.logger.info(f'Stop order canceled; move stop_px further from market to {stop_px}')
                    new_stop_order = None
            except bravado.exception.HTTPServiceUnavailable:
                # XXX we should check the error message to be sure the "overloaded" condition happened.
                self.logger.error(traceback2.format_exc())
            except Exception as e:
                self.logger.warning(e)
                self.logger.error(traceback2.format_exc())
                break
            # Bitmex has rejected order due to load-shedding policy. Per docs, wait 500 ms, then retry. Note: this is a blocking sleep().
            sleep(0.5)
            attempts += 1
        if not new_stop_order:
            failure_message = 'from overload condition and/or cancellation' if attempts >= 1 else None
            self.broadcast_order_failure(symbol, quantity, decision_px, stop_px=stop_px,
                                         failure_message=failure_message)
            return StatusCode.ERROR

        # For stop orders, there is no price, just a stop-price.
        create_timestamp = new_stop_order[0]['timestamp'].timestamp()
        self.insert_order(new_stop_order[0]['orderID'], new_stop_order[0]['symbol'], new_stop_order[0]['price'],
                          new_stop_order[0]['side'], new_stop_order[0]['orderQty'], 'Stop', create_timestamp,
                          decision_px, stop_px=new_stop_order[0]['stopPx'])

        self.broadcast_message(symbol, quantity, new_stop_order[0]['avgPx'], decision_px=decision_px, stop_px=stop_px,
                               ord_status=new_stop_order[0]['ordStatus'])

        return StatusCode.OK

    # position parameter is non-null when we are placing an order to close said position.
    def place_order(self, symbol, quantity, decision_px, position=None):
        self.logger.info(f'Place order: symbol:{symbol} quantity:{quantity}')

        # DO NOT use API method Order.Order_newBulk() to post both the new order and the new stop-limit order.
        # Oddly, the API for bulk orders fails when the ordType differs between orders.

        # Support up to 5 retries in case Bitmex rejects our order due to load-shedding policy.
        attempts, new_order = 0, None
        while attempts < 5 and not new_order:
            self.logger.info(f'Attempt to place order on attempt:{attempts}')
            try:
                new_order = self.bitmex_client.Order.Order_new(symbol=symbol, orderQty=quantity,
                                                               ordType='Market').result()
                break
            except bravado.exception.HTTPServiceUnavailable:
                # XXX we should check the error message to be sure the "overloaded" condition happened.
                self.logger.error(traceback2.format_exc())
            except Exception as e:
                self.logger.warning(e)
                self.logger.error(traceback2.format_exc())
                break
            # Bitmex has rejected order due to load-shedding policy. Per docs, wait 500 ms, then retry. Note: this is a blocking sleep().
            sleep(0.5)
            attempts += 1
        if not new_order:
            failure_message = 'from overload condition' if attempts >= 1 else None
            self.broadcast_order_failure(symbol, quantity, decision_px, position=position,
                                         failure_message=failure_message)
            return StatusCode.ERROR

        # Persist new order to data store.
        create_timestamp = new_order[0]['timestamp'].timestamp()
        self.insert_order(new_order[0]['orderID'], new_order[0]['symbol'], new_order[0]['price'], new_order[0]['side'],
                          new_order[0]['orderQty'], 'Market', create_timestamp, decision_px)

        # Register realized P&L only when a position is closed.
        realized_pnl = None
        if position:
            realized_pnl = (1.0 / position['avgEntryPrice'] - 1.0 / new_order[0]['avgPx']) * abs(quantity)
            realized_pnl *= (1.0 - position['commission'])

        # Message interested parties about trade. Include trade-price if order filled.
        self.broadcast_message(symbol, quantity, new_order[0]['avgPx'], decision_px=decision_px,
                               realized_pnl=realized_pnl, ord_status=new_order[0]['ordStatus'])

        # Initiate stop order if we are not closing a position.
        if not position:
            entry_px = float(new_order[0]['avgPx'])
            self.place_stop_order(symbol, -quantity, entry_px, decision_px)

        return StatusCode.OK

    def close_open_positions(self, symbol, decision_px, side=None):
        # Close open positions.
        self.logger.info('Query positions to close')
        try:
            positions = self.bitmex_client.Position.Position_get(filter=json.dumps({"symbol": "XBTUSD"})).result()
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
            return StatusCode.ERROR

        was_error = False
        for pos in positions[0]:
            # Skip over flat positions.
            if pos['currentQty'] == 0: continue

            # Make sure we are on the right side.  Note: short positions are negative.
            if side == 'short' and pos['currentQty'] > 0:
                continue
            if side == 'long' and pos['currentQty'] < 0:
                continue

            # Unwind position by multiplying currentQty by -1.
            symbol = pos['symbol']
            order_qty = -1 * pos['currentQty']
            code = self.place_order(symbol, order_qty, decision_px, position=pos)
            was_error |= code == StatusCode.ERROR

        return StatusCode.OK if not was_error else StatusCode.ERROR

    # Cancel open orders and unwind any open positions. If side is specified, then only unwind
    # positions on the specified side.
    def resolve_positions(self, symbol, decision_px, side=None):
        self.logger.info('Resolve positions')

        # Cancel open orders.
        self.logger.info('Cancel all orders')
        try:
            self.bitmex_client.Order.Order_cancelAll(symbol=symbol).result()
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
            return StatusCode.ERROR

        return self.close_open_positions(symbol, decision_px, side)

    def reconcile_positions_with_decision_logs(self):
        self.logger.info('Reconciling positions with decision logs')
        try:
            positions = self.bitmex_client.Position.Position_get(filter=json.dumps({'symbol': 'XBTUSD'})).result()
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
            return

        # Immediately return if there are no position listings.
        if len(positions[0]) <= 0:
            return

        # Calculate net of short and long decision positions.
        short_decision = self.read_last_decision('XBTUSD', 'short')
        long_decision = self.read_last_decision('XBTUSD', 'long')
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

        self.logger.info(f"net_position:{net_position} positions[0][0]['currentQty']:{positions[0][0]['currentQty']}")
        if net_position != positions[0][0]['currentQty']:
            side = 'short' if positions[0][0]['currentQty'] < 0 else 'long'
            decision_position = abs(positions[0][0]['currentQty'])
            decision_px = positions[0][0]['avgEntryPrice']
            self.write_decision('XBTUSD', side, decision_position, decision_px, active=False, synthetic=True)
            # Maintain flat decision for other side.
            other_side = 'short' if side == 'long' else 'short'
            self.write_decision('XBTUSD', other_side, 0, 0, active=False, synthetic=True)

    def reconcile_fills_and_positions(self):
        self.logger.info('Reconciling fills and positions')

        # Scan trade history up to 1 minute ago, as we should call this method each minute.
        now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
        start_time = now - 60
        start_time_dt = datetime.fromtimestamp(start_time, tz=timezone.utc)
        start_time_str = start_time_dt.strftime("%Y-%m-%d %H:%M")

        # Look back 1 minute. The pitfalls here are (a) that there is network outage longer than that,
        # or (b) that a trade executes during the small window between 1 minute ago and when the
        # trade-history query was last done (which might well be more than 1 minute ago).
        # The count of 64 for results is arbitrary and conceivably could miss some fills.

        self.logger.info('Query trade history')
        try:
            trade_history = self.bitmex_client.Execution.Execution_getTradeHistory(
                symbol='XBTUSD', count=64, reverse=True, filter=json.dumps(
                    {"execType": "Trade", "startTime": start_time_str})).result()
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
            return

        for trade in trade_history[0]:
            self.insert_fill_conditionally(trade)
            # Broadcast status of Stop orders if (i) order was completely filled or (ii) order was cancelled.
            case1 = trade['ordStatus'] == 'Filled' and trade['cumQty'] == trade['orderQty']
            case2 = trade['ordStatus'] == 'Canceled'
            if trade['ordType'] == 'Stop' and (case1 or case2):
                # Use negative quantity for sell-side trades.
                quantity = trade['cumQty'] if trade['side'] == 'Buy' else -trade['cumQty']
                self.broadcast_message(trade['symbol'], quantity, trade['avgPx'], stop_px=trade['stopPx'],
                                       ord_status=trade['ordStatus'])

        self.logger.info('Query positions to persist')
        try:
            positions = self.bitmex_client.Position.Position_get(filter=json.dumps({'symbol': 'XBTUSD'})).result()
        except Exception as e:
            self.logger.warning(e)
            self.logger.error(traceback2.format_exc())
            return

        for pos in positions[0]:
            self.insert_position(pos)

    # Reconcile broker-side notion of trades / positions with our backend.
    def reconcile_fills_and_positions_after_delay(self, delay):
        t = threading.Timer(delay, self.reconcile_fills_and_positions)
        try:
            t.start()
        except Exception as e:
            self.logger.warning(e)
            t.cancel()

    def get_stop_threshold(self, px, side):
        if side == 'long':
            use_absolute = self.defaults.getboolean('bitmex.tradebot.decision.long.stop.delta.absolute')
            delta = self.defaults.getfloat('bitmex.tradebot.decision.long.stop.delta', 0)
        else:
            use_absolute = self.defaults.getboolean('bitmex.tradebot.decision.short.stop.delta.absolute')
            # Negate delta for shorts as stop-price for shorts opposes direction of the stop-price for longs.
            delta = -self.defaults.getfloat('bitmex.tradebot.decision.short.stop.delta', 400)
        if use_absolute:
            stop_threshold = px - delta
        else:
            stop_threshold = (1.0 - delta) * px
        return stop_threshold

    def exceeds_stop_threshold(self, last_px, decisions, side):
        # No stop-condition triggers if we do not hold any open position.
        if len(decisions) <= 0 or abs(decisions[-1]['position']) <= 0:
            return False

        # Time-stop triggers when the current position has been held 3 or more hours.
        if sum([np.sign(d['position']) for d in decisions[0:]]) >= 180:
            return True

        # A more restricted version of the time-stop triggers if there are gaps in the decision log.
        # We assume gaps if the time elapsed between the first and last decision is 3 or more hours,
        # which equates to 10740 seconds (actually 60 seconds less than 3 hours, as we assume the first
        # minute-sample is recorded after the initial 60 seconds of the 3-hour time-swath has expired).

        if sum([np.sign(d['position']) for d in decisions[0:]]) >= len(decisions) >= 2 and \
                (decisions[-1]['timestamp_dt'].timestamp() - decisions[0]['timestamp_dt'].timestamp()) >= 10740:
            return True

        stop_threshold = self.get_stop_threshold(float(decisions[-1]['price']), side)
        self.logger.info(
            f'Check whether stop-price reached for last_px:{last_px} side:{side} stop_threshold:{stop_threshold}')

        if side == 'long' and last_px < stop_threshold:
            self.logger.info('Stop threshold exceeded (long decision)')
            return True

        if side == 'short' and last_px > stop_threshold:
            self.logger.info('Stop threshold exceeded (short decision)')
            return True

        return False

    def make_long_trading_decision(self, df):
        self.logger.info('Make long trading decision.')

        # Get current position, 1+ for long/short, 0 for flat.
        decisions = self.read_decisions('XBTUSD', 'long', 1)
        cur_position = decisions[-1]['position'] if len(decisions) else 0
        last_px = decisions[-1]['price'] if len(decisions) else 0
        last_buy_fill = self.read_last_fill('XBTUSD', 'BUY')
        avg_px = 0
        if last_buy_fill:
            avg_px = last_buy_fill['avg_px'] if len(last_buy_fill) else 0
        exit_px = min(last_px, avg_px)
        mkt_price = self.read_market_price()
        stop_threshold = 10 + self.defaults.getfloat('bitmex.tradebot.decision.long.stop.delta', 3)
        last_idx = -1
        self.logger.info(
            f'df.z_180.iloc[last_idx]:{df.z_180.iloc[last_idx]} df.close_px.iloc[last_idx]:{df.close_px.iloc[last_idx]} stop threshold:{stop_threshold} mkt_price:{mkt_price}')

        # Default decision position/px in case no trade takes place below.
        decision_position, decision_px = cur_position, last_px

        if df.z_180.iloc[-1] > 10 and cur_position == 0 and df.volatility_180.iloc[-2] < 0.0005:
            self.logger.info(
                f'Open new position only if it implies a change in our current position of {cur_position}.')
            long_size = self.defaults.getint('bitmex.tradebot.decision.long.size')
            code = self.place_order('XBTUSD', long_size, df.close_px.iloc[-1])
            if code == StatusCode.OK:
                decision_position, decision_px = 1, last_px
        elif df.chg_5.iloc[-1] < -25 or (cur_position == 1 and df.low.iloc[-1] < exit_px - stop_threshold):
            self.logger.info(
                f'Close position, but only if it implies a change in our current position of {cur_position}.')
            code = self.resolve_positions('XBTUSD', exit_px, 'long')
            if code == StatusCode.OK:
                decision_position, decision_px = 0, 0
        else:
            self.logger.info('Hold onto current position.')

        # Each time the trading trigger fires, we write this decision for our long strategy.
        self.write_decision('XBTUSD', 'long', decision_position, decision_px, mkt_price=mkt_price)

    def make_short_trading_decision(self, df):
        self.logger.info('Make short trading decision.')

        # Get current position, 1+ for long/short, 0 for flat.
        decisions = self.read_decisions('XBTUSD', 'short', 180)
        cur_position = decisions[-1]['position'] if len(decisions) else 0
        threshold = self.defaults.getfloat('bitmex.tradebot.decision.short.threshold', 3)
        last_idx = len(df.index) - 1
        self.logger.info(
            f'df.ma_comps.iloc[last_idx]:{df.ma_comps.iloc[last_idx]} df.close_px.iloc[last_idx]:{df.close_px.iloc[last_idx]} df.close_px.iloc[last_idx-1]:{df.close_px.iloc[last_idx - 1]} df.ma_20_days.iloc[last_idx]:{df.ma_20_days.iloc[last_idx]} threshold:{threshold}')

        # Default decision position/px in case no trade takes place below.
        last_px = decisions[-1]['price'] if len(decisions) else 0
        decision_position, decision_px = cur_position, last_px

        if cur_position <= 0 \
                and df.ma_comps.iloc[last_idx] >= threshold \
                and df.close_px.iloc[last_idx - 1] * 0.99 > df.close_px.iloc[last_idx] > df.ma_20_days.iloc[last_idx]:
            self.logger.info(
                f'Open new position only if it implies a change in our current position of {cur_position}.')
            short_size = self.defaults.getint('bitmex.tradebot.decision.short.size')
            # negative quantity means short the contract
            code = self.place_order('XBTUSD', -short_size, df.close_px.iloc[last_idx])
            if code == StatusCode.OK:
                decision_position, decision_px = short_size, df.close_px.iloc[last_idx]
        elif self.exceeds_stop_threshold(df.close_px.iloc[last_idx], decisions, 'short'):
            self.logger.info(
                f'Close position after 3 hours, but only if it implies a change in our current position of {cur_position}.')
            code = self.resolve_positions('XBTUSD', df.close_px.iloc[last_idx],
                                          'short') if cur_position > 0 else StatusCode.OK
            if code == StatusCode.OK:
                decision_position, decision_px = 0, 0
        else:
            self.logger.info('Hold onto current position.')

        # Each time the trading trigger fires, we write this decision for our short strategy.
        self.write_decision('XBTUSD', 'short', decision_position, decision_px)

    def conditionally_trade(self):
        now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
        self.logger.info(f'Trading trigger fired at {now}')

        # Incorporate any external position-changes into our decision logs.
        self.reconcile_positions_with_decision_logs()

        # Read the last 21 days of 1m trade-buckets into Panda dataframe.
        df = self.read_trade_buckets_into_dataframe('XBTUSD', 21)
        if df.empty: return

        # Resample data, eliminating unused columns.
        df['time'] = pd.to_datetime(df.timestamp_dt)
        df['my_date'] = df.time.dt.date
        df['hour'] = df.time.dt.hour

        del df['timestamp_dt']
        del df['high_px']
        del df['home_notional']

        df.index = pd.DatetimeIndex(df.time)
        # one minute version use 1 min bars with no resampling
        df['chg_5'] = df.close_px - df.close_px.shift(5)

        df['pct_chg'] = df['close_px'] / df['close_px'].shift(1) - 1
        df['pct_fwd'] = df['pct_chg'].shift(-1)
        df['pct_5'] = df['close_px'] / df['close_px'].shift(5) - 1

        df['volatility_180'] = df.pct_chg.rolling(180).std()
        df['z_180'] = df.pct_5 / df.volatility_180

        df = df[-2:]

        # Consider long trade.
        self.make_long_trading_decision(df)

        # Consider short trade.
        # self.make_short_trading_decision(df)

        # Update any new fills and positions.
        self.reconcile_fills_and_positions_after_delay(3)

    def gracefully_finish(self):
        self.logger.info("Got Interrupt Signal. Gracefully Closing Bot.")
        self.logger.info("Bot Closed.......")
        self.notify("Trading Bot Stopped.")
