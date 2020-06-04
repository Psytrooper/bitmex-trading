"""
Recurrent neural networks, or RNNs, are specifically designed to work, learn, and predict sequence data.
A recurrent neural network is a neural network where the output of the network from one time step is provided as an
input in the subsequent time step. This allows the model to make a decision as to what to predict based on both the
 input for the current time step and direct knowledge of what was output in the prior time step.
The most successful and widely used RNN is the long short-term memory network, or LSTM for short.
"""

# univariate multi-step lstm
import os
import numpy as np

from sklearn.metrics import mean_squared_error
from keras.models import Sequential, load_model
from keras.layers import Dense, LSTM
from matplotlib import pyplot as plt
from sklearn.preprocessing import MinMaxScaler


from src.prediction.common import horizon_transform, split_series
from src.utils.logger import custom_logger as logger


from src.settings import MODEL_DIR


class LstmPredictor:
    def __init__(self, dim=(20, 1, 5), model_name="lstm.h5"):
        self.model = None
        self.model_path = os.path.join(MODEL_DIR, model_name)

        self.n_inputs, self.n_features, self.n_outputs = dim

        self.__scaler = MinMaxScaler(feature_range=(0, 1))

    # train the model
    def train(self, series, verbose=2, epochs=10, batch_size=16):
        logger.info("training... LSTM")
        # prepare data
        x, y = horizon_transform(series=series, n_steps_in=self.n_inputs, n_steps_out=self.n_outputs)

        # define parameters
        n_samples = x.shape[0]

        # expected lstm_1_input to have 3 dimensions
        x = x.reshape((n_samples, self.n_inputs, self.n_features))

        # define model
        self.model = Sequential()
        self.model.add(LSTM(200, activation='relu', input_shape=(self.n_inputs, self.n_features)))
        self.model.add(Dense(100, activation='relu'))
        self.model.add(Dense(self.n_outputs))
        self.model.compile(loss='mse', optimizer='adam')

        # fit network
        self.model.fit(x, y, epochs=epochs, batch_size=batch_size, verbose=verbose)
        logger.info("training is completed")
        self.model.save(self.model_path)

        return self.model

    def load_model(self):
        loaded = load_model(self.model_path)
        return loaded

    # make a forecast
    def predict(self, series, pred_start=-1, n_preds=-1):
        # scale transform
        series = self.__scaler.fit_transform(series)

        if not self.n_inputs < pred_start <= len(series):
            pred_start = len(series)
        if n_preds < 0:
            n_preds = self.n_outputs

        # select last history during n_steps
        _s = pred_start - self.n_inputs
        _e = pred_start
        in_x = [0 for _ in range(_s, 0)] + series[max(0, _s): _e]

        out_y = []
        while len(out_y) < n_preds:
            in_x = np.array(in_x).reshape((1, self.n_inputs, 1))

            y_hats = self.model.predict(in_x, verbose=0)

            out_y.extend(y_hats.reshape((-1)).tolist())
            in_x = out_y[-self.n_inputs:]

        # inverse scale transform
        return self.__scaler.inverse_transform(out_y[:n_preds])

    def scale_trans(self, series):
        return self.__scaler.fit_transform(np.array([series]))[0].tolist()

    def inv_scale_trans(self, series):
        return self.__scaler.inverse_transform(np.array([series]))[0].tolist()

    # evaluate a single model
    def validate(self, series):
        scaled_series = series  # self.scale_trans(series)

        train, test = split_series(series=scaled_series, ratio=0.6)

        self.train(series=train)
        self.model = self.load_model()

        train_x, train_y = horizon_transform(series=train, n_steps_in=self.n_inputs, n_steps_out=self.n_outputs)
        test_x, test_y = horizon_transform(series=test, n_steps_in=self.n_inputs, n_steps_out=self.n_outputs)

        train_preds = self.model.predict(train_x.reshape((train_x.shape[0], self.n_inputs, self.n_features)), verbose=0)
        logger.info("eval MSE: %.3f" % mean_squared_error(train_y[:, -1].reshape(-1), train_preds[:, -1].reshape(-1)))

        test_preds = self.model.predict(test_x.reshape((test_x.shape[0], self.n_inputs, self.n_features)), verbose=0)
        logger.info("eval MSE: %.3f" % mean_squared_error(test_y[:, -1].reshape(-1), test_preds[:, -1].reshape(-1)))

        # shift for plotting....
        plt.title("LSTM")
        plt.plot(series, label='Actual', color='blue')
        # plt.plot(self.inv_scale_trans((np.concatenate((train_preds, test_preds), axis=0))[:, -1].reshape(-1)), label='Training', color='yellow')
        plt.plot(np.concatenate((train_preds, test_preds), axis=0)[:, -1].reshape(-1), label='Training', color='yellow')
        plt.legend(loc='best')
        plt.figure(figsize=(10, 3))
        plt.show()


if __name__ == '__main__':
    from src.prediction.common import load_csv, resampling

    csv_path = os.path.join("buckets.csv")
    df = load_csv(csv_path=csv_path, fields=['close_px'])
    day_df = resampling(df=df, timeframe='1 day')
    hour_df = resampling(df=df, timeframe='1 hour')

    raw = df.close_px.tolist()
    hour_df['close_px'].plot()
    plt.figure(figsize=(300, 1))
    plt.show()

    # 1 day = 1440
    # t_series = df.close_px.tolist()[-1440:]
    # LongShortTermMemoryNetwork((30, 1, 5)).validate(series=t_series)
