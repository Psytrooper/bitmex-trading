Create Table: CREATE TABLE `decisions` (
  `timestamp_dt` datetime NOT NULL,
  `symbol` varchar(255) NOT NULL,
  `side` enum('long','short') NOT NULL,
  `position` int(11) NOT NULL,
  `price` decimal(16,6) DEFAULT NULL,
  `mkt_price` decimal(16,6) DEFAULT NULL,
  `synthetic` tinyint(1) NOT NULL DEFAULT '0',
  `active` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`timestamp_dt`,`symbol`,`side`,`synthetic`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;


Create Table: CREATE TABLE `fills` (
  `transaction_dt` datetime NOT NULL,
  `exec_id` varchar(255) NOT NULL,
  `order_id` varchar(255) NOT NULL,
  `symbol` varchar(255) NOT NULL,
  `side` enum('Sell','Buy') NOT NULL,
  `price` decimal(16,6) NOT NULL,
  `stop_px` decimal(16,6) DEFAULT NULL,
  `order_qty` int(11) NOT NULL,
  `order_type` varchar(255) NOT NULL,
  `order_status` varchar(255) NOT NULL,
  `last_px` decimal(16,6) NOT NULL,
  `last_qty` int(11) DEFAULT NULL,
  `leaves_qty` int(11) DEFAULT NULL,
  `cum_qty` int(11) DEFAULT NULL,
  `avg_px` int(11) DEFAULT NULL,
  `created_dt` datetime NOT NULL,
  PRIMARY KEY (`exec_id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

Create Table: CREATE TABLE `orders` (
  `order_id` varchar(255) NOT NULL,
  `symbol` varchar(255) NOT NULL,
  `price` decimal(16,6) DEFAULT NULL,
  `decision_px` decimal(16,6) DEFAULT NULL,
  `stop_px` decimal(16,6) DEFAULT NULL,
  `side` enum('Sell','Buy') DEFAULT NULL,
  `quantity` int(11) DEFAULT NULL,
  `order_type` enum('Market','StopLimit') NOT NULL DEFAULT 'Market',
  `created_dt` datetime NOT NULL,
  PRIMARY KEY (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;



Create Table: CREATE TABLE `positions` (
  `pid` int(11) NOT NULL AUTO_INCREMENT,
  `symbol` varchar(255) NOT NULL,
  `current_qty` int(11) NOT NULL,
  `avg_cost_price` decimal(16,6) DEFAULT NULL,
  `unrealised_pnl` decimal(20,6) DEFAULT NULL,
  `current_timestamp_dt` datetime NOT NULL,
  PRIMARY KEY (`pid`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=latin1;

Create Table: CREATE TABLE `tradeBin1m` (
  `timestamp_dt` datetime NOT NULL,
  `symbol` varchar(255) NOT NULL,
  `open_px` decimal(16,6) DEFAULT NULL,
  `high_px` decimal(16,6) DEFAULT NULL,
  `low_px` decimal(16,6) DEFAULT NULL,
  `close_px` decimal(16,6) DEFAULT NULL,
  `trades` int(11) DEFAULT NULL,
  `volume` bigint(20) DEFAULT NULL,
  `vwap` decimal(16,6) DEFAULT NULL,
  `last_size` int(11) DEFAULT NULL,
  `turnover` bigint(20) DEFAULT NULL,
  `home_notional` decimal(20,8) DEFAULT NULL,
  `foreign_notional` decimal(20,8) DEFAULT NULL,
  PRIMARY KEY (`timestamp_dt`,`symbol`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1
