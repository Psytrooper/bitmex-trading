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
    
    mysql -u dbmasteruser -h ls-4e56047ea277b5a32fe49d197ed4a95b9bed4934.cvbyip4fxbpt.eu-west-1.rds.amazonaws.com -p samellasneed < ./scripts/sql/create-tables-updated.sql
    
    mysql -u dbmasteruser -h ls-4e56047ea277b5a32fe49d197ed4a95b9bed4934.cvbyip4fxbpt.eu-west-1.rds.amazonaws.com -p 
    -p {|W]}3{yfgL|~lHO)Ggvwu>9t_vk}TY1
    
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

## Stoping the scraper and the bot.
    kill -15 $(ps aux | grep '[b]itmex_scraper_trading_bot.py' | awk '{print $2}') 



# Minitoring:
## bot_monitor.py
* it will be monitoring the trading bot process.
* if it doesn't find the process, it will send an alert and try to re-start the Trading Bot.
* this check will be triggered at n mins of interval. So the max downtime would be n mins.
* it will also keep reading the logs.
* if it finds keywords: Error or Exception in log, it will count that and send an alert.
* **config/bitmex_monitor_bot.ini**: to configure the script and the insatnce.

## Starting the monitor bot
    nohup python3 bot_monitor.py 2>&1 &> /dev/null &

## Stoping the monitor bot.
    kill -15 $(ps aux | grep '[b]ot_monitor.py' | awk '{print $2}')
