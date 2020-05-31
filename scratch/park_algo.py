#!/usr/bin/env python
# coding: utf-8

# In[85]:


# import packages
import pandas as pd
import numpy as np
import datetime
import time
import math


# In[87]:


df = pd.read_csv('bitmex-btc-ohlcv-1-minute-data.csv')
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


# In[ ]:





# In[88]:


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


# Skip first 20 days.
five_min = five_min[5760:]

df = five_min




# In[ ]:





# In[159]:


# trading system logic

# 5min testing
df['position'] = 0
df['entry'] = 0
new = [df.position.iloc[0]]
#new_2 = [df.entry.iloc[0]]
for i in range(1, len(df.index)): 
    if df.z_480.iloc[i] > 4 and df.close.iloc[i] < df.ma_20_days.iloc[i] * 1.5: # hold 180
        new.append(1)
     #   new_2.append(df.close.iloc[i])
    elif sum(new[-36:]) == 36:
        new.append(0)
    #    new_2.append(0)
    else:
        #new.append(0)
        new.append(new[i-1])
    #    new_2.append(new_2[i-1])
df['position'] = new
#df['entry'] = new_2

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


# In[ ]:





# In[ ]:





# In[158]:


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





# In[21]:


df['ma_5'] = df['close'].rolling(5).mean()
df['ma_10'] = df['close'].rolling(10).mean()
df['ma_20'] = df['close'].rolling(20).mean()
df['ma_50'] = df['close'].rolling(50).mean()
df['ma_200'] = df['close'].rolling(200).mean()
df['ma_20_days'] = df['close'].rolling(28800).mean()


df['pct_chg'] = df['close'] / df['close'].shift(1) - 1
df['pct_chg_5'] = df['close'] / df['close'].shift(5) - 1
df['pct_chg_60'] = df['close'] / df['close'].shift(60) - 1
df['pct_fwd'] = df['pct_chg'].shift(-1)
df['volatility_240'] = df.pct_chg.rolling(240).std()
df['volatility_480'] = df.pct_chg_5.rolling(480).std()
df['volatility_1440'] = df.pct_chg_60.rolling(1440).std()
df['z_240'] = df.pct_chg / df.volatility_240
df['z_480'] = df.pct_chg_5 / df.volatility_480
df['z_1440'] = df.pct_chg_60 / df.volatility_1440

def vwap(df):
    q = df.volume.values
    p = df.close.values
    return df.assign(vwap_running=(p * q).cumsum() / q.cumsum())

df = df.groupby(df.my_date, group_keys=False).apply(vwap)

df = df[1440:]


# In[18]:


len(df)


# In[7]:


df.iloc[985:990]


# In[40]:


df['position'] = 0
#df['entry'] = 0
new = [df.position.iloc[0]]
#new_2 = [df.entry.iloc[0]]
for i in range(1, len(df.index)):
    #if df.z_240.iloc[i] > 5: 
    #if df.z_480.iloc[i] > 4: # hold 180
    #if df.close.iloc[i] > df.ma_20_days.iloc[i] and df.z_480.iloc[i] > 3 and df.close.iloc[i-5] < df.ma_20_days.iloc[i-5]:
    #if df.z_480.iloc[i] > 3 and df.close.iloc[i-5] > df.ma_20_days.iloc[i-5]: 
    #if df.z_tfi_chg.iloc[i] > 3.75 and df.dt_sign_sum.iloc[i] == 4:
    #if df.z_pct_chg.iloc[i] > 3 and df.dt_sign_sum.iloc[i] < 2:
    #if df.dt_chg_sum.iloc[i] == 4 and df.dt_chg_sum.iloc[i-1] != 4 and df.close.iloc[i] < df.close.iloc[i-8] - 2.5:
    #if df.dt_sign_sum.iloc[i] == 4 and df.dt_sign_sum.iloc[i-1] != 4 and df.close.iloc[i] < df.close.iloc[i-8] - 2.5:
    #if df.dt_sign_sum.iloc[i] == 0 and df.dt_sign_sum.iloc[i-1] != 0 and df.close.iloc[i] > df.close.iloc[i-8] + 2.5:
    #if df.pct_200.iloc[i] > 0.5:
        new.append(1)
        #new_2.append(df.close.iloc[i])
    #elif sum(new[-180:]) == 180:
    #    new.append(0)
    elif df.close.iloc[i] < df.ma_20_days.iloc[i]:
        new.append(0)
    #elif df.dt_chg_sum.iloc[i] != 4:
    #elif df.dt_sign_sum.iloc[i] != 0 or df.close.iloc[i] > new_2[-1] + 5:
    #elif df.dt_sign_sum.iloc[i] != 4 or df.close.iloc[i] < new_2[-1] - 5:
    #    new.append(0)
    #    new_2.append(0)
    else:
        #new.append(0)
        new.append(new[i-1])
    #    new_2.append(new_2[i-1])
df['position'] = new
#df['entry'] = new_2

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


# In[41]:


df[['strategy', 'buy_and_hold']].plot(subplots=True)


# In[42]:


print('trade analysis BTC points')
t_stat = (all_trades.pnl.mean() * math.sqrt(all_trades.pnl.count()) ) / all_trades.pnl.std()
print('mean ' + str(all_trades.pnl.mean()))
print('std ' + str(all_trades.pnl.std()))
print('min ' + str(all_trades.pnl.min()))
print('max ' + str(all_trades.pnl.max()))
print('count ' + str(all_trades.pnl.count()))
print('t-stat ' + str(t_stat))

trade_exits.cum_pnl.plot()


# In[11]:


# aggregate pct_changes, 


# In[ ]:




