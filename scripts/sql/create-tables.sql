CREATE TABLE orders (
  order_id VARCHAR(255) NOT NULL,
  symbol VARCHAR(255) NOT NULL,
  price DECIMAL(16,6) NOT NULL,
  side enum('Sell','Buy') NOT NULL,
  quantity INT NOT NULL,
  created_dt DATETIME NOT NULL,
  PRIMARY KEY(order_id)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

CREATE TABLE fills (
  transaction_dt DATETIME NOT NULL,
  exec_id VARCHAR(255) NOT NULL,
  order_id VARCHAR(255) NOT NULL,
  symbol VARCHAR(255) NOT NULL,
  side enum('Sell','Buy') NOT NULL,
  price DECIMAL(16,6) NOT NULL,
  order_qty INT NOT NULL,
  order_type VARCHAR(255) NOT NULL,
  order_status VARCHAR(255) NOT NULL,
  last_px DECIMAL(16,6) NOT NULL,
  last_qty INT DEFAULT NULL,
  leaves_qty INT DEFAULT NULL,
  cum_qty INT DEFAULT NULL,
  avg_px INT DEFAULT NULL,
  created_dt DATETIME NOT NULL,
  PRIMARY KEY(exec_id)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

CREATE TABLE positions (
  pid INT NOT NULL AUTO_INCREMENT,
  symbol VARCHAR(255) NOT NULL,
  current_qty INT NOT NULL,
  avg_cost_price DECIMAL(16,6) DEFAULT NULL,
  unrealised_pnl DECIMAL(20,6) DEFAULT NULL,
  current_timestamp_dt DATETIME NOT NULL,
  PRIMARY KEY(pid)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

CREATE TABLE movements (
  symbol VARCHAR(255) NOT NULL,
  m_status enum('start', 'end_price_reversal', 'end_price_stabilized') NOT NULL,
  direction enum('up', 'down') DEFAULT NULL,
  price DECIMAL(16,6) NOT NULL,
  last_modified_dt DATETIME NOT NULL,
  PRIMARY KEY(symbol)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

-- This table houses Bitmex trade-buckets for each minute.
CREATE TABLE tradeBin1m (
  timestamp_dt DATETIME NOT NULL,
  symbol VARCHAR(255) NOT NULL,
  open_px DECIMAL(16,6),
  high_px DECIMAL(16,6),
  low_px DECIMAL(16,6),
  close_px DECIMAL(16,6),
  trades INT,
  volume BIGINT,
  vwap DECIMAL(16,6),
  last_size INT,
  turnover BIGINT,
  home_notional DECIMAL(20,8),
  foreign_notional DECIMAL(20,8),
  PRIMARY KEY(timestamp_dt, symbol)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

CREATE TABLE decisions (
  timestamp_dt DATETIME NOT NULL,
  symbol VARCHAR(255) NOT NULL,
  side enum('long', 'short') NOT NULL,
  position INT  NOT NULL,
  price DECIMAL(16,6) DEFAULT NULL,
  PRIMARY KEY(timestamp_dt, symbol, side)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
