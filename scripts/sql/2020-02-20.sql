ALTER TABLE orders MODIFY price DECIMAL(16,6) DEFAULT NULL;
ALTER TABLE orders MODIFY COLUMN `order_type` enum('Market','Stop', 'StopLimit') NOT NULL DEFAULT 'Market';
