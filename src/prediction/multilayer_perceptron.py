"""
MLP is a class of feedforward artificial neural network(ANN). It usually consists of three layers: input layers, hidden
layers and output layer. A simple example of MLP by Mohamed Zahran It can be powerful in time series forecasting due to
the following natures:
"""

import os
import numpy as np
from matplotlib import pyplot as plt
from keras.models import Sequential, load_model
from keras.layers import Dense


from sklearn.metrics import mean_squared_error
from src.utils.logger import custom_logger as logger
from src.prediction.common import horizon_transform, split_series
from src.settings import MODEL_DIR


MODEL = os.path.join(MODEL_DIR, 'mlp.h5')


class MultilayerPerceptron:
    def __init__(self, dim=(30, 5), debug=False, b_log_trans=False):
        self.debug = debug

        self.model = None
        self.n_steps_in, self.n_steps_out = dim
        self.b_log_trans = b_log_trans

    def train(self, series, n_epochs=500):
        logger.info("training... MLP")
        if self.b_log_trans:
            series = np.log(series)

        x, y = horizon_transform(series=series, n_steps_in=self.n_steps_in, n_steps_out=self.n_steps_out)

        # model
        self.model = Sequential()
        self.model.add(Dense(100, activation='relu', input_dim=self.n_steps_in))
        self.model.add(Dense(self.n_steps_out))
        self.model.compile(optimizer='adam', loss='mse')

        # fit model
        self.model.fit(x, y, epochs=n_epochs, verbose=0)
        self.model.save(MODEL)
        logger.info("training is completed")

        # evaluate
        y_hats = self.model.predict(x)
        if self.b_log_trans:
            error = mean_squared_error(np.exp(y), np.exp(y_hats))
        else:
            error = mean_squared_error(y, y_hats)
        logger.info("eval MSE: %.3f" % error)

        return self.model

    @staticmethod
    def load():
        loaded = load_model(MODEL)
        return loaded

    def predict(self, series, pred_start=-1, n_preds=-1):
        if self.model is None:
            # TODO : train in case of no existing the pre-trained model, unless loading
            try:
                self.model = self.load()
            except Exception as e:
                logger.warning(str(e))
                self.train(series=series)

        if not self.n_steps_in < pred_start <= len(series):
            pred_start = len(series)
        if n_preds == -1:
            n_preds = self.n_steps_out

        _s = pred_start - self.n_steps_in
        _e = pred_start
        in_x = [0 for _ in range(_s, 0)] + series[max(0, _s): _e]

        out_y = []
        # select last history during n_steps
        while len(out_y) < n_preds:

            if self.b_log_trans:
                in_x = np.log(in_x)
            in_x = np.array(in_x).reshape((1, self.n_steps_in))

            y_hats = self.model.predict(in_x, verbose=0)

            if self.b_log_trans:
                y_hats = np.exp(y_hats)

            out_y.extend(y_hats.reshape((-1)).tolist())

            # append the predicted result to history
            in_x = (in_x[0].tolist() + out_y)[-self.n_steps_in:]

        return out_y[:n_preds]

    def __validate(self, series):
        train, test = split_series(series=series, n_tests=self.n_steps_out)

        pred_start = n_train = len(train)
        n_test = len(test)

        forecast = self.predict(series=train, pred_start=pred_start)

        x, y = horizon_transform(series=train, n_steps_in=self.n_steps_in, n_steps_out=self.n_steps_out)
        y_hats = self.model.predict(x, verbose=0)
        if self.b_log_trans:
            y_hats = np.exp(y_hats)
        predictions = y_hats[:, -1].reshape(-1).tolist()

        # plt.plot(train + test)
        plt.title("MLP")
        plt.plot(range(0, n_train), train, color='blue', label='history')
        plt.plot(range(n_train, n_train + n_test), test, color='red', label='expected')
        plt.plot(range(self.n_steps_in + self.n_steps_out - 1, n_train), predictions, color='green',
                 label='predicted')
        plt.plot(range(n_train, n_train + n_test), forecast, color='green', label='predicted')
        plt.legend(framealpha=1, frameon=True)
        plt.show()
