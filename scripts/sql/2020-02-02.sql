-- Add stop_px column to fills so as to distinguish Market and StopLimit orders.
ALTER TABLE fills ADD COLUMN `stop_px` DECIMAL(16,6) DEFAULt NULL AFTER `price`;
