import time
import pandas as pd
from datetime import datetime, timezone


from src.prediction.lstm import LstmPredictor


TIME_TO_NEW_TRAIN = {
    '1w': int(pd.to_timedelta('7 day').total_seconds()),
    '2d': int(pd.to_timedelta('2 day').total_seconds()),
    '1d': int(pd.to_timedelta('1 day').total_seconds()),
    '8h': int(pd.to_timedelta('1 day').total_seconds())
}


def time_frame():
    return int(pd.to_timedelta('3day').total_seconds())


class TrendPredictor:
    def __init__(self):
        self.predictor_1day = LstmPredictor(dim=(20, 1, 1))

        self.predictor_1hour = LstmPredictor(dim=(48, 1, 1))

        self.predictor_30min = LstmPredictor(dim=(48, 1, 1))

        self.predictor_5min = LstmPredictor(dim=(480, 1, 5))

    def predict(self, df):
        _df_1day = df.resample(rule=pd.to_timedelta('1 day')).mean()
        _df_1hour = df.resample(rule=pd.to_timedelta('1 hour')).mean()
        _df_30min = df.resample(rule=pd.to_timedelta('30 min')).mean()
        _df_1min = df.copy()

        now = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()

        if round(now) % TIME_TO_NEW_TRAIN['8h'] == 0:
            self.min_predictor.train()
        if round(now) % TIME_TO_NEW_TRAIN['1d'] == 0:
            self.min_predictor.train()
        if round(now) % TIME_TO_NEW_TRAIN['2d'] == 0:
            self.hour_predictor.train()
        if round(now) % TIME_TO_NEW_TRAIN['7w'] == 0:
            self.day_predictor.train()

        self.min_predictor.predict()
        self.hour_predictor.predict()
        self.day_predictor.predict()

    def upgrade(self):
        pass


if __name__ == '__main__':

    # from src.prediction.common import load_csv
    # df = load_csv('buckets.csv')
    #
    # df_hour = df.resample(rule=pd.to_timedelta('1 hour')).mean()
    # df_day = df.resample(rule=pd.to_timedelta('1 day')).mean()
    #
    # df_last_480_mins = df.tail(480)  # select last 480 minutes
    # print(df_last_480_mins.head())
    #
    # df_last_20_days = df_day.tail(20)  # select last 20 days:
    # print(df_last_20_days.head())
    #
    # df_last_48_hours = df_hour.tail(48)  # select last 48 hours
    # print(df_last_48_hours.head())

    pass
