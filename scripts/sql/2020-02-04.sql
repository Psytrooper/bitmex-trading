-- Incorporate synthetic column into primary key for decisions.
ALTER TABLE decisions
	DROP PRIMARY KEY,
	ADD PRIMARY KEY (timestamp_dt, symbol, side, synthetic);
