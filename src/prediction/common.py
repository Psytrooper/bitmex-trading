import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from statsmodels.tsa.stattools import acf, pacf
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from statsmodels.tsa.stattools import adfuller


from src.utils.logger import custom_logger as logger


TIMESTAMP = "timestamp_dt"


# dateparse = lambda x: dateutil.parser.parse(x)
# dateparse = lambda col: pd.to_datetime(col, utc=True)


def load_csv(csv_path, fields=None):
    logger.info(f"loading from csv file '{csv_path}'")
    if fields is not None and TIMESTAMP not in fields:
        fields = fields.append(TIMESTAMP)
    # read csv
    df = pd.read_csv(csv_path, header=0, index_col=TIMESTAMP, usecols=fields,
                     parse_dates=[TIMESTAMP], date_parser=lambda col: pd.to_datetime(col, utc=True),
                     keep_default_na=True)
    logger.info(f"success")
    logger.info("raw data: \n{}".format(df.head()))
    return df


def resampling(df, timeframe, method='mean'):
    """

    :param df: dataFrame
    :param timeframe:  freq
    :param method:  'mean' | 'sum'  | 'left'
    :return:
    """
    logger.info(f"re-sampling freq: {timeframe}, mode: {method}")
    if method == 'mean':
        re_sampled = df.resample(rule=pd.to_timedelta(timeframe)).mean()
    elif method == 'sum':
        re_sampled = df.resample(rule=pd.to_timedelta(timeframe)).sum()
    else:
        re_sampled = df.resample(rule=pd.to_timedelta(timeframe)).left()

    re_sampled = re_sampled.fillna(0)
    logger.info("re-sampled data: \n{}".format(re_sampled.head()))
    return re_sampled


def filtering(df, conditions=None):
    """

    :param df:
    :param conditions:  label1 == condition1, label2 == condition2
    :return:
    """
    if conditions is None:
        return df

    logger.info(f"filtering, conditions: {conditions}")
    for label, cond in zip(conditions):
        df = df[df[label] == cond]
    return df


def autocorr(series):
    logger.info('Auto-correlation check')
    lag_acf = acf(series, nlags=20)
    # Plot ACF:
    plt.title('Autocorrelation')
    plt.plot(lag_acf)
    plt.show()
    return lag_acf


def partial_autocorr(series):
    logger.info('Partial Auto-correlation check')

    lag_pacf = pacf(series, nlags=20, method='ols')
    # Plot PACF:
    plt.title('Partial Auto-correlation')
    plt.plot(lag_pacf)
    plt.show()
    return lag_pacf


# --------------------------------------------------------------------------------------------------------------------
def autocorr2(series):
    plot_acf(np.array(series))
    plt.show()


def partial_autocorr2(series):
    plot_pacf(np.array(series))
    plt.show()
# --------------------------------------------------------------------------------------------------------------------


def augmented_dickey_fuller(series):
    result = adfuller(series)
    if isinstance(result, tuple):
        result = list(result)
    else:  # float
        result = list([result])

    logger.info('Augmented dickey-fuller check')
    labels = ['ADF Test Statistic', 'p-value', '#Number of Lags Used', 'Number of Observations Used']
    for value, label in zip(result, labels):
        logger.info(f"\t{label} : {value}")

    if result[1] <= 0.05:
        logger.info("\tReject the null hypothesis. Data has no unit root and is stationary.")
    else:
        logger.warning(
            "\tFail to reject the null hypothesis. Time series has a unit root, indicating it is non-stationary.")


def horizon_transform(series, n_steps_in, n_steps_out):
    x, y = list(), list()
    for i in range(len(series)):
        # find the end of this pattern
        end_ix = i + n_steps_in
        out_end_ix = end_ix + n_steps_out
        # check if we are beyond the sequence
        if out_end_ix > len(series):
            break
        # gather input and output parts of the pattern
        seq_x, seq_y = series[i:end_ix], series[end_ix:out_end_ix]
        x.append(seq_x)
        y.append(seq_y)
    return np.array(x), np.array(y)


def split_series(series, ratio=0.8):
    train = series[:int(len(series) * ratio)]
    test = series[int(len(series) * ratio):]
    return train, test


def visualize(history, predict, title=""):
    # plot (for debugging)
    plt.rcParams["figure.figsize"] = (30, 3)
    plt.title(title)

    plt.plot(range(0, len(history)), history, color='blue', label='history')
    plt.plot(range(len(history), len(history) + len(predict)), predict, color='green', label='predict')

    plt.legend(framealpha=1, frameon=True)
    plt.show()
