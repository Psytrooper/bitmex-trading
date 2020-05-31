-- Make order_id the PK for orders.
ALTER TABLE orders ADD PRIMARY KEY (order_id);

-- Modify orders to accomodate order type and stop-price for stop-orders.
-- Order types should be strings recognized by Bitmex.
ALTER TABLE orders \
	ADD COLUMN `decision_px` DECIMAL(16,6) DEFAULT NULL AFTER `price`, \
	ADD COLUMN `stop_px` DECIMAL(16,6) DEFAULT NULL AFTER `decision_px`, \
	ADD COLUMN `order_type` enum('Market','StopLimit') NOT NULL DEFAULT 'Market' AFTER `quantity`;

-- Add boolean column that says whether decision was synthetic or not.
ALTER TABLE decisions ADD COLUMN `synthetic` BOOLEAN NOT NULL DEFAULT FALSE;
