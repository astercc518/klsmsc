-- Migration: Add business_type column to supplier_rates table
-- Date: 2026-01-30
-- Description: Allow suppliers to have multiple business types (sms/voice/data) at the rate level

-- Add business_type column to supplier_rates table
ALTER TABLE supplier_rates 
ADD COLUMN IF NOT EXISTS business_type VARCHAR(20) DEFAULT 'sms' NOT NULL 
COMMENT '业务类型：sms/voice/data'
AFTER supplier_id;

-- Create index for faster filtering by business_type
CREATE INDEX IF NOT EXISTS idx_supplier_rates_business_type 
ON supplier_rates(business_type);

-- Update existing records to have 'sms' as default business_type (already default)
UPDATE supplier_rates SET business_type = 'sms' WHERE business_type IS NULL OR business_type = '';
