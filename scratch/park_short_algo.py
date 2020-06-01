#!/usr/bin/env python
# coding: utf-8

# In[1]:


# import packages
import pandas as pd
import numpy as np
import datetime
import time
import math


# In[2]:


df = pd.read_csv('D:/Users/scaleIT/Dropbox/ipython/Data/Park/bitmex-btc-ohlcv-1-minute-data.csv')
del df['Unnamed: 0']
df['time'] = pd.to_datetime(df.timestamp)
df['my_date'] = df.time.dt.date
df['hour'] = df.time.dt.hour
del df['timestamp']
del df['foreignNotional']
del df['lastSize']
del df['turnover'] # what is this?
del df['trades']
del df['open']
del df['vwap']
del df['symbol']


# In[3]:


# delete 2017
df = df[350000:]


# In[4]:


df.index = pd.DatetimeIndex(df.time)
five_min = pd.DataFrame()
five_min['close'] = df.close.resample('5min').last()
five_min['high'] = df.high.resample('5min').max()
five_min['homeNotional'] = df.homeNotional.resample('5min').sum()
five_min['low'] = df.low.resample('5min').min()
five_min['volume'] = df.homeNotional.resample('5min').sum()
five_min['my_date'] = df.my_date.resample('5min').last()
five_min['hour'] = df.hour.resample('5min').last()
five_min['time'] = df.time.resample('5min').last()


five_min['ma_5'] = five_min['close'].rolling(5).mean()
five_min['ma_10'] = five_min['close'].rolling(10).mean()
five_min['ma_20'] = five_min['close'].rolling(20).mean()
five_min['ma_50'] = five_min['close'].rolling(50).mean()
five_min['ma_200'] = five_min['close'].rolling(200).mean()
five_min['ma_20_days'] = five_min['close'].rolling(5760).mean()


five_min['pct_chg'] = five_min['close'] / five_min['close'].shift(1) - 1
#five_min['pct_chg_5'] = five_min['close'] / five_min['close'].shift(5) - 1
five_min['pct_chg_60'] = five_min['close'] / five_min['close'].shift(12) - 1
five_min['pct_fwd'] = five_min['pct_chg'].shift(-1)
#five_min['volatility_240'] = five_min.pct_chg.rolling(240).std()
five_min['volatility_480'] = five_min.pct_chg.rolling(96).std()
five_min['volatility_5_day'] = five_min.pct_chg_60.rolling(1440).std()
five_min['volatility_20_day'] = five_min.pct_chg_60.rolling(5760).std()


#five_min['z_240'] = five_min.pct_chg / five_min.volatility_240
five_min['z_480'] = five_min.pct_chg / five_min.volatility_480
five_min['z_5_day'] = five_min.pct_chg_60 / five_min.volatility_5_day

def vwap(df):
    q = df.volume.values
    p = df.close.values
    return df.assign(vwap_running=(p * q).cumsum() / q.cumsum())

five_min = five_min.groupby(five_min.my_date, group_keys=False).apply(vwap)

five_min = five_min[5760:]

df = five_min

df['ma_5_10'] = np.where(df.ma_5 > df.ma_10,1,0)
df['ma_10_20'] = np.where(df.ma_10 > df.ma_20,1,0)
df['ma_20_50'] = np.where(df.ma_20 > df.ma_50,1,0)
df['ma_50_200'] = np.where(df.ma_50 > df.ma_200,1,0)

df['ma_comps'] = df[['ma_5_10', 'ma_10_20', 'ma_20_50', 'ma_50_200']].sum(axis=1)


# In[5]:


# trading system logic short side

# 5min testing
df['position'] = 0
df['entry'] = 0
new = [df.position.iloc[0]]
new_2 = [df.entry.iloc[0]]
for i in range(1, len(df.index)): 
    if df.ma_comps.iloc[i] >= 3 and df.close.iloc[i] < df.close.iloc[i-1]*0.99 and df.close.iloc[i] > df.ma_20_days.iloc[i]:
        new.append(1)
        new_2.append(df.close.iloc[i])
    elif sum(new[-36:]) == 36 or df.close.iloc[i] > new_2[-1]+400:
        new.append(0)
        new_2.append(0)
    else:
        #new.append(0)
        new.append(new[i-1])
        new_2.append(new_2[i-1])
df['position'] = new
df['entry'] = new_2

df['buys'] = np.where((df.position == 1) & (df.position.shift(1) == 0), 1, 0)
df['sells'] = np.where((df.position == 0) & (df.position.shift(1) == 1), 1, 0)

df.loc[df['sells'] == 1, 'close'] 
df.loc[df['buys'] == 1, 'close']

#changed position to 'buys' and 'sells'
all_trades = pd.concat([
        pd.DataFrame({'Price': df.loc[df['buys'] == 1, 'close'],
                          'Position': df.loc[df['buys'] == 1, 'position']}),
        pd.DataFrame({'Price': df.loc[df['sells'] == 1, 'close'],
                          'Position': df.loc[df['sells'] == 1, 'position']}),



    ])
all_trades.sort_index(inplace = True)

# pct pnl
#all_trades['pnl'] = np.where(all_trades.Position == 0, all_trades.Price / all_trades.Price.shift(1) - 1, np.nan)
# points pnl
all_trades['pnl'] = np.where(all_trades.Position == 0, all_trades.Price - all_trades.Price.shift(1), np.nan)

trade_exits = all_trades[all_trades.Position == 0]
trade_exits['cum_pnl'] = trade_exits.pnl.cumsum()


df['strat_pct'] = df.pct_fwd * df['position']

df['strat_hpr'] = df['strat_pct'] + 1

df['strategy'] = 0
df.loc[df.index[0], 'strategy'] = 1
df['strategy'].iloc[1:] = df['strat_hpr'].iloc[1:].cumprod()


df['buy_and_hold_hpr'] = df['pct_fwd'] + 1
df['buy_and_hold'] = 0
df.loc[df.index[0], 'buy_and_hold'] = 1
df['buy_and_hold'].iloc[1:] = df['buy_and_hold_hpr'].iloc[1:].cumprod()

df['hold_max'] = df.buy_and_hold.cummax()
df['strategy_max'] = df.strategy.cummax()
df['hold_dd'] = df.buy_and_hold / df.hold_max - 1
df['strategy_dd'] = df.strategy / df.strategy_max - 1

df[['strategy', 'buy_and_hold']].plot(subplots=True)


# In[6]:


print('trade analysis BTC points')
t_stat = (all_trades.pnl.mean() * math.sqrt(all_trades.pnl.count()) ) / all_trades.pnl.std()
print('mean ' + str(all_trades.pnl.mean()))
print('std ' + str(all_trades.pnl.std()))
print('min ' + str(all_trades.pnl.min()))
print('max ' + str(all_trades.pnl.max()))
print('count ' + str(all_trades.pnl.count()))
print('t-stat ' + str(t_stat))

trade_exits.cum_pnl.plot()


# In[ ]:
