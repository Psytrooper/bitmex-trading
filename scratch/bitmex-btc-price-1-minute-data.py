#!/usr/bin/env python
# coding: utf-8

# In[32]:


import requests
import datetime
import pandas as pd
import time


# In[14]:


# API Doc Link:
# https://www.bitmex.com/api/explorer/#!/Trade/Trade_getBucketed

# API URL
# https://www.bitmex.com/api/v1/trade/bucketed?binSize=1m&partial=false&symbol=XBTUSD&count=1000&start=0&reverse=true
def fetch_btc_minute_ohlcv_historical(start):
    
    url = 'https://www.bitmex.com/api/v1/trade/bucketed?binSize=1m&partial=false&symbol=XBTUSD&count=1000&start={}&reverse=true'        .format(start)
    
    page = requests.get(url)
    data = page.json()
    df = pd.DataFrame(data)

    return df


# In[34]:


df = pd.DataFrame()
start = 0

while start <= 1400000: # per day 1440 min, 945 days ( June, 2017 to Today) * 1440
    df_fetch = fetch_btc_minute_ohlcv_historical(start)
    df = df.append(df_fetch)
    start = start + 1001 # increase the count by 1001
    time.sleep(2) # add 2 second delay before each request to overcome rate limits
    
df


# In[35]:


df_master = df.copy()


# In[36]:


df_master


# In[39]:


df_master.sort_values("timestamp", inplace=True)


# In[43]:


df_master.reset_index(inplace=True)


# In[47]:


df_master.drop(['index'], axis = 1, inplace=True)


# In[49]:


df_master.to_csv("bitmex-btc-ohlcv-1-minute-data.csv")
df_master

