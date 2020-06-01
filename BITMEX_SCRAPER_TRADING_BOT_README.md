# Bitmex Trading Bot

This bot trades against Bitmex.  It accesses the Bitmex API through a [Python client](https://github.com/BitMEX/api-connectors/tree/master/official-http/python-swaggerpy).

## Installation.

Install system dependencies and python modules as follows:

Move to project directory

    $ cd /path/to/bitmex

Instal the Python 3.6 and MySql 5.7. 

    $ ./scripts/setup/bitmex-install.sh

Note*: Do change the script according to the installed package manager. Script is written for **yum**.

Install the Dependent python libraries.
List of required python libraries is [here](requirements.txt)

    $ python3 -m pip install -r requirements.txt
    sudo yum install python36-devel  # for psutil

Cretea the below Tables in configured Database.

    $ mysql -u username -p password database_name < ./scripts/sql/create-tables-updated.sql
    
    bitmex\scripts\sql\create-tables-updated.sql
    /home/ec2-user/bitmex/scripts/sql/create-tables-updated.sql


# Trading Strategies:
As of this writing, there are two strategies implemented in two different github branch.
1. feature-scraper
2. algo2

# BitmexTradescraper Class:
This class subscribes to bitmex's **tradeBin1m**. That means, bitmex will publish every minute 1-minute trade bins to subscribers. i.e at every minute, we will have the updated data.

# BitmexTradingBot Class:
On every update form the bitmex to scraper, scraper will raise an event as **UPDATE_EVENT**. On this event, **BitmexTradingBot** will reconsile the decisions or positions from the bitmex. After reconcilation, it will take short/long buy/sell decision.


# Code Flow:
1. creating two task thread as : scraper and trade bot.
2. scraper subscribes to bitmex's tradeBin1m topic.
3. bitmex publishes data to scraper at 1 min of interval
4. on data receive, scraper publish an UPDATE_EVENT to trade bot.
5. on UPDATE_EVENT, bot takes decisions.
6. above 3-5 step will be in loop.

*Note: Bot will be taking decisons every minute.

## Launching the trading bot.
    nohup python3 ./bitmex_scraper_trading_bot.py --instance 2 2>&1 &> /dev/null &

## Stopping the scraper and the bot.
    kill -15 $(ps aux | grep '[b]itmex_scraper_trading_bot.py' | awk '{print $2}') 



# Monitoring:
## bot_monitor.py
* it will be monitoring the trading bot process.
* if it doesn't find the process, it will send an alert and try to re-start the Trading Bot.
* this check will be triggered at n mins of interval. So the max downtime would be n mins.
* it will also keep reading the logs.
* if it finds keywords: Error or Exception in log, it will count that and send an alert.
* **config/bitmex_monitor_bot.ini**: to configure the script and the insatnce.

## Starting the monitor bot
    nohup python3 bot_monitor.py 2>&1 &> /dev/null &

## Stopping the monitor bot.
    kill -15 $(ps aux | grep '[b]ot_monitor.py' | awk '{print $2}')



## Monitoring activity.

Aside from simply previewing script logs under `bitmex/logs`, you may monitor activity with certain commands issued from the command-line shell, or from the MySQL client shell `mysql`.

### Monitoring bot activity from the command-line shell.

To see if the scripts are running, run this command:

    $ ps eax | grep python3

That should show your the *nix processes running the trading bot and trade-bucket-scraper.

### Monitoring bot activity from `mysql` shell.

Our scripts read/write data to a MySQL data store.  You can view records from tables in this data store to gauge recent activity.  For example, to see what trading decisions have been made recently, you can do this:
```
mysql> select * from decisions order by timestamp_dt desc limit 32;
+---------------------+--------+-------+----------+-------------+-----------+
| timestamp_dt        | symbol | side  | position | price       | synthetic |
+---------------------+--------+-------+----------+-------------+-----------+
| 2020-02-05 19:14:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:14:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:13:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:13:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:12:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:12:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:11:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:11:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:10:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:10:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:09:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:09:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:08:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:08:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:07:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:07:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:06:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:06:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:05:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:05:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:04:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:04:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:03:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:03:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:02:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:02:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:01:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:01:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 19:00:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 19:00:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
| 2020-02-05 18:59:02 | XBTUSD | short |        1 | 9677.000000 |         0 |
| 2020-02-05 18:59:02 | XBTUSD | long  |        0 |    0.000000 |         0 |
+---------------------+--------+-------+----------+-------------+-----------+
32 rows in set (0.00 sec)
```
They `synthetic` column would only be true (ie, `1`) in the event that the trading bot reconciled a difference between an external trade (as acknowledged by open positions on our account on Bitmex) and the bot's internal record of decisions.

Looking at the record of `fills` tells us what trades have actually happened, and when:
```
mysql> select * from fills order by transaction_dt desc limit 16;
+---------------------+--------------------------------------+--------------------------------------+--------+------+-------------+-------------+-----------+------------+-----------------+-------------+----------+------------+---------+--------+---------------------+
| transaction_dt      | exec_id                              | order_id                             | symbol | side | price       | stop_px     | order_qty | order_type | order_status    | last_px     | last_qty | leaves_qty | cum_qty | avg_px | created_dt          |
+---------------------+--------------------------------------+--------------------------------------+--------+------+-------------+-------------+-----------+------------+-----------------+-------------+----------+------------+---------+--------+---------------------+
| 2020-02-05 18:30:03 | 42c8d0a8-67b2-5259-3021-dc2100b09fd5 | 64d1c1a5-a0c9-5812-82fb-9963005c1af4 | XBTUSD | Sell | 9653.500000 |        NULL |         1 | Market     | Filled          | 9653.500000 |        1 |          0 |       1 |   9654 | 2020-02-05 18:30:07 |
| 2020-02-05 10:30:03 | e97aa5bc-a84a-063a-4266-e09621159b02 | b2ac6225-acb1-77ef-2ebd-e53c2ce30251 | XBTUSD | Sell | 9319.000000 | 9319.000000 |     10000 | StopLimit  | Filled          | 9320.500000 |    10000 |          0 |   10000 |   9321 | 2020-02-05 10:30:06 |
| 2020-02-05 10:30:02 | 79d0218e-4c69-ec3f-02e9-f9478b7930b9 | 15578644-d730-32c0-1b25-291bda073ca0 | XBTUSD | Buy  | 9321.000000 |        NULL |     10000 | Market     | Filled          | 9321.000000 |    10000 |          0 |   10000 |   9322 | 2020-02-05 10:30:06 |
| 2020-02-05 10:29:03 | 61c4828d-9116-34b7-40e9-27b4326a573b | 5b87b967-1a34-580c-4d89-9bca5f048950 | XBTUSD | Sell | 9327.000000 | 9327.000000 |     10000 | StopLimit  | Filled          | 9328.500000 |    10000 |          0 |   10000 |   9329 | 2020-02-05 10:29:05 |
| 2020-02-05 10:29:02 | ea4d5f15-1190-d357-b6c0-99c171244ba9 | 3c735c9c-c673-7033-8671-2471ac3dc8c4 | XBTUSD | Buy  | 9329.000000 |        NULL |     10000 | Market     | Filled          | 9329.000000 |    10000 |          0 |   10000 |   9330 | 2020-02-05 10:29:05 |
| 2020-02-05 10:28:02 | 7c6e9a63-7b94-4508-c826-7d6c48f7efd3 | 3f371668-657e-9414-bc2c-6beb77857eca | XBTUSD | Sell | 9327.500000 | 9327.500000 |     10000 | StopLimit  | Filled          | 9330.000000 |    10000 |          0 |   10000 |   9330 | 2020-02-05 10:28:04 |
| 2020-02-05 10:28:01 | b4514075-5afd-9579-90de-41f095323e5f | 188002fb-8abb-dd6c-4e7a-3d84e2bf6eca | XBTUSD | Buy  | 9330.500000 |        NULL |     10000 | Market     | Filled          | 9330.500000 |    10000 |          0 |   10000 |   9330 | 2020-02-05 10:28:04 |
| 2020-02-05 10:25:01 | 4af68c51-5458-2164-e5d5-89cfd28dac67 | 2fbc3887-f2c0-7c25-4fab-236cae57801f | XBTUSD | Buy  | 9291.500000 |        NULL |     10000 | Market     | Filled          | 9291.500000 |    10000 |          0 |   10000 |   9291 | 2020-02-05 10:25:04 |
| 2020-02-05 10:25:01 | 82389222-0451-c6c4-c578-b628d0b1a681 | 9054cbea-08ff-1abd-b9f9-1cb4dbe5280a | XBTUSD | Sell | 9288.500000 | 9288.500000 |     10000 | StopLimit  | Filled          | 9291.000000 |    10000 |          0 |   10000 |   9291 | 2020-02-05 10:25:04 |
| 2020-02-03 11:44:02 | 9120ba10-ff08-6103-a292-39fc18214885 | 3329723c-8de6-093b-60a5-ca68522d27bc | XBTUSD | Sell | 9363.000000 |        NULL |     10000 | Market     | Filled          | 9363.000000 |    10000 |          0 |   10000 |   9364 | 2020-02-03 11:44:05 |
| 2020-02-03 11:43:02 | 76cdf5f3-a1be-2ce3-bed0-a976bb63773b | 84bb0cbf-3ac6-1585-a001-62d17278444c | XBTUSD | Buy  | 9358.500000 |        NULL |     10000 | Market     | Filled          | 9358.500000 |    10000 |          0 |   10000 |   9359 | 2020-02-03 11:43:04 |
| 2020-02-03 05:02:01 | d1dc48e3-1e55-e22e-060a-e8da41dd9a63 | 14d695c1-8f6f-4fab-7c31-9a20647dcd5f | XBTUSD | Buy  | 9380.000000 |        NULL |         1 | Market     | Filled          | 9380.000000 |        1 |          0 |       1 |   9380 | 2020-02-03 05:02:04 |
| 2020-02-03 02:02:07 | fd6755a6-30b8-8624-8fcb-cab846e9747f | d0065120-9e35-47d3-3ff7-59aa698caf65 | XBTUSD | Sell | 9325.500000 |        NULL |         1 | Market     | Filled          | 9325.500000 |        1 |          0 |       1 |   9326 | 2020-02-03 02:02:10 |
| 2020-02-03 02:02:05 | 7f8b205c-2b63-990a-c0e5-b99c3c67db5d | da0401cd-9f38-3f24-052d-7cc11d7f4e30 | XBTUSD | Sell | 9341.500000 |        NULL |     10000 | Market     | PartiallyFilled | 9341.500000 |     3466 |       6534 |    3466 |   9342 | 2020-02-03 02:02:10 |
| 2020-02-03 02:02:05 | dae93b07-7acc-255c-5a82-419f4990a315 | da0401cd-9f38-3f24-052d-7cc11d7f4e30 | XBTUSD | Sell | 9341.500000 |        NULL |     10000 | Market     | Filled          | 9341.500000 |     6534 |          0 |   10000 |   9342 | 2020-02-03 02:02:10 |
| 2020-02-03 01:32:03 | 8a20e08a-0bf4-c775-5f4e-f68cb7ba5673 | bfa1630f-04da-7e49-ac65-5c0da1093164 | XBTUSD | Buy  | 9540.000000 |        NULL |     10000 | Market     | PartiallyFilled | 9540.000000 |     1389 |       8611 |    1389 |   9540 | 2020-02-03 01:32:07 |
+---------------------+--------------------------------------+--------------------------------------+--------+------+-------------+-------------+-----------+------------+-----------------+-------------+----------+------------+---------+--------+---------------------+
16 rows in set (0.01 sec)
```
To see a recent, per-minute snapshots of open positions, you can do this:
```
mysql> select * from positions order by current_timestamp_dt desc limit 16;
+-------+--------+-------------+----------------+----------------+----------------------+
| pid   | symbol | current_qty | avg_cost_price | unrealised_pnl | current_timestamp_dt |
+-------+--------+-------------+----------------+----------------+----------------------+
| 14099 | XBTUSD |          -1 |    9653.500000 |     -45.000000 | 2020-02-05 19:16:05  |
| 14098 | XBTUSD |          -1 |    9653.500000 |     -39.000000 | 2020-02-05 19:15:05  |
| 14097 | XBTUSD |          -1 |    9653.500000 |     -39.000000 | 2020-02-05 19:14:05  |
| 14096 | XBTUSD |          -1 |    9653.500000 |     -35.000000 | 2020-02-05 19:13:05  |
| 14095 | XBTUSD |          -1 |    9653.500000 |     -43.000000 | 2020-02-05 19:12:05  |
| 14094 | XBTUSD |          -1 |    9653.500000 |     -32.000000 | 2020-02-05 19:11:05  |
| 14093 | XBTUSD |          -1 |    9653.500000 |     -12.000000 | 2020-02-05 19:10:05  |
| 14092 | XBTUSD |          -1 |    9653.500000 |      -6.000000 | 2020-02-05 19:09:05  |
| 14091 | XBTUSD |          -1 |    9653.500000 |      -7.000000 | 2020-02-05 19:08:05  |
| 14090 | XBTUSD |          -1 |    9653.500000 |      -8.000000 | 2020-02-05 19:07:05  |
| 14089 | XBTUSD |          -1 |    9653.500000 |     -11.000000 | 2020-02-05 19:06:05  |
| 14088 | XBTUSD |          -1 |    9653.500000 |      -8.000000 | 2020-02-05 19:05:05  |
| 14087 | XBTUSD |          -1 |    9653.500000 |     -21.000000 | 2020-02-05 19:04:05  |
| 14086 | XBTUSD |          -1 |    9653.500000 |     -14.000000 | 2020-02-05 19:03:05  |
| 14085 | XBTUSD |          -1 |    9653.500000 |     -38.000000 | 2020-02-05 19:02:05  |
| 14084 | XBTUSD |          -1 |    9653.500000 |     -44.000000 | 2020-02-05 19:01:05  |
+-------+--------+-------------+----------------+----------------+----------------------+
16 rows in set (0.01 sec)
```
The trading bot also maintains an archive of orders that it posts to the Bitmex API.  You can view recent orders like this:
```
mysql> select * from orders order by created_dt desc limit 16;
+--------------------------------------+--------+--------------+-------------+--------------+------+----------+------------+---------------------+
| order_id                             | symbol | price        | decision_px | stop_px      | side | quantity | order_type | created_dt          |
+--------------------------------------+--------+--------------+-------------+--------------+------+----------+------------+---------------------+
| 5c6e1fb2-cbc7-ea09-bf0f-7515905c95a2 | XBTUSD | 10053.500000 | 9677.000000 | 10053.500000 | Buy  |        1 | StopLimit  | 2020-02-05 18:30:04 |
| 64d1c1a5-a0c9-5812-82fb-9963005c1af4 | XBTUSD |  9653.500000 | 9677.000000 |         NULL | Sell |        1 | Market     | 2020-02-05 18:30:03 |
| b2ac6225-acb1-77ef-2ebd-e53c2ce30251 | XBTUSD |  9319.000000 | 9328.500000 |  9319.000000 | Sell |    10000 | StopLimit  | 2020-02-05 10:30:03 |
| 15578644-d730-32c0-1b25-291bda073ca0 | XBTUSD |  9321.000000 | 9328.500000 |         NULL | Buy  |    10000 | Market     | 2020-02-05 10:30:02 |
| 5b87b967-1a34-580c-4d89-9bca5f048950 | XBTUSD |  9327.000000 | 9330.000000 |  9327.000000 | Sell |    10000 | StopLimit  | 2020-02-05 10:29:03 |
| 3c735c9c-c673-7033-8671-2471ac3dc8c4 | XBTUSD |  9329.000000 | 9330.000000 |         NULL | Buy  |    10000 | Market     | 2020-02-05 10:29:02 |
| 3f371668-657e-9414-bc2c-6beb77857eca | XBTUSD |  9327.500000 | 9347.500000 |  9327.500000 | Sell |    10000 | StopLimit  | 2020-02-05 10:28:02 |
| 188002fb-8abb-dd6c-4e7a-3d84e2bf6eca | XBTUSD |  9330.500000 | 9347.500000 |         NULL | Buy  |    10000 | Market     | 2020-02-05 10:28:01 |
| 9054cbea-08ff-1abd-b9f9-1cb4dbe5280a | XBTUSD |  9288.500000 | 9286.000000 |  9288.500000 | Sell |    10000 | StopLimit  | 2020-02-05 10:25:01 |
| 2fbc3887-f2c0-7c25-4fab-236cae57801f | XBTUSD |  9291.500000 | 9286.000000 |         NULL | Buy  |    10000 | Market     | 2020-02-05 10:25:01 |
| 3329723c-8de6-093b-60a5-ca68522d27bc | XBTUSD |  9363.000000 | 9358.000000 |         NULL | Sell |    10000 | Market     | 2020-02-03 11:44:02 |
| 84bb0cbf-3ac6-1585-a001-62d17278444c | XBTUSD |  9358.500000 | 9371.500000 |         NULL | Buy  |    10000 | Market     | 2020-02-03 11:43:02 |
| 8b359216-9cf6-b985-74c7-9cf5fb4f6ac8 | XBTUSD |  9356.500000 | 9371.500000 |  9359.000000 | Sell |    10000 | StopLimit  | 2020-02-03 11:43:02 |
| 14d695c1-8f6f-4fab-7c31-9a20647dcd5f | XBTUSD |  9380.000000 | 9379.500000 |         NULL | Buy  |        1 | Market     | 2020-02-03 05:02:01 |
| d0065120-9e35-47d3-3ff7-59aa698caf65 | XBTUSD |  9325.500000 | 9250.500000 |         NULL | Sell |        1 | Market     | 2020-02-03 02:02:07 |
| da0401cd-9f38-3f24-052d-7cc11d7f4e30 | XBTUSD |  9341.500000 | 9250.500000 |         NULL | Sell |    10000 | Market     | 2020-02-03 02:02:05 |
+--------------------------------------+--------+--------------+-------------+--------------+------+----------+------------+---------------------+
16 rows in set (0.00 sec)
```

## Other documentation.

See this [github repo](https://github.com/BitMEX/api-connectors/tree/master/official-http/python-swaggerpy) for simple examples of how the Python client connects to the Bitmex API.

Documentation for Python 3.x is [available online](https://docs.python.org/3/index.html).

See this [github repo](https://github.com/Yelp/bravado/blob/master/bravado/exception.py) for a list of exceptions the Python client might return when Bitmex API errors happen.

Documentation for the Bitmex RESTful API is [available here](https://www.bitmex.com/app/restAPI).  There are also useful tips for order-processing on Bitmex throughout the site at `bitmex.com`.

That's all for now!
