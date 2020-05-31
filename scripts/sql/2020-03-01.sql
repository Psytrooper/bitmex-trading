-- Add "mkt_price" column to house most recent market price (as distinct from the decision price).
-- Allow for NULL values, as the mkt_price for now is useless in synthetic decisions.
ALTER TABLE decisions ADD COLUMN `mkt_price` DECIMAL(16,6) DEFAULT NULL AFTER `price`;

-- Add "active" column to indicate that a trade-decision is being considered.
ALTER TABLE decisions ADD COLUMN `active` BOOLEAN NOT NULL DEFAULT FALSE AFTER `synthetic`;
