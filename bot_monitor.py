import psutil
import boto3
import traceback2
import sys
import logging
import subprocess
import os
import time
import io
import configparser

from logging.handlers import RotatingFileHandler

def publish_through_boto3(notification):
        try:
            logger.info(notification)
            sns = boto3.session.Session(profile_name='bitmex-sns').client('sns')
            sns.publish(TopicArn=defaults.get('sns.topic.arn'), Message=notification, Subject='Bitmex trade')
        except Exception:
            logger.info(traceback2.format_exc())
            sys.exit(1)

def try_starting_bot():
    logger.info("Trying To Start The Bot.")
    os.system(f'nohup python3 ./{script_to_monitor} --instance {restart_config_to_pick} 2>&1 &> /dev/null &')
    logger.info("Checking Bot Re-start Status.")
    if checkIfProcessRunning(script_to_monitor):
        logger.info("Bot  Started.")
    else:
        logger.info("Send An Alert")
        publish_through_boto3("Re-Starting Bot Failed.")
    
def count_error_logs(log_stream):
    count = 0
    while True:
        line = log_stream.readline()
        if len(line) > 0:
            line = line.lower()
            if ('ERROR'.lower() in line) or ('EXCEPTION'.lower() in line):
                count = count + 1
        else:
            return count


def get_logger():
	logger = logging.getLogger('bot')
	logger.setLevel(logging.DEBUG)
	# create file handler which logs even debug messages
	fh = RotatingFileHandler(defaults.get('log.monitor.outfile'), maxBytes=20000000, backupCount = 4)
	fh.setLevel(logging.INFO)
	# create console handler with a higher log level
	ch = logging.StreamHandler()
	ch.setLevel(logging.INFO)
	# create formatter and add it to the handlers
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	ch.setFormatter(formatter)
	fh.setFormatter(formatter)
	# add the handlers to logger
	logger.addHandler(ch)
	logger.addHandler(fh)
	return logger

def checkIfProcessRunning(scriptName):
    '''
    Check if there is any running process that contains the given name processName.
    '''
    #Iterate over the all the running process
    for proc in psutil.process_iter():
        try:
            if len(proc.cmdline()) > 1:
                if (proc.cmdline()[1].endswith(scriptName)):
                    logger.info(f"Bot Is Running With Pid: {proc.pid}")
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def interrupt_handler(sif, frame):
    publish_through_boto3("Monitor Bot Closed. Got Signal:{sif}")
    sys.exit(0)

# Read configuration.
config = configparser.ConfigParser()
config.read(f'config/bitmex_monitor_bot.ini')
defaults = config['DEFAULT']

script_to_monitor = defaults.get('bitmex.start.script.name', 'bitmex_scraper_trading_bot.py')
monitor_interval = defaults.getint('bitmex.monitor.check.interval', 10)
restart_config_to_pick = defaults.getint('bitmex.restart.ini', 0)

logger = get_logger()
bot_file_stream = io.open('logs/bitmex_trading_bot.log', mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True)
scrapper_file_stream = io.open('logs/bitmex_trade_buckets.log', mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True)
while(True):
    if checkIfProcessRunning(script_to_monitor):
        bot_error_count = count_error_logs(bot_file_stream)
        if(bot_error_count > 0):
            logger.info(f'Send an alert about bot error: {bot_error_count}')
            publish_through_boto3(f'There were exceptions:{bot_error_count} in Bitmex Trading bot')
        scraper_error_count = count_error_logs(scrapper_file_stream)
        if scraper_error_count > 0:
            logger.info(f'Send an alert about scraper error: {scraper_error_count}')
            publish_through_boto3(f'There were exceptions:{scraper_error_count} in Bitmex Scraper bot')
    else:
        publish_through_boto3("Trading Bot Is Not Running : Will Try to Re Start.")
        try_starting_bot()
        logger.info('Trading Bot process was not running. Re-start Tsriggered')
    time.sleep(monitor_interval * 60) # checks every 10 mins


